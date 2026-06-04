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

    # 指定从 .env 文件读取
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

YQrequirement="""角色: 你是一个有高中学历的真人,请用最简洁的话直接回答问题或者提出问题, 不要发挥. 记忆中有的信息不要重复问客户, 不要回答一些和领域无关的问题 """
# 实例化配置对象
settings = Settings()
