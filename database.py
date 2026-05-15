# database.py
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    
# ========================================================
# 1. 数据库连接配置 (Database URL)
# ========================================================
# ⚠️ 注意：异步必须使用 mysql+aiomysql 驱动！
# 如果你是部署在本地的边缘节点（比如 RK3588）或 Docker 容器内，请将 127.0.0.1 替换为对应的内网 IP。
settings = Settings()

# ========================================================
# 2. 初始化异步引擎 (Async Engine)
# ========================================================
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,              # 生产环境设为 False；调试时设为 True 可以看底层打印的 SQL 语句
    pool_pre_ping=True,      # 每次拿连接前先 ping 一下，完美解决 MySQL "MySQL server has gone away" 错误
    pool_size=10,            # 核心连接池大小 (适合普通并发)
    max_overflow=20          # 应对突发流量的额外最大连接数
)

# ========================================================
# 3. 初始化异步会话工厂 (SessionLocal)
# ========================================================
# 这就是 main.py 中 `async with AsyncSessionLocal() as db:` 的来源
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 异步环境下极其重要：防止 commit 后对象属性被过期销毁而报错
    autocommit=False,
    autoflush=False,
)

# ========================================================
# 4. 声明 ORM 基类 (Base)
# ========================================================
# 所有 models.py 里的模型类都必须继承这个 Base！
Base = declarative_base()