"""认证业务层测试。"""

from datetime import timedelta

import pytest
from app_service.core.auth_security import hash_password, verify_token
from app_service.db.base import Base
from app_service.db.session import SessionLocal, engine
from app_service.models.db_models import AuthSession, UserAccount
from app_service.services.auth_service import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidCsrfTokenError,
    login,
    logout,
    resolve_session,
    utc_now,
    validate_csrf_token,
)
from sqlalchemy import select

TEST_PASSWORD = "CorrectPassword123!"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture()
def db():
    """为每个测试提供相互隔离的数据库会话。"""

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def create_user(db, **overrides) -> UserAccount:
    """创建一个可登录的测试用户。"""

    values = {
        "username": "hr_admin",
        "display_name": "测试 HR",
        "password_hash": TEST_PASSWORD_HASH,
        "status": "normal",
        "failed_login_count": 0,
    }
    values.update(overrides)

    user = UserAccount(**values)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_login_success_creates_session_and_resets_failures(db):
    """正确凭据应创建会话，并清除之前的失败状态。"""

    user = create_user(
        db,
        failed_login_count=3,
        locked_until=utc_now() - timedelta(minutes=1),
    )

    result = login(
        db=db,
        username="  HR_Admin  ",
        password=TEST_PASSWORD,
    )

    db.refresh(user)
    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.user_id == user.user_id)
    )

    assert result.user.user_id == user.user_id
    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert user.last_login_at is not None
    assert auth_session is not None
    assert auth_session.token_hash != result.session_token
    assert auth_session.csrf_token_hash != result.csrf_token
    assert verify_token(result.session_token, auth_session.token_hash)
    assert verify_token(result.csrf_token, auth_session.csrf_token_hash)


def test_wrong_password_uses_generic_error_and_increments_count(db):
    """密码错误不得暴露账号信息，并应增加连续失败次数。"""

    user = create_user(db)

    with pytest.raises(InvalidCredentialsError, match="用户名或密码错误"):
        login(db, user.username, "WrongPassword123!")

    db.refresh(user)
    assert user.failed_login_count == 1
    assert user.locked_until is None


def test_unknown_username_uses_same_generic_error(db):
    """不存在的用户名与密码错误必须使用相同的对外反馈。"""

    with pytest.raises(InvalidCredentialsError, match="用户名或密码错误"):
        login(db, "unknown_user", "WrongPassword123!")


def test_fifth_failed_login_locks_account(db):
    """第 5 次连续失败应锁定账号 15 分钟。"""

    user = create_user(db, failed_login_count=4)
    before_login = utc_now()

    with pytest.raises(AccountLockedError, match="登录失败，请稍后重试"):
        login(db, user.username, "WrongPassword123!")

    db.refresh(user)
    assert user.failed_login_count == 5
    assert user.locked_until is not None
    assert user.locked_until >= before_login + timedelta(minutes=14, seconds=50)
    assert user.locked_until <= before_login + timedelta(minutes=15, seconds=10)


def test_locked_account_cannot_login_with_correct_password(db):
    """锁定期间即使密码正确，也不能创建会话。"""

    user = create_user(
        db,
        failed_login_count=5,
        locked_until=utc_now() + timedelta(minutes=10),
    )

    with pytest.raises(AccountLockedError, match="登录失败，请稍后重试"):
        login(db, user.username, TEST_PASSWORD)

    session_count = len(db.scalars(select(AuthSession)).all())
    assert session_count == 0


def test_disabled_account_uses_generic_error(db):
    """禁用账号不得登录，也不能向外暴露禁用状态。"""

    user = create_user(db, status="disabled")

    with pytest.raises(InvalidCredentialsError, match="用户名或密码错误"):
        login(db, user.username, TEST_PASSWORD)


def test_resolve_session_returns_authenticated_user(db):
    """有效令牌应恢复对应的用户和会话。"""

    user = create_user(db)
    login_result = login(db, user.username, TEST_PASSWORD)

    authenticated = resolve_session(db, login_result.session_token)

    assert authenticated is not None
    assert authenticated.user.user_id == user.user_id
    assert authenticated.session.user_id == user.user_id


def test_resolve_session_rejects_invalid_expired_and_revoked_tokens(db):
    """无效、过期或已撤销的令牌都不能恢复登录状态。"""

    user = create_user(db)
    login_result = login(db, user.username, TEST_PASSWORD)

    assert resolve_session(db, "invalid-token") is None

    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.user_id == user.user_id)
    )
    assert auth_session is not None

    auth_session.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert resolve_session(db, login_result.session_token) is None

    auth_session.expires_at = utc_now() + timedelta(hours=1)
    auth_session.revoked_at = utc_now()
    db.commit()
    assert resolve_session(db, login_result.session_token) is None


def test_validate_csrf_token(db):
    """写操作只接受当前会话对应的 CSRF 令牌。"""

    user = create_user(db)
    login_result = login(db, user.username, TEST_PASSWORD)
    authenticated = resolve_session(db, login_result.session_token)

    assert authenticated is not None
    validate_csrf_token(authenticated, login_result.csrf_token)

    with pytest.raises(InvalidCsrfTokenError, match="CSRF Token 无效"):
        validate_csrf_token(authenticated, "invalid-csrf-token")

    with pytest.raises(InvalidCsrfTokenError, match="CSRF Token 无效"):
        validate_csrf_token(authenticated, None)


def test_logout_revokes_current_session_and_is_idempotent(db):
    """退出应撤销当前会话；重复退出不应报错。"""

    user = create_user(db)
    login_result = login(db, user.username, TEST_PASSWORD)

    logout(db, login_result.session_token)

    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.user_id == user.user_id)
    )
    assert auth_session is not None
    assert auth_session.revoked_at is not None
    assert resolve_session(db, login_result.session_token) is None

    logout(db, login_result.session_token)
    logout(db, None)
    logout(db, "unknown-token")
