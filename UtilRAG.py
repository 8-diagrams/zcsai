# UtilRAG.py
import asyncio
from loguru import logger
from sqlalchemy.future import select
from openai import AsyncOpenAI

# 导入你自己的 ORM 模型
from models import KnowledgeBase, ActivityKBMount 
# 导入我们之前写的文本转向量工具
from UtilVector import get_embeddings
# 💡 强烈建议：为了防止 SQLite 本地文件被多进程锁死，请把 llm_client 和 qdrant_client 统一放在 config.py 里初始化！
from glbclient import qdrant_client

from config import settings 
llm_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL
)


def _point_sort_key(hit):
    """
    Qdrant query_points already returns vector hits by relevance. Keep that as
    the primary ordering signal and only use added_at as a tie-breaker.
    """
    score = hit.score if getattr(hit, "score", None) is not None else 0
    added_at = (hit.payload or {}).get("added_at", "1970-01-01T00:00:00")
    return (score, added_at)


def _shorten(text, limit=80):
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _describe_kb(kb, mount=None):
    parts = [
        f"id={kb.id}",
        f"name={kb.name}",
        f"org={kb.org_id}",
        f"group={kb.group_id}",
        f"shared={kb.is_shared_to_groups}",
        f"collection={kb.vector_collection_name}",
    ]
    if mount is not None:
        parts.extend([
            f"priority={mount.priority}",
            f"mount_guideline={'yes' if mount.mount_guideline else 'no'}",
        ])
    return " ".join(parts)


async def retrieve_rag_context(db, activity_id: str, org_id: str, group_id: str, visitor_msg: str, log):
    """
    独立封装的 RAG 知识库检索模块
    """
    kb_context_snippets = []
    kb_instructions = []
    
    try:
        log.info(
            "📚 RAG START activity={} org={} group={} msg_len={} msg_preview='{}'",
            activity_id,
            org_id,
            group_id,
            len(visitor_msg or ""),
            _shorten(visitor_msg),
        )
        
        # 1. 联合查询：查出授权的知识库基本信息 + 挂载关系
        mounts_stmt = (
            select(KnowledgeBase, ActivityKBMount)
            .join(ActivityKBMount, KnowledgeBase.id == ActivityKBMount.kb_id)
            .where(ActivityKBMount.activity_id == activity_id)
            .where(KnowledgeBase.org_id == org_id)
            .order_by(ActivityKBMount.priority.desc())
        )
        mounts_res = await db.execute(mounts_stmt)
        allowed_kbs = mounts_res.all()
        log.info(
            "📚 RAG mounted_kbs count={} activity={} org={} group={}",
            len(allowed_kbs),
            activity_id,
            org_id,
            group_id,
        )
        
        # 2. 解析与提取
        if allowed_kbs:
            for kb, mount in allowed_kbs:
                log.info("📚 RAG mounted_kb {}", _describe_kb(kb, mount))
            
            # 🔥 性能优化核心：只请求 1 次大模型 API 将访客消息向量化
            log.debug("正在将访客消息转化为 Embedding 向量...")
            try:
                msg_embeddings = await get_embeddings(llm_client, [visitor_msg])
                query_vector = msg_embeddings[0]
                log.info(
                    "📚 RAG embedding_ok dims={} activity={} mounted_kbs={}",
                    len(query_vector) if query_vector else 0,
                    activity_id,
                    len(allowed_kbs),
                )
            except Exception as emb_e:
                log.error(f"❌ 访客消息向量化失败，降级跳过 RAG 检索: {emb_e}")
                return "暂无", "无特殊约束"

            # 遍历每一个命中的知识库
            for kb, mount in allowed_kbs:
                # 2.1 提取指引 (挂载级优先于主库级)
                guideline = mount.mount_guideline if mount.mount_guideline else kb.usage_guideline
                if guideline:
                    kb_instructions.append(f"【{kb.name}】: {guideline}")
                
                # 2.2 真实的 Qdrant 向量检索
                try:
                    log.info(
                        "📚 RAG qdrant_query kb_id={} kb_name={} collection={} limit=10",
                        kb.id,
                        kb.name,
                        kb.vector_collection_name,
                    )
                    # 🎯 适配 Qdrant 1.16.0+ 最新版 API
                    # 1. 方法名由 search 变更为 query_points
                    # 2. 向量参数名由 query_vector 变更为 query
                    search_result = await qdrant_client.query_points(
                        collection_name=kb.vector_collection_name, 
                        query=query_vector,
                        limit=10  # 🎯 扩大召回池
                    )
                    
                    if search_result and search_result.points:
                        points = search_result.points
                        score_parts = []
                        for hit in points[:10]:
                            payload = hit.payload or {}
                            score_parts.append(
                                "score={:.4f} added_at={} text='{}'".format(
                                    hit.score if getattr(hit, "score", None) is not None else 0,
                                    payload.get("added_at", ""),
                                    _shorten(payload.get("text", ""), 60),
                                )
                            )
                        log.info(
                            "📚 RAG qdrant_hits kb_id={} count={} hits=[{}]",
                            kb.id,
                            len(points),
                            "; ".join(score_parts),
                        )
                        
                        # 2. 重排：语义分优先，更新时间只做同分辅助。
                        # 之前单纯按 added_at 排序，会让新的弱相关片段挤掉旧的强相关片段。
                        points_sorted = sorted(
                            points, 
                            key=_point_sort_key,
                            reverse=True
                        )
                        
                        # 3. 精准截断 (Truncate)：只取重排后最新、最相关的 Top 3
                        top_3_points = points_sorted[:3]
                        
                        # 4. 提取原文并拼接
                        extracted_texts = []
                        for hit in top_3_points:
                            payload = hit.payload or {}
                            text = payload.get("text", "")
                            # 可选：如果你想让大模型明确知道这是什么时候的规矩，可以把时间也拼进去
                            added_time = payload.get("added_at", "")[:10]
                            if added_time and added_time != "1970-01-01":
                                extracted_texts.append(f"[更新于 {added_time}]: {text}")
                            else:
                                extracted_texts.append(text)
                                
                        combined_text = "\n".join(extracted_texts)
                        
                        snippet = f"[{kb.name} 相关资料]:\n{combined_text}"
                        kb_context_snippets.append(snippet)
                        log.info(
                            "📚 RAG selected kb_id={} selected_count={} selected_preview='{}'",
                            kb.id,
                            len(top_3_points),
                            _shorten(combined_text, 160),
                        )
                    else:
                        log.info(
                            "📚 RAG qdrant_no_hits kb_id={} kb_name={} collection={}",
                            kb.id,
                            kb.name,
                            kb.vector_collection_name,
                        )
                        
                except Exception as ve:
                    # 单个库如果因为没建好等原因查失败了，不能阻断整个流程
                    log.warning(
                        "⚠️ RAG qdrant_failed kb_id={} kb_name={} collection={} error={}",
                        kb.id,
                        kb.name,
                        kb.vector_collection_name,
                        ve,
                    )
        else:
            raw_mounts_res = await db.execute(
                select(KnowledgeBase, ActivityKBMount)
                .join(ActivityKBMount, KnowledgeBase.id == ActivityKBMount.kb_id)
                .where(ActivityKBMount.activity_id == activity_id)
                .order_by(ActivityKBMount.priority.desc())
            )
            raw_mounts = raw_mounts_res.all()
            if raw_mounts:
                for kb, mount in raw_mounts:
                    log.warning(
                        "📚 RAG mounted_but_org_filtered requested_org={} requested_group={} {}",
                        org_id,
                        group_id,
                        _describe_kb(kb, mount),
                    )
            else:
                log.warning(
                    "📚 RAG no_kb_mounts activity={} org={} group={}",
                    activity_id,
                    org_id,
                    group_id,
                )
                
    except Exception as e:
        log.error(f"❌ UtilRAG 主逻辑发生致命异常: {e}")

    # 3. 组装最终结果
    final_kb_context = "\n\n".join(kb_context_snippets) if kb_context_snippets else "暂无相关产品背景知识。"
    final_kb_instructions = "\n".join(kb_instructions) if kb_instructions else "无特殊约束"
    log.info(
        "📚 RAG END activity={} context_snippets={} instruction_count={} has_context={}",
        activity_id,
        len(kb_context_snippets),
        len(kb_instructions),
        bool(kb_context_snippets),
    )
    
    return final_kb_context, final_kb_instructions
