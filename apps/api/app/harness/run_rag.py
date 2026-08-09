import argparse
import asyncio
import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from qdrant_client import QdrantClient

from app.agents.factory import create_recommendation_model
from app.agents.graph import AgentRuntime
from app.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.harness.rag_evaluator import RagEvalCase, RagHarness
from app.harness.ragas_runner import run_ragas
from app.rag.factory import create_rag_index
from app.rag.reranker import LocalCrossEncoderReranker
from app.rag.service import KnowledgeService
from app.rag.store import FastEmbedDenseEncoder, QdrantRagIndex
from app.seed import PROJECT_ROOT, seed_knowledge_if_empty, seed_menu_if_empty


def load_rag_cases(path: Path) -> list[RagEvalCase]:
    return [
        RagEvalCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def main(
    run_llm_judge: bool = False,
    use_local_reranker: bool = False,
) -> int:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        qdrant_url=":memory:",
        redis_checkpoints=False,
        web_search_enabled=False,
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    if use_local_reranker:
        index = QdrantRagIndex(
            client=QdrantClient(":memory:"),
            collection_name=settings.qdrant_collection,
            dense_encoder=FastEmbedDenseEncoder(settings.rag_dense_model),
            reranker=LocalCrossEncoderReranker(settings.rag_reranker_model),
        )
    else:
        index = create_rag_index(settings)
    with database.session_factory() as session:
        seed_menu_if_empty(session)
        seed_knowledge_if_empty(session)
        KnowledgeService(session, index).rebuild()

    runtime = AgentRuntime(
        session_factory=database.session_factory,
        rag_index=index,
        checkpointer=InMemorySaver(),
        recommendation_model=create_recommendation_model(settings),
    )
    cases = load_rag_cases(PROJECT_ROOT / "data" / "evals" / "rag_cases.jsonl")
    harness = RagHarness(runtime)
    results = [await harness.run_case(case) for case in cases]
    for result in results:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))

    if run_llm_judge:
        report = await run_ragas(settings, cases, results)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    database.close()
    return 0 if all(result.passed for result in results) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DD Cafe RAG evaluation")
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Also run the four DeepSeek-judged RAGAS metrics",
    )
    parser.add_argument(
        "--local-reranker",
        action="store_true",
        help="Use the production BGE cross-encoder during retrieval evaluation",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(
        asyncio.run(
            main(
                run_llm_judge=arguments.ragas,
                use_local_reranker=arguments.local_reranker,
            )
        )
    )
