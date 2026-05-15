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


async def retrieve_rag_context(db, activity_id: str, org_id: str, group_id: str, visitor_msg: str, log):
    """
    独立封装的 RAG 知识库检索模块
    """
    kb_context_snippets = []
    kb_instructions = []
    
    try:
        log.debug("📚 正在进入 UtilRAG: 拉取当前活动挂载的授权知识库...")
        
        # 1. 联合查询：查出授权的知识库基本信息 + 挂载关系
        mounts_stmt = (
            select(KnowledgeBase, ActivityKBMount)
            .join(ActivityKBMount, KnowledgeBase.id == ActivityKBMount.kb_id)
            .where(ActivityKBMount.activity_id == activity_id)
            .where(
                (KnowledgeBase.group_id == group_id) | 
                ((KnowledgeBase.org_id == org_id) & (KnowledgeBase.is_shared_to_groups == True))
            )
            .order_by(ActivityKBMount.priority.desc())
        )
        mounts_res = await db.execute(mounts_stmt)
        allowed_kbs = mounts_res.all()
        
        # 2. 解析与提取
        if allowed_kbs:
            log.info(f"📚 RAG 命中 {len(allowed_kbs)} 个授权知识库，开始合并规则与向量检索...")
            
            # 🔥 性能优化核心：只请求 1 次大模型 API 将访客消息向量化
            log.debug("正在将访客消息转化为 Embedding 向量...")
            try:
                msg_embeddings = await get_embeddings(llm_client, [visitor_msg])
                query_vector = msg_embeddings[0]
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
                    # 🎯 适配 Qdrant 1.16.0+ 最新版 API
                    # 1. 方法名由 search 变更为 query_points
                    # 2. 向量参数名由 query_vector 变更为 query
                    search_result = await qdrant_client.query_points(
                        collection_name=kb.vector_collection_name, 
                        query=query_vector,
                        limit=3 # 🎯 每次查询取出相关度最高的 3 个切片片段
                    )
                    
                    # 3. 返回结果变更为 QueryResponse 对象，数据列表存储在 .points 属性中
                    if search_result and search_result.points:
                        # 提取 payload 中的原文并拼接
                        extracted_texts = [hit.payload.get("text", "") for hit in search_result.points]
                        combined_text = "\n".join(extracted_texts)
                        
                        snippet = f"[{kb.name} 相关资料]:\n{combined_text}"
                        kb_context_snippets.append(snippet)
                        
                except Exception as ve:
                    # 单个库如果因为没建好等原因查失败了，不能阻断整个流程
                    log.warning(f"⚠️ 知识库 [{kb.name}] 向量检索失败 (可能集合不存在): {ve}")
                
    except Exception as e:
        log.error(f"❌ UtilRAG 主逻辑发生致命异常: {e}")

    # 3. 组装最终结果
    final_kb_context = "\n\n".join(kb_context_snippets) if kb_context_snippets else "暂无相关产品背景知识。"
    final_kb_instructions = "\n".join(kb_instructions) if kb_instructions else "无特殊约束"
    
    return final_kb_context, final_kb_instructions
    