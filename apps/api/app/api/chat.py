import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.agents.graph import AgentRuntime

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=80)
    table_number: str = Field(min_length=1, max_length=32)
    request_id: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


def encode_sse(event: dict) -> str:
    event_type = str(event.get("type", "message"))
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


@router.post("/stream", response_class=StreamingResponse)
async def stream_chat(body: ChatRequest, request: Request) -> StreamingResponse:
    runtime: AgentRuntime = request.app.state.agent_runtime

    async def event_stream():
        try:
            async for event in runtime.stream(
                session_id=body.session_id,
                table_number=body.table_number,
                request_id=body.request_id,
                message=body.message,
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
