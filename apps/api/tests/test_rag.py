from collections.abc import Iterable, Sequence

import pytest
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocumentModel
from app.rag.schemas import IndexedChunk, KnowledgeCreate, KnowledgeUpdate
from app.rag.service import KnowledgeService
from app.rag.store import QdrantRagIndex


class RecordingIndex:
    def __init__(self) -> None:
        self.replaced: list[tuple[str, list[IndexedChunk]]] = []
        self.deleted: list[str] = []
        self.rebuilt: list[IndexedChunk] = []

    def replace_document(
        self,
        document_id: str,
        chunks: Sequence[IndexedChunk],
    ) -> None:
        self.replaced.append((document_id, list(chunks)))

    def delete(self, document_id: str) -> None:
        self.deleted.append(document_id)

    def search(self, query: str, limit: int = 5):
        return []

    def rebuild(self, chunks: Iterable[IndexedChunk]) -> None:
        self.rebuilt = list(chunks)


class FailingIndex(RecordingIndex):
    def replace_document(
        self,
        document_id: str,
        chunks: Sequence[IndexedChunk],
    ) -> None:
        del document_id, chunks
        raise RuntimeError("qdrant unavailable")


class FakeDenseEncoder:
    dimension = 2

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [1.0, 0.0] if "纸巾" in text else [0.0, 1.0]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def encode_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeReranker:
    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        return [1.0 if query[:2] in document else 0.0 for document in documents]


def indexed_chunk(
    chunk_id: str,
    document_id: str,
    title: str,
    content: str,
) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_index=0,
        title=title,
        content=content,
        source_type="guide",
    )


def test_knowledge_crud_chunks_content_and_skips_unchanged_updates(session: Session) -> None:
    index = RecordingIndex()
    service = KnowledgeService(session, index)
    long_content = "纸巾在桌下收纳篮。" * 80

    created = service.create(
        KnowledgeCreate(title="纸巾位置", content=long_content, source_type="guide")
    )
    unchanged = service.update(created.id, KnowledgeUpdate(content=long_content))
    updated = service.update(created.id, KnowledgeUpdate(content="纸巾在吧台右侧"))
    service.delete(created.id)

    assert created.index_status == "ready"
    assert len(created.content_sha256) == 64
    assert len(index.replaced[0][1]) > 1
    assert len({chunk.chunk_id for chunk in index.replaced[0][1]}) == len(
        index.replaced[0][1]
    )
    assert unchanged.version == 1
    assert updated.version == 2
    assert len(index.replaced) == 2
    assert index.deleted == [created.id]
    assert service.list_all() == []


def test_failed_indexing_is_recorded_for_retry(session: Session) -> None:
    service = KnowledgeService(session, FailingIndex())

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        service.create(
            KnowledgeCreate(title="纸巾位置", content="纸巾在桌下", source_type="guide")
        )

    document = session.query(KnowledgeDocumentModel).one()
    assert document.index_status == "failed"
    assert "qdrant unavailable" in (document.index_error or "")


def test_qdrant_bm25_rrf_and_rerank_prefer_relevant_chunk() -> None:
    index = QdrantRagIndex(
        client=QdrantClient(":memory:"),
        collection_name="test-knowledge",
        dense_encoder=FakeDenseEncoder(),
        reranker=FakeReranker(),
    )
    index.replace_document(
        "tissues",
        [indexed_chunk("tissues:0", "tissues", "纸巾位置", "纸巾在桌下收纳篮里")],
    )
    index.replace_document(
        "wifi",
        [indexed_chunk("wifi:0", "wifi", "无线网络", "无线网络名称是 DD-Guest")],
    )

    results = index.search("纸巾在哪", limit=2)

    assert results[0].chunk_id == "tissues:0"
    assert results[0].document_id == "tissues"
    assert results[0].title == "纸巾位置"
    assert results[0].evidence == "纸巾在桌下收纳篮里"


def test_rrf_uses_chunk_id_and_does_not_collapse_duplicate_content() -> None:
    index = QdrantRagIndex(
        client=QdrantClient(":memory:"),
        collection_name="duplicate-content",
        dense_encoder=FakeDenseEncoder(),
        reranker=FakeReranker(),
    )
    content = "纸巾在桌下"
    index.replace_document(
        "source-a",
        [indexed_chunk("source-a:0", "source-a", "A", content)],
    )
    index.replace_document(
        "source-b",
        [indexed_chunk("source-b:0", "source-b", "B", content)],
    )

    results = index.search("纸巾", limit=5)

    assert {result.chunk_id for result in results} == {"source-a:0", "source-b:0"}
