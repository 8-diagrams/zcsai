# deps.py — 共享依赖: 数据库会话 / JWT 鉴权 / 角色守卫
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import AsyncSessionLocal
from models import User

# --- 密码哈希 (直接用 bcrypt,跳过 passlib —— passlib 1.7.x 与 bcrypt 5.x 不兼容) ---
# bcrypt 最长 72 字节,超出截断
def _norm(p: str) -> bytes:
    return p.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_norm(plain), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_norm(plain), hashed.encode("utf-8"))
    except Exception:
        return False


# --- JWT ---
def create_access_token(sub: str, extra: Optional[dict] = None) -> str:
    payload = {
        "sub": sub,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# --- 通用 DB 会话依赖 ---
async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


# --- 当前用户 ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise cred_exc
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise cred_exc
    except JWTError:
        raise cred_exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise cred_exc
    return user


# --- 角色守卫工厂 ---
ROLE_RANK = {
    "agent": 1,
    "group_admin": 2,
    "org_admin": 3,
    "platform_admin": 4,
}


def require_roles(*roles: str):
    """
    要求当前登录用户角色在 roles 内。
    """
    role_set = set(roles)

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in role_set:
            raise HTTPException(status_code=403, detail=f"角色 {user.role} 无权访问")
        return user

    return _guard


def require_min_role(min_role: str):
    """
    最低角色等级守卫:agent < group_admin < org_admin < platform_admin
    """
    threshold = ROLE_RANK[min_role]

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < threshold:
            raise HTTPException(status_code=403, detail=f"需要至少 {min_role} 权限")
        return user

    return _guard


# --- 租户守卫: 防止 org_admin 越权访问别人的 org ---
def require_same_org(org_id_param: str = "org_id"):
    """
    用法:
        @router.get("/api/orgs/{org_id}/groups",
                    dependencies=[Depends(require_same_org())])
    平台超管(platform_admin)直接放行。
    """

    async def _guard(
        org_id: str = Path(..., alias=org_id_param),
        user: User = Depends(get_current_user),
    ):
        if user.role == "platform_admin":
            return
        if user.org_id != org_id:
            raise HTTPException(status_code=403, detail="禁止访问其他公司数据")

    return _guard


def assert_same_org(user: User, target_org_id: Optional[str]):
    """函数内手动校验:用于 body 里带 org_id 的接口。"""
    if user.role == "platform_admin":
        return
    if target_org_id and user.org_id != target_org_id:
        raise HTTPException(status_code=403, detail="禁止操作其他公司资源")


def assert_same_group(user: User, target_group_id: Optional[str]):
    """组管理员/坐席的组隔离。org_admin+ 不受限制。"""
    if user.role in ("platform_admin", "org_admin"):
        return
    if target_group_id and user.group_id != target_group_id:
        raise HTTPException(status_code=403, detail="禁止操作其他组的资源")
