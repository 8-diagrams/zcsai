# UtilRAG.py
import asyncio
from sqlalchemy.future import select
# ⚠️ 注意：这里需要根据你实际的文件结构，导入对应的 ORM 模型
from models import KnowledgeBase, ActivityKBMount 

from loguru import logger 

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
            
            for kb, mount in allowed_kbs:
                # 提取指引 (挂载级优先于主库级)
                guideline = mount.mount_guideline if mount.mount_guideline else kb.usage_guideline
                if guideline:
                    kb_instructions.append(f"【{kb.name}】: {guideline}")
                
                # 向量检索 (伪代码：防阻塞丢进线程池)
                # snippet = await asyncio.to_thread(
                #     vector_db_client.search, 
                #     collection_name=kb.vector_collection_name, 
                #     query=visitor_msg
                # )
                
                # 临时挡板数据
                snippet = f"[{kb.name} 相关资料]: 如果客户问相关问题，请依此作答。"
                kb_context_snippets.append(snippet)
                
    except Exception as e:
        log.error(f"❌ UtilRAG 检索发生异常: {e}")

    # 3. 组装最终结果
    final_kb_context = "\n".join(kb_context_snippets) if kb_context_snippets else "暂无"
    final_kb_instructions = "\n".join(kb_instructions) if kb_instructions else "无特殊约束"
    
    return final_kb_context, final_kb_instructions
    