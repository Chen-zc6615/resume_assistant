"""FastAPI 应用工厂：路由挂载、鉴权中间件、CORS、启动建表、前端静态托管（生产）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app_service.api import agent, auth, jobs, parse, requirements, resume, screen, talent, tasks
from app_service.core.logger import setup_logging
from app_service.db.session import SessionLocal, init_db
from app_service.services import auth_service

# 前端构建产物（vite build）；存在则由本服务直接托管（生产裸跑部署）
# app.py 位于 services/app/src/app_service/ 下，dist 在 services/app/web/dist
_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

# 无需登录即可访问的 API（登录本身 + 容器健康检查）
_PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/health"}


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
    # 首次启动 seed 管理员（hr_admin），空表时才创建，幂等
    db = SessionLocal()
    try:
        auth.ensure_admin_user(db)
    finally:
        db.close()
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

    @app.middleware("http")
    async def require_session(request, call_next):
        """API 鉴权门卫：/api/* 除公开路径外必须携带有效会话令牌。"""
        path = request.url.path
        if path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
            header = request.headers.get("authorization", "")
            token = header[7:].strip() if header.lower().startswith("bearer ") else None
            db = SessionLocal()
            try:
                authenticated = auth_service.resolve_session(db, token)
                user = authenticated.user if authenticated else None
            finally:
                db.close()
            if user is None:
                return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
            request.state.auth_user = user
        return await call_next(request)

    # API 路由先注册（优先于静态托管）
    app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
    app.include_router(resume.router, prefix="/api/resumes", tags=["简历"])
    app.include_router(parse.router, prefix="/api/parse", tags=["解析批次"])
    app.include_router(requirements.router, prefix="/api/requirements", tags=["需求"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["岗位"])
    app.include_router(screen.router, prefix="/api/screening", tags=["初筛"])
    app.include_router(talent.router, prefix="/api/talent", tags=["人才库/面试"])
    app.include_router(agent.router, prefix="/api/agent", tags=["任务（兼容接口）"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])

    # 生产：托管前端构建产物（开发模式下走 Vite 5173，不冲突）
    if _DIST.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(_DIST), html=True), name="spa")

    return app
