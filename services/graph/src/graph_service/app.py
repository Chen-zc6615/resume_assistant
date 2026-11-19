from contextlib import asynccontextmanager

from fastapi import FastAPI

from graph_service.api.routes import router
from graph_service.core.config import get_settings
from graph_service.core.logger import setup_logging
from graph_service.db.neo4j_store import GraphStore


def create_app(store: GraphStore | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        graph_store = store or GraphStore(get_settings())
        graph_store.init_schema()
        app.state.graph_store = graph_store  # 放进储物柜，供接口取用
        yield
        graph_store.close()

    app = FastAPI(
        title="Graph Service",
        description="Resume / job skill knowledge graph (Neo4j)",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
