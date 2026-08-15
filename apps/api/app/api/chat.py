import json
import logging

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.agents.graph import AgentRuntime
from app.agents.state import ImageAttachment
from app.api.dependencies import verify_session_token
from app.util.paths import safe_path

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ImageRef(BaseModel):
    image_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-f0-9]+$")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=80)
    table_number: str = Field(min_length=1, max_length=32)
    request_id: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=0, max_length=2000)
    images: list[ImageRef] = Field(default_factory=list, max_length=3)


def encode_sse(event: dict) -> str:
    event_type = str(event.get("type", "message"))
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


def _resolve_images(
    session_id: str,
    image_refs: list[ImageRef],
    upload_dir: str,
) -> list[ImageAttachment]:
    try:
        session_dir = safe_path(upload_dir, session_id)
    except ValueError:
        return []
    resolved: list[ImageAttachment] = []
    for ref in image_refs:
        candidates = list(session_dir.glob(f"{ref.image_id}.*"))
        if candidates:
            resolved.append(
                ImageAttachment(
                    image_id=ref.image_id,
                    local_path=str(candidates[0]),
                )
            )
    return resolved


@router.post("/stream", response_class=StreamingResponse)
async def stream_chat(
    body: ChatRequest,
    request: Request,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> StreamingResponse:
    with request.app.state.database.session_factory() as session:
        verify_session_token(session, body.session_id, x_session_token)

    runtime: AgentRuntime = request.app.state.agent_runtime
    settings = request.app.state.settings
    images = _resolve_images(body.session_id, body.images, settings.upload_dir)

    if not body.message.strip() and not images:
        async def _empty_stream():
            yield encode_sse(
                {
                    "type": "error",
                    "message": "请输入文字或上传图片。",
                    "request_id": body.request_id,
                }
            )
        return StreamingResponse(
            _empty_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        try:
            async for event in runtime.stream(
                session_id=body.session_id,
                table_number=body.table_number,
                request_id=body.request_id,
                message=body.message,
                images=images,
            ):
                yield encode_sse(event)
        except Exception:
            logger.exception("Chat stream failed", extra={"request_id": body.request_id})
            yield encode_sse(
                {
                    "type": "error",
                    "message": "本次对话处理失败，请稍后重试。",
                    "request_id": body.request_id,
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
