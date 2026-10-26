"""受限 Text2SQL：模型产出的 SQL 必须通过 AST 白名单后才可执行。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlglot import exp, parse

from app_service.core.config import get_settings


class UnsafeSQL(ValueError):
    """SQL 不符合只读查询策略。"""


# Agent 只需要招聘分析字段。认证、Agent 审计表、简历原文和文件地址均不开放。
ALLOWED_SCHEMA: dict[str, frozenset[str]] = {
    "requirements": frozenset({
        "requirement_id", "requirement_name", "dept", "deadline", "description",
        "status", "created_by", "created_at", "updated_at",
    }),
    "jobs": frozenset({
        "job_id", "requirement_id", "job_code", "headcount", "major", "job_name",
        "job_jd", "job_min_degree", "job_min_exp_years", "job_required_skills",
        "job_optional_skills", "bonus_items", "job_status", "job_created_by", "created_at", "updated_at",
    }),
    "resumes": frozenset({
        "resume_id", "original_file_name", "status", "failure_reason",
        "interview_status", "created_at", "updated_at",
    }),
    "resume_profiles": frozenset({
        "resume_id", "name", "gender", "highest_education",
        "graduation_institution", "total_work_months", "phone", "email",
        "created_at", "updated_at",
    }),
    "profile_skills": frozenset({"id", "resume_id", "skill_name"}),
    "education_experiences": frozenset({
        "education_id", "resume_id", "school", "major", "education_level", "start_date", "end_date", "is_current",
    }),
    "work_experiences": frozenset({
        "work_id", "resume_id", "company", "position", "start_date", "end_date", "is_current", "description",
    }),
    "project_experiences": frozenset({
        "project_id", "resume_id", "project_name", "role", "start_date", "end_date", "description",
    }),
    "requirement_resume_groups": frozenset({
        "id", "requirement_id", "resume_id", "added_by", "created_at", "updated_at",
    }),
    "job_resume_groups": frozenset({
        "id", "job_id", "resume_id", "added_by", "match_detail", "created_at", "updated_at",
    }),
    "filter_runs": frozenset({
        "run_id", "template_id", "job_id", "status", "total", "passed", "rejected",
        "pending_review", "created_at", "updated_at",
    }),
    "filter_results": frozenset({
        "result_id", "run_id", "resume_id", "result", "reasons",
    }),
    "interviews": frozenset({
        "interview_id", "resume_id", "job_id", "interview_time", "way", "interviewer",
        "note", "notify_way", "created_by", "created_at", "updated_at",
    }),
    "talent_pool": frozenset({
        "pool_id", "resume_id", "source_requirement_id", "source_job_id", "note", "created_by",
        "knowledge_sync_status", "knowledge_talent_card_id", "knowledge_chunk_count",
        "knowledge_sync_error", "knowledge_synced_at", "created_at", "updated_at",
    }),
}

SENSITIVE_COLUMNS = frozenset({"phone", "email"})
ALLOWED_FUNCTIONS = frozenset({
    "AND", "ARRAY_AGG", "AVG", "BOOL_AND", "BOOL_OR", "COALESCE", "COUNT",
    "DATE_TRUNC", "EXTRACT", "JSON_AGG", "LENGTH", "LOWER", "MAX", "MIN",
    "NOT", "OR", "STRING_AGG", "SUM", "UPPER",
})
_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Merge, exp.Transaction,
)


def schema_prompt() -> str:
    lines = ["可查询数据库结构（仅下列字段）："]
    for table, columns in ALLOWED_SCHEMA.items():
        lines.append(f"- {table}({', '.join(sorted(columns))})")
    lines.append("phone/email 只能用于 IS NULL/IS NOT NULL 等布尔判断，禁止直接返回。")
    return "\n".join(lines)


def validate_and_rewrite_sql(sql: str, *, max_rows: int | None = None) -> tuple[str, list[str]]:
    """验证单条 SELECT，并强制 LIMIT；返回规范 SQL 和涉及的表。"""
    limit = max_rows or get_settings().agent_max_result_rows
    raw_sql = sql.strip().rstrip(";")
    if "--" in raw_sql or "/*" in raw_sql or "*/" in raw_sql:
        raise UnsafeSQL("禁止 SQL 注释")
    try:
        statements = parse(raw_sql, read="postgres")
    except Exception as exc:
        raise UnsafeSQL("SQL 语法无效") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsafeSQL("只允许一条 SELECT 查询")
    statement = statements[0]
    if any(statement.find(node) is not None for node in _FORBIDDEN_NODES):
        raise UnsafeSQL("查询包含写入或管理语句")
    if statement.args.get("locks") or statement.args.get("into"):
        raise UnsafeSQL("禁止锁定或 SELECT INTO 查询")
    if statement.find(exp.Star) is not None:
        raise UnsafeSQL("禁止 SELECT *，必须显式列出字段")

    aliases: dict[str, str] = {}
    tables: list[str] = []
    for table_node in statement.find_all(exp.Table):
        table_name = table_node.name.lower()
        if table_name not in ALLOWED_SCHEMA:
            raise UnsafeSQL(f"不允许访问表：{table_name}")
        if table_node.db or table_node.catalog:
            raise UnsafeSQL("禁止跨 schema 或跨数据库查询")
        aliases[table_node.alias_or_name.lower()] = table_name
        if table_name not in tables:
            tables.append(table_name)
    if not tables:
        raise UnsafeSQL("查询必须访问允许的业务表")

    for column in statement.find_all(exp.Column):
        column_name = column.name.lower()
        if column.table:
            table_name = aliases.get(column.table.lower())
            if table_name is None or column_name not in ALLOWED_SCHEMA[table_name]:
                raise UnsafeSQL(f"不允许访问字段：{column.sql()}")
        elif not any(column_name in ALLOWED_SCHEMA[table] for table in tables):
            # CTE/聚合别名可能在 ORDER BY 中引用；仅允许确实由 SELECT 产生的别名。
            projection_aliases = {item.alias.lower() for item in statement.expressions if item.alias}
            if column_name not in projection_aliases:
                raise UnsafeSQL(f"不允许访问字段：{column_name}")

    for function in statement.find_all(exp.Func):
        name = function.sql_name().upper()
        if name not in ALLOWED_FUNCTIONS:
            raise UnsafeSQL(f"不允许使用函数：{name}")

    for projection in statement.expressions:
        direct = projection.this if isinstance(projection, exp.Alias) else projection
        sensitive = [
            column for column in direct.find_all(exp.Column)
            if column.name.lower() in SENSITIVE_COLUMNS
        ]
        for column in sensitive:
            # 敏感字段只允许形成 `phone IS [NOT] NULL` 这样的存在性信号。
            if not isinstance(column.parent, exp.Is) or not isinstance(column.parent.expression, exp.Null):
                raise UnsafeSQL(f"敏感字段 {column.name} 只能用于空值布尔判断")

    current_limit = statement.args.get("limit")
    if current_limit is None:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(limit)))
    else:
        limit_expr = current_limit.expression
        if not isinstance(limit_expr, exp.Literal) or not limit_expr.is_int:
            raise UnsafeSQL("LIMIT 必须是整数常量")
        if int(limit_expr.this) > limit:
            current_limit.set("expression", exp.Literal.number(limit))
    return statement.sql(dialect="postgres"), tables


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return value


def execute_readonly(db: Session, sql: str) -> dict[str, Any]:
    """在当前事务内执行校验后的 SQL，不提交任何事务。"""
    settings = get_settings()
    safe_sql, tables = validate_and_rewrite_sql(sql)
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        # 独立事务既保证数据库级只读，也不会把调用方随后持久化消息/动作的事务设为只读。
        with db.get_bind().connect() as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text(f"SET LOCAL statement_timeout = {int(settings.agent_sql_timeout_ms)}"))
                rows = connection.execute(text(safe_sql)).mappings().all()
    else:
        rows = db.execute(text(safe_sql)).mappings().all()
    serialized = [
        {key: _json_value(value) for key, value in row.items() if key.lower() not in SENSITIVE_COLUMNS}
        for row in rows
    ]
    return {
        "sql": safe_sql,
        "row_count": len(serialized),
        "rows": serialized,
        "sources": [f"DB:{table}" for table in tables],
    }
