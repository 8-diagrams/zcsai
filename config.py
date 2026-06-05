from pydantic_settings import BaseSettings, SettingsConfigDict
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
    QDRANT_DATA_PATH: str = "./qdrant_data"

    # JWT / RBAC
    JWT_SECRET: str = "please-change-me-in-prod"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # 允许跨域的前端 origin (逗号分隔)
    FRONTEND_ORIGINS: str = "http://localhost:3001,http://127.0.0.1:3001"

    # 上传素材本地落盘目录 (生产可换对象存储); 通过 /media 静态挂载对外访问
    UPLOAD_DIR: str = "./uploads"

    # 对外公开访问本服务的根地址 (含协议+域名+端口, 不带末尾斜杠), 如 https://api.example.com。
    # 用于把 /media/xxx 这类相对路径拼成访客 widget 能直接打开的绝对 URL。
    # 留空则下发相对路径 (仅同源前端可用)。
    PUBLIC_BASE_URL: str = ""

    # 指定从 .env 文件读取
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def to_public_url(url: str) -> str:
    """把相对媒体路径 (/media/xxx) 拼成绝对 URL; 已是绝对地址或未配置 base 时原样返回。"""
    if not url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return url
    return base + (url if url.startswith("/") else "/" + url)


YQrequirement="""角色: 你是一个有高中学历的真人,请用最简洁的话直接回答问题或者提出问题, 不要发挥. 记忆中有的信息不要重复问客户, 不要回答一些和领域无关的问题 """
# 实例化配置对象
settings = Settings()
