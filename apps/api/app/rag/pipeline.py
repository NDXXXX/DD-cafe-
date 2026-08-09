from collections.abc import Sequence
from time import perf_counter
from typing import Protocol

import jieba

from app.rag.rewrite import QueryRewriteModel, rewrite_query
from app.rag.schemas import RagResult, RetrievedDocument

STOP_WORDS = {"它", "这个", "那个", "在", "哪", "哪里", "怎么", "的", "吗", "呢"}


class KnowledgeSearch(Protocol):
    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]: ...


class RagPipeline:
    def __init__(
        self,
        knowledge: KnowledgeSearch,
        rewrite_model: QueryRewriteModel,
    ) -> None:
        self.knowledge = knowledge
        self.rewrite_model = rewrite_model

    async def run(
        self,
        query: str,
        history: Sequence[tuple[str, str]],
        limit: int = 5,
    ) -> RagResult:
        started = perf_counter()
        rewrite_started = perf_counter()
        rewritten = await rewrite_query(self.rewrite_model, query, history)
        rewrite_ms = self._elapsed_ms(rewrite_started)

        retrieval_started = perf_counter()
        retrieved = self.knowledge.search(rewritten.query, limit)
        evidence = self._sufficient_evidence(rewritten.query, retrieved)
        retrieval_ms = self._elapsed_ms(retrieval_started)
        degraded_steps = ["query_rewrite"] if rewritten.degraded else []
        return RagResult(
            original_query=query,
            rewritten_query=rewritten.query,
            evidence=evidence,
            timings_ms={
                "rewrite": rewrite_ms,
                "retrieval": retrieval_ms,
                "total": self._elapsed_ms(started),
            },
            degraded_steps=degraded_steps,
            no_evidence=not evidence,
        )

    @classmethod
    def _sufficient_evidence(
        cls,
        query: str,
        documents: list[RetrievedDocument],
    ) -> list[RetrievedDocument]:
        query_tokens = cls._content_tokens(query)
        return [
            document
            for document in documents
            if document.rerank_score > 0
            or bool(query_tokens.intersection(cls._content_tokens(
                f"{document.title} {document.evidence}"
            )))
        ]

    @staticmethod
    def _content_tokens(text: str) -> set[str]:
        return {
            token.strip().lower()
            for token in jieba.lcut(text)
            if token.strip() and token.strip().lower() not in STOP_WORDS
        }

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)
