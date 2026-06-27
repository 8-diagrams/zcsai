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
# 全局向量数据库客户端
# ========================================================
# 生产环境通过 QDRANT_URL/HOST 连接独立 Qdrant 服务; 本地未配置时兼容旧 path 模式。
qdrant_client = AsyncQdrantClient(**settings.qdrant_client_config())
