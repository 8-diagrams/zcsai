# router_admin.py — SaaS 管理后台的全部 CRUD 接口 + RBAC
import copy
import json
import uuid
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from qdrant_client.models import Distance, PointStruct, VectorParams

from deps import (
    assert_same_group,
    assert_same_org,
    get_current_user,
    get_db,
    hash_password,
    require_min_role,
    require_roles,
)
from models import (
    Activity,
    ActivityEventRule,
    ActivityKBMount,
    AgentNotification,
    Employee,
    Group,
    KnowledgeBase,
    Material,
    Message,
    Organization,
    Referrer,
    SessionRecord,
    SessionRuleFire,
    User,
)
import RuleEngine
from router_auth import UserOut
from glbclient import qdrant_client
from UtilVector import chunk_text, get_embeddings

router = APIRouter(prefix="/api", tags=["admin"])


# =============================================================
# 辅助函数
# =============================================================
def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _json_clone(value):
    return copy.deepcopy(value)


async def _reinsert_qdrant_kb_records(
    source_collection: str,
    target_collection: str,
    *,
    source_kb_id: str,
    target_kb_id: str,
) -> int:
    """Reinsert KB vector records into a fresh isolated collection."""
    logger.info(
        "KB_SHARE_COPY start source_kb={} target_kb={} source_collection={} target_collection={}",
        source_kb_id,
        target_kb_id,
        source_collection,
        target_collection,
    )

    def _vector_size(vector) -> Optional[int]:
        if isinstance(vector, dict):
            for value in vector.values():
                size = _vector_size(value)
                if size:
                    return size
            return None
        if isinstance(vector, list):
            return len(vector)
        return None

    def _vectors_config_from_point_vector(vector):
        if isinstance(vector, dict):
            return {
                name: VectorParams(size=_vector_size(value) or 1536, distance=Distance.COSINE)
                for name, value in vector.items()
            }
        return VectorParams(size=_vector_size(vector) or 1536, distance=Distance.COSINE)

    copied = 0
    offset = None
    collection_created = False
    try:
        while True:
            points, offset = await qdrant_client.scroll(
                collection_name=source_collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not collection_created:
                first_vector = next((point.vector for point in points if point.vector is not None), None)
                vectors_config = _vectors_config_from_point_vector(first_vector)
                await qdrant_client.create_collection(
                    collection_name=target_collection,
                    vectors_config=vectors_config,
                )
                collection_created = True
                logger.info(
                    "KB_SHARE_COPY target collection created source_collection={} target_collection={} vector_size={}",
                    source_collection,
                    target_collection,
                    _vector_size(first_vector) or 1536,
                )

            if points:
                point_structs = []
                for point in points:
                    if point.vector is None:
                        continue
                    payload = _json_clone(point.payload or {})
                    payload["source_kb"] = target_kb_id
                    point_structs.append(
                        PointStruct(
                            id=str(uuid.uuid4()),
                            vector=point.vector,
                            payload=payload,
                        )
                    )
                if point_structs:
                    await qdrant_client.upsert(
                        collection_name=target_collection,
                        points=point_structs,
                    )
                    copied += len(point_structs)
            if offset is None:
                break
    except Exception:
        logger.exception(
            "KB_SHARE_COPY failed source_kb={} target_kb={} source_collection={} target_collection={} copied={}",
            source_kb_id,
            target_kb_id,
            source_collection,
            target_collection,
            copied,
        )
        if collection_created:
            try:
                await qdrant_client.delete_collection(collection_name=target_collection)
            except Exception:
                logger.exception("KB_SHARE_COPY cleanup failed target_collection={}", target_collection)
        raise

    logger.info(
        "KB_SHARE_COPY done source_kb={} target_kb={} source_collection={} target_collection={} copied={}",
        source_kb_id,
        target_kb_id,
        source_collection,
        target_collection,
        copied,
    )
    return copied


async def _rebuild_qdrant_kb_from_raw_text(
    raw_text: str,
    target_collection: str,
    *,
    target_kb_id: str,
    llm_client: AsyncOpenAI,
) -> int:
    """Build a fresh KB collection from the raw text stored in MySQL."""
    logger.info(
        "KB_SHARE_COPY rebuild_from_raw_text start target_kb={} target_collection={}",
        target_kb_id,
        target_collection,
    )
    collection_created = False
    try:
        chunks = await chunk_text(raw_text)
        if not chunks:
            raise ValueError("知识库原文为空或无法切片")

        embeddings = await get_embeddings(llm_client, chunks)
        vector_size = len(embeddings[0]) if embeddings else 1536
        await qdrant_client.create_collection(
            collection_name=target_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        collection_created = True

        current_time = datetime.utcnow().isoformat()
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "text": chunk,
                    "source_kb": target_kb_id,
                    "added_at": current_time,
                    "type": "share_copy",
                },
            )
            for chunk, emb in zip(chunks, embeddings)
        ]
        if points:
            await qdrant_client.upsert(collection_name=target_collection, points=points)

        logger.info(
            "KB_SHARE_COPY rebuild_from_raw_text done target_kb={} target_collection={} copied={}",
            target_kb_id,
            target_collection,
            len(points),
        )
        return len(points)
    except Exception:
        logger.exception(
            "KB_SHARE_COPY rebuild_from_raw_text failed target_kb={} target_collection={}",
            target_kb_id,
            target_collection,
        )
        if collection_created:
            try:
                await qdrant_client.delete_collection(collection_name=target_collection)
            except Exception:
                logger.exception("KB_SHARE_COPY cleanup failed target_collection={}", target_collection)
        raise


def _remap_rule_actions(actions: list, material_id_map: dict, source_group_id: str, target_group_id: str) -> list:
    def _remap(value, key=None):
        if isinstance(value, dict):
            return {k: _remap(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [_remap(item) for item in value]
        if key == "material_id" and value in material_id_map:
            return material_id_map[value]
        if key == "target_group_id" and value == source_group_id:
            return target_group_id
        return value

    return _remap(_json_clone(actions or []))


def _scope_org(stmt, user: User, model):
    """非平台超管 → 只能看自己 org 的资源。"""
    if user.role != "platform_admin":
        stmt = stmt.where(model.org_id == user.org_id)
    return stmt


# =============================================================
# 1. 代理商 (referrers) — platform_admin Only
# =============================================================
class ReferrerIn(BaseModel):
    name: str
    commission_rate: float = 0.0


class ReferrerOut(BaseModel):
    id: str
    name: str
    commission_rate: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/referrers", response_model=List[ReferrerOut])
async def list_referrers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("platform_admin")),
):
    res = await db.execute(select(Referrer).order_by(desc(Referrer.created_at)))
    return res.scalars().all()


@router.post("/referrers", response_model=ReferrerOut)
async def create_referrer(
    body: ReferrerIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("platform_admin")),
):
    obj = Referrer(id=_gen_id("ref"), name=body.name, commission_rate=body.commission_rate)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/referrers/{rid}", response_model=ReferrerOut)
async def update_referrer(
    rid: str,
    body: ReferrerIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("platform_admin")),
):
    res = await db.execute(select(Referrer).where(Referrer.id == rid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "代理商不存在")
    obj.name = body.name
    obj.commission_rate = body.commission_rate
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/referrers/{rid}")
async def delete_referrer(
    rid: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("platform_admin")),
):
    res = await db.execute(select(Referrer).where(Referrer.id == rid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "代理商不存在")
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 2. 公司/租户 (organizations) — platform_admin
# =============================================================
class OrganizationIn(BaseModel):
    name: str
    api_key: Optional[str] = None
    plan_type: str = "free"
    referrer_id: Optional[str] = None


class OrganizationOut(BaseModel):
    id: str
    name: str
    api_key: str
    plan_type: str
    referrer_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/organizations", response_model=List[OrganizationOut])
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Organization).order_by(desc(Organization.created_at))
    if user.role != "platform_admin":
        # 公司管理员/组管理员/坐席只能看自己 org
        if not user.org_id:
            return []
        stmt = stmt.where(Organization.id == user.org_id)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/organizations", response_model=OrganizationOut)
async def create_org(
    body: OrganizationIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("platform_admin")),
):
    obj = Organization(
        id=_gen_id("org"),
        name=body.name,
        api_key=body.api_key or f"sk_{uuid.uuid4().hex}",
        plan_type=body.plan_type,
        referrer_id=body.referrer_id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/organizations/{oid}", response_model=OrganizationOut)
async def update_org(
    oid: str,
    body: OrganizationIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "platform_admin" and user.org_id != oid:
        raise HTTPException(403, "禁止修改其他公司")
    res = await db.execute(select(Organization).where(Organization.id == oid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "公司不存在")
    obj.name = body.name
    if user.role == "platform_admin":
        if body.api_key:
            obj.api_key = body.api_key
        obj.plan_type = body.plan_type
        obj.referrer_id = body.referrer_id
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/organizations/{oid}")
async def delete_org(
    oid: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("platform_admin")),
):
    res = await db.execute(select(Organization).where(Organization.id == oid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "公司不存在")
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 3. 项目组 (groups) — org_admin+
# =============================================================
class GroupIn(BaseModel):
    name: str


class GroupOut(BaseModel):
    id: str
    org_id: str
    name: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/orgs/{org_id}/groups", response_model=List[GroupOut])
async def list_groups(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    stmt = select(Group).where(Group.org_id == org_id).order_by(desc(Group.created_at))
    if user.role in ("group_admin", "agent") and user.group_id:
        stmt = stmt.where(Group.id == user.group_id)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/orgs/{org_id}/groups", response_model=GroupOut)
async def create_group(
    org_id: str,
    body: GroupIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("org_admin")),
):
    assert_same_org(user, org_id)
    obj = Group(id=_gen_id("grp"), org_id=org_id, name=body.name)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/orgs/{org_id}/groups/{gid}", response_model=GroupOut)
async def update_group(
    org_id: str,
    gid: str,
    body: GroupIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("org_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(select(Group).where(Group.id == gid, Group.org_id == org_id))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "组不存在")
    obj.name = body.name
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/orgs/{org_id}/groups/{gid}")
async def delete_group(
    org_id: str,
    gid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("org_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(select(Group).where(Group.id == gid, Group.org_id == org_id))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "组不存在")
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 4. 坐席 (employees) — org_admin / group_admin (限本组)
# =============================================================
class EmployeeIn(BaseModel):
    name: str
    group_id: Optional[str] = None
    is_ai: bool = False
    status: str = "offline"


class EmployeeOut(BaseModel):
    id: str
    org_id: str
    group_id: Optional[str] = None
    name: str
    is_ai: bool
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/orgs/{org_id}/employees", response_model=List[EmployeeOut])
async def list_employees(
    org_id: str,
    group_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    stmt = select(Employee).where(Employee.org_id == org_id).order_by(desc(Employee.created_at))
    if user.role in ("group_admin", "agent") and user.group_id:
        stmt = stmt.where(Employee.group_id == user.group_id)
    elif group_id:
        stmt = stmt.where(Employee.group_id == group_id)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/orgs/{org_id}/employees", response_model=EmployeeOut)
async def create_employee(
    org_id: str,
    body: EmployeeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    if user.role == "group_admin":
        body.group_id = user.group_id
    obj = Employee(
        id=_gen_id("emp"),
        org_id=org_id,
        group_id=body.group_id,
        name=body.name,
        is_ai=body.is_ai,
        status=body.status,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/orgs/{org_id}/employees/{eid}", response_model=EmployeeOut)
async def update_employee(
    org_id: str,
    eid: str,
    body: EmployeeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(Employee).where(Employee.id == eid, Employee.org_id == org_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "坐席不存在")
    assert_same_group(user, obj.group_id)
    obj.name = body.name
    obj.is_ai = body.is_ai
    obj.status = body.status
    if user.role != "group_admin":
        obj.group_id = body.group_id
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/orgs/{org_id}/employees/{eid}")
async def delete_employee(
    org_id: str,
    eid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(Employee).where(Employee.id == eid, Employee.org_id == org_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "坐席不存在")
    assert_same_group(user, obj.group_id)
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 5. 活动剧本 (activities) — org_admin / group_admin
# =============================================================
class ActivityIn(BaseModel):
    name: str
    group_id: str
    welcome_message: Optional[str] = None
    closing_message: Optional[str] = None
    stages_config: Optional[dict] = None  # 阶段名 -> 指引
    global_guideline: Optional[str] = None


class ActivityOut(BaseModel):
    id: str
    org_id: str
    group_id: str
    name: str
    welcome_message: Optional[str] = None
    closing_message: Optional[str] = None
    stages_config: Optional[dict] = None
    global_guideline: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_obj(cls, a: Activity) -> "ActivityOut":
        try:
            stages = json.loads(a.stages_config) if a.stages_config else None
        except Exception:
            stages = None
        return cls(
            id=a.id,
            org_id=a.org_id,
            group_id=a.group_id,
            name=a.name,
            welcome_message=a.welcome_message,
            closing_message=a.closing_message,
            stages_config=stages,
            global_guideline=a.global_guideline,
            created_at=a.created_at,
        )


class ActivityDetailMaterialOut(BaseModel):
    id: str
    group_id: Optional[str] = None
    is_shared_to_groups: bool
    activity_id: Optional[str] = None
    kind: str
    title: str
    description: Optional[str] = None
    media_url: Optional[str] = None
    text_content: Optional[str] = None
    dependency_reason: str


class ActivityDetailKBOut(BaseModel):
    kb_id: str
    kb_name: Optional[str] = None
    usage_guideline: Optional[str] = None
    vector_collection_name: Optional[str] = None
    raw_text_available: bool = False
    raw_text_chars: int = 0
    priority: int
    mount_guideline: Optional[str] = None
    group_id: Optional[str] = None
    is_shared_to_groups: bool = False


class ActivityDetailRuleOut(BaseModel):
    id: str
    name: str
    activity_id: Optional[str] = None
    scope: str
    priority: int
    is_active: bool
    phase: str
    conditions: dict
    actions: List[dict]
    fire_policy: str
    short_circuit: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActivityDetailSummaryOut(BaseModel):
    stages: int
    materials: int
    kbs: int
    activity_rules: int
    global_rules: int


class ActivityDetailOut(BaseModel):
    activity: ActivityOut
    group: Optional[GroupOut] = None
    materials: List[ActivityDetailMaterialOut]
    kb_mounts: List[ActivityDetailKBOut]
    rules: List[ActivityDetailRuleOut]
    summary: ActivityDetailSummaryOut


@router.get("/orgs/{org_id}/activities", response_model=List[ActivityOut])
async def list_activities(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    stmt = select(Activity).where(Activity.org_id == org_id).order_by(desc(Activity.created_at))
    if user.role in ("group_admin", "agent") and user.group_id:
        stmt = stmt.where(Activity.group_id == user.group_id)
    res = await db.execute(stmt)
    return [ActivityOut.from_orm_obj(a) for a in res.scalars().all()]


def _collect_material_ids_from_actions(actions: Any) -> set[str]:
    found: set[str] = set()

    def _walk(value: Any, key: Optional[str] = None):
        if isinstance(value, dict):
            for k, v in value.items():
                _walk(v, k)
            return
        if isinstance(value, list):
            for item in value:
                _walk(item, key)
            return
        if key == "material_id" and isinstance(value, str) and value:
            found.add(value)

    _walk(actions)
    return found


@router.get("/orgs/{org_id}/activities/{aid}/detail", response_model=ActivityDetailOut)
async def get_activity_detail(
    org_id: str,
    aid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    activity_res = await db.execute(select(Activity).where(Activity.id == aid, Activity.org_id == org_id))
    activity = activity_res.scalar_one_or_none()
    if not activity:
        raise HTTPException(404, "活动不存在")
    assert_same_group(user, activity.group_id)

    group_res = await db.execute(select(Group).where(Group.id == activity.group_id, Group.org_id == org_id))
    group = group_res.scalar_one_or_none()

    rules_res = await db.execute(
        select(ActivityEventRule)
        .where(ActivityEventRule.org_id == org_id)
        .where(
            (ActivityEventRule.activity_id == aid)
            | (ActivityEventRule.activity_id.is_(None))
        )
        .order_by(desc(ActivityEventRule.priority), desc(ActivityEventRule.created_at))
    )
    rules = rules_res.scalars().all()

    material_ids = set()
    for rule in rules:
        material_ids.update(_collect_material_ids_from_actions(rule.actions or []))

    material_stmt = select(Material).where(Material.org_id == org_id).where(Material.activity_id == aid)
    if material_ids:
        material_stmt = select(Material).where(Material.org_id == org_id).where(
            or_(Material.activity_id == aid, Material.id.in_(material_ids))
        )
    material_res = await db.execute(material_stmt)
    materials = []
    for mat in material_res.scalars().all():
        reasons = []
        if mat.activity_id == aid:
            reasons.append("activity")
        if mat.id in material_ids:
            reasons.append("rule_action")
        materials.append(
            ActivityDetailMaterialOut(
                id=mat.id,
                group_id=mat.group_id,
                is_shared_to_groups=mat.is_shared_to_groups,
                activity_id=mat.activity_id,
                kind=mat.kind,
                title=mat.title,
                description=mat.description,
                media_url=mat.media_url,
                text_content=mat.text_content,
                dependency_reason=",".join(reasons) or "activity",
            )
        )

    kb_res = await db.execute(
        select(KnowledgeBase, ActivityKBMount)
        .join(ActivityKBMount, KnowledgeBase.id == ActivityKBMount.kb_id)
        .where(ActivityKBMount.activity_id == aid)
        .where(KnowledgeBase.org_id == org_id)
        .order_by(desc(ActivityKBMount.priority))
    )
    kb_mounts = [
        ActivityDetailKBOut(
            kb_id=kb.id,
            kb_name=kb.name,
            usage_guideline=kb.usage_guideline,
            vector_collection_name=kb.vector_collection_name,
            raw_text_available=bool((kb.raw_text or "").strip()),
            raw_text_chars=len(kb.raw_text or ""),
            priority=mount.priority,
            mount_guideline=mount.mount_guideline,
            group_id=kb.group_id,
            is_shared_to_groups=kb.is_shared_to_groups,
        )
        for kb, mount in kb_res.all()
    ]

    activity_rules = [r for r in rules if r.activity_id == aid]
    global_rules = [r for r in rules if r.activity_id is None]
    stages = ActivityOut.from_orm_obj(activity).stages_config or {}
    return ActivityDetailOut(
        activity=ActivityOut.from_orm_obj(activity),
        group=group,
        materials=materials,
        kb_mounts=kb_mounts,
        rules=[
            ActivityDetailRuleOut(
                id=rule.id,
                name=rule.name,
                activity_id=rule.activity_id,
                scope="activity" if rule.activity_id == aid else "global",
                priority=rule.priority,
                is_active=rule.is_active,
                phase=rule.phase,
                conditions=rule.conditions or {},
                actions=rule.actions or [],
                fire_policy=rule.fire_policy,
                short_circuit=rule.short_circuit,
                created_at=rule.created_at,
                updated_at=rule.updated_at,
            )
            for rule in rules
        ],
        summary=ActivityDetailSummaryOut(
            stages=len(stages),
            materials=len(materials),
            kbs=len(kb_mounts),
            activity_rules=len(activity_rules),
            global_rules=len(global_rules),
        ),
    )


@router.post("/orgs/{org_id}/activities", response_model=ActivityOut)
async def create_activity(
    org_id: str,
    body: ActivityIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    assert_same_group(user, body.group_id)
    obj = Activity(
        id=_gen_id("act"),
        org_id=org_id,
        group_id=body.group_id,
        name=body.name,
        welcome_message=body.welcome_message,
        closing_message=body.closing_message,
        stages_config=json.dumps(body.stages_config, ensure_ascii=False) if body.stages_config else None,
        global_guideline=body.global_guideline,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ActivityOut.from_orm_obj(obj)


@router.patch("/orgs/{org_id}/activities/{aid}", response_model=ActivityOut)
async def update_activity(
    org_id: str,
    aid: str,
    body: ActivityIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(Activity).where(Activity.id == aid, Activity.org_id == org_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "活动不存在")
    assert_same_group(user, obj.group_id)
    obj.name = body.name
    obj.welcome_message = body.welcome_message
    obj.closing_message = body.closing_message
    obj.stages_config = json.dumps(body.stages_config, ensure_ascii=False) if body.stages_config else None
    obj.global_guideline = body.global_guideline
    if user.role != "group_admin":
        obj.group_id = body.group_id
    await db.commit()
    await db.refresh(obj)
    return ActivityOut.from_orm_obj(obj)


@router.delete("/orgs/{org_id}/activities/{aid}")
async def delete_activity(
    org_id: str,
    aid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(Activity).where(Activity.id == aid, Activity.org_id == org_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "活动不存在")
    assert_same_group(user, obj.group_id)
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


class ActivityShareCopyIn(BaseModel):
    target_group_id: str
    name: Optional[str] = None


class ActivityShareCopyOut(BaseModel):
    source_activity_id: str
    new_activity: ActivityOut
    copied_materials: int
    copied_kbs: int
    copied_kb_points: int
    skipped_kbs: int = 0
    copied_rules: int
    material_id_map: dict
    kb_id_map: dict
    skipped_kb_ids: list[str] = Field(default_factory=list)
    rule_id_map: dict


@router.post("/orgs/{org_id}/activities/{aid}/share-copy", response_model=ActivityShareCopyOut)
async def share_copy_activity(
    org_id: str,
    aid: str,
    body: ActivityShareCopyIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("org_admin")),
):
    """Copy one activity and its activity-scoped assets into another group.

    The new activity is data-isolated: materials, mounted KB records/Qdrant
    collections, mounts, and activity-specific rules all get new IDs.
    """
    assert_same_org(user, org_id)

    source_res = await db.execute(select(Activity).where(Activity.id == aid, Activity.org_id == org_id))
    source = source_res.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "源活动不存在")

    group_res = await db.execute(select(Group).where(Group.id == body.target_group_id, Group.org_id == org_id))
    target_group = group_res.scalar_one_or_none()
    if not target_group:
        raise HTTPException(404, "目标组不存在或不属于本公司")

    new_collections: list[str] = []
    material_id_map: dict[str, str] = {}
    kb_id_map: dict[str, str] = {}
    rule_id_map: dict[str, str] = {}
    skipped_kb_ids: list[str] = []
    copied_kb_points = 0

    try:
        new_activity = Activity(
            id=_gen_id("act"),
            org_id=org_id,
            group_id=body.target_group_id,
            name=body.name or f"{source.name} 副本",
            welcome_message=source.welcome_message,
            closing_message=source.closing_message,
            stages_config=source.stages_config,
            global_guideline=source.global_guideline,
        )
        db.add(new_activity)

        material_res = await db.execute(
            select(Material).where(Material.org_id == org_id, Material.activity_id == source.id)
        )
        source_materials = material_res.scalars().all()
        for mat in source_materials:
            new_mid = f"mat_{uuid.uuid4().hex[:12]}"
            material_id_map[mat.id] = new_mid
            db.add(Material(
                id=new_mid,
                org_id=org_id,
                group_id=body.target_group_id,
                is_shared_to_groups=False,
                activity_id=new_activity.id,
                kind=mat.kind,
                title=mat.title,
                description=mat.description,
                media_url=mat.media_url,
                text_content=mat.text_content,
            ))

        mounts_res = await db.execute(
            select(KnowledgeBase, ActivityKBMount)
            .join(ActivityKBMount, KnowledgeBase.id == ActivityKBMount.kb_id)
            .where(ActivityKBMount.activity_id == source.id)
            .where(KnowledgeBase.org_id == org_id)
        )
        source_mounts = mounts_res.all()
        main_settings = request.app.state.main_settings
        llm_client = AsyncOpenAI(
            api_key=main_settings.LLM_API_KEY,
            base_url=main_settings.LLM_BASE_URL,
        )
        for kb, mount in source_mounts:
            new_kb_id = f"kb_{uuid.uuid4().hex[:12]}"
            new_collection = f"col_{org_id}_{new_kb_id}"
            try:
                if (kb.raw_text or "").strip():
                    copied_points = await _rebuild_qdrant_kb_from_raw_text(
                        kb.raw_text,
                        new_collection,
                        target_kb_id=new_kb_id,
                        llm_client=llm_client,
                    )
                else:
                    copied_points = await _reinsert_qdrant_kb_records(
                        kb.vector_collection_name,
                        new_collection,
                        source_kb_id=kb.id,
                        target_kb_id=new_kb_id,
                    )
            except Exception:
                logger.exception(
                    "KB_SHARE_COPY skipped source_kb={} source_collection={} target_kb={} target_collection={}",
                    kb.id,
                    kb.vector_collection_name,
                    new_kb_id,
                    new_collection,
                )
                skipped_kb_ids.append(kb.id)
                continue

            kb_id_map[kb.id] = new_kb_id
            db.add(KnowledgeBase(
                id=new_kb_id,
                name=kb.name,
                usage_guideline=kb.usage_guideline,
                raw_text=kb.raw_text,
                org_id=org_id,
                group_id=body.target_group_id,
                is_shared_to_groups=False,
                vector_collection_name=new_collection,
            ))
            db.add(ActivityKBMount(
                activity_id=new_activity.id,
                kb_id=new_kb_id,
                priority=mount.priority,
                mount_guideline=mount.mount_guideline,
            ))
            copied_kb_points += copied_points
            new_collections.append(new_collection)

        rules_res = await db.execute(
            select(ActivityEventRule).where(
                ActivityEventRule.org_id == org_id,
                ActivityEventRule.activity_id == source.id,
            )
        )
        source_rules = rules_res.scalars().all()
        for rule in source_rules:
            new_rule_id = _gen_id("rule")
            rule_id_map[rule.id] = new_rule_id
            db.add(ActivityEventRule(
                id=new_rule_id,
                org_id=org_id,
                activity_id=new_activity.id,
                name=rule.name,
                priority=rule.priority,
                is_active=rule.is_active,
                phase=rule.phase,
                conditions=_json_clone(rule.conditions),
                actions=_remap_rule_actions(
                    rule.actions,
                    material_id_map,
                    source.group_id,
                    body.target_group_id,
                ),
                fire_policy=rule.fire_policy,
                short_circuit=rule.short_circuit,
            ))

        await db.commit()
        await db.refresh(new_activity)
        return ActivityShareCopyOut(
            source_activity_id=source.id,
            new_activity=ActivityOut.from_orm_obj(new_activity),
            copied_materials=len(material_id_map),
            copied_kbs=len(kb_id_map),
            copied_kb_points=copied_kb_points,
            skipped_kbs=len(skipped_kb_ids),
            copied_rules=len(rule_id_map),
            material_id_map=material_id_map,
            kb_id_map=kb_id_map,
            skipped_kb_ids=skipped_kb_ids,
            rule_id_map=rule_id_map,
        )
    except Exception:
        await db.rollback()
        for collection in new_collections:
            try:
                await qdrant_client.delete_collection(collection_name=collection)
            except Exception:
                pass
        raise


# =============================================================
# 6. 知识库列表 (复用 router_kb 写接口;读 + 删 在这里实现)
# =============================================================
class KBOut(BaseModel):
    id: str
    name: str
    usage_guideline: Optional[str] = None
    org_id: str
    group_id: Optional[str] = None
    is_shared_to_groups: bool
    vector_collection_name: str

    class Config:
        from_attributes = True


@router.get("/orgs/{org_id}/kbs", response_model=List[KBOut])
async def list_kbs(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    stmt = select(KnowledgeBase).where(KnowledgeBase.org_id == org_id)
    # 组隔离: group_admin/agent 只能看本组 OR 已共享给全组的库; org_admin+ 看全 org。
    # (与 router_material.list_materials / UtilRAG 的可见性一致)
    if user.role in ("group_admin", "agent") and user.group_id:
        stmt = stmt.where(
            or_(
                KnowledgeBase.group_id == user.group_id,
                KnowledgeBase.is_shared_to_groups.is_(True),
            )
        )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.delete("/kbs/{kb_id}")
async def delete_kb(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("org_admin")),
):
    res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = res.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, "知识库不存在")
    assert_same_org(user, kb.org_id)
    await db.delete(kb)
    await db.commit()
    # 同步删 Qdrant collection
    try:
        from glbclient import qdrant_client
        await qdrant_client.delete_collection(collection_name=kb.vector_collection_name)
    except Exception:
        pass
    return {"status": "ok"}


# 列出某活动已挂载的知识库
class KBMountOut(BaseModel):
    activity_id: str
    kb_id: str
    priority: int
    mount_guideline: Optional[str] = None
    kb_name: Optional[str] = None


@router.get("/activities/{activity_id}/kb-mounts", response_model=List[KBMountOut])
async def list_activity_kb_mounts(
    activity_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 校验 activity 属于自己 org
    a_res = await db.execute(select(Activity).where(Activity.id == activity_id))
    a = a_res.scalar_one_or_none()
    if not a:
        raise HTTPException(404, "活动不存在")
    assert_same_org(user, a.org_id)

    mounts_res = await db.execute(
        select(ActivityKBMount).where(ActivityKBMount.activity_id == activity_id)
    )
    mounts = mounts_res.scalars().all()
    if not mounts:
        return []
    kb_ids = [m.kb_id for m in mounts]
    kb_res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))
    kbs = {k.id: k.name for k in kb_res.scalars().all()}
    return [
        KBMountOut(
            activity_id=m.activity_id,
            kb_id=m.kb_id,
            priority=m.priority,
            mount_guideline=m.mount_guideline,
            kb_name=kbs.get(m.kb_id),
        )
        for m in mounts
    ]


@router.delete("/activities/{activity_id}/kb-mounts/{kb_id}")
async def unmount_kb(
    activity_id: str,
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    a_res = await db.execute(select(Activity).where(Activity.id == activity_id))
    a = a_res.scalar_one_or_none()
    if not a:
        raise HTTPException(404, "活动不存在")
    assert_same_org(user, a.org_id)
    assert_same_group(user, a.group_id)

    res = await db.execute(
        select(ActivityKBMount).where(
            ActivityKBMount.activity_id == activity_id,
            ActivityKBMount.kb_id == kb_id,
        )
    )
    m = res.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "挂载关系不存在")
    await db.delete(m)
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 7. 会话 + 消息 (sessions / messages) — 全部角色按隔离规则
# =============================================================
class SessionOut(BaseModel):
    id: str
    org_id: str
    group_id: Optional[str] = None
    activity_id: Optional[str] = None
    employee_id: Optional[str] = None
    platform_type: Optional[str] = None
    visitor_uid: Optional[str] = None
    visitor_nickname: Optional[str] = None
    visitor_email: Optional[str] = None
    status: Optional[str] = None
    current_stage: Optional[str] = None
    current_emotion: Optional[str] = None
    is_human_takeover: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/orgs/{org_id}/sessions", response_model=List[SessionOut])
async def list_sessions(
    org_id: str,
    group_id: Optional[str] = Query(None),
    activity_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    stmt = select(SessionRecord).where(SessionRecord.org_id == org_id)
    if user.role in ("group_admin", "agent") and user.group_id:
        stmt = stmt.where(SessionRecord.group_id == user.group_id)
    elif group_id:
        stmt = stmt.where(SessionRecord.group_id == group_id)
    if activity_id:
        stmt = stmt.where(SessionRecord.activity_id == activity_id)
    if status:
        stmt = stmt.where(SessionRecord.status == status)
    stmt = stmt.order_by(desc(SessionRecord.created_at)).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


# 坐席专用:我的会话
@router.get("/me/sessions", response_model=List[SessionOut])
async def my_sessions(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.org_id:
        return []
    stmt = select(SessionRecord).where(SessionRecord.org_id == user.org_id)
    if user.role == "agent" and user.employee_id:
        stmt = stmt.where(SessionRecord.employee_id == user.employee_id)
    elif user.group_id:
        stmt = stmt.where(SessionRecord.group_id == user.group_id)
    if status:
        stmt = stmt.where(SessionRecord.status == status)
    stmt = stmt.order_by(desc(SessionRecord.created_at)).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


class MessageOut(BaseModel):
    id: int
    session_id: str
    sender_type: str
    sender_id: Optional[str] = None
    content: str
    content_type: str = "text"
    media_url: Optional[str] = None
    media_caption: Optional[str] = None
    stage_at_send: Optional[str] = None
    emotion_at_send: Optional[str] = None
    visitor_nickname_at_send: Optional[str] = None
    visitor_email_at_send: Optional[str] = None
    visitor_platform_at_send: Optional[str] = None
    visitor_platform_id_at_send: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


async def _load_session_or_403(sid: str, db: AsyncSession, user: User) -> SessionRecord:
    s_res = await db.execute(select(SessionRecord).where(SessionRecord.id == sid))
    sess = s_res.scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "会话不存在")
    assert_same_org(user, sess.org_id)
    if user.role == "agent":
        if user.employee_id and sess.employee_id and sess.employee_id != user.employee_id:
            raise HTTPException(403, "无权访问其他坐席的会话")
    elif user.role == "group_admin" and user.group_id:
        if sess.group_id and sess.group_id != user.group_id:
            raise HTTPException(403, "无权查看其他组会话")
    return sess


@router.get("/sessions/{sid}/messages", response_model=List[MessageOut])
async def session_messages(
    sid: str,
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _load_session_or_403(sid, db, user)
    res = await db.execute(
        select(Message)
        .where(Message.session_id == sid)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return res.scalars().all()


class MessageIn(BaseModel):
    content: str


@router.post("/sessions/{sid}/messages", response_model=MessageOut)
async def send_session_message(
    sid: str,
    body: MessageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sess = await _load_session_or_403(sid, db, user)
    if sess.status and sess.status != "active":
        raise HTTPException(400, "会话已不处于活跃状态,无法发送")
    text = (body.content or "").strip()
    if not text:
        raise HTTPException(400, "消息内容不能为空")
    msg = Message(
        session_id=sid,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="employee",
        sender_id=user.employee_id or user.id,
        content=text,
        stage_at_send=sess.current_stage,
        emotion_at_send=sess.current_emotion,
        visitor_nickname_at_send=sess.visitor_nickname,
        visitor_email_at_send=sess.visitor_email,
        visitor_platform_at_send=sess.platform_type,
        visitor_platform_id_at_send=sess.visitor_uid,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # 坐席发的消息必须下发到访客 WS 窗口 (接管态下没有 LLM 帮忙推送了)。
    # 同时写 Mem0, 与 /agent-reply 行为一致。失败只记日志, 不阻塞 API。
    try:
        from main import manager as visitor_manager
        from memory_service import memory_add
        if sess.visitor_uid and text:
            await memory_add(
                [{"role": "assistant", "content": text}],
                user_id=sess.visitor_uid,
            )
        if sess.activity_id and sess.visitor_uid:
            conn_id = f"{sess.activity_id}_{sess.visitor_uid}"
            ws_msg = {
                "action": "inject_reply",
                "data": {"session_id": sid, "text": text, "simulate_typing": True, "by": "human"},
            }
            from loguru import logger as _lg
            _lg.info(f"📤 [send_session_message] 下发访客 conn_id={conn_id} payload={ws_msg}")
            await visitor_manager.send_to_client(conn_id, ws_msg)
    except Exception:
        from loguru import logger as _lg
        _lg.exception(f"send_session_message 推送/Mem0 失败 sid={sid}")
    return msg


class TransferIn(BaseModel):
    target_employee_id: str


@router.post("/sessions/{sid}/transfer")
async def transfer_session(
    sid: str,
    body: TransferIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    sess = await _load_session_or_403(sid, db, user)
    emp_res = await db.execute(select(Employee).where(Employee.id == body.target_employee_id))
    emp = emp_res.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "目标坐席不存在")
    if emp.org_id != sess.org_id:
        raise HTTPException(403, "目标坐席不属于本公司")
    # 转接 = 转人工接管, 目标必须是真人坐席 (AI 坐席被 takeout 挡板挡住, 转给它会让会话静默)
    if emp.is_ai:
        raise HTTPException(400, "只能转接给真人坐席，不能转给 AI 坐席")
    sess.employee_id = emp.id
    # 转接 = 转给真人接管: 关闭 AI 自动回复, 记录接管人/时间。
    # status 保持 active, 让接收坐席能通过 /agent-reply 正常发消息
    # (transferred 状态会被 agent-reply 的 active 校验挡掉)。
    sess.is_human_takeover = True
    sess.human_takeover_at = datetime.utcnow()
    sess.human_takeover_by = emp.id
    db.add(Message(
        session_id=sid,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="system",
        sender_id=user.id,
        content=f"会话已转接至坐席 {emp.name} ({emp.id})，AI 自动回复已关闭",
    ))
    await db.commit()
    return {"status": "ok"}


@router.post("/sessions/{sid}/close")
async def close_session(
    sid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sess = await _load_session_or_403(sid, db, user)
    if sess.status == "closed":
        return {"status": "ok"}
    sess.status = "closed"
    db.add(Message(
        session_id=sid,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="system",
        sender_id=user.id,
        content="会话已关闭",
    ))
    await db.commit()
    return {"status": "ok"}


class VisitorProfileIn(BaseModel):
    visitor_nickname: Optional[str] = None
    visitor_email: Optional[str] = None


@router.patch("/sessions/{sid}/visitor-profile", response_model=SessionOut)
async def update_visitor_profile(
    sid: str,
    body: VisitorProfileIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新访客 profile(昵称/email),便于后续主动联系访客。

    隔离规则同会话读取:坐席只能改自己的会话,组管理员限本组,org 管理员限本 org。
    仅传入的字段会被更新;传 null/不传则保持原值不变。
    """
    sess = await _load_session_or_403(sid, db, user)
    if body.visitor_nickname is not None:
        sess.visitor_nickname = body.visitor_nickname
    if body.visitor_email is not None:
        sess.visitor_email = body.visitor_email
    await db.commit()
    await db.refresh(sess)
    return sess


# =============================================================
# 8. 用户管理 (users) — platform_admin (全部) / org_admin (本 org)
# =============================================================
class UserIn(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    role: str = Field(..., description="platform_admin | org_admin | group_admin | agent")
    org_id: Optional[str] = None
    group_id: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: bool = True


class UserPatchIn(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    org_id: Optional[str] = None
    group_id: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/users", response_model=List[UserOut])
async def list_users(
    role: Optional[str] = Query(None),
    org_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    stmt = select(User).order_by(desc(User.created_at))
    if user.role == "platform_admin":
        if org_id:
            stmt = stmt.where(User.org_id == org_id)
    elif user.role == "org_admin":
        stmt = stmt.where(User.org_id == user.org_id)
    else:  # group_admin: 只看本组的坐席账号
        stmt = stmt.where(User.org_id == user.org_id).where(User.group_id == user.group_id).where(User.role == "agent")
    if role:
        stmt = stmt.where(User.role == role)
    res = await db.execute(stmt)
    return [UserOut.model_validate(u) for u in res.scalars().all()]


@router.post("/users", response_model=UserOut)
async def create_user(
    body: UserIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    if user.role == "org_admin":
        if body.role == "platform_admin":
            raise HTTPException(403, "公司管理员不能创建平台管理员")
        body.org_id = user.org_id
    elif user.role == "group_admin":
        # 组管理员只能为本组创建坐席(agent)登录账号; 不能建更高角色或跨组/跨公司。
        if body.role != "agent":
            raise HTTPException(403, "组管理员只能创建坐席(agent)账号")
        body.org_id = user.org_id
        body.group_id = user.group_id
        # 若绑定了坐席, 校验该坐席属于本组本公司
        if body.employee_id:
            emp_res = await db.execute(select(Employee).where(Employee.id == body.employee_id))
            emp = emp_res.scalar_one_or_none()
            if not emp:
                raise HTTPException(404, "绑定的坐席不存在")
            if emp.org_id != user.org_id or emp.group_id != user.group_id:
                raise HTTPException(403, "只能绑定本组的坐席")

    # 唯一性校验
    dup = await db.execute(select(User).where(User.email == body.email))
    if dup.scalar_one_or_none():
        raise HTTPException(400, "邮箱已被占用")

    obj = User(
        id=_gen_id("usr"),
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        org_id=body.org_id,
        group_id=body.group_id,
        employee_id=body.employee_id,
        is_active=body.is_active,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return UserOut.model_validate(obj)


@router.patch("/users/{uid}", response_model=UserOut)
async def update_user(
    uid: str,
    body: UserPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    res = await db.execute(select(User).where(User.id == uid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "用户不存在")
    if user.role != "platform_admin" and obj.org_id != user.org_id:
        raise HTTPException(403, "禁止修改其他公司用户")
    if user.role == "org_admin" and body.role == "platform_admin":
        raise HTTPException(403, "无权升为平台超管")
    if user.role == "group_admin":
        # 组管理员只能管理本组的坐席(agent)账号, 且不能改角色/换组
        if obj.role != "agent" or obj.group_id != user.group_id:
            raise HTTPException(403, "组管理员只能管理本组坐席账号")
        if body.role is not None and body.role != "agent":
            raise HTTPException(403, "组管理员不能变更账号角色")
        if body.group_id is not None and body.group_id != user.group_id:
            raise HTTPException(403, "组管理员不能把账号转出本组")

    if body.display_name is not None:
        obj.display_name = body.display_name
    if body.password:
        obj.password_hash = hash_password(body.password)
    if body.role:
        obj.role = body.role
    if body.org_id is not None and user.role == "platform_admin":
        obj.org_id = body.org_id
    if body.group_id is not None:
        obj.group_id = body.group_id
    if body.employee_id is not None:
        obj.employee_id = body.employee_id
    if body.is_active is not None:
        obj.is_active = body.is_active

    await db.commit()
    await db.refresh(obj)
    return UserOut.model_validate(obj)


@router.delete("/users/{uid}")
async def delete_user(
    uid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    res = await db.execute(select(User).where(User.id == uid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "用户不存在")
    if user.role != "platform_admin" and obj.org_id != user.org_id:
        raise HTTPException(403, "禁止删除其他公司用户")
    if user.role == "group_admin" and (obj.role != "agent" or obj.group_id != user.group_id):
        raise HTTPException(403, "组管理员只能删除本组坐席账号")
    if obj.id == user.id:
        raise HTTPException(400, "不能删除自己")
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 9. 汇总统计 (公司看板) — org_admin+ 看自己 org;platform_admin 全部
# =============================================================
class StatsOut(BaseModel):
    organizations: int
    groups: int
    employees: int
    activities: int
    sessions: int
    messages: int


@router.get("/stats/overview", response_model=StatsOut)
async def stats_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    async def _count(model, scope_org: bool = True):
        stmt = select(func.count()).select_from(model)
        if scope_org and user.role != "platform_admin" and user.org_id:
            stmt = stmt.where(model.org_id == user.org_id)
        res = await db.execute(stmt)
        return res.scalar() or 0

    return StatsOut(
        organizations=(await _count(Organization, scope_org=False)) if user.role == "platform_admin" else 1,
        groups=await _count(Group),
        employees=await _count(Employee),
        activities=await _count(Activity),
        sessions=await _count(SessionRecord),
        messages=await _count(Message),
    )


# =============================================================
# 8.1 Dashboard 角色感知汇总 (按 role 自动定范围)
# =============================================================
class DashboardSummaryOut(BaseModel):
    scope: str
    counts: dict
    session_status: dict
    emotion_distribution: dict
    my: dict


EMOTION_KEYS = ["calm", "joy", "excited", "hesitation", "impatience", "anger"]
SESSION_STATUS_KEYS = ["active", "closed", "transferred"]


@router.get("/dashboard/summary", response_model=DashboardSummaryOut)
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard 汇总: 后端按 user.role 决定数据范围, 前端按 scope 渲染对应视图。
    - platform_admin: 全平台
    - org_admin:      本公司
    - group_admin:    本公司 + 会话/坐席按本组收窄
    - agent:          本组概览 + my(我的活跃/接管/未读通知)
    """
    role = user.role
    scope = {"platform_admin": "platform", "org_admin": "org",
             "group_admin": "group", "agent": "agent"}.get(role, "org")

    def _apply_org(stmt, model):
        if role != "platform_admin" and user.org_id:
            stmt = stmt.where(model.org_id == user.org_id)
        return stmt

    def _apply_group(stmt, model):
        # group_admin / agent 在 org 基础上再按本组收窄 (model 须有 group_id)
        if role in ("group_admin", "agent") and user.group_id:
            stmt = stmt.where(model.group_id == user.group_id)
        return stmt

    async def _count(model, *, group_scope: bool = False, extra=None):
        stmt = select(func.count()).select_from(model)
        stmt = _apply_org(stmt, model)
        if group_scope:
            stmt = _apply_group(stmt, model)
        if extra is not None:
            stmt = stmt.where(extra)
        res = await db.execute(stmt)
        return res.scalar() or 0

    # --- 资产/实体计数 ---
    counts = {}
    if role == "platform_admin":
        cnt_stmt = select(func.count()).select_from(Organization)
        counts["organizations"] = (await db.execute(cnt_stmt)).scalar() or 0
    counts["groups"] = await _count(Group)
    counts["employees"] = await _count(Employee, group_scope=True)
    counts["activities"] = await _count(Activity, group_scope=True)
    counts["kbs"] = await _count(KnowledgeBase, group_scope=True)
    counts["materials"] = await _count(Material, group_scope=True)
    counts["sessions_total"] = await _count(SessionRecord, group_scope=True)
    counts["sessions_active"] = await _count(
        SessionRecord, group_scope=True, extra=(SessionRecord.status == "active"))
    counts["sessions_human_takeover"] = await _count(
        SessionRecord, group_scope=True, extra=(SessionRecord.is_human_takeover.is_(True)))

    # --- 会话状态分布 (一次 group_by 查出) ---
    ss_stmt = select(SessionRecord.status, func.count()).select_from(SessionRecord)
    ss_stmt = _apply_group(_apply_org(ss_stmt, SessionRecord), SessionRecord).group_by(SessionRecord.status)
    ss_rows = (await db.execute(ss_stmt)).all()
    ss_map = {str(k): v for k, v in ss_rows}
    session_status = {k: ss_map.get(k, 0) for k in SESSION_STATUS_KEYS}

    # --- 情绪分布 (按 sessions.current_emotion) ---
    em_stmt = select(SessionRecord.current_emotion, func.count()).select_from(SessionRecord)
    em_stmt = _apply_group(_apply_org(em_stmt, SessionRecord), SessionRecord).group_by(SessionRecord.current_emotion)
    em_rows = (await db.execute(em_stmt)).all()
    # current_emotion 是 Python 枚举 SQLEnum, 查出来是 CustomerEmotion 对象,
    # 取 .value 才是 'calm'/'joy' 等; 兼容已是字符串/None 的情况。
    def _ekey(k):
        if k is None:
            return None
        return getattr(k, "value", k)
    em_map = {}
    for k, v in em_rows:
        em_map[_ekey(k)] = em_map.get(_ekey(k), 0) + v
    emotion_distribution = {k: em_map.get(k, 0) for k in EMOTION_KEYS}

    # --- agent 专属: 我的面板 ---
    my = {}
    if role == "agent" and user.employee_id:
        my_active_stmt = select(func.count()).select_from(SessionRecord).where(
            SessionRecord.employee_id == user.employee_id,
            SessionRecord.status == "active",
        )
        my["active_sessions"] = (await db.execute(my_active_stmt)).scalar() or 0
        my_takeover_stmt = select(func.count()).select_from(SessionRecord).where(
            SessionRecord.employee_id == user.employee_id,
            SessionRecord.is_human_takeover.is_(True),
        )
        my["takeover_sessions"] = (await db.execute(my_takeover_stmt)).scalar() or 0
        # 未读通知: 定向给我 OR 同组广播
        from sqlalchemy import or_ as _or
        noti_stmt = select(func.count()).select_from(AgentNotification).where(
            AgentNotification.org_id == user.org_id,
            AgentNotification.is_read.is_(False),
            _or(
                AgentNotification.target_employee_id == user.employee_id,
                AgentNotification.target_employee_id.is_(None),
            ),
        )
        if user.group_id:
            noti_stmt = noti_stmt.where(
                _or(AgentNotification.group_id == user.group_id, AgentNotification.group_id.is_(None))
            )
        my["unread_notifications"] = (await db.execute(noti_stmt)).scalar() or 0

    return DashboardSummaryOut(
        scope=scope,
        counts=counts,
        session_status=session_status,
        emotion_distribution=emotion_distribution,
        my=my,
    )


# =============================================================
# 10. 真人接管 / 释放 / 人工发消息
# =============================================================
class TakeoverIn(BaseModel):
    reason: Optional[str] = None


@router.post("/sessions/{sid}/takeover")
async def takeover_session(
    sid: str,
    body: TakeoverIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """坐席主动接管:之后该 session 跳过 LLM,所有访客消息只入库不回复,等人工通过 /agent-reply 发。"""
    sess = await _load_session_or_403(sid, db, user)
    sess.is_human_takeover = True
    sess.human_takeover_at = datetime.utcnow()
    sess.human_takeover_by = user.employee_id or user.id
    if user.employee_id:
        sess.employee_id = user.employee_id  # 接管者成为本会话当前坐席
    db.add(Message(
        session_id=sid,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="system",
        sender_id=user.id,
        content=f"[系统] {user.display_name or user.id} 已接管会话" + (f": {body.reason}" if body.reason else ""),
    ))
    await db.commit()
    return {"status": "ok", "human_takeover_at": sess.human_takeover_at}


@router.post("/sessions/{sid}/release")
async def release_session(
    sid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """放回 AI 继续接待。"""
    sess = await _load_session_or_403(sid, db, user)
    if not sess.is_human_takeover:
        return {"status": "noop", "msg": "会话未处于人工接管中"}
    sess.is_human_takeover = False
    sess.human_takeover_at = None
    sess.human_takeover_by = None
    db.add(Message(
        session_id=sid,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="system",
        sender_id=user.id,
        content=f"[系统] {user.display_name or user.id} 已释放会话, AI 重新接管",
    ))
    await db.commit()
    return {"status": "ok"}


class AgentReplyIn(BaseModel):
    content: str = ""
    content_type: str = "text"               # text/image/video/link
    media_url: Optional[str] = None
    media_caption: Optional[str] = None
    material_id: Optional[str] = None        # 引用素材库 -> 后端取出填充 content_type/media_url


@router.post("/sessions/{sid}/agent-reply", response_model=MessageOut)
async def agent_reply(
    sid: str,
    body: AgentReplyIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """坐席在接管中发消息: 写 Message + Mem0 + WS push 给访客。支持文本与图片/视频/链接。"""
    sess = await _load_session_or_403(sid, db, user)
    if not sess.is_human_takeover:
        raise HTTPException(400, "会话未处于人工接管中,请先 /takeover")

    content_type = body.content_type or "text"
    media_url = body.media_url
    media_caption = body.media_caption
    text = (body.content or "").strip()

    # 引用素材库: 取出素材填充 content_type/media_url (校验同 org)
    if body.material_id:
        mres = await db.execute(select(Material).where(Material.id == body.material_id))
        mat = mres.scalar_one_or_none()
        if not mat:
            raise HTTPException(404, "素材不存在")
        assert_same_org(user, mat.org_id)
        if mat.kind == "text":
            content_type = "text"
            text = (mat.text_content or "").strip()
        else:
            content_type = mat.kind            # image/video
            media_url = mat.media_url
            media_caption = media_caption or mat.title

    # 校验: 文本类要 content 非空; 媒体类要 media_url 非空
    if content_type == "text":
        if not text:
            raise HTTPException(400, "消息内容不能为空")
    else:
        if not (media_url or "").strip():
            raise HTTPException(400, f"content_type={content_type} 必须提供 media_url")

    msg = Message(
        session_id=sid,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="employee",
        sender_id=user.employee_id or user.id,
        content=text if content_type == "text" else (media_url or ""),
        content_type=content_type,
        media_url=media_url,
        media_caption=media_caption,
        stage_at_send=sess.current_stage,
        emotion_at_send=sess.current_emotion,
        visitor_nickname_at_send=sess.visitor_nickname,
        visitor_email_at_send=sess.visitor_email,
        visitor_platform_at_send=sess.platform_type,
        visitor_platform_id_at_send=sess.visitor_uid,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # 写 Mem0 + WS push 给访客 (异步, 失败不阻塞 API)
    try:
        from main import manager as visitor_manager
        from memory_service import memory_add
        # 仅文本进 Mem0 (媒体 URL 无记忆价值)
        if sess.visitor_uid and content_type == "text" and text:
            await memory_add(
                [{"role": "assistant", "content": text}],
                user_id=sess.visitor_uid,
            )
        if sess.activity_id and sess.visitor_uid:
            conn_id = f"{sess.activity_id}_{sess.visitor_uid}"
            from loguru import logger as _lg
            if content_type == "text":
                ws_msg = {
                    "action": "inject_reply",
                    "data": {"session_id": sid, "text": text, "simulate_typing": True, "by": "human"},
                }
            else:
                from config import to_public_url
                payload = {"session_id": sid, "kind": content_type, "url": to_public_url(media_url), "by": "human"}
                if media_caption:
                    payload["caption"] = media_caption
                ws_msg = {"action": "inject_media", "data": payload}
            _lg.info(f"📤 [agent_reply] 下发访客 conn_id={conn_id} payload={ws_msg}")
            await visitor_manager.send_to_client(conn_id, ws_msg)
    except Exception:
        # 记日志即可,不向调用方暴露
        from loguru import logger as _lg
        _lg.exception(f"agent_reply 推送/Mem0 失败 sid={sid}")
    return msg


# =============================================================
# 11. 规则引擎 CRUD + dry-run + metadata
# =============================================================
class RuleIn(BaseModel):
    activity_id: Optional[str] = None
    name: str
    priority: int = 0
    is_active: bool = True
    phase: str = Field("post_llm", description="pre_llm | post_llm")
    conditions: dict
    actions: List[dict]
    fire_policy: str = "once_per_session"
    short_circuit: bool = False


class RulePatchIn(BaseModel):
    activity_id: Optional[str] = None
    name: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    phase: Optional[str] = None
    conditions: Optional[dict] = None
    actions: Optional[List[dict]] = None
    fire_policy: Optional[str] = None
    short_circuit: Optional[bool] = None


class RuleOut(BaseModel):
    id: str
    org_id: str
    activity_id: Optional[str] = None
    name: str
    priority: int
    is_active: bool
    phase: str
    conditions: dict
    actions: List[dict]
    fire_policy: str
    short_circuit: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/orgs/{org_id}/event-rules", response_model=List[RuleOut])
async def list_event_rules(
    org_id: str,
    activity_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_same_org(user, org_id)
    stmt = select(ActivityEventRule).where(ActivityEventRule.org_id == org_id)
    if activity_id:
        stmt = stmt.where(
            (ActivityEventRule.activity_id == activity_id)
            | (ActivityEventRule.activity_id.is_(None))
        )
    stmt = stmt.order_by(desc(ActivityEventRule.priority), desc(ActivityEventRule.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/orgs/{org_id}/event-rules", response_model=RuleOut)
async def create_event_rule(
    org_id: str,
    body: RuleIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    if body.activity_id:
        # 校验 activity 属于本 org
        a_res = await db.execute(
            select(Activity).where(Activity.id == body.activity_id, Activity.org_id == org_id)
        )
        if not a_res.scalar_one_or_none():
            raise HTTPException(404, "activity_id 不存在或不属于本公司")
    obj = ActivityEventRule(
        id=_gen_id("rule"),
        org_id=org_id,
        activity_id=body.activity_id,
        name=body.name,
        priority=body.priority,
        is_active=body.is_active,
        phase=body.phase,
        conditions=body.conditions,
        actions=body.actions,
        fire_policy=body.fire_policy,
        short_circuit=body.short_circuit,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/orgs/{org_id}/event-rules/{rid}", response_model=RuleOut)
async def update_event_rule(
    org_id: str,
    rid: str,
    body: RulePatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(ActivityEventRule).where(
            ActivityEventRule.id == rid,
            ActivityEventRule.org_id == org_id,
        )
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "规则不存在")
    for f in ("activity_id", "name", "priority", "is_active", "phase",
              "conditions", "actions", "fire_policy", "short_circuit"):
        v = getattr(body, f)
        if v is not None:
            setattr(obj, f, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/orgs/{org_id}/event-rules/{rid}")
async def delete_event_rule(
    org_id: str,
    rid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(ActivityEventRule).where(
            ActivityEventRule.id == rid,
            ActivityEventRule.org_id == org_id,
        )
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "规则不存在")
    await db.delete(obj)
    await db.commit()
    return {"status": "ok"}


class RuleToggleIn(BaseModel):
    is_active: bool


@router.post("/orgs/{org_id}/event-rules/{rid}/toggle")
async def toggle_event_rule(
    org_id: str,
    rid: str,
    body: RuleToggleIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    res = await db.execute(
        select(ActivityEventRule).where(
            ActivityEventRule.id == rid,
            ActivityEventRule.org_id == org_id,
        )
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "规则不存在")
    obj.is_active = body.is_active
    await db.commit()
    return {"status": "ok", "is_active": obj.is_active}


class DryRunIn(BaseModel):
    conditions: dict
    simulated_ctx: dict


@router.post("/orgs/{org_id}/event-rules/dry-run")
async def dry_run_event_rule(
    org_id: str,
    body: DryRunIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """干跑: 把 conditions + 一个手工编辑的 ctx 喂进 RuleEngine.match_rule, 立刻知道是否命中。"""
    assert_same_org(user, org_id)
    matched = RuleEngine.match_rule(body.conditions, body.simulated_ctx)
    return {"matched": matched}


@router.get("/event-rules/metadata")
async def event_rules_metadata(_: User = Depends(get_current_user)):
    """前端节点画布的下拉框元数据。"""
    return RuleEngine.metadata_for_frontend()


# =============================================================
# 12. 员工通知 Inbox
# =============================================================
class NotificationOut(BaseModel):
    id: int
    org_id: str
    group_id: Optional[str] = None
    target_employee_id: Optional[str] = None
    session_id: Optional[str] = None
    rule_id: Optional[str] = None
    level: str
    title: str
    body: Optional[str] = None
    is_read: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/me/notifications", response_model=List[NotificationOut])
async def my_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.org_id:
        return []
    stmt = select(AgentNotification).where(AgentNotification.org_id == user.org_id)
    # 定向到我 or 同组广播
    eid_filter = []
    if user.employee_id:
        eid_filter.append(AgentNotification.target_employee_id == user.employee_id)
    eid_filter.append(AgentNotification.target_employee_id.is_(None))
    if user.group_id:
        from sqlalchemy import or_
        stmt = stmt.where(or_(*eid_filter)).where(
            (AgentNotification.group_id == user.group_id) | (AgentNotification.group_id.is_(None))
        )
    if unread_only:
        stmt = stmt.where(AgentNotification.is_read.is_(False))
    stmt = stmt.order_by(desc(AgentNotification.created_at)).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/notifications/{nid}/read")
async def mark_notification_read(
    nid: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    res = await db.execute(select(AgentNotification).where(AgentNotification.id == nid))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "通知不存在")
    if obj.org_id != user.org_id and user.role != "platform_admin":
        raise HTTPException(403, "禁止操作其他公司通知")
    obj.is_read = True
    await db.commit()
    return {"status": "ok"}


# =============================================================
# 13. 规则触发审计 (后台复盘)
# =============================================================
class RuleFireOut(BaseModel):
    id: int
    session_id: str
    rule_id: str
    fired_at: Optional[datetime] = None
    fired_at_stage: Optional[str] = None
    fired_at_total_turn: Optional[int] = None
    fired_at_stage_turn: Optional[int] = None
    actions_executed: Optional[Any] = None

    class Config:
        from_attributes = True


@router.get("/sessions/{sid}/rule-fires", response_model=List[RuleFireOut])
async def session_rule_fires(
    sid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _load_session_or_403(sid, db, user)
    res = await db.execute(
        select(SessionRuleFire)
        .where(SessionRuleFire.session_id == sid)
        .order_by(desc(SessionRuleFire.fired_at))
    )
    return res.scalars().all()
