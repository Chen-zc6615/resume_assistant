"""Baseline the application schema and add talent knowledge sync fields.

This first revision supports both an empty database and the legacy database
that predates Alembic. All creation and additive changes are idempotent so the
existing production schema can be enrolled without losing data.

Revision ID: 20261018_0001
Revises:
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261018_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BASELINE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS requirements (
        requirement_id BIGSERIAL PRIMARY KEY,
        requirement_name VARCHAR(100) NOT NULL,
        dept VARCHAR(100),
        deadline VARCHAR(10),
        description TEXT,
        status SMALLINT NOT NULL,
        created_by VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resumes (
        resume_id BIGSERIAL PRIMARY KEY,
        original_file_name VARCHAR(255) NOT NULL,
        file_key VARCHAR(500) NOT NULL,
        sha256 VARCHAR(64) NOT NULL UNIQUE,
        raw_text TEXT,
        status SMALLINT NOT NULL,
        failure_reason TEXT,
        interview_status SMALLINT,
        uploaded_by VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_accounts (
        user_id BIGSERIAL PRIMARY KEY,
        username VARCHAR(100) NOT NULL,
        display_name VARCHAR(100) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL,
        failed_login_count INTEGER NOT NULL,
        locked_until TIMESTAMP WITH TIME ZONE,
        last_login_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT ck_user_accounts_status CHECK (status IN ('normal', 'disabled')),
        CONSTRAINT ck_user_accounts_failed_login_count CHECK (failed_login_count >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES user_accounts (user_id),
        token_hash VARCHAR(64) NOT NULL,
        csrf_token_hash VARCHAR(64) NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id BIGSERIAL PRIMARY KEY,
        requirement_id BIGINT NOT NULL REFERENCES requirements (requirement_id),
        job_code VARCHAR(20),
        headcount INTEGER,
        major VARCHAR(200),
        job_name VARCHAR(100) NOT NULL,
        job_jd TEXT NOT NULL,
        job_min_degree VARCHAR(20),
        job_min_exp_years SMALLINT,
        job_required_skills JSON,
        job_optional_skills JSON,
        bonus_items JSON,
        job_status SMALLINT NOT NULL,
        job_created_by VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_resume_groups (
        id BIGSERIAL PRIMARY KEY,
        requirement_id BIGINT NOT NULL REFERENCES requirements (requirement_id),
        resume_id BIGINT NOT NULL REFERENCES resumes (resume_id),
        added_by VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT uq_requirement_resume UNIQUE (requirement_id, resume_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_profiles (
        profile_id BIGSERIAL PRIMARY KEY,
        resume_id BIGINT NOT NULL UNIQUE REFERENCES resumes (resume_id),
        name VARCHAR(50) NOT NULL,
        gender INTEGER,
        phone VARCHAR(20),
        email VARCHAR(100),
        highest_education VARCHAR(20),
        graduation_institution VARCHAR(100),
        total_work_months INTEGER,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS education_experiences (
        education_id BIGSERIAL PRIMARY KEY,
        profile_id BIGINT NOT NULL REFERENCES resume_profiles (profile_id),
        school VARCHAR(100) NOT NULL,
        major VARCHAR(100),
        education_level VARCHAR(20),
        start_date VARCHAR(7),
        end_date VARCHAR(7),
        is_current BOOLEAN
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS filter_templates (
        template_id BIGSERIAL PRIMARY KEY,
        template_name VARCHAR(100) NOT NULL,
        job_id BIGINT NOT NULL REFERENCES jobs (job_id),
        rules JSON NOT NULL,
        created_by VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS interviews (
        interview_id BIGSERIAL PRIMARY KEY,
        resume_id BIGINT NOT NULL REFERENCES resumes (resume_id),
        job_id BIGINT REFERENCES jobs (job_id),
        interview_time VARCHAR(30),
        way VARCHAR(50),
        interviewer VARCHAR(100),
        note TEXT,
        notify_way VARCHAR(30),
        created_by VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_resume_groups (
        id BIGSERIAL PRIMARY KEY,
        job_id BIGINT NOT NULL REFERENCES jobs (job_id),
        resume_id BIGINT NOT NULL REFERENCES resumes (resume_id),
        added_by VARCHAR(50) NOT NULL,
        match_detail JSON,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT uq_job_resume UNIQUE (job_id, resume_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_skills (
        id BIGSERIAL PRIMARY KEY,
        profile_id BIGINT NOT NULL REFERENCES resume_profiles (profile_id),
        skill_name VARCHAR(80) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_experiences (
        project_id BIGSERIAL PRIMARY KEY,
        profile_id BIGINT NOT NULL REFERENCES resume_profiles (profile_id),
        project_name VARCHAR(200) NOT NULL,
        role VARCHAR(100),
        start_date VARCHAR(7),
        end_date VARCHAR(7),
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS talent_pool (
        pool_id BIGSERIAL PRIMARY KEY,
        resume_id BIGINT NOT NULL UNIQUE REFERENCES resumes (resume_id),
        source_requirement_id BIGINT REFERENCES requirements (requirement_id),
        source_job_id BIGINT REFERENCES jobs (job_id),
        note TEXT,
        created_by VARCHAR(50) NOT NULL,
        knowledge_sync_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
        knowledge_document_id VARCHAR(100),
        knowledge_chunk_count INTEGER,
        knowledge_sync_error VARCHAR(500),
        knowledge_synced_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT ck_talent_pool_knowledge_sync_status CHECK (
            knowledge_sync_status IN ('pending', 'syncing', 'success', 'failed')
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS work_experiences (
        work_id BIGSERIAL PRIMARY KEY,
        profile_id BIGINT NOT NULL REFERENCES resume_profiles (profile_id),
        company VARCHAR(150) NOT NULL,
        position VARCHAR(100) NOT NULL,
        start_date VARCHAR(7),
        end_date VARCHAR(7),
        is_current BOOLEAN,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS filter_runs (
        run_id BIGSERIAL PRIMARY KEY,
        template_id BIGINT REFERENCES filter_templates (template_id),
        job_id BIGINT NOT NULL REFERENCES jobs (job_id),
        rules_snapshot JSON NOT NULL,
        status SMALLINT NOT NULL,
        total INTEGER NOT NULL,
        passed INTEGER NOT NULL,
        rejected INTEGER NOT NULL,
        pending_review INTEGER NOT NULL,
        finished_at TIMESTAMP WITHOUT TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS filter_results (
        result_id BIGSERIAL PRIMARY KEY,
        run_id BIGINT NOT NULL REFERENCES filter_runs (run_id),
        resume_id BIGINT NOT NULL REFERENCES resumes (resume_id),
        profile_id BIGINT REFERENCES resume_profiles (profile_id),
        result VARCHAR(20) NOT NULL,
        reasons JSON NOT NULL
    )
    """,
)


def upgrade() -> None:
    for statement in _BASELINE_TABLES:
        op.execute(statement)

    # Enrol legacy databases whose talent_pool table predates these columns.
    op.execute(
        """
        ALTER TABLE talent_pool
            ADD COLUMN IF NOT EXISTS knowledge_sync_status
                VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS knowledge_document_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS knowledge_chunk_count INTEGER,
            ADD COLUMN IF NOT EXISTS knowledge_sync_error VARCHAR(500),
            ADD COLUMN IF NOT EXISTS knowledge_synced_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.conname = 'ck_talent_pool_knowledge_sync_status'
                  AND t.relname = 'talent_pool'
                  AND n.nspname = current_schema()
            ) THEN
                ALTER TABLE talent_pool
                    ADD CONSTRAINT ck_talent_pool_knowledge_sync_status
                    CHECK (
                        knowledge_sync_status
                        IN ('pending', 'syncing', 'success', 'failed')
                    );
            END IF;
        END
        $$
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_accounts_username "
        "ON user_accounts (username)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id "
        "ON auth_sessions (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires_at "
        "ON auth_sessions (expires_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_auth_sessions_token_hash "
        "ON auth_sessions (token_hash)"
    )


def downgrade() -> None:
    raise RuntimeError(
        "The initial production baseline is intentionally non-destructive; "
        "restore the pre-deployment backup instead."
    )
