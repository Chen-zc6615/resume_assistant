from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app_service.core.config import get_settings
from app_service.core.auth_security import (
    generate_token,
    hash_password,
    hash_token,
    normalize_username,
    verify_password,
    verify_token,
)

from app_service.models.db_models import AuthSession, UserAccount

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15

DUMMY_PASSWORD_HASH = hash_password(generate_token())


class InvalidCredentialsError(Exception):
    pass


class AccountLockedError(Exception):
    pass


@dataclass
class LoginResult:
    user: UserAccount
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass
class AuthenticatedSession:
    user: UserAccount
    session: AuthSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def login(db: Session, username: str, password: str) -> LoginResult:
    settings = get_settings()
    normalized_username = normalize_username(username)
    statement = (
        select(UserAccount).where(UserAccount.username == normalized_username).with_for_update()
    )

    user = db.scalar(statement)

    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise InvalidCredentialsError("用户名或密码错误")

    now = utc_now()

    if user.status != "normal":
        verify_password(password, user.password_hash)
        raise InvalidCredentialsError("用户名或密码错误")

    if user.locked_until is not None:
        locked_until = ensure_utc(user.locked_until)
        if now < locked_until:
            raise AccountLockedError("登录失败，请稍后重试")
        user.failed_login_count = 0
        user.locked_until = None

    password_is_valid = verify_password(
        password,
        user.password_hash,
    )

    if not password_is_valid:
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(
                minutes=LOCK_DURATION_MINUTES,
            )
            db.commit()
            raise AccountLockedError("登录失败，请稍后重试")

        db.commit()
        raise InvalidCredentialsError("用户名或密码错误")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    session_token = generate_token()
    csrf_token = generate_token()

    expires_at = now + timedelta(
        hours=settings.auth_session_hours,
    )

    auth_session = AuthSession(
        user_id=user.user_id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=expires_at,
        revoked_at=None,
        last_seen_at=now,
    )

    db.add(auth_session)
    db.commit()
    db.refresh(user)

    return LoginResult(
        user=user,
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )

def resolve_session(db: Session, session_token: str | None) -> AuthenticatedSession | None:
    if not session_token:
        return None

    session_token_hash = hash_token(session_token)
    statement = select(AuthSession).where(
        AuthSession.token_hash == session_token_hash
    )

    auth_session = db.scalar(statement)

    if auth_session is None:
        return None

    if auth_session.revoked_at is not None:
        return None

    now = utc_now()

    expires_at = ensure_utc(auth_session.expires_at)

    if now >= expires_at:
        return None

    user = auth_session.user

    if user is None or user.status != "normal":
        return None

    return AuthenticatedSession(
        user=user,
        session=auth_session,
    )


class InvalidCsrfTokenError(Exception):
    pass


def validate_csrf_token(authenticated: AuthenticatedSession, csrf_token: str | None) -> None:
    if not csrf_token:
        raise InvalidCsrfTokenError("CSRF Token 无效")

    expected_hash = authenticated.session.csrf_token_hash
    if not verify_token(csrf_token, expected_hash):
        raise InvalidCsrfTokenError("CSRF Token 无效")


def logout(db: Session, session_token: str | None) -> None:
    if not session_token:
        return
    session_token_hash = hash_token(session_token)

    statement = (
        select(AuthSession).where(AuthSession.token_hash == session_token_hash).with_for_update()
    )

    auth_session = db.scalar(statement)

    if auth_session is None:
        return

    if auth_session.revoked_at is None:
        auth_session.revoked_at = utc_now()
        db.commit()

