from __future__ import annotations

from contextlib import asynccontextmanager  #装饰器

from fastapi import FastAPI

from app_service.api import agent, auth, jobs, parse, requirements, resume, screen, talent, tasks
from app_service.core.auth_middleware import register_auth_middleware
from app_service.core.logger import setup_logging
from app_service.db.session import SessionLocal, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()  #创建数据库中不存在的table
    db = SessionLocal()  #创建一个与数据库的会话连接
    try:
        auth.ensure_admin_user(db)  #确认数据库中有管理员账号，如果没有就创建一个
    finally:
        db.close()  #关闭与数据库的会话连接
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="智能简历筛选助手",
        description="批量解析、归一化、硬性初筛、人工审核入库",
        version="0.1.0",
        lifespan=lifespan,
    )


    # 鉴权门卫（含公开路径白名单）单独住在 core/auth_middleware.py
    register_auth_middleware(app)

    # API 路由注册
    app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
    app.include_router(resume.router, prefix="/api/resumes", tags=["简历"])
    app.include_router(parse.router, prefix="/api/parse", tags=["解析批次"])
    app.include_router(requirements.router, prefix="/api/requirements", tags=["需求"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["岗位"])
    app.include_router(screen.router, prefix="/api/screening", tags=["初筛"])
    app.include_router(talent.router, prefix="/api/talent", tags=["人才库/面试"])
    app.include_router(agent.router, prefix="/api/agent", tags=["任务（兼容接口）"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])

    return app
