import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
#from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
#from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Boolean, select, update
from mem0 import Memory
from openai import AsyncOpenAI
import sys
from loguru import logger
import traceback
import time
import random
from typing import Optional
from UtilLLM import generate_ai_reply_with_retry

import UtilRAG #import retrieve_rag_context
import UtilMem

#move to config.py
from config import settings, YQrequirement

#router
from router_kb import router as kb_router
from router_auth import router as auth_router
from router_admin import router as admin_router


# 移除默认配置
logger.remove()
# 添加控制台输出（带颜色，方便肉眼看）
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>", level="INFO")
# 添加文件日志（持久化，方便查昨天的Bug）
logger.add("logs/agent_server.log", rotation="10 MB", level="DEBUG")



print("====== 终极调试 ======")
print("我读到的 API KEY 是: [", settings.LLM_API_KEY, "]")
print("我读到的 Base URL 是: [", settings.LLM_BASE_URL, "]")
print("======================")

# ==========================================
# 2. 初始化数据库与 ORM 模型
# ==========================================
"""
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG_MODE, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    welcome_message: Mapped[str] = mapped_column(Text, nullable=True)
    stages_config: Mapped[str] = mapped_column(Text, nullable=True)

class SessionRecord(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(50))
    group_id: Mapped[str] = mapped_column(String(50), nullable=True)
    activity_id: Mapped[str] = mapped_column(String(50), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(50), nullable=True)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(50))
    org_id: Mapped[str] = mapped_column(String(50))
    group_id: Mapped[str] = mapped_column(String(50), nullable=True)
    activity_id: Mapped[str] = mapped_column(String(50), nullable=True)
    sender_type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
"""
from database import engine, Base, AsyncSessionLocal

# ---------------------------------------------------------
# 🚨 第 2 步：显式引入 models.py 里的所有表！
# (极其关键：如果不在这里 import，SQLAlchemy 就不知道这些表的存在，启动时就不会自动建表，查询也会报错)
# ---------------------------------------------------------
from models import (
    SessionRecord, Activity, Message, KnowledgeBase, ActivityKBMount, Employee, CustomerEmotion,
    ActivityEventRule, SessionRuleFire, AgentNotification, WebhookDeadLetter,
)
import RuleEngine
from deps import decode_token

# ==========================================
# 3. 初始化 AI 客户端与 Mem0 记忆引擎
# ==========================================
llm_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL
)

mem0_llm_model = 'gpt-4o-mini'

mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "saas_visitor_memories",
            "path": settings.MEMORY_DB_PATH 
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "api_key": settings.LLM_API_KEY,
            # 如果你用的是国内代理或私有部署，需要把 base_url 也传给它
            "openai_base_url": settings.LLM_BASE_URL, 
            "model": mem0_llm_model,
            "temperature": 0.1
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "api_key": settings.LLM_API_KEY,
            "openai_base_url": settings.LLM_BASE_URL,
            # 默认使用 OpenAI 的小模型作为向量转化器，极便宜
            "model": settings.LLM_EMBEDDING_MODEL, 
        }
    }
}

visitor_memory_layer = Memory.from_config(mem0_config)

# ==========================================
# 4. WebSocket 连接管理器
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, conn_id: str):
        await ws.accept()
        self.active_connections[conn_id] = ws
        if settings.DEBUG_MODE: print(f"[🔗 WS Connected] {conn_id}")

    def disconnect(self, conn_id: str):
        if conn_id in self.active_connections:
            del self.active_connections[conn_id]
            if settings.DEBUG_MODE: print(f"[❌ WS Disconnected] {conn_id}")

    async def send_to_client(self, conn_id: str, message: dict):
        if conn_id in self.active_connections:
            await self.active_connections[conn_id].send_json(message)

manager = ConnectionManager()


# ==========================================
# 4.5 员工 WebSocket 连接管理器
# ==========================================
# 同一个 employee_id 可能在多 tab 登录,对应多条 WebSocket。这里用 list 而不是覆盖式 dict[str, WS]。
class AgentConnectionManager:
    """转人工通知 / 系统通知的实时推送通道。单向 push, 不接收业务消息。"""
    def __init__(self):
        self.conns: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, employee_id: str):
        await ws.accept()
        self.conns.setdefault(employee_id, []).append(ws)
        if settings.DEBUG_MODE: print(f"[🔗 Agent WS Connected] employee={employee_id}")

    def disconnect(self, ws: WebSocket, employee_id: str):
        if employee_id in self.conns:
            self.conns[employee_id] = [w for w in self.conns[employee_id] if w is not ws]
            if not self.conns[employee_id]:
                del self.conns[employee_id]
            if settings.DEBUG_MODE: print(f"[❌ Agent WS Disconnected] employee={employee_id}")

    async def push(self, employee_id: str, message: dict):
        for ws in list(self.conns.get(employee_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                # 推不动就当 tab 已关; 留给 disconnect 清理
                pass


agent_manager = AgentConnectionManager()

# ==========================================
# 5. 核心：大模型推理与记忆处理 (后台任务)
# ==========================================


# ==========================================
# 1. 配置 Loguru：彩色输出 + 写入文件
# ==========================================


# ==========================================
# 2. 深度监控版的推理函数
# ==========================================
# ==========================================
# 根据 activity 匹配一个接待坐席
# 默认策略：同 org_id + group_id 下，is_ai=1 且 status='online' 的随机一个
# 后续可在此函数内细化(轮询/负载均衡/技能匹配等)
# ==========================================
async def match_employee_for_activity(db, activity: Activity, log) -> Optional[Employee]:
    res = await db.execute(
        select(Employee).where(
            Employee.org_id == activity.org_id,
            Employee.group_id == activity.group_id,
            Employee.is_ai.is_(True),
            Employee.status == "online",
        )
    )
    candidates = res.scalars().all()
    if not candidates:
        log.warning(f"⚠️ 活动 {activity.id} (org={activity.org_id}, group={activity.group_id}) 下没有 online 的 AI 坐席")
        return None
    chosen = random.choice(candidates)
    log.info(f"🎯 为活动 {activity.id} 匹配到坐席 {chosen.id} ({chosen.name}) / 候选数={len(candidates)}")
    return chosen


async def process_ai_reply(connection_id: str, session_id: str, visitor_msg: str, visitor_uid: str, activity_id: str):
    # 为当前 Session 创建一个独立的日志标识（Logger Context）
    log = logger.bind(session_id=session_id, visitor=visitor_uid, activity=activity_id, conn=connection_id)
    log.info(f"🚀 [新任务] 开始处理 | activity={activity_id} visitor={visitor_uid} session={session_id} text='{visitor_msg}'")
    metrics = {
            "A_DB_Session": 0,
            "B_DB_Activity": 0,
            "C_Mem0_Search": 0,
            "B5_RAG":0,
            "D_LLM_Chat": 0,
            "E_DB_Save_WS": 0,
            "E_WS": 0,
            "F_Mem0_Add": 0,
            "Total_Process": 0
        }
        
    # 记录总流程开始时间
    t_process_start = time.perf_counter()
    async with AsyncSessionLocal() as db:
        try:
            t0 = time.perf_counter()
            # A. 查找 Session
            log.debug(f"Session {session_id} 正在查询数据库获取 Session 信息...")
            result = await db.execute(select(SessionRecord).where(SessionRecord.id == session_id))
            sess = result.scalar_one_or_none()
            metrics["A_DB_Session"] = time.perf_counter() - t0
            if not sess:
                # 首次进线：用 URL 上的 activity_id 反查 activity，从中拿 org/group，再分配 employee
                log.info(f"🆕 Session {session_id} 在 DB 中不存在，开始首次建会话流程")
                act_res = await db.execute(select(Activity).where(Activity.id == activity_id))
                act = act_res.scalar_one_or_none()
                if not act:
                    log.error(f"Session {session_id}❌ 前端传入的 activity_id={activity_id} 在 activities 表中不存在，放弃建会话")
                    return
                log.info(f"Session {session_id} 📋 命中活动剧本: id={act.id} name={act.name} org={act.org_id} group={act.group_id}")

                matched = await match_employee_for_activity(db, act, log)
                bind_employee_id = matched.id if matched is not None else None
                if bind_employee_id is None:
                    log.warning(f"Session {session_id} ⚠️ 未匹配到坐席，session.employee_id 将留空(NULL)")

                sess = SessionRecord(
                    id=session_id,
                    org_id=act.org_id,
                    group_id=act.group_id,
                    activity_id=activity_id,
                    employee_id=bind_employee_id,
                    visitor_uid=visitor_uid,
                    platform_type="web_demo",
                    status="active",
                )
                db.add(sess)
                await db.flush()
                log.success(
                    f"Session {session_id} ✅ 新会话已落库 | session_id={session_id} org={sess.org_id} group={sess.group_id} "
                    f"activity={sess.activity_id} employee={sess.employee_id} visitor={visitor_uid}"
                )
            else:
                log.info(
                    f"Session {session_id} 🔁 命中已有 Session | org={sess.org_id} group={sess.group_id} "
                    f"activity={sess.activity_id} employee={sess.employee_id} stage={sess.current_stage}"
                )
            session = sess
            # A.5 立刻把访客的话落库 (独立提交，保证 LLM 失败也不会丢访客输入)
            # stage/emotion 快照是访客说话当下的 session 状态 (LLM 还没跑)
            db.add(Message(
                session_id=session_id,
                org_id=sess.org_id,
                group_id=sess.group_id,
                activity_id=sess.activity_id,
                sender_type="visitor",
                sender_id=visitor_uid,
                content=visitor_msg,
                stage_at_send=sess.current_stage,
                emotion_at_send=sess.current_emotion,
            ))
            await db.commit()
            log.info(f"Session {session_id} 📝 访客消息已落库 (session={session_id}, len={len(visitor_msg)}, stage={sess.current_stage}, emotion={sess.current_emotion})")

            # A.6 接管挡板: 接管中则跳过 LLM/RAG/Mem0 检索，仅把访客消息写入 Mem0 后即返回
            # (员工人工回复路径在 P2 实现，会负责把 employee 端的话也写 Mem0)
            if sess.is_human_takeover:
                log.info(f"Session {session_id} 🤝 已被员工 {sess.human_takeover_by} 接管 (at={sess.human_takeover_at})，跳过 LLM 推理")
                try:
                    visitor_memory_layer.add(
                        [{"role": "user", "content": visitor_msg}],
                        user_id=visitor_uid,
                    )
                    log.debug(f"Session {session_id} 🧠 takeover 下访客消息已写入 Mem0")
                except Exception as e:
                    log.warning(f"Session {session_id} ⚠️ takeover 下 Mem0 写入失败: {e}")
                return

            # A.7 Pre-LLM 规则评估: 主要用于「转人工拦截 / 关键词阻断 / block_llm」
            # 注意上下文还没有 LLM 输出 (emotion/tags 来自 sess 当前快照), 所以这里只评估静态条件。
            try:
                pre_rules = await RuleEngine.load_active_rules(
                    db, org_id=sess.org_id, activity_id=sess.activity_id, phase="pre_llm",
                )
                if pre_rules:
                    pre_ctx = RuleEngine.build_context_pre_llm(
                        cur_stage=sess.current_stage,
                        cur_emotion=sess.current_emotion,
                        total_turn=sess.total_turn_count,
                        stage_turn=sess.stage_turn_count,
                    )
                    matched_pre = await RuleEngine.evaluate(
                        pre_rules, pre_ctx, db,
                        session_id=session_id,
                        current_stage=sess.current_stage,
                        current_total_turn=sess.total_turn_count,
                    )
                    if matched_pre:
                        pre_result = await RuleEngine.dispatch_many(
                            matched_pre, pre_ctx,
                            db=db, sess=sess,
                            visitor_conn_id=connection_id,
                            visitor_manager=manager,
                            agent_manager=agent_manager,
                            log=log,
                        )
                        if pre_result.transfer_to_human or pre_result.blocked_llm:
                            log.warning(f"Session {session_id} 🛑 Pre-LLM 规则命中, 跳过 LLM 调用 (transfer={pre_result.transfer_to_human}, blocked={pre_result.blocked_llm})")
                            return
            except Exception as e:
                log.exception(f"Session {session_id} Pre-LLM 规则评估异常: {e}")

            # B. 查找 Activity
            t0 = time.perf_counter()
            log.debug(f"Session {session_id} 当前 Session 绑定 Activity ID: {sess.activity_id}")
            activity_name = "未绑定活动"
            current_guideline = "自由交流"
            
            if sess.activity_id:
                act_res = await db.execute(select(Activity).where(Activity.id == sess.activity_id))
                act = act_res.scalar_one_or_none()
                if act:
                    activity_name = act.name
                    stages = json.loads(act.stages_config) if act.stages_config else {}
                    current_guideline = stages.get(sess.current_stage, "自由交流")
            else:
                log.info(f"Session {session_id} 活动不存在 {activity_id} 客户消息:{visitor_msg}")
                return 
            metrics["B_DB_Activity"] = time.perf_counter() - t0
            log.info(f"Session {session_id} 📋  活动剧本: [{activity_name}] | 当前阶段: [{sess.current_stage}]")

            # ==========================================
            # [优雅重构] B.5 调用 UtilRAG 获取静态知识
            # ==========================================
            t0 = time.perf_counter()
            final_kb_context, final_kb_instructions = "暂无", "无特殊约束"
            
            if sess.activity_id:
                final_kb_context, final_kb_instructions = await UtilRAG.retrieve_rag_context(
                    db=db, 
                    activity_id=sess.activity_id, 
                    org_id=sess.org_id, 
                    group_id=sess.group_id, 
                    visitor_msg=visitor_msg, 
                    log=log
                )
                log.info(f"Session {session_id} RAG GOT final_kb_context {(final_kb_context) } final_kb_instructions { (final_kb_instructions) }")
            metrics["B5_RAG"] = time.perf_counter() - t0
            
            # C. 检索 Mem0 记忆
            t0 = time.perf_counter()
            log.debug(f"Session {session_id} 正在调用 Mem0 检索长期记忆...")
            try:
                relevant_memories = visitor_memory_layer.search(query=visitor_msg, filters={"user_id": visitor_uid} )
                memory_context = UtilMem.ProcMem( relevant_memories , log=log)
                log.success(f"Session {session_id} 💡 唤醒记忆成功，条数: {len(relevant_memories)}")
            except Exception as me:
                log.warning(f"Session {session_id} ⚠️ Mem0 检索失败 (可能是首次连接): {me}  {traceback.format_exc()} ")
                memory_context = "暂无"
            metrics["C_Mem0_Search"] = time.perf_counter() - t0
            
            # D. 调用大模型 (已重构为带质检与状态裁判的高级引擎)
            t0 = time.perf_counter()
            log.info(f"Session {session_id} 📡 正在呼叫云端大模型 (LLM)，附带质检与状态机裁判...")
            
            # 1. 提取当前状态机所需配料 (防空指针处理)
            current_stage_key = session.current_stage
            stages_config = {} 
            try:
                stages_config = json.loads(act.stages_config)
            except Exception as e:
                logger.info(f"Session {session_id} parse json stages config error.")
                pass 
            stage_config = stages_config.get(current_stage_key, {}) if act.stages_config else {}
            allowed_next_stages = stage_config.get("next_possible_stages", [])
            stage_guideline = stage_config.get("ai_guideline", "自然对话即可。")
            global_guideline = act.global_guideline if act.global_guideline else "无特殊全局限制。"
            start_time = asyncio.get_event_loop().time()
            # 2. 呼叫我们封装好的高内聚 LLM 引擎
            ai_decision = await generate_ai_reply_with_retry(
                session_id=session_id,
                llm_client=llm_client,
                model_name=settings.LLM_MODEL_NAME,
                visitor_msg=visitor_msg,
                # 传入上下文参数
                activity_name=act.name,
                current_stage=current_stage_key,
                allowed_next_stages=allowed_next_stages,
                global_guideline=global_guideline,
                stage_guideline=stage_guideline,
                kb_context=final_kb_context,
                kb_instructions=final_kb_instructions,
                memory_context=memory_context,
                max_retries=3
            )
            
            # 记录大模型耗时 (完美兼容你之前的监控逻辑)
            metrics["D_LLM_Chat"] = time.perf_counter() - t0
            log.info(f"LLM 裁判最终决策结果: {ai_decision}")
            
            # 3. 解析大模型的双重输出
            # 拿到准备发给客户的话 (无缝对接你后面的代码)
            ai_reply_text = ai_decision["reply_content"]
            
            # 拿到系统内部流转数据
            judged_next_stage = ai_decision.get("next_stage", current_stage_key)
            detected_lang = ai_decision.get("detected_language", "unknown")
            reason = ai_decision.get("stage_reason", "无")
            tags = ai_decision.get("extracted_tags", [])
            detected_emotion = ai_decision.get("customer_emotion", CustomerEmotion.CALM.value)

            log.info(f"🗣️ 访客语言: {detected_lang} | 裁判判断流转至: {judged_next_stage} | 情绪: {detected_emotion} | 标签: {tags} | 理由: {reason}")

            # 4. 核心：原子更新 stage / emotion / 回合数。
            #    用 SQL 表达式 (col = col + 1) 防止 visitor 并发连发时的读改写竞态。
            prev_emotion_value = sess.current_emotion  # 必须在 refresh 前抓: 用于规则的 emotion_degraded 判定
            stage_flipped = judged_next_stage != current_stage_key
            if stage_flipped:
                log.warning(f"🔄 客户触发 SOP 流转: 【{current_stage_key}】 ➡️ 【{judged_next_stage}】 (stage_turn 重置为 1)")
                new_stage_turn = 1
            else:
                # 留在原 stage：自增。SessionRecord.stage_turn_count 在表达式里就是 SQL 字段引用。
                new_stage_turn = SessionRecord.stage_turn_count + 1

            await db.execute(
                update(SessionRecord)
                .where(SessionRecord.id == session_id)
                .values(
                    current_stage=judged_next_stage,
                    current_emotion=detected_emotion,
                    total_turn_count=SessionRecord.total_turn_count + 1,
                    stage_turn_count=new_stage_turn,
                )
            )
            await db.commit()
            # 把内存里的 ORM 对象与 DB 重新对齐 (后续 employee Message insert 要用 sess.current_stage / current_emotion)
            await db.refresh(sess)
            log.debug(f"Session {session_id} 状态已更新: stage={sess.current_stage}, emotion={sess.current_emotion}, total_turn={sess.total_turn_count}, stage_turn={sess.stage_turn_count}")

            # 4.5 Post-LLM 规则评估: 发送支付链接 / 图片 / webhook / 转人工 等增强类
            try:
                post_rules = await RuleEngine.load_active_rules(
                    db, org_id=sess.org_id, activity_id=sess.activity_id, phase="post_llm",
                )
                if post_rules:
                    post_ctx = RuleEngine.build_context_post_llm(
                        prev_stage=current_stage_key,
                        prev_emotion=prev_emotion_value,
                        new_total_turn=sess.total_turn_count,
                        new_stage_turn=sess.stage_turn_count,
                        llm_decision=ai_decision,
                    )
                    matched_post = await RuleEngine.evaluate(
                        post_rules, post_ctx, db,
                        session_id=session_id,
                        current_stage=sess.current_stage,
                        current_total_turn=sess.total_turn_count,
                    )
                    if matched_post:
                        post_result = await RuleEngine.dispatch_many(
                            matched_post, post_ctx,
                            db=db, sess=sess,
                            visitor_conn_id=connection_id,
                            visitor_manager=manager,
                            agent_manager=agent_manager,
                            log=log,
                        )
                        # override_reply 覆盖即将发给访客的 AI 文本
                        if post_result.override_reply is not None:
                            log.warning(f"Session {session_id} 🔁 LLM 回复被规则覆盖")
                            ai_reply_text = post_result.override_reply
                        # 转人工后续访客消息会在 A.6 挡板被吃掉, 这里仍正常发完本轮 LLM 回复
                        if post_result.transfer_to_human:
                            log.warning(f"Session {session_id} 🤝 本轮已触发转人工(下一轮起 LLM 关闭)")
            except Exception as e:
                log.exception(f"Session {session_id} Post-LLM 规则评估异常: {e}")

            duration = asyncio.get_event_loop().time() - start_time
            log.success(f"✨ LLM 生成完毕 (耗时: {duration:.2f}s): {ai_reply_text[:30]}...")

            # E. 持久化并发送
            log.debug("正在写入聊天明细到 MySQL...")
            t0 = time.perf_counter()
            db.add(Message(
                session_id=session_id,
                org_id=sess.org_id,
                group_id=sess.group_id,
                activity_id=sess.activity_id,
                sender_type="employee",
                sender_id=sess.employee_id,
                content=ai_reply_text,
                stage_at_send=sess.current_stage,       # post-flip stage (db.refresh 之后的)
                emotion_at_send=sess.current_emotion,   # 这一轮 LLM 检测到的情绪
                llm_decision_raw=ai_decision,           # LLM 完整决策快照，供后台复盘
            ))
            await db.commit()
            log.info(f"📝 AI 回复已落库 (session={session_id}, employee={sess.employee_id}, len={len(ai_reply_text)})")
            metrics["E_DB_Save"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            log.info(f"📤 正在通过 WebSocket 推送指令到插件: {connection_id}")
            await manager.send_to_client(connection_id, {
                "action": "inject_reply",
                "data": {"session_id": session_id, "text": ai_reply_text, "simulate_typing": True}
            })
            #send WS
            metrics["E_WS"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            # ==========================================
            # F. 记忆刻录 (极其关键：让 Mem0 吸收新知识)
            # ==========================================
            log.debug("🧠 正在将本轮对话喂给 Mem0 进行画像提取...")
            try:
                # 把用户说的话和 AI 的回复一起扔给 Mem0，它会在后台自动提取并更新画像
                visitor_memory_layer.add(
                    [
                        {"role": "user", "content": visitor_msg}, 
                        {"role": "assistant", "content": ai_reply_text}
                    ],
                    user_id=visitor_uid
                )
                log.success("🧠 Mem0 记忆刻录完成！")
            except Exception as e:
                log.warning(f"⚠️ Mem0 刻录记忆时发生异常: {e}")
            metrics["F_Mem0_Add"] = time.perf_counter() - t0
            metrics["Total_Process"] = time.perf_counter() - t_process_start    
            log.success("✅ 整个 Session 流程处理圆满结束！")
            report = (
                            f"\n{'='*45}\n"
                            f"⏱️ Session [{session_id}] 性能耗时诊断报告\n"
                            f"{'-'*45}\n"
                            f"A. 查会话 (MySQL)      : {metrics['A_DB_Session']:.3f} 秒\n"
                            f"B. 查剧本 (MySQL)      : {metrics['B_DB_Activity']:.3f} 秒\n"
                            f"C. Mem0 搜记忆 (Search): {metrics['C_Mem0_Search']:.3f} 秒  <-- 重点关注\n"
                            f"C. B5_RAG 搜知识库 (Search): {metrics['B5_RAG']:.3f} 秒  <-- 重点关注\n"
                            
                            f"D. 大模型推理 (LLM)    : {metrics['D_LLM_Chat']:.3f} 秒\n"
                            f"E. 落库及WS下发        : {metrics['E_DB_Save_WS']:.3f} 秒\n"
                            f"F. Mem0 存记忆 (Add)   : {metrics['F_Mem0_Add']:.3f} 秒  <-- 重点关注\n"
                            f"{'-'*45}\n"
                            f"✅ 总体链路总耗时      : {metrics['Total_Process']:.3f} 秒\n"
                            f"{'='*45}"
                        )
            log.success(report)
        except Exception as e:
            log.exception(f"💥 处理会话时发生崩溃: {e}")
            
# ==========================================
# 6. FastAPI 路由挂载
# ==========================================
app = FastAPI(title="SaaS AI Agent Hub")
#give a setting to state.
app.state.main_settings = settings

_cors_origins = [o.strip() for o in settings.FRONTEND_ORIGINS.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(kb_router)

#router
# URL: /ws/{activity_id}/{visitor_uid}
#   - activity_id 决定剧本和 org/group/employee 归属（后端反查）
#   - visitor_uid 是访客的稳定唯一标识（前端 cookie/localStorage 持久化）
# connection_id = {activity_id}_{visitor_uid}，天然按访客隔离，避免多访客冲突
@app.websocket("/ws/{activity_id}/{visitor_uid}")
async def websocket_endpoint(websocket: WebSocket, activity_id: str, visitor_uid: str, background_tasks: BackgroundTasks):
    connection_id = f"{activity_id}_{visitor_uid}"
    logger.info(f"🔌 [WS Connect] activity={activity_id} visitor={visitor_uid} conn={connection_id}")
    await manager.connect(websocket, connection_id)

    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            logger.info(f"📥 [WS Recv] conn={connection_id} raw={data_str}")
            if data.get("action") == "new_visitor_message":
                payload = data["payload"]

                # 立刻回复 ACK，保持前端长连接健康
                await websocket.send_json({"action": "ack"})

                # visitor_uid 优先以 URL 为准（连接级身份），payload 里允许同时带上但以 URL 覆盖
                payload_visitor_uid = payload.get("visitor_uid")
                if payload_visitor_uid and payload_visitor_uid != visitor_uid:
                    logger.warning(
                        f"⚠️ payload.visitor_uid={payload_visitor_uid} 与 URL visitor_uid={visitor_uid} 不一致，以 URL 为准"
                    )

                # 将全套 AI 逻辑（查库+查记忆+请求LLM）放入后台任务，实现超高并发
                asyncio.create_task(
                    process_ai_reply(
                        connection_id,
                        payload["session_id"],
                        payload["text"],
                        visitor_uid,
                        activity_id,
                    )
                )
            else:
                logger.info(f"ℹ️ [WS Recv] conn={connection_id} 非业务消息 action={data.get('action')}，已忽略")
    except WebSocketDisconnect:
        logger.info(f"🔌 [WS Disconnect] conn={connection_id} (正常断开)")
        manager.disconnect(connection_id)
    except Exception as e:
        logger.exception(f"💥 [WS Error] conn={connection_id} err={e}")
        manager.disconnect(connection_id)


# ==========================================
# 员工通知 WebSocket: /ws/agent/{employee_id}?token=<JWT>
# 单向 push 通道, 用于转人工邀请 / 系统通知; 不接收业务消息
# ==========================================
@app.websocket("/ws/agent/{employee_id}")
async def agent_websocket_endpoint(websocket: WebSocket, employee_id: str, token: str = Query(...)):
    # 用 JWT 校验当前 token.sub 对应的 user 是否绑定了这个 employee_id
    try:
        payload = decode_token(token)
        sub_user_id = payload.get("sub")
        if not sub_user_id:
            raise ValueError("token 缺 sub")
    except Exception as e:
        logger.warning(f"[Agent WS] token 校验失败 employee={employee_id}: {e}")
        await websocket.close(code=4401)
        return

    # 校验绑定关系
    async with AsyncSessionLocal() as db:
        from models import User
        ur = await db.execute(select(User).where(User.id == sub_user_id))
        u = ur.scalar_one_or_none()
        if not u or u.employee_id != employee_id:
            logger.warning(f"[Agent WS] user {sub_user_id} 与 employee {employee_id} 不匹配, 拒绝")
            await websocket.close(code=4403)
            return

    await agent_manager.connect(websocket, employee_id)
    try:
        while True:
            # 单向 push, 但仍要 receive 保持连接活跃
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"🔌 [Agent WS Disconnect] employee={employee_id}")
        agent_manager.disconnect(websocket, employee_id)
    except Exception as e:
        logger.exception(f"💥 [Agent WS Error] employee={employee_id} err={e}")
        agent_manager.disconnect(websocket, employee_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

    