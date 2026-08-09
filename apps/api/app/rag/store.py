from collections.abc import Iterable, Sequence
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import jieba
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi

from app.rag.reranker import Reranker
from app.rag.schemas import IndexedChunk, RetrievedDocument

RRF_K = 60
DEFAULT_CANDIDATES = 15


class DenseEncoder(Protocol):
    dimension: int

    def encode_documents(self, texts: list[str]) -> list[list[float]]: ...

    def encode_query(self, text: str) -> list[float]: ...


class FastEmbedDenseEncoder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        descriptions = {
            description["model"]: description
            for description in TextEmbedding.list_supported_models()
        }
        if model_name not in descriptions:
            raise ValueError(f"FastEmbed 不支持模型：{model_name}")
        self.dimension = int(descriptions[model_name]["dim"])
        self._model: TextEmbedding | None = None

    @property
    def model(self) -> TextEmbedding:
        if self._model is None:
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.model.passage_embed(texts)]

    def encode_query(self, text: str) -> list[float]:
        return next(self.model.query_embed(text)).tolist()


class QdrantRagIndex:
    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        dense_encoder: DenseEncoder,
        reranker: Reranker,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.dense_encoder = dense_encoder
        self.reranker = reranker
        self._chunks: dict[str, IndexedChunk] = {}

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.dense_encoder.dimension,
                    distance=models.Distance.COSINE,
                )
            },
        )

    def replace_document(
        self,
        document_id: str,
        chunks: Sequence[IndexedChunk],
    ) -> None:
        self.ensure_collection()
        self._delete_document_points(document_id)
        self._chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk.document_id != document_id
        }
        if not chunks:
            return

        texts = [f"{chunk.title}\n{chunk.content}" for chunk in chunks]
        vectors = self.dense_encoder.encode_documents(texts)
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=self._point_id(chunk.chunk_id),
                    vector={"dense": vector},
                    payload=chunk.model_dump(mode="json"),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
            wait=True,
        )
        self._chunks.update({chunk.chunk_id: chunk for chunk in chunks})

    def delete(self, document_id: str) -> None:
        if self.client.collection_exists(self.collection_name):
            self._delete_document_points(document_id)
        self._chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk.document_id != document_id
        }

    def rebuild(self, chunks: Iterable[IndexedChunk]) -> None:
        materialized = list(chunks)
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self._chunks.clear()
        self.ensure_collection()
        by_document: dict[str, list[IndexedChunk]] = {}
        for chunk in materialized:
            by_document.setdefault(chunk.document_id, []).append(chunk)
        for document_id, document_chunks in by_document.items():
            self.replace_document(document_id, document_chunks)

    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]:
        if not self._chunks:
            return []
        candidates = max(limit * 3, DEFAULT_CANDIDATES)
        dense_ranking = self._dense_ranking(query, candidates)
        bm25_ranking = self._bm25_ranking(query, candidates)
        fused_scores = self._rrf(dense_ranking, bm25_ranking)
        ranked_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)[:candidates]
        documents = [
            f"{self._chunks[chunk_id].title}\n{self._chunks[chunk_id].content}"
            for chunk_id in ranked_ids
        ]
        try:
            rerank_scores = self.reranker.rerank(query, documents)
            if len(rerank_scores) != len(ranked_ids):
                raise ValueError("精排分数数量与候选文档不一致")
        except (OSError, RuntimeError, ValueError):
            rerank_scores = [fused_scores[chunk_id] for chunk_id in ranked_ids]

        results = [
            RetrievedDocument(
                chunk_id=chunk_id,
                document_id=self._chunks[chunk_id].document_id,
                title=self._chunks[chunk_id].title,
                source_type=self._chunks[chunk_id].source_type,
                evidence=self._chunks[chunk_id].content,
                retrieval_score=fused_scores[chunk_id],
                rerank_score=rerank_score,
            )
            for chunk_id, rerank_score in zip(ranked_ids, rerank_scores, strict=True)
        ]
        results.sort(
            key=lambda item: (item.rerank_score, item.retrieval_score),
            reverse=True,
        )
        return results[:limit]

    def _dense_ranking(self, query: str, limit: int) -> list[str]:
        if not self.client.collection_exists(self.collection_name):
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=self.dense_encoder.encode_query(query),
            using="dense",
            limit=limit,
            with_payload=True,
        )
        return [
            str((point.payload or {}).get("chunk_id", ""))
            for point in response.points
            if str((point.payload or {}).get("chunk_id", "")) in self._chunks
        ]

    def _bm25_ranking(self, query: str, limit: int) -> list[str]:
        chunk_ids = list(self._chunks)
        corpus = [self._tokens(self._chunk_text(self._chunks[chunk_id])) for chunk_id in chunk_ids]
        query_tokens = self._tokens(query)
        if not query_tokens or not any(corpus):
            return []
        scores = BM25Okapi(corpus).get_scores(query_tokens)
        ranked = sorted(
            zip(chunk_ids, scores, strict=True),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        return [chunk_id for chunk_id, score in ranked[:limit] if float(score) > 0]

    @staticmethod
    def _rrf(*rankings: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        return scores

    def _delete_document_points(self, document_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [token.strip().lower() for token in jieba.lcut(text) if token.strip()]

    @staticmethod
    def _chunk_text(chunk: IndexedChunk) -> str:
        return f"{chunk.title} {chunk.content}"

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"dd-cafe-knowledge-chunk:{chunk_id}"))
