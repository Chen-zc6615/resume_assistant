"""认证路由：登录会话的签发、校验与撤销。

会话令牌经 Authorization: Bearer <token> 传递（非 Cookie 模式），
浏览器跨站无法携带该头，CSRF 攻击面不存在，故不强制 CSRF 校验。
"""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_service.core.auth_security import hash_password
from app_service.db.session import SessionLocal
from app_service.models.db_models import UserAccount
from app_service.models.schemas import AuthUserOut, LoginRequest
from app_service.services import auth_service
from app_service.services.auth_service import (
    AccountLockedError,
    AuthenticatedSession,
    InvalidCredentialsError,
)

router = APIRouter()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def extract_bearer_token(request: Request) -> str | None:
    """从 Authorization 头提取 Bearer 令牌。"""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def require_auth(request: Request, db: Session = Depends(get_db)) -> AuthenticatedSession:
    """业务端点依赖：校验会话令牌并返回当前用户。"""
    authenticated = auth_service.resolve_session(db, extract_bearer_token(request))
    if authenticated is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return authenticated


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """校验凭据，签发会话令牌（服务端只保存哈希）。"""
    try:
        result = auth_service.login(db, body.username, body.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    except AccountLockedError:
        raise HTTPException(status_code=423, detail="失败次数过多，账号已临时锁定")
    return {
        "user": AuthUserOut.model_validate(result.user),
        "session_token": result.session_token,
        "expires_at": result.expires_at,
    }


@router.get("/me")
def me(authenticated: AuthenticatedSession = Depends(require_auth)) -> AuthUserOut:
    """返回当前登录用户信息。"""
    return AuthUserOut.model_validate(authenticated.user)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> dict:
    """撤销当前会话令牌。"""
    auth_service.logout(db, extract_bearer_token(request))
    return {"ok": True}


@router.get("/health")
def health() -> dict:
    """公开健康端点（容器 healthcheck 专用，无需登录）。"""
    return {"status": "ok"}


def ensure_admin_user(db: Session) -> None:
    """首次启动（空表）时 seed 管理员账号，幂等。"""
    from app_service.core.config import get_settings

    if db.scalar(select(UserAccount.user_id).limit(1)) is not None:
        return
    settings = get_settings()
    db.add(
        UserAccount(
            username="hr_admin",
            display_name="李婷",
            password_hash=hash_password(settings.auth_admin_password),
            status="normal",
        )
    )
    db.commit()
