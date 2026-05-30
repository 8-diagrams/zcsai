import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
#from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
#from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Boolean, select
from mem0 import Memory
from openai import AsyncOpenAI
import sys
from loguru import logger
import traceback
import time
import random
from typing import Optional

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
from models import SessionRecord, Activity, Message, KnowledgeBase, ActivityKBMount, Employee

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
            log.debug("正在查询数据库获取 Session 信息...")
            result = await db.execute(select(SessionRecord).where(SessionRecord.id == session_id))
            sess = result.scalar_one_or_none()
            metrics["A_DB_Session"] = time.perf_counter() - t0
            if not sess:
                # 首次进线：用 URL 上的 activity_id 反查 activity，从中拿 org/group，再分配 employee
                log.info(f"🆕 Session {session_id} 在 DB 中不存在，开始首次建会话流程")
                act_res = await db.execute(select(Activity).where(Activity.id == activity_id))
                act = act_res.scalar_one_or_none()
                if not act:
                    log.error(f"❌ 前端传入的 activity_id={activity_id} 在 activities 表中不存在，放弃建会话")
                    return
                log.info(f"📋 命中活动剧本: id={act.id} name={act.name} org={act.org_id} group={act.group_id}")

                matched = await match_employee_for_activity(db, act, log)
                bind_employee_id = matched.id if matched is not None else None
                if bind_employee_id is None:
                    log.warning("⚠️ 未匹配到坐席，session.employee_id 将留空(NULL)")

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
                    f"✅ 新会话已落库 | session_id={session_id} org={sess.org_id} group={sess.group_id} "
                    f"activity={sess.activity_id} employee={sess.employee_id} visitor={visitor_uid}"
                )
            else:
                log.info(
                    f"🔁 命中已有 Session | org={sess.org_id} group={sess.group_id} "
                    f"activity={sess.activity_id} employee={sess.employee_id} stage={sess.current_stage}"
                )

            # B. 查找 Activity
            t0 = time.perf_counter()
            log.debug(f"当前 Session 绑定 Activity ID: {sess.activity_id}")
            activity_name = "未绑定活动"
            current_guideline = "自由交流"
            
            if sess.activity_id:
                act_res = await db.execute(select(Activity).where(Activity.id == sess.activity_id))
                act = act_res.scalar_one_or_none()
                if act:
                    activity_name = act.name
                    stages = json.loads(act.stages_config) if act.stages_config else {}
                    current_guideline = stages.get(sess.current_stage, "自由交流")
            metrics["B_DB_Activity"] = time.perf_counter() - t0
            log.info(f"📋  活动剧本: [{activity_name}] | 当前阶段: [{sess.current_stage}]")

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
                log.info(f"RAG GOT final_kb_context {(final_kb_context) } final_kb_instructions { (final_kb_instructions) }")
            metrics["B5_RAG"] = time.perf_counter() - t0
            
            # C. 检索 Mem0 记忆
            t0 = time.perf_counter()
            log.debug("正在调用 Mem0 检索长期记忆...")
            try:
                relevant_memories = visitor_memory_layer.search(query=visitor_msg, filters={"user_id": visitor_uid} )
                memory_context = UtilMem.ProcMem( relevant_memories , log=log)
                log.success(f"💡 唤醒记忆成功，条数: {len(relevant_memories)}")
            except Exception as me:
                log.warning(f"⚠️ Mem0 检索失败 (可能是首次连接): {me}  {traceback.format_exc()} ")
                memory_context = "暂无"
            metrics["C_Mem0_Search"] = time.perf_counter() - t0
            
            # D. 调用大模型
            t0 = time.perf_counter()
            log.info("📡 正在呼叫云端大模型 (LLM)...")
            start_time = asyncio.get_event_loop().time()
            # 构建结构化的 System 字典
            system_prompt_dict = {
                "role_definition": f"{YQrequirement}",
                "current_task": current_guideline,
                "kb_special_instructions": final_kb_instructions,
                "kb_standard_context": final_kb_context,
                "customer_memory_profile": memory_context
            } 
            system_prompt_json = json.dumps(system_prompt_dict, ensure_ascii=False, indent=2)
            log.debug(f"🧮 提交给大模型的 JSON:\n{system_prompt_json}")

            messages = [
                {"role": "system", "content": system_prompt_json},
                {"role": "user", "content": visitor_msg}
            ]
            log.info(f"LLM message {messages}")
            response = await llm_client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                max_tokens=2000,
                temperature=0.7
            )
            metrics["D_LLM_Chat"] = time.perf_counter() - t0
            log.info(f"LLM resp { response }")
            ai_reply_text = response.choices[0].message.content.strip()
            
            duration = asyncio.get_event_loop().time() - start_time
            log.success(f"✨ LLM 生成完毕 (耗时: {duration:.2f}s): {ai_reply_text[:30]}...")

            # E. 持久化并发送
            log.debug("正在写入聊天明细到 MySQL...")
            t0 = time.perf_counter()
            db.add(Message(
                session_id=session_id, org_id=sess.org_id, group_id=sess.group_id,
                activity_id=sess.activity_id, sender_type="employee", content=ai_reply_text
            ))
            await db.commit()
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

    