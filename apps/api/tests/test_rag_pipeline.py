from collections.abc import Sequence

import pytest

from app.rag.pipeline import RagPipeline
from app.rag.schemas import RetrievedDocument


class RewriteModel:
    def __init__(self, rewritten: str = "纸巾在哪里", fail: bool = False) -> None:
        self.rewritten = rewritten
        self.fail = fail
        self.calls = 0

    async def rewrite_query(
        self,
        query: str,
        history: Sequence[tuple[str, str]],
    ) -> str:
        del query, history
        self.calls += 1
        if self.fail:
            raise RuntimeError("deepseek unavailable")
        return self.rewritten


class RecordingKnowledgeService:
    def __init__(self, results: list[RetrievedDocument]) -> None:
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]:
        self.queries.append(query)
        return self.results[:limit]


def evidence(
    content: str = "纸巾在桌下收纳篮里",
    rerank_score: float = 1.0,
    title: str = "纸巾位置",
) -> RetrievedDocument:
    return RetrievedDocument(
        chunk_id="tissues:0",
        document_id="tissues",
        title=title,
        source_type="guide",
        evidence=content,
        retrieval_score=0.03,
        rerank_score=rerank_score,
    )


@pytest.mark.asyncio
async def test_query_rewrite_only_runs_for_context_dependent_query() -> None:
    model = RewriteModel()
    service = RecordingKnowledgeService([evidence()])
    pipeline = RagPipeline(service, model)

    direct = await pipeline.run("纸巾在哪里", [("assistant", "纸巾在桌下")])
    contextual = await pipeline.run("它在哪里", [("assistant", "我们刚才在说纸巾")])

    assert direct.rewritten_query == "纸巾在哪里"
    assert contextual.rewritten_query == "纸巾在哪里"
    assert model.calls == 1
    assert service.queries == ["纸巾在哪里", "纸巾在哪里"]


@pytest.mark.asyncio
async def test_query_rewrite_failure_falls_back_to_original_query() -> None:
    model = RewriteModel(fail=True)
    service = RecordingKnowledgeService([evidence()])

    result = await RagPipeline(service, model).run(
        "它在哪里",
        [("assistant", "我们刚才在说纸巾")],
    )

    assert result.rewritten_query == "它在哪里"
    assert result.degraded_steps == ["query_rewrite"]
    assert service.queries == ["它在哪里"]


@pytest.mark.asyncio
async def test_pipeline_returns_the_exact_single_retrieval_result() -> None:
    service = RecordingKnowledgeService([evidence()])

    result = await RagPipeline(service, RewriteModel()).run("纸巾在哪里", [])

    assert len(service.queries) == 1
    assert result.evidence[0].chunk_id == "tissues:0"
    assert set(result.timings_ms) == {"rewrite", "retrieval", "total"}
    assert result.no_evidence is False


@pytest.mark.asyncio
async def test_pipeline_rejects_unrelated_negative_score_evidence() -> None:
    service = RecordingKnowledgeService(
        [
            evidence(
                title="无线网络",
                content="无线网络名称是 DD-Guest",
                rerank_score=-2.0,
            )
        ]
    )

    result = await RagPipeline(service, RewriteModel()).run("纸巾在哪里", [])

    assert result.evidence == []
    assert result.no_evidence is True
