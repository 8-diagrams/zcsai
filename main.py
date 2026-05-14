import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Boolean, select
from mem0 import Memory
from openai import AsyncOpenAI
import sys 
from loguru import logger
import traceback

import UtilMem


# 移除默认配置
logger.remove()
# 添加控制台输出（带颜色，方便肉眼看）
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>", level="INFO")
# 添加文件日志（持久化，方便查昨天的Bug）
logger.add("logs/agent_server.log", rotation="10 MB", level="DEBUG")

# ==========================================
# 1. 全局配置管理 (加载 .env)
# ==========================================
class Settings(BaseSettings):
    DATABASE_URL: str
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    MEMORY_DB_PATH: str = "./memory_db"
    DEBUG_MODE: bool = False
    LLM_EMBEDDING_MODEL: str

    # 指定从 .env 文件读取
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

YQrequirement="""角色: 你是一个有高中学历的真人,请用最简洁的话直接回答问题或者提出问题, 不要发挥 """
# 实例化配置对象
settings = Settings()

print("====== 终极调试 ======")
print("我读到的 API KEY 是: [", settings.LLM_API_KEY, "]")
print("我读到的 Base URL 是: [", settings.LLM_BASE_URL, "]")
print("======================")

# ==========================================
# 2. 初始化数据库与 ORM 模型
# ==========================================
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
async def process_ai_reply(connection_id: str, session_id: str, visitor_msg: str, visitor_uid: str):
    # 为当前 Session 创建一个独立的日志标识（Logger Context）
    log = logger.bind(session_id=session_id, visitor=visitor_uid)
    log.info(f"🚀 [新任务] 开始处理会话消息: '{visitor_msg}'")

    async with AsyncSessionLocal() as db:
        try:
            # A. 查找 Session
            log.debug("正在查询数据库获取 Session 信息...")
            result = await db.execute(select(SessionRecord).where(SessionRecord.id == session_id))
            sess = result.scalar_one_or_none()
            
            if not sess:
                log.error(f"❌ 找不到会话对象: {session_id}")
                return

            # B. 查找 Activity
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
            
            log.info(f"📋  活动剧本: [{activity_name}] | 当前阶段: [{sess.current_stage}]")

            # C. 检索 Mem0 记忆
            log.debug("正在调用 Mem0 检索长期记忆...")
            try:
                relevant_memories = visitor_memory_layer.search(query=visitor_msg, filters={"user_id": visitor_uid} )
                memory_context = UtilMem.ProcMem( relevant_memories , log=log)
                log.success(f"💡 唤醒记忆成功，条数: {len(relevant_memories)}")
            except Exception as me:
                log.warning(f"⚠️ Mem0 检索失败 (可能是首次连接): {me}  {traceback.format_exc()} ")
                memory_context = "暂无"

            # D. 调用大模型
            log.info("📡 正在呼叫云端大模型 (LLM)...")
            start_time = asyncio.get_event_loop().time()

            messages=[
                {"role": "system", "content": f"你是一个金牌客服, {YQrequirement}。剧本任务：{current_guideline}。记忆：{memory_context}"},
                {"role": "user", "content": visitor_msg}
            ]
            log.info(f"LLM message {messages}")
            response = await llm_client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                max_tokens=2000,
                temperature=0.7
            )
            log.info(f"LLM resp { response }")
            ai_reply_text = response.choices[0].message.content.strip()
            
            duration = asyncio.get_event_loop().time() - start_time
            log.success(f"✨ LLM 生成完毕 (耗时: {duration:.2f}s): {ai_reply_text[:30]}...")

            # E. 持久化并发送
            log.debug("正在写入聊天明细到 MySQL...")
            db.add(Message(
                session_id=session_id, org_id=sess.org_id, group_id=sess.group_id,
                activity_id=sess.activity_id, sender_type="employee", content=ai_reply_text
            ))
            await db.commit()

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
                
            log.info(f"📤 正在通过 WebSocket 推送指令到插件: {connection_id}")
            await manager.send_to_client(connection_id, {
                "action": "inject_reply",
                "data": {"session_id": session_id, "text": ai_reply_text, "simulate_typing": True}
            })
            
            log.success("✅ 整个 Session 流程处理圆满结束！")

        except Exception as e:
            log.exception(f"💥 处理会话时发生崩溃: {e}")
            
# ==========================================
# 6. FastAPI 路由挂载
# ==========================================
app = FastAPI(title="SaaS AI Agent Hub")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.websocket("/ws/{org_id}/{employee_id}")
async def websocket_endpoint(websocket: WebSocket, org_id: str, employee_id: str, background_tasks: BackgroundTasks):
    connection_id = f"{org_id}_{employee_id}"
    await manager.connect(websocket, connection_id)
    
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            logger.info(f"input data [{data_str}]",  )
            if data.get("action") == "new_visitor_message":
                payload = data["payload"]
                
                # 立刻回复 ACK，保持前端长连接健康
                await websocket.send_json({"action": "ack"})
                
                # 将全套 AI 逻辑（查库+查记忆+请求LLM）放入后台任务，实现超高并发
                asyncio.create_task(
                    process_ai_reply(
                        connection_id, 
                        payload["session_id"], 
                        payload["text"],
                        payload["visitor_uid"]
                    )
                )
    except WebSocketDisconnect:
        logger.info(f"exception for {connection_id}, {traceback.format_exc() } ")
        manager.disconnect(connection_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

    