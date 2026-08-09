from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.agents.graph import AgentRuntime
from app.agents.model import (
    DeepSeekRecommendationModel,
    DemoRecommendationModel,
    RecommendationModel,
)
from app.agents.web_search import WebSearchTool
from app.config import Settings
from app.db.session import Database
from app.rag.service import KnowledgeIndex


@asynccontextmanager
async def checkpointer_context(settings: Settings) -> AsyncIterator[BaseCheckpointSaver]:
    if not settings.redis_checkpoints:
        yield InMemorySaver()
        return

    ttl = {
        "default_ttl": settings.checkpoint_ttl_minutes,
        "refresh_on_read": True,
    }
    async with AsyncRedisSaver.from_conn_string(settings.redis_url, ttl=ttl) as checkpointer:
        await checkpointer.asetup()
        yield checkpointer


def create_recommendation_model(settings: Settings) -> RecommendationModel:
    if settings.deepseek_api_key is None:
        return DemoRecommendationModel()
    api_key = settings.deepseek_api_key.get_secret_value().strip()
    if not api_key:
        return DemoRecommendationModel()
    return DeepSeekRecommendationModel(
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )


def create_agent_runtime(
    settings: Settings,
    database: Database,
    rag_index: KnowledgeIndex,
    checkpointer: BaseCheckpointSaver,
) -> AgentRuntime:
    return AgentRuntime(
        session_factory=database.session_factory,
        rag_index=rag_index,
        checkpointer=checkpointer,
        recommendation_model=create_recommendation_model(settings),
        web_search=WebSearchTool() if settings.web_search_enabled else None,
    )
