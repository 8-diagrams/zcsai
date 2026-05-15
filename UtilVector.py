# UtilVector.py
from loguru import logger
from openai import AsyncOpenAI
# 假设你有一个全局的配置获取 API Key，如果没有，这里直接填入
# client = AsyncOpenAI(api_key="sk-xxxx")

async def chunk_text(text: str, max_chunk_size: int = 500) -> list[str]:
    """极其轻量级的文本切片器"""
    chunks = []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for p in paragraphs:
        if len(p) <= max_chunk_size:
            chunks.append(p)
        else:
            sentences = p.split("。")
            current_chunk = ""
            for s in sentences:
                if len(current_chunk) + len(s) < max_chunk_size:
                    current_chunk += s + "。"
                else:
                    chunks.append(current_chunk)
                    current_chunk = s + "。"
            if current_chunk: chunks.append(current_chunk)
    return [c for c in chunks if c]

async def get_embeddings(llm_client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """调用大模型，将文本转化为向量"""
    response = await llm_client.embeddings.create(
        input=texts,
        model="text-embedding-3-small" # 推荐使用 small，便宜且标准 (1536维)
    )
    return [data.embedding for data in response.data]


