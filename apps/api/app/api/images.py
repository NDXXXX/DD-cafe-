import asyncio
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.api.dependencies import verify_session_token
from app.util.paths import safe_path

router = APIRouter(prefix="/api/images", tags=["images"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_CLEANUP_TTL_SECONDS = 24 * 60 * 60  # 24 hours
_CLEANUP_INTERVAL_SECONDS = 60 * 60  # run cleanup at most once per hour
_last_cleanup = 0.0


def _cleanup_old_uploads(upload_dir: Path) -> None:
    """Delete uploaded images older than 24 hours."""
    now = time.time()
    if not upload_dir.is_dir():
        return
    for session_dir in upload_dir.iterdir():
        if not session_dir.is_dir():
            continue
        for img_file in session_dir.iterdir():
            if img_file.is_file() and (now - img_file.stat().st_mtime) > _CLEANUP_TTL_SECONDS:
                img_file.unlink(missing_ok=True)
        # Remove empty session directories
        if not any(session_dir.iterdir()):
            session_dir.rmdir()


async def _maybe_cleanup(upload_dir: Path) -> None:
    """Run cleanup at most once per hour, off the event loop."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup = now
    await asyncio.to_thread(_cleanup_old_uploads, upload_dir)


class ImageUploadResponse(BaseModel):
    image_id: str = Field(description="UUID for this upload")
    url: str = Field(description="Relative URL to fetch the image")


@router.post("/upload", response_model=ImageUploadResponse)
async def upload_image(
    file: UploadFile,
    session_id: str = Form(min_length=1, max_length=80),
    request: Request = None,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    settings = request.app.state.settings
    with request.app.state.database.session_factory() as session:
        verify_session_token(session, session_id, x_session_token)
    if not file.filename:
        return JSONResponse(status_code=400, content={"error": {"message": "文件名为空"}})

    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": f"不支持的文件类型: {ext}"}},
        )

    content = bytearray()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > max_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "message": f"文件大小超过 {settings.max_upload_size_mb}MB 限制"
                    }
                },
            )

    image_id = uuid.uuid4().hex
    await _maybe_cleanup(Path(settings.upload_dir).resolve())
    try:
        session_dir = safe_path(settings.upload_dir, session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": {"message": "无效的会话 ID"}})
    session_dir.mkdir(parents=True, exist_ok=True)
    image_path = session_dir / f"{image_id}{ext}"
    image_path.write_bytes(bytes(content))

    url = f"/api/images/{session_id}/{image_id}{ext}"
    return JSONResponse(
        content=ImageUploadResponse(image_id=image_id, url=url).model_dump()
    )


@router.get("/{session_id}/{filename}", response_model=None)
async def serve_image(
    session_id: str,
    filename: str,
    request: Request = None,
):
    settings = request.app.state.settings
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return JSONResponse(status_code=404, content={"error": {"message": "文件不存在"}})
    try:
        file_path = safe_path(settings.upload_dir, session_id, filename)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": {"message": "文件不存在"}})
    if not file_path.is_file():
        return JSONResponse(status_code=404, content={"error": {"message": "文件不存在"}})
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)
