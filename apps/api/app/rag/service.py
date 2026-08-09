from collections.abc import Iterable, Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocumentModel, now_utc
from app.orders.errors import OrderNotFound
from app.rag.ingestion import as_indexed_chunk, build_chunk_models, sha256_text
from app.rag.schemas import (
    IndexedChunk,
    KnowledgeCreate,
    KnowledgeUpdate,
    KnowledgeView,
    RetrievedDocument,
)


class KnowledgeIndex(Protocol):
    def replace_document(
        self,
        document_id: str,
        chunks: Sequence[IndexedChunk],
    ) -> None: ...

    def delete(self, document_id: str) -> None: ...

    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]: ...

    def rebuild(self, chunks: Iterable[IndexedChunk]) -> None: ...


class KnowledgeService:
    def __init__(self, session: Session, index: KnowledgeIndex) -> None:
        self.session = session
        self.index = index

    def list_all(self) -> list[KnowledgeView]:
        statement = select(KnowledgeDocumentModel).order_by(KnowledgeDocumentModel.title)
        return [KnowledgeView.model_validate(document) for document in self.session.scalars(statement)]

    def create(self, body: KnowledgeCreate) -> KnowledgeView:
        document = KnowledgeDocumentModel(
            title=body.title,
            content=body.content,
            source_type=body.source_type,
            version=1,
            content_sha256=sha256_text(body.content),
            index_status="pending",
        )
        self.session.add(document)
        self.session.flush()
        self._sync_chunks(document)
        self.session.commit()
        self.session.refresh(document)
        return self._index_document(document)

    def update(self, document_id: str, body: KnowledgeUpdate) -> KnowledgeView:
        document = self._require(document_id)
        changes = body.model_dump(exclude_none=True)
        if all(getattr(document, field) == value for field, value in changes.items()):
            return KnowledgeView.model_validate(document)
        content_changed = "content" in changes and changes["content"] != document.content
        for field, value in changes.items():
            setattr(document, field, value)
        document.version += 1
        document.content_sha256 = sha256_text(document.content)
        document.index_status = "pending"
        document.index_error = None
        document.indexed_at = None
        if content_changed:
            self._sync_chunks(document)
        self.session.commit()
        self.session.refresh(document)
        return self._index_document(document)

    def delete(self, document_id: str) -> None:
        document = self._require(document_id)
        self.index.delete(document_id)
        self.session.delete(document)
        self.session.commit()

    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]:
        results = self.index.search(query, limit)
        if results:
            return results
        if self.session.scalar(select(KnowledgeDocumentModel.id).limit(1)) is None:
            return []
        self.rebuild()
        return self.index.search(query, limit)

    def rebuild(self) -> int:
        documents = list(self.session.scalars(select(KnowledgeDocumentModel)))
        for document in documents:
            document.content_sha256 = sha256_text(document.content)
            document.index_status = "pending"
            document.index_error = None
            document.indexed_at = None
            self._sync_chunks(document)
        self.session.commit()
        chunks = [
            as_indexed_chunk(document, chunk)
            for document in documents
            for chunk in document.chunks
        ]
        try:
            self.index.rebuild(chunks)
        except Exception as error:
            for document in documents:
                document.index_status = "failed"
                document.index_error = str(error)
            self.session.commit()
            raise
        indexed_at = now_utc()
        for document in documents:
            document.index_status = "ready"
            document.index_error = None
            document.indexed_at = indexed_at
        self.session.commit()
        return len(documents)

    def _index_document(self, document: KnowledgeDocumentModel) -> KnowledgeView:
        chunks = [as_indexed_chunk(document, chunk) for chunk in document.chunks]
        try:
            self.index.replace_document(document.id, chunks)
        except Exception as error:
            document.index_status = "failed"
            document.index_error = str(error)
            document.indexed_at = None
            self.session.commit()
            raise
        document.index_status = "ready"
        document.index_error = None
        document.indexed_at = now_utc()
        self.session.commit()
        self.session.refresh(document)
        return KnowledgeView.model_validate(document)

    def _sync_chunks(self, document: KnowledgeDocumentModel) -> None:
        expected = build_chunk_models(document)
        current_signature = [
            (chunk.id, chunk.chunk_index, chunk.content_sha256) for chunk in document.chunks
        ]
        expected_signature = [
            (chunk.id, chunk.chunk_index, chunk.content_sha256) for chunk in expected
        ]
        if current_signature == expected_signature:
            return
        document.chunks.clear()
        self.session.flush()
        document.chunks.extend(expected)

    def _require(self, document_id: str) -> KnowledgeDocumentModel:
        document = self.session.get(KnowledgeDocumentModel, document_id)
        if document is None:
            raise OrderNotFound("知识条目不存在")
        return document
