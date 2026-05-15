# glbclient.py
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from config import settings

# ========================================================
# 全局大模型客户端 (单例)
# ========================================================
# 业务内所有的 AI 请求（对话、翻译、向量化）都共用这一个客户端，极致复用连接池。
llm_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL
)

# ========================================================
# 全局向量数据库客户端 (单例)
# ========================================================
# 彻底解决 SQLite/RocksDB 本地文件被反锁 (Database is locked) 的问题。
qdrant_client = AsyncQdrantClient(path=settings.QDRANT_DATA_PATH)
