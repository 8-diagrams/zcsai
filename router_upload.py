# router_upload.py
# 素材/媒体文件上传基建: 存本地 settings.UPLOAD_DIR, 通过 main.py 的 /media 静态挂载对外访问。
# 写盘用 run_in_threadpool 包同步 IO, 不引入 aiofiles。
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from starlette.concurrency import run_in_threadpool
from loguru import logger

from config import settings
from deps import get_current_user
from models import User

router = APIRouter()

# 扩展名 -> kind 白名单
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTS = {"mp4", "webm"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB 上限, 可后续调


def _kind_for_ext(ext: str) -> str:
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return ""


@router.post("/api/uploads")
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传图片/视频 -> 返回 {url, kind}。url 形如 /media/<uuid>.<ext>, 可直接给前端 <img>/<video> 用。"""
    original = file.filename or ""
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    kind = _kind_for_ext(ext)
    if not kind:
        raise HTTPException(400, f"不支持的文件类型 .{ext}; 仅支持图片({','.join(sorted(IMAGE_EXTS))})/视频({','.join(sorted(VIDEO_EXTS))})")

    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"文件过大, 上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(settings.UPLOAD_DIR, fname)

    def _write():
        with open(fpath, "wb") as f:
            f.write(data)

    await run_in_threadpool(_write)
    url = f"/media/{fname}"
    logger.info(f"[upload] user={user.id} saved {fname} ({len(data)} bytes, kind={kind})")
    return {"url": url, "kind": kind}
