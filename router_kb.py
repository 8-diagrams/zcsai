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

from models import ActivityKBMount, KnowledgeBase, Activity
from sqlalchemy.future import select

router = APIRouter()

# 💡 魔法就在这里：path="./qdrant_data" 会在你的项目里建一个文件夹存向量！
# 就像 SQLite 的 .db 文件一样，不需要独立安装任何数据库软件。
from glbclient import qdrant_client



 # 请替换成你的 Key


class CreateKBRequest(BaseModel):
    name: str
    org_id: str
    group_id: str = None
    usage_guideline: str = None
    raw_text: str  # 粘贴进来的产品手册纯文本

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

@router.post("/api/kb/create")
async def create_knowledge_base(request: Request, req: CreateKBRequest, db: AsyncSession = Depends(get_db)):
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
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={"text": chunk, "source_kb": kb_id} # 把原文当做 payload 存进去
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
from datetime import datetime

# 1. 定义追加知识的前端请求结构
class AppendKBRequest(BaseModel):
    kb_id: str        # 目标知识库的 ID
    raw_text: str     # 需要追加的新知识文本

# 2. 追加知识的路由接口
@router.post("/api/kb/append")
async def append_knowledge(request: Request, req: AppendKBRequest, db: AsyncSession = Depends(get_db)):
    try:
        logger.info(f"need to append_knowledge {req}")
        # 第一步：去 MySQL 里查一下，这个 kb_id 存不存在？它的 collection_name 是什么？
        result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == req.kb_id))
        kb = result.scalar_one_or_none()
        
        if not kb:
            raise HTTPException(status_code=404, detail="找不到指定的知识库")

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

# 1. 定义前端传过来的挂载请求参数
class MountKBRequest(BaseModel):
    activity_id: str        # 目标活动的 ID
    kb_id: str              # 知识库的 ID
    priority: int = 0       # 挂载优先级（数字越大越优先）
    mount_guideline: str = None  # 🔥 杀手锏：活动专属的特殊指引

# 2. 挂载接口逻辑
@router.post("/api/kb/mount")
async def mount_knowledge_base(req: MountKBRequest, db: AsyncSession = Depends(get_db)):
    try:
        # 第一步：严谨起见，先校验活动和知识库存不存在 (可选，但推荐)
        kb_res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == req.kb_id))
        if not kb_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="找不到该知识库")
            
        act_res = await db.execute(select(Activity).where(Activity.id == req.activity_id))
        if not act_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="找不到该活动")

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
        