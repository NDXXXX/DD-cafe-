import asyncio
import json
from collections.abc import Iterable
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.graph import AgentRuntime
from app.agents.model import DemoRecommendationModel
from app.db.base import Base
from app.db.session import Database
from app.harness.evaluator import AgentHarness, EvalCase
from app.rag.schemas import RetrievedDocument
from app.seed import PROJECT_ROOT, seed_menu_if_empty


class DemoKnowledgeIndex:
    def upsert(self, document_id: str, title: str, content: str, source_type: str) -> None:
        pass

    def delete(self, document_id: str) -> None:
        pass

    def rebuild(self, documents: Iterable[tuple[str, str, str, str]]) -> None:
        pass

    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]:
        del limit
        if "纸巾" not in query:
            return []
        return [
            RetrievedDocument(
                chunk_id="tissues:0",
                document_id="tissues",
                title="纸巾位置",
                source_type="restaurant_guide",
                evidence="纸巾在桌下收纳篮里",
                retrieval_score=1.0,
                rerank_score=1.2,
            )
        ]


def load_cases(path: Path) -> list[EvalCase]:
    return [
        EvalCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def main() -> int:
    database = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_menu_if_empty(session)
    runtime = AgentRuntime(
        session_factory=database.session_factory,
        rag_index=DemoKnowledgeIndex(),
        checkpointer=InMemorySaver(),
        recommendation_model=DemoRecommendationModel(),
    )
    harness = AgentHarness(runtime)
    cases = load_cases(PROJECT_ROOT / "data" / "evals" / "cases.jsonl")
    results = [await harness.run_case(case) for case in cases]
    for result in results:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
    database.close()
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
