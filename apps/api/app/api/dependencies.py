import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.models import SessionModel
from app.rag.store import QdrantRagIndex

SessionTokenHeader = Annotated[str | None, Header(alias="X-Session-Token")]


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()


def get_rag_index(request: Request) -> QdrantRagIndex:
    return request.app.state.rag_index


def require_admin(
    request: Request,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    configured = request.app.state.settings.admin_api_key
    if configured is None:
        raise HTTPException(status_code=403, detail="管理接口未启用（未配置 ADMIN_API_KEY）")
    if x_admin_key is None or not secrets.compare_digest(
        configured.get_secret_value(), x_admin_key
    ):
        raise HTTPException(status_code=403, detail="管理密钥无效")


def verify_session_token(session: Session, session_id: str, token: str | None) -> None:
    if not token:
        raise HTTPException(status_code=401, detail="缺少会话令牌")
    model = session.get(SessionModel, session_id)
    if model is None or not secrets.compare_digest(model.token, token):
        raise HTTPException(status_code=403, detail="会话令牌无效")
