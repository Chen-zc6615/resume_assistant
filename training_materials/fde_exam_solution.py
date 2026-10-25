# /// script
# requires-python = ">=3.12"
# dependencies = ["sqlglot>=26,<30"]
# ///
"""第二阶段 FDE 考核的可复现实操答案。"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlglot import exp, parse
from sqlglot.errors import ParseError

SHANGHAI = ZoneInfo("Asia/Shanghai")
POLICY_CUTOFF = date(2024, 3, 1)
OLD_DAILY_LIMIT = 600.0
NEW_DAILY_LIMIT = 800.0


def timestamp() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class AuditCalculation:
    ticket_id: str
    policy_version: str
    invoice_date: str
    daily_limit: float
    days: int
    claimed_amount: float
    approved_amount: float
    overage_amount: float
    citation: str


def calculate_reimbursement(
    *, ticket_id: str, invoice_date: date, days: int, claimed_amount: float
) -> AuditCalculation:
    if days <= 0 or claimed_amount < 0:
        raise ValueError("天数必须为正数，申报金额不得为负数")
    if invoice_date < POLICY_CUTOFF:
        version = "2022旧规（2024-03-01前适用）"
        limit = OLD_DAILY_LIMIT
        citation = "WIKI-FIN-AUDIT-202404#历史制度过渡期"
    else:
        version = "202403版新规（2024-03-01起适用）"
        limit = NEW_DAILY_LIMIT
        citation = "WIKI-FIN-TRAVEL-202403#住宿标准"
    approved = min(claimed_amount, limit * days)
    return AuditCalculation(
        ticket_id=ticket_id,
        policy_version=version,
        invoice_date=invoice_date.isoformat(),
        daily_limit=limit,
        days=days,
        claimed_amount=round(claimed_amount, 2),
        approved_amount=round(approved, 2),
        overage_amount=round(claimed_amount - approved, 2),
        citation=citation,
    )


class SecurityViolationError(RuntimeError):
    pass


class SafeSQLGateway:
    ALLOWED_TABLES = {"tb_travel_expense", "tb_audit_records"}
    MAX_ROWS = 100

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            """CREATE TABLE tb_travel_expense (
                ticket_id TEXT PRIMARY KEY,
                employee_name TEXT NOT NULL,
                amount REAL NOT NULL
            )"""
        )
        self.connection.execute(
            "INSERT INTO tb_travel_expense VALUES (?, ?, ?)",
            ("EXP20240315-01", "周建华", 2400.0),
        )
        self.connection.commit()

    def validate(self, sql: str) -> str:
        try:
            statements = parse(sql, read="sqlite")
        except ParseError as exc:
            raise SecurityViolationError(f"SQL 语法解析失败：{exc}") from exc
        if len(statements) != 1:
            raise SecurityViolationError("只允许执行一条 SQL，已拦截多语句注入")

        tree = statements[0]
        if not isinstance(tree, exp.Select):
            raise SecurityViolationError("只允许 SELECT 查询")
        forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Command)
        if any(tree.find(node_type) is not None for node_type in forbidden):
            raise SecurityViolationError("AST 检测到写操作或管理命令")

        tables = {table.name.lower() for table in tree.find_all(exp.Table)}
        if not tables:
            raise SecurityViolationError("查询必须访问授权业务表")
        unauthorized = tables - self.ALLOWED_TABLES
        if unauthorized:
            raise SecurityViolationError(
                f"禁止访问未授权表：{', '.join(sorted(unauthorized))}"
            )
        if len(list(tree.find_all(exp.Join))) > 2:
            raise SecurityViolationError("JOIN 数量超过安全上限")

        if tree.args.get("limit") is None:
            tree = tree.limit(self.MAX_ROWS)
        return tree.sql(dialect="sqlite")

    def execute(self, sql: str) -> tuple[str, list[tuple[Any, ...]]]:
        safe_sql = self.validate(sql)
        # 限制 SQLite 虚拟机步数，防止合法 SELECT 构造计算型 DoS。
        steps = 0

        def progress() -> int:
            nonlocal steps
            steps += 1
            return int(steps > 10_000)

        self.connection.set_progress_handler(progress, 100)
        try:
            rows = self.connection.execute(safe_sql).fetchall()
        except sqlite3.OperationalError as exc:
            raise SecurityViolationError(f"查询被资源预算中止：{exc}") from exc
        finally:
            self.connection.set_progress_handler(None, 0)
        return safe_sql, rows


class SimulatedOAGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def submit_clawback(self, payload: dict[str, Any]) -> dict[str, Any]:
        receipt = {
            "receipt_id": f"OA-{uuid.uuid4().hex[:8].upper()}",
            "status": "ACCEPTED",
            **payload,
        }
        self.calls.append(receipt)
        return receipt


class ApprovalGate:
    def __init__(self, secret: str, gateway: SimulatedOAGateway, ttl_seconds: int = 300):
        if len(secret) < 24:
            raise ValueError("审批密钥至少 24 个字符")
        self.secret = secret.encode()
        self.gateway = gateway
        self.ttl_seconds = ttl_seconds
        self.snapshots: dict[str, dict[str, Any]] = {}

    def suspend(self, *, ticket_id: str, clawback_amount: float) -> dict[str, Any]:
        token_id = f"token_approve_{uuid.uuid4().hex[:10]}"
        expires_at = int(time.time()) + self.ttl_seconds
        payload = {"ticket_id": ticket_id, "clawback_amount": clawback_amount}
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
        signed = f"{token_id}|{expires_at}|{payload_hash}"
        signature = hmac.new(self.secret, signed.encode(), hashlib.sha256).hexdigest()
        token = f"{token_id}.{signature}"
        self.snapshots[token_id] = {
            "status": "SUSPENDED",
            "expires_at": expires_at,
            "payload_hash": payload_hash,
            "payload": payload,
        }
        return {"status": "SUSPENDED", "token": token, "expires_at": expires_at, **payload}

    def resume(self, token: str, *, approver: str) -> dict[str, Any]:
        try:
            token_id, supplied = token.rsplit(".", 1)
        except ValueError as exc:
            raise SecurityViolationError("审批 Token 格式错误") from exc
        snapshot = self.snapshots.get(token_id)
        if snapshot is None:
            raise SecurityViolationError("审批 Token 不存在")
        if snapshot["status"] != "SUSPENDED":
            raise SecurityViolationError("审批 Token 已消费，禁止重放")
        if time.time() > snapshot["expires_at"]:
            snapshot["status"] = "EXPIRED"
            raise SecurityViolationError("审批 Token 已过期")
        payload_json = json.dumps(snapshot["payload"], sort_keys=True, separators=(",", ":"))
        actual_hash = hashlib.sha256(payload_json.encode()).hexdigest()
        if not hmac.compare_digest(actual_hash, snapshot["payload_hash"]):
            raise SecurityViolationError("审批内容已被篡改")
        signed = f"{token_id}|{snapshot['expires_at']}|{actual_hash}"
        expected = hmac.new(self.secret, signed.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise SecurityViolationError("审批 Token 签名无效")

        snapshot["status"] = "CONSUMED"
        receipt = self.gateway.submit_clawback(
            {**snapshot["payload"], "approved_by": approver}
        )
        return {"status": "RESUMED", "receipt": receipt}


@dataclass(frozen=True)
class Span:
    name: str
    duration_ms: float
    input_tokens: int = 0
    output_tokens: int = 0


class Trace:
    INPUT_USD_PER_M = 0.15
    OUTPUT_USD_PER_M = 0.60

    def __init__(self, name: str) -> None:
        self.trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        self.name = name
        self.started = time.perf_counter()
        self.spans: list[Span] = []

    def add(self, name: str, started: float, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.spans.append(
            Span(name, round((time.perf_counter() - started) * 1000, 3), input_tokens, output_tokens)
        )

    def summary(self) -> dict[str, Any]:
        input_tokens = sum(span.input_tokens for span in self.spans)
        output_tokens = sum(span.output_tokens for span in self.spans)
        cost = (
            input_tokens * self.INPUT_USD_PER_M
            + output_tokens * self.OUTPUT_USD_PER_M
        ) / 1_000_000
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "total_latency_ms": round((time.perf_counter() - self.started) * 1000, 3),
            "total_tokens": input_tokens + output_tokens,
            "total_cost_usd": round(cost, 8),
            "spans": [asdict(span) for span in self.spans],
        }


def run_traced_workflow() -> dict[str, Any]:
    trace = Trace("TravelAudit")
    started = time.perf_counter()
    intent = "TRAVEL_AUDIT"
    trace.add("1.Intent_Routing", started)

    started = time.perf_counter()
    policy = {"daily_limit": OLD_DAILY_LIMIT, "citation": "WIKI-FIN-AUDIT-202404"}
    trace.add("2.Wiki_RAG", started)

    gateway = SafeSQLGateway()
    started = time.perf_counter()
    _, rows = gateway.execute(
        "SELECT ticket_id, employee_name, amount FROM tb_travel_expense "
        "WHERE ticket_id = 'EXP20240315-01' LIMIT 1"
    )
    trace.add("3.Safe_Text2SQL", started)

    started = time.perf_counter()
    calculation = calculate_reimbursement(
        ticket_id="EXP20240220-03",
        invoice_date=date(2024, 2, 20),
        days=2,
        claimed_amount=1800.0,
    )
    trace.add("4.Deterministic_Calculation", started)
    return {
        "intent": intent,
        "policy": policy,
        "database_rows": rows,
        "calculation": asdict(calculation),
        "trace": trace.summary(),
    }


def run_exam() -> None:
    print(f"[{timestamp()}] FDE 实操自检开始")

    result = calculate_reimbursement(
        ticket_id="EXP20240220-03",
        invoice_date=date(2024, 2, 20),
        days=2,
        claimed_amount=1800.0,
    )
    assert result.daily_limit == 600.0
    assert result.approved_amount == 1200.0
    assert result.overage_amount == 600.0
    print(f"[{timestamp()}] TASK1 PASS {json.dumps(asdict(result), ensure_ascii=False)}")

    sql_gateway = SafeSQLGateway()
    # 预热解析器，5ms 断言只度量实际拦截，不计模块导入。
    sql_gateway.validate("SELECT * FROM tb_travel_expense LIMIT 1")
    attacks = [
        "SELECT * FROM tb_travel_expense; DROP TABLE tb_travel_expense; --",
        "SELECT * FROM tb_executive_salary",
    ]
    for attack in attacks:
        started = time.perf_counter()
        try:
            sql_gateway.validate(attack)
            raise AssertionError("恶意 SQL 未被拦截")
        except SecurityViolationError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            assert elapsed < 5.0
            print(f"[{timestamp()}] TASK2 BLOCKED {elapsed:.3f}ms {exc}")
    safe_sql, _ = sql_gateway.execute("SELECT * FROM tb_travel_expense")
    assert "LIMIT 100" in safe_sql.upper()
    assert sql_gateway.connection.execute("SELECT 1").fetchone() == (1,)
    print(f"[{timestamp()}] TASK2 PASS rewritten={safe_sql!r} connection=healthy")

    oa = SimulatedOAGateway()
    gate = ApprovalGate("exam-secret-key-at-least-24-characters", oa)
    suspended = gate.suspend(ticket_id="EXP20240220-03", clawback_amount=600.0)
    assert not oa.calls
    print(f"[{timestamp()}] TASK3 STATUS: SUSPENDED {json.dumps(suspended, ensure_ascii=False)}")
    resumed = gate.resume(suspended["token"], approver="财务主管-测试账号")
    assert len(oa.calls) == 1
    print(f"[{timestamp()}] TASK3 PASS {json.dumps(resumed, ensure_ascii=False)}")

    workflow = run_traced_workflow()
    assert len(workflow["trace"]["spans"]) >= 3
    print(f"[{timestamp()}] TASK4 PASS {json.dumps(workflow['trace'], ensure_ascii=False)}")
    print(f"[{timestamp()}] ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    run_exam()
