# router_auth.py — 登录 / 当前用户
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from deps import (
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    verify_password,
)
from models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    role: str
    org_id: Optional[str] = None
    group_id: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/login", response_model=LoginOut)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(User).where(User.email == form.username))
    user = res.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")

    user.last_login_at = datetime.utcnow()
    await db.commit()

    token = create_access_token(sub=user.id, extra={"role": user.role})
    return LoginOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


# 平台超管首次部署可调用 /api/auth/bootstrap?secret=xxx 重置 root 密码
class BootstrapIn(BaseModel):
    secret: str
    email: str = "admin@local"
    password: str = "admin123"
    display_name: str = "平台超管"


@router.post("/bootstrap", response_model=UserOut)
async def bootstrap_root(payload: BootstrapIn, db: AsyncSession = Depends(get_db)):
    """
    临时引导接口:用 .env 中的 JWT_SECRET 作为校验,确保安全。
    用于初始化或重置平台超管密码 (admin@local / admin123)。
    """
    from config import settings

    if payload.secret != settings.JWT_SECRET:
        raise HTTPException(status_code=403, detail="bootstrap secret 错误")

    res = await db.execute(select(User).where(User.email == payload.email))
    user = res.scalar_one_or_none()
    if user:
        user.password_hash = hash_password(payload.password)
        user.is_active = True
        user.role = "platform_admin"
    else:
        user = User(
            id=f"usr_{uuid.uuid4().hex[:10]}",
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
            role="platform_admin",
        )
        db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)
