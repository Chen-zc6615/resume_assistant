import pytest
from app_service.models.schemas import LoginRequest
from pydantic import ValidationError


def test_valid_login_request():
    request = LoginRequest(
        username="  HR_Admin  ",
        password="TestPassword123!",
    )

    assert request.username == "HR_Admin"
    assert request.password == "TestPassword123!"


def test_blank_username_is_rejected():
    with pytest.raises(ValidationError):
        LoginRequest(
            username="   ",
            password="TestPassword123!",
        )


def test_blank_password_is_rejected():
    with pytest.raises(ValidationError):
        LoginRequest(
            username="hr_admin",
            password="",
        )


def test_password_whitespace_is_preserved():
    request = LoginRequest(
        username="hr_admin",
        password=" password ",
    )
    assert request.password == " password "



def test_oversized_password_is_rejected():
    oversized_password = "密" * 25
    with pytest.raises(ValidationError):
        LoginRequest(
            username="hr_admin",
            password=oversized_password,
        )
