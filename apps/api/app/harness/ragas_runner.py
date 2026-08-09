import asyncio
import sys
import types
import warnings
from collections.abc import Sequence

from fastembed import TextEmbedding
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import Settings
from app.harness.rag_evaluator import RagEvalCase, RagEvalResult


class RagasCaseScores(BaseModel):
    case_id: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


class RagasReport(BaseModel):
    averages: dict[str, float]
    cases: list[RagasCaseScores]


class FastEmbedEvaluationEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model = TextEmbedding(model_name=model_name)

    def embed_text(self, text: str, **kwargs) -> list[float]:
        del kwargs
        return next(self.model.query_embed(text)).tolist()

    async def aembed_text(self, text: str, **kwargs) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text, **kwargs)


def load_ragas_components():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import langchain_community.chat_models.vertexai  # noqa: F401
    except ModuleNotFoundError:
        # Ragas 0.4.3 still imports a path removed by langchain-community 0.4.2.
        # This eval-only shim can be removed when upstream issue #2748 is released.
        compatibility_module = types.ModuleType(
            "langchain_community.chat_models.vertexai"
        )
        compatibility_module.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[compatibility_module.__name__] = compatibility_module

    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    return llm_factory, Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall


async def run_ragas(
    settings: Settings,
    cases: Sequence[RagEvalCase],
    results: Sequence[RagEvalResult],
) -> RagasReport:
    if settings.deepseek_api_key is None:
        raise ValueError("运行 RAGAS 需要 DEEPSEEK_API_KEY")
    api_key = settings.deepseek_api_key.get_secret_value().strip()
    if not api_key:
        raise ValueError("运行 RAGAS 需要 DEEPSEEK_API_KEY")
    if len(cases) != len(results):
        raise ValueError("评测用例与运行结果数量不一致")

    llm_factory, Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall = (
        load_ragas_components()
    )
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.deepseek_base_url,
    )
    evaluator_llm = llm_factory(settings.deepseek_model, client=client)
    embeddings = FastEmbedEvaluationEmbedding(settings.rag_dense_model)
    faithfulness = Faithfulness(llm=evaluator_llm)
    answer_relevancy = AnswerRelevancy(llm=evaluator_llm, embeddings=embeddings)
    context_precision = ContextPrecision(llm=evaluator_llm)
    context_recall = ContextRecall(llm=evaluator_llm)

    scores: list[RagasCaseScores] = []
    for case, result in zip(cases, results, strict=True):
        faithfulness_result = await faithfulness.ascore(
            user_input=case.question,
            response=result.answer,
            retrieved_contexts=result.retrieved_contexts,
        )
        relevancy_result = await answer_relevancy.ascore(
            user_input=case.question,
            response=result.answer,
        )
        precision_result = await context_precision.ascore(
            user_input=case.question,
            reference=case.reference,
            retrieved_contexts=result.retrieved_contexts,
        )
        recall_result = await context_recall.ascore(
            user_input=case.question,
            reference=case.reference,
            retrieved_contexts=result.retrieved_contexts,
        )
        scores.append(
            RagasCaseScores(
                case_id=case.id,
                faithfulness=float(faithfulness_result.value),
                answer_relevancy=float(relevancy_result.value),
                context_precision=float(precision_result.value),
                context_recall=float(recall_result.value),
            )
        )

    metric_names = (
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    )
    averages = {
        metric: sum(getattr(score, metric) for score in scores) / len(scores)
        for metric in metric_names
    }
    return RagasReport(averages=averages, cases=scores)
