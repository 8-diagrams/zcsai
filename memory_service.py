import asyncio
from functools import lru_cache

from mem0 import Memory

from config import settings


mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "saas_visitor_memories",
            **settings.qdrant_mem0_config(),
        },
    },
    "llm": {
        "provider": "openai",
        "config": {
            "api_key": settings.LLM_API_KEY,
            "openai_base_url": settings.LLM_BASE_URL,
            "model": "gpt-4o-mini",
            "temperature": 0.1,
        },
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "api_key": settings.LLM_API_KEY,
            "openai_base_url": settings.LLM_BASE_URL,
            "model": settings.LLM_EMBEDDING_MODEL,
        },
    },
}


@lru_cache(maxsize=1)
def get_memory_layer():
    return Memory.from_config(mem0_config)


async def memory_search(*, query: str, filters: dict):
    memory_layer = await asyncio.to_thread(get_memory_layer)
    return await asyncio.to_thread(memory_layer.search, query=query, filters=filters)


async def memory_add(messages: list[dict], *, user_id: str):
    memory_layer = await asyncio.to_thread(get_memory_layer)
    return await asyncio.to_thread(memory_layer.add, messages, user_id=user_id)
