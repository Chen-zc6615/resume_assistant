import pytest
from app_service.core.auth_security import (
    generate_token,
    hash_password,
    hash_token,
    normalize_username,
    verify_password,
    verify_token,
)


def test_normalize_username():
    assert normalize_username(" HR_Admin ") == "hr_admin"
    assert normalize_username("hr_user") == "hr_user"


def test_hash_and_verify_password():
    password = "TestPassword123!"
    password_hash = hash_password(password)
    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("WrongPassword123!", password_hash) is False



def test_same_password_generates_different_hashes():
    first_hash = hash_password("SamePassword123!")
    second_hash = hash_password("SamePassword123!")
    assert first_hash != second_hash
    assert verify_password("SamePassword123!", first_hash) is True
    assert verify_password("SamePassword123!", second_hash) is True


def test_empty_password_is_rejected():
    with pytest.raises(ValueError, match="密码不能为空"):
        hash_password("")


def test_password_over_72_bytes_is_rejected():
    oversized_password = "a" * 73
    with pytest.raises(ValueError, match="72"):
        hash_password(oversized_password)


def test_invalid_password_hash_returns_false():
    assert verify_password("TestPassword123!", "not-a-bcrypt-hash") is False


def test_generate_and_hash_token():
    first_token = generate_token()
    second_token = generate_token()
    assert first_token != second_token
    token_hash = hash_token(first_token)
    assert token_hash != first_token
    assert len(token_hash) == 64


def test_verify_token():
    token = generate_token()
    token_hash = hash_token(token)
    assert verify_token(token, token_hash) is True
    assert verify_token("fake-token", token_hash) is False
    assert verify_token("", token_hash) is False
