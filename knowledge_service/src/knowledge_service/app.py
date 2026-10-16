from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from knowledge_service.api.routes import router
from knowledge_service.core.config import get_settings
from knowledge_service.core.logger import setup_logging
from knowledge_service.services.knowledge import KnowledgeService


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    app.state.knowledge_service = KnowledgeService(get_settings())
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Resume Knowledge Service",
        description="Independent document indexing, hybrid retrieval, reranking and citations",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app

