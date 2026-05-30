# router_kb.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response 
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from loguru import logger

# 导入咱们写的工具和数据库地基
from UtilVector import chunk_text, get_embeddings
from database import AsyncSessionLocal
from datetime import datetime, timezone 

from models import ActivityKBMount, KnowledgeBase, Activity, User
from sqlalchemy.future import select

# 共享依赖: DB 会话 + 当前登录用户 + 同 org 校验
from deps import get_db, get_current_user, require_min_role, assert_same_org

router = APIRouter()

# 💡 魔法就在这里：path="./qdrant_data" 会在你的项目里建一个文件夹存向量！
# 就像 SQLite 的 .db 文件一样，不需要独立安装任何数据库软件。
from glbclient import qdrant_client



 # 请替换成你的 Key


class CreateKBRequest(BaseModel):
    name: str
    org_id: str
    group_id: str = None
    is_shared_to_groups : bool = False
    usage_guideline: str = None
    raw_text: str  # 粘贴进来的产品手册纯文本

@router.post("/api/kb/create")
async def create_knowledge_base(
    request: Request,
    req: CreateKBRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, req.org_id)
    kb_id = f"kb_{uuid.uuid4().hex[:12]}"
    collection_name = f"col_{req.org_id}_{kb_id}"
    logger.info(f"need to create KB_ID {collection_name}")
    try:
        # 1. 文本切片
        chunks = await chunk_text(req.raw_text)
        if not chunks:
            raise HTTPException(status_code=400, detail="文本内容为空")

        #get setting from main.py
        main_settings = request.app.state.main_settings
        llm_client = AsyncOpenAI(
            api_key=main_settings.LLM_API_KEY,
            base_url=main_settings.LLM_BASE_URL
        )
        # 2. 获取向量 (呼叫 OpenAI)
        embeddings = await get_embeddings(llm_client, chunks)
        
        # 3. 写入本地 Qdrant
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
        
        points = []
        current_time = datetime.now(timezone.utc).isoformat()
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "text": chunk, 
                        "source_kb": kb_id,
                        "added_at": current_time, # 🆕 注入时间戳
                        "type": "create"          # 🆕 标记操作类型
                    } 
                )
            )
            
        await qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )
        
        # 4. 写入 MySQL (同步业务关系数据)
        new_kb = KnowledgeBase(
            id=kb_id,
            name=req.name,
            usage_guideline=req.usage_guideline,
            org_id=req.org_id,
            group_id=req.group_id,
            is_shared_to_groups=req.is_shared_to_groups,
            vector_collection_name=collection_name
        )
        db.add(new_kb)
        await db.commit()
        
        return {"status": "success", "kb_id": kb_id, "chunk_count": len(chunks)}

    except Exception as e:
        # 如果中途报错（比如 MySQL 连不上），静默清理刚才建的向量表
        try:
            await qdrant_client.delete_collection(collection_name=collection_name)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")

from sqlalchemy.future import select # 确保顶部引入了 select


# 1. 定义追加知识的前端请求结构
class AppendKBRequest(BaseModel):
    kb_id: str        # 目标知识库的 ID
    raw_text: str     # 需要追加的新知识文本

# 2. 追加知识的路由接口
@router.post("/api/kb/append")
async def append_knowledge(
    request: Request,
    req: AppendKBRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    try:
        logger.info(f"need to append_knowledge {req}")
        # 第一步：去 MySQL 里查一下，这个 kb_id 存不存在？它的 collection_name 是什么？
        result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == req.kb_id))
        kb = result.scalar_one_or_none()

        if not kb:
            raise HTTPException(status_code=404, detail="找不到指定的知识库")
        assert_same_org(user, kb.org_id)

        # 第二步：对追加进来的新文本进行切片
        chunks = await chunk_text(req.raw_text)
        if not chunks:
            raise HTTPException(status_code=400, detail="追加的文本内容为空或无法提取")
        main_settings = request.app.state.main_settings
        llm_client = AsyncOpenAI(
            api_key=main_settings.LLM_API_KEY,
            base_url=main_settings.LLM_BASE_URL
        )    
        # 第三步：获取新文本的向量 (Embedding)
        embeddings = await get_embeddings(llm_client, chunks)
        
        # 第四步：组装成新的数据点 (Points)，并打上时间戳
        points = []
        current_time = datetime.utcnow().isoformat()
        
        for chunk, emb in zip(chunks, embeddings):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),  # 💡 关键：每次追加都生成全新的 UUID
                    vector=emb,
                    payload={
                        "text": chunk, 
                        "source_kb": req.kb_id,
                        "added_at": current_time, # 记录这是什么时候追加的
                        "type": "append"          # 标记数据类型，方便以后做管理
                    }
                )
            )
            
        # 第五步：往已经存在的 Collection 中强行插入 (Upsert)
        await qdrant_client.upsert(
            collection_name=kb.vector_collection_name, # 直接使用 MySQL 里记录的集合名
            points=points
        )
        
        return {
            "status": "success", 
            "message": f"成功向知识库 [{kb.name}] 追加了 {len(chunks)} 条记忆切片",
            "added_chunk_count": len(chunks)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"追加知识失败: {str(e)}")

# ========================================================
# 3. 替换知识库 (Replace) 🆕 完整新增区块
# ========================================================
class ReplaceKBRequest(BaseModel):
    kb_id: str
    new_raw_text: str  # 最新的完整文本

@router.post("/api/kb/replace")
async def replace_knowledge(
    request: Request,
    req: ReplaceKBRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    try:
        logger.info(f"need to replace_knowledge {req.kb_id}")
        # 第一步：查 MySQL 获取 collection_name
        result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == req.kb_id))
        kb = result.scalar_one_or_none()

        if not kb:
            raise HTTPException(status_code=404, detail="找不到指定的知识库")
        assert_same_org(user, kb.org_id)

        # 第二步：对新的文本进行切片与向量化
        chunks = await chunk_text(req.new_raw_text)
        if not chunks:
            raise HTTPException(status_code=400, detail="替换的文本内容为空")
            
        main_settings = request.app.state.main_settings
        llm_client = AsyncOpenAI(
            api_key=main_settings.LLM_API_KEY,
            base_url=main_settings.LLM_BASE_URL
        )    
        
        embeddings = await get_embeddings(llm_client, chunks)

        # 🚨 第三步 (核心)：去 Qdrant 里精准删除该 kb_id 下的所有老切片
        await qdrant_client.delete(
            collection_name=kb.vector_collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_kb", 
                        match=MatchValue(value=req.kb_id) # 匹配当初入库时埋下的 payload 标签
                    )
                ]
            )
        )
        
        # 第四步：打上最新的时间戳，重新插入数据点
        points = []
        current_time = datetime.now(timezone.utc).isoformat()
        
        for chunk, emb in zip(chunks, embeddings):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()), 
                    vector=emb,
                    payload={
                        "text": chunk, 
                        "source_kb": req.kb_id, 
                        "added_at": current_time, # 🆕 更新为最新的时间戳
                        "type": "replace" 
                    } 
                )
            )
            
        await qdrant_client.upsert(
            collection_name=kb.vector_collection_name,
            points=points
        )
        
        return {
            "status": "success", 
            "message": f"成功清空老数据，并为 [{kb.name}] 替换了 {len(chunks)} 条最新知识切片",
            "new_chunk_count": len(chunks)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"替换知识失败: {str(e)}")
        
# 1. 定义前端传过来的挂载请求参数
class MountKBRequest(BaseModel):
    activity_id: str        # 目标活动的 ID
    kb_id: str              # 知识库的 ID
    priority: int = 0       # 挂载优先级（数字越大越优先）
    mount_guideline: str = None  # 🔥 杀手锏：活动专属的特殊指引

# 2. 挂载接口逻辑
@router.post("/api/kb/mount")
async def mount_knowledge_base(
    req: MountKBRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    try:
        # 第一步：严谨起见，先校验活动和知识库存不存在 (可选，但推荐)
        kb_res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == req.kb_id))
        kb_obj = kb_res.scalar_one_or_none()
        if not kb_obj:
            raise HTTPException(status_code=404, detail="找不到该知识库")
        assert_same_org(user, kb_obj.org_id)

        act_res = await db.execute(select(Activity).where(Activity.id == req.activity_id))
        act_obj = act_res.scalar_one_or_none()
        if not act_obj:
            raise HTTPException(status_code=404, detail="找不到该活动")
        assert_same_org(user, act_obj.org_id)

        # 第二步：查询是否已经挂载过了？
        mount_stmt = select(ActivityKBMount).where(
            ActivityKBMount.activity_id == req.activity_id,
            ActivityKBMount.kb_id == req.kb_id
        )
        mount_res = await db.execute(mount_stmt)
        existing_mount = mount_res.scalar_one_or_none()

        # 第三步：存在则更新 (Upsert)，不存在则新建
        if existing_mount:
            existing_mount.priority = req.priority
            existing_mount.mount_guideline = req.mount_guideline
            action_msg = "更新挂载配置成功"
        else:
            new_mount = ActivityKBMount(
                activity_id=req.activity_id,
                kb_id=req.kb_id,
                priority=req.priority,
                mount_guideline=req.mount_guideline
            )
            db.add(new_mount)
            action_msg = "挂载知识库成功"

        await db.commit() # 正式落库
        
        return {
            "status": "success", 
            "message": action_msg,
            "data": {
                "activity_id": req.activity_id,
                "kb_id": req.kb_id
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"挂载失败: {str(e)}")
        