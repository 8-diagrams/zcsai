# router_material.py
# 素材库 CRUD: 镜像 router_kb 的鉴权 + 多租户/共享语义(参考 UtilRAG 的可见性查询)。
# 媒体类素材的 media_url 可先经 /api/uploads 拿到; text 类直接存 text_content。
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from deps import get_db, get_current_user, require_min_role, assert_same_org
from models import Material, User

router = APIRouter()

ALLOWED_KINDS = {"image", "video", "text"}


class MaterialIn(BaseModel):
    group_id: Optional[str] = None
    is_shared_to_groups: bool = False
    activity_id: Optional[str] = None
    kind: str                       # image/video/text
    title: str
    description: Optional[str] = None
    media_url: Optional[str] = None
    text_content: Optional[str] = None


class MaterialPatchIn(BaseModel):
    group_id: Optional[str] = None
    is_shared_to_groups: Optional[bool] = None
    activity_id: Optional[str] = None
    kind: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    media_url: Optional[str] = None
    text_content: Optional[str] = None


class MaterialOut(BaseModel):
    id: str
    org_id: str
    group_id: Optional[str] = None
    is_shared_to_groups: bool
    activity_id: Optional[str] = None
    kind: str
    title: str
    description: Optional[str] = None
    media_url: Optional[str] = None
    text_content: Optional[str] = None

    class Config:
        from_attributes = True


def _validate_payload(kind: str, media_url: Optional[str], text_content: Optional[str]):
    if kind not in ALLOWED_KINDS:
        raise HTTPException(400, f"非法 kind={kind!r}, 仅支持 {sorted(ALLOWED_KINDS)}")
    if kind in ("image", "video") and not (media_url or "").strip():
        raise HTTPException(400, f"kind={kind} 必须提供 media_url")
    if kind == "text" and not (text_content or "").strip():
        raise HTTPException(400, "kind=text 必须提供 text_content")


@router.post("/api/orgs/{org_id}/materials", response_model=MaterialOut)
async def create_material(
    org_id: str,
    body: MaterialIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    assert_same_org(user, org_id)
    _validate_payload(body.kind, body.media_url, body.text_content)
    # group_admin 创建时若未指定 group_id, 落到自己组
    group_id = body.group_id if body.group_id is not None else user.group_id
    mat = Material(
        id=f"mat_{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        group_id=group_id,
        is_shared_to_groups=body.is_shared_to_groups,
        activity_id=body.activity_id,
        kind=body.kind,
        title=body.title,
        description=body.description,
        media_url=body.media_url,
        text_content=body.text_content,
    )
    db.add(mat)
    await db.commit()
    await db.refresh(mat)
    logger.info(f"[material] created {mat.id} org={org_id} kind={mat.kind} by={user.id}")
    return mat


@router.get("/api/orgs/{org_id}/materials", response_model=List[MaterialOut])
async def list_materials(
    org_id: str,
    activity_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """可见性镜像 UtilRAG: 本组 OR (同 org 且 is_shared_to_groups=True)。
    org_admin+ 看全 org; group_admin/agent 受组隔离。"""
    assert_same_org(user, org_id)
    stmt = select(Material).where(Material.org_id == org_id)

    # 组隔离: 仅 group 受限角色才加可见性过滤
    if user.role in ("group_admin", "agent") and user.group_id:
        stmt = stmt.where(
            or_(
                Material.group_id == user.group_id,
                Material.is_shared_to_groups.is_(True),
            )
        )
    if activity_id is not None:
        # activity_id 指定时: 该 activity 专属 OR org 级通用(activity_id IS NULL)
        stmt = stmt.where(
            or_(Material.activity_id == activity_id, Material.activity_id.is_(None))
        )
    if kind is not None:
        stmt = stmt.where(Material.kind == kind)
    res = await db.execute(stmt)
    return res.scalars().all()


async def _load_material_or_403(mid: str, db: AsyncSession, user: User) -> Material:
    res = await db.execute(select(Material).where(Material.id == mid))
    mat = res.scalar_one_or_none()
    if not mat:
        raise HTTPException(404, "素材不存在")
    assert_same_org(user, mat.org_id)
    return mat


@router.patch("/api/materials/{mid}", response_model=MaterialOut)
async def update_material(
    mid: str,
    body: MaterialPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    mat = await _load_material_or_403(mid, db, user)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(mat, k, v)
    # 改完做一致性校验
    _validate_payload(mat.kind, mat.media_url, mat.text_content)
    await db.commit()
    await db.refresh(mat)
    return mat


@router.delete("/api/materials/{mid}")
async def delete_material(
    mid: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_min_role("group_admin")),
):
    mat = await _load_material_or_403(mid, db, user)
    await db.delete(mat)
    await db.commit()
    return {"status": "ok"}
