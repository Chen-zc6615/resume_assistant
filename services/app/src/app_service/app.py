"""FastAPI 应用工厂：路由挂载、CORS、启动建表、前端静态托管（生产）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app_service.api import agent, jobs, parse, requirements, resume, screen, talent
from app_service.core.logger import setup_logging
from app_service.db.session import init_db

# 前端构建产物（vite build）；存在则由本服务直接托管（生产裸跑部署）
# app.py 位于 services/app/src/app_service/ 下，dist 在 services/app/web/dist
_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


class SPAStaticFiles(StaticFiles):
    """Vue Router history 模式支持：未命中的路径回退到 index.html。"""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException:
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="智能简历筛选助手",
        description="批量解析、归一化、硬性初筛、人工审核入库",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # MVP：本地前端开发服务器
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API 路由先注册（优先于静态托管）
    app.include_router(resume.router, prefix="/api/resumes", tags=["简历"])
    app.include_router(parse.router, prefix="/api/parse", tags=["解析批次"])
    app.include_router(requirements.router, prefix="/api/requirements", tags=["需求"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["岗位"])
    app.include_router(screen.router, prefix="/api/screening", tags=["初筛"])
    app.include_router(talent.router, prefix="/api/talent", tags=["人才库/面试"])
    app.include_router(agent.router, prefix="/api/agent", tags=["招聘 Agent"])

    # 生产：托管前端构建产物（开发模式下走 Vite 5173，不冲突）
    if _DIST.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(_DIST), html=True), name="spa")

    return app
