import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.factory import checkpointer_context, create_agent_runtime
from app.api.catalog import router as catalog_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.images import router as images_router
from app.api.knowledge import router as knowledge_router
from app.api.orders import router as orders_router
from app.api.sessions import router as sessions_router
from app.config import Settings, get_settings
from app.db.base import Base
from app.db.session import Database
from app.orders.errors import OrderConflict, OrderError, OrderNotFound
from app.rag.factory import create_rag_index
from app.rag.service import KnowledgeService
from app.seed import seed_knowledge_if_empty, seed_menu_if_empty

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(app_settings.database_url)
        application.state.database = database
        application.state.settings = app_settings
        application.state.rag_index = create_rag_index(app_settings)
        if app_settings.auto_create_schema:
            Base.metadata.create_all(database.engine)
        if app_settings.seed_demo_data:
            with database.session_factory() as session:
                seed_menu_if_empty(session)
                seed_knowledge_if_empty(session)
        if app_settings.seed_demo_data and app_settings.qdrant_url != ":memory:":
            # 冷启动时整库重建一次，避免首个检索请求触发羊群式全量重建。
            with database.session_factory() as session:
                try:
                    KnowledgeService(
                        session, application.state.rag_index
                    ).rebuild_if_pending()
                except Exception:
                    logger.exception("RAG 冷启动重建失败，将在首次检索时重试")
        try:
            async with checkpointer_context(app_settings) as checkpointer:
                application.state.agent_runtime = create_agent_runtime(
                    app_settings,
                    database,
                    application.state.rag_index,
                    checkpointer,
                )
                yield
        finally:
            database.close()

    application = FastAPI(title="DD Cafe API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(catalog_router)
    application.include_router(sessions_router)
    application.include_router(orders_router)
    application.include_router(knowledge_router)
    application.include_router(chat_router)
    application.include_router(images_router)

    @application.exception_handler(OrderError)
    async def handle_order_error(_request: Request, error: OrderError) -> JSONResponse:
        status_code = 400
        if isinstance(error, OrderNotFound):
            status_code = 404
        elif isinstance(error, OrderConflict):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": error.code, "message": str(error)}},
        )

    return application


app = create_app()
