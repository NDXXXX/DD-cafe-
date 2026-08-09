import sys
from pathlib import Path

import pytest

from app.harness.rag_evaluator import RagEvalCase, RagHarness
from app.harness.ragas_runner import load_ragas_components
from app.harness.run import load_cases
from app.harness.run_rag import load_rag_cases


def test_eval_cases_are_valid_and_cover_safe_routes() -> None:
    cases_path = Path(__file__).resolve().parents[3] / "data" / "evals" / "cases.jsonl"
    cases = load_cases(cases_path)

    assert len(cases) == 6
    routes = {case.expected_route for case in cases}
    assert routes == {"recommend", "order", "recommend_then_order", "clarify"}
    ambiguous = next(case for case in cases if case.id == "ambiguous-write")
    assert "cart" in ambiguous.forbidden_events
    iced_americano = next(case for case in cases if case.id == "explicit-iced-americano")
    assert iced_americano.expected_temperature == "冰"


def test_rag_eval_cases_cover_retrieval_and_no_answer() -> None:
    cases_path = Path(__file__).resolve().parents[3] / "data" / "evals" / "rag_cases.jsonl"
    cases = load_rag_cases(cases_path)

    assert len(cases) == 6
    assert all(case.reference for case in cases)
    assert any(case.expected_document_ids for case in cases)
    assert any(case.expect_no_evidence for case in cases)


class FakeRagRuntime:
    async def stream(self, **kwargs):
        request_id = kwargs["request_id"]
        yield {
            "type": "evidence",
            "request_id": request_id,
            "items": [
                {
                    "chunk_id": "tissues:0",
                    "document_id": "tissues",
                    "title": "纸巾位置",
                    "source_type": "guide",
                    "evidence": "纸巾在桌下",
                    "retrieval_score": 0.03,
                    "rerank_score": 1.0,
                }
            ],
        }
        yield {
            "type": "rag_trace",
            "request_id": request_id,
            "timings_ms": {"total": 1.0},
        }
        yield {"type": "token", "request_id": request_id, "text": "纸巾在桌下。"}
        yield {"type": "done", "request_id": request_id}


@pytest.mark.asyncio
async def test_rag_harness_uses_the_contexts_from_the_same_agent_run() -> None:
    case = RagEvalCase(
        id="tissues",
        question="纸巾在哪里？",
        reference="纸巾在桌下。",
        expected_document_ids=["tissues"],
    )

    result = await RagHarness(FakeRagRuntime()).run_case(case)

    assert result.passed is True
    assert result.retrieved_contexts == ["纸巾在桌下"]
    assert result.answer == "纸巾在桌下。"
    assert result.reciprocal_rank == 1.0


def test_ragas_current_api_can_be_loaded_with_scoped_compatibility_shim() -> None:
    components = load_ragas_components()

    assert len(components) == 5
    assert "langchain_community.chat_models.vertexai" in sys.modules
