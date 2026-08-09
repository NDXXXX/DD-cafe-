from pydantic import BaseModel, ConfigDict, Field

from app.agents.graph import AgentRuntime


class RagEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    reference: str
    expected_document_ids: list[str] = Field(default_factory=list)
    expect_no_evidence: bool = False


class RagEvalResult(BaseModel):
    case_id: str
    passed: bool
    answer: str
    retrieved_contexts: list[str]
    retrieved_document_ids: list[str]
    hit_at_k: bool
    reciprocal_rank: float
    no_answer_correct: bool
    order_mutated: bool
    timings_ms: dict[str, float]
    failures: list[str]


class RagHarness:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    async def run_case(self, case: RagEvalCase) -> RagEvalResult:
        trace = [
            event
            async for event in self.runtime.stream(
                session_id=f"rag-eval-{case.id}",
                table_number="EVAL",
                request_id=f"rag-eval-request-{case.id}",
                message=case.question,
            )
        ]
        answer = "".join(
            str(event.get("text", "")) for event in trace if event.get("type") == "token"
        )
        evidence_event = next(
            (event for event in trace if event.get("type") == "evidence"),
            {"items": []},
        )
        items = evidence_event["items"]
        document_ids = [str(item["document_id"]) for item in items]
        contexts = [str(item["evidence"]) for item in items]
        trace_event = next(
            (event for event in trace if event.get("type") == "rag_trace"),
            {"timings_ms": {}},
        )
        order_mutated = any(
            event.get("type") in {"cart", "order", "cancellation"} for event in trace
        )

        if case.expected_document_ids:
            hit_at_k = all(
                document_id in document_ids for document_id in case.expected_document_ids
            )
            ranks = [
                document_ids.index(document_id) + 1
                for document_id in case.expected_document_ids
                if document_id in document_ids
            ]
            reciprocal_rank = 1.0 / min(ranks) if ranks else 0.0
        else:
            hit_at_k = not document_ids
            reciprocal_rank = 0.0

        no_answer_correct = True
        if case.expect_no_evidence:
            no_answer_correct = not document_ids and any(
                phrase in answer for phrase in ("暂时没有", "不知道", "询问店员")
            )

        failures: list[str] = []
        if not hit_at_k:
            failures.append("检索结果未命中预期知识文档")
        if not no_answer_correct:
            failures.append("无证据问题没有安全拒答")
        if order_mutated:
            failures.append("知识评测请求修改了订单状态")
        return RagEvalResult(
            case_id=case.id,
            passed=not failures,
            answer=answer,
            retrieved_contexts=contexts,
            retrieved_document_ids=document_ids,
            hit_at_k=hit_at_k,
            reciprocal_rank=reciprocal_rank,
            no_answer_correct=no_answer_correct,
            order_mutated=order_mutated,
            timings_ms=dict(trace_event["timings_ms"]),
            failures=failures,
        )
