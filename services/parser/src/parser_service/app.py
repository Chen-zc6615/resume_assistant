from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from parser_service.api.routes import router
from parser_service.core.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Resume Parser Service",
        description="Independent PDF validation, text extraction and OCR service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app

