from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_rag_index, get_session
from app.rag.schemas import KnowledgeCreate, KnowledgeUpdate, KnowledgeView, RetrievedDocument
from app.rag.service import KnowledgeService
from app.rag.store import QdrantRagIndex

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
SessionDep = Annotated[Session, Depends(get_session)]
IndexDep = Annotated[QdrantRagIndex, Depends(get_rag_index)]


class ReindexResult(BaseModel):
    indexed_count: int


@router.get("", response_model=list[KnowledgeView])
def list_knowledge(session: SessionDep, index: IndexDep) -> list[KnowledgeView]:
    return KnowledgeService(session, index).list_all()


@router.post("", response_model=KnowledgeView, status_code=status.HTTP_201_CREATED)
def create_knowledge(
    body: KnowledgeCreate,
    session: SessionDep,
    index: IndexDep,
) -> KnowledgeView:
    return KnowledgeService(session, index).create(body)


@router.put("/{document_id}", response_model=KnowledgeView)
def update_knowledge(
    document_id: str,
    body: KnowledgeUpdate,
    session: SessionDep,
    index: IndexDep,
) -> KnowledgeView:
    return KnowledgeService(session, index).update(document_id, body)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(
    document_id: str,
    session: SessionDep,
    index: IndexDep,
) -> Response:
    KnowledgeService(session, index).delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search/results", response_model=list[RetrievedDocument])
def search_knowledge(
    session: SessionDep,
    index: IndexDep,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=20),
) -> list[RetrievedDocument]:
    return KnowledgeService(session, index).search(q, limit)


@router.post("/reindex", response_model=ReindexResult)
def reindex_knowledge(session: SessionDep, index: IndexDep) -> ReindexResult:
    count = KnowledgeService(session, index).rebuild()
    return ReindexResult(indexed_count=count)
