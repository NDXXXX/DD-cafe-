from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.rag.store import QdrantRagIndex


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()


def get_rag_index(request: Request) -> QdrantRagIndex:
    return request.app.state.rag_index
