import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.agents.graph import AgentRuntime
from app.agents.image_edit import ImageEditModel
from app.agents.image_gen import ImageGenModel
from app.agents.model import (
    DeepSeekRecommendationModel,
    DemoRecommendationModel,
    QwenVLRecommendationModel,
    RecommendationModel,
)
from app.agents.vision import VisionModel
from app.agents.web_search import WebSearchTool
from app.config import Settings
from app.db.session import Database
from app.rag.service import KnowledgeIndex

logger = logging.getLogger(__name__)


@asynccontextmanager
async def checkpointer_context(settings: Settings) -> AsyncIterator[BaseCheckpointSaver]:
    if not settings.redis_checkpoints:
        yield InMemorySaver()
        return

    ttl = {
        "default_ttl": settings.checkpoint_ttl_minutes,
        "refresh_on_read": True,
    }
    try:
        async with AsyncRedisSaver.from_conn_string(settings.redis_url, ttl=ttl) as checkpointer:
            await checkpointer.asetup()
            yield checkpointer
    except Exception:
        # 无 Redis（本地开发未起 infra）时 fail-open 到内存检查点，
        # 保证应用仍可启动；代价是跨进程重启不保留对话记忆。
        logger.warning(
            "Redis 检查点不可用，已回退到内存检查点（跨进程重启不保留对话记忆）",
            exc_info=True,
        )
        yield InMemorySaver()


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


def create_vision_model(settings: Settings) -> VisionModel | None:
    if settings.vision_api_key is None:
        return None
    api_key = settings.vision_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return VisionModel(
        api_key=api_key,
        base_url=settings.vision_base_url,
        model=settings.vision_model,
    )


def create_multimodal_reply_model(settings: Settings) -> QwenVLRecommendationModel | None:
    if settings.vision_api_key is None:
        return None
    api_key = settings.vision_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return QwenVLRecommendationModel(
        api_key=api_key,
        base_url=settings.vision_base_url,
        model=settings.vision_model,
    )


def create_image_gen_model(settings: Settings) -> ImageGenModel | None:
    if settings.vision_api_key is None:
        return None
    api_key = settings.vision_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return ImageGenModel(
        api_key=api_key,
        base_url=settings.vision_base_url,
        model=settings.image_gen_model,
        size=settings.image_gen_size,
    )


def create_image_edit_model(settings: Settings) -> ImageEditModel | None:
    if settings.vision_api_key is None:
        return None
    api_key = settings.vision_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return ImageEditModel(api_key=api_key, model=settings.image_edit_model)


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
        vision_model=create_vision_model(settings),
        multimodal_reply_model=create_multimodal_reply_model(settings),
        image_gen_model=create_image_gen_model(settings),
        image_edit_model=create_image_edit_model(settings),
        upload_dir=settings.upload_dir,
    )
