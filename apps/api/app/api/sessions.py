from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.sessions.service import SessionService

router = APIRouter(prefix="/api", tags=["sessions"])
SessionDep = Annotated[Session, Depends(get_session)]


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=80)


class SessionView(BaseModel):
    session_id: str
    token: str


@router.post("/sessions", response_model=SessionView)
def create_session(body: SessionCreateRequest, session: SessionDep) -> SessionView:
    token = SessionService(session).get_or_create_token(body.session_id)
    return SessionView(session_id=body.session_id, token=token)
