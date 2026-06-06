# 后端 FastAPI 镜像 (uv 管依赖, 单 worker —— 见 README: 嵌入式 Qdrant 约束)
FROM python:3.11-slim

# 安装 uv (官方静态二进制)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 先装依赖 (利用层缓存): 只 COPY 锁文件
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 再 COPY 源码 (.dockerignore 已排除数据目录/前端/venv)
COPY . .

# 运行期数据目录 (会被 compose 卷覆盖, 这里建好占位)
RUN mkdir -p uploads qdrant_data memory_db logs

EXPOSE 1081

# 单 worker: glbclient/mem0 各用嵌入式 Qdrant(path=...), 一个目录只能一个进程打开。
# 多 worker 会 "already accessed by another instance" 崩溃。
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1081", "--workers", "1"]
