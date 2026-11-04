"""HTTP 鉴权门卫：/api/* 除公开路径外必须携带有效会话令牌。"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.responses import JSONResponse

from app_service.db.session import SessionLocal
from app_service.services import auth_service

# 无需登录即可访问的 API（登录本身 + 容器健康检查）
_PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/health"}


def register_auth_middleware(app: FastAPI) -> None:
    """把会话门卫注册为 HTTP 中间件；在 create_app 中调用一次。"""

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
