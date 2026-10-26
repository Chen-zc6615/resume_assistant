from __future__ import annotations

import pytest
from app_service.services.safe_text2sql import UnsafeSQL, validate_and_rewrite_sql


def test_accepts_joined_select_and_injects_limit():
    sql, tables = validate_and_rewrite_sql(
        "SELECT p.name, s.skill_name FROM resume_profiles p "
        "JOIN profile_skills s ON s.resume_id = p.resume_id WHERE s.skill_name = 'Python'"
    )
    assert "LIMIT 50" in sql
    assert tables == ["resume_profiles", "profile_skills"]


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM resumes",
        "SELECT * FROM resumes",
        "SELECT raw_text FROM resumes",
        "SELECT password_hash FROM auth_users",
        "SELECT phone FROM resume_profiles",
        "SELECT concat(phone, '') AS leaked FROM resume_profiles",
        "SELECT pg_read_file('/etc/passwd') AS leaked FROM jobs",
        "SELECT pg_sleep(10) AS delayed FROM jobs",
        "SELECT job_name FROM jobs FOR UPDATE",
        "SELECT job_name FROM jobs -- bypass",
        "SELECT name FROM public.resume_profiles",
        "SELECT name FROM resume_profiles; SELECT job_name FROM jobs",
    ],
)
def test_rejects_unsafe_sql(sql: str):
    with pytest.raises(UnsafeSQL):
        validate_and_rewrite_sql(sql)


def test_sensitive_columns_can_only_be_used_as_boolean_signal():
    sql, _ = validate_and_rewrite_sql(
        "SELECT name, (phone IS NOT NULL AND email IS NOT NULL) AS contact_complete "
        "FROM resume_profiles LIMIT 200"
    )
    assert "contact_complete" in sql
    assert "LIMIT 50" in sql


def test_only_known_columns_are_allowed():
    with pytest.raises(UnsafeSQL, match="not_a_column"):
        validate_and_rewrite_sql("SELECT not_a_column FROM jobs")
