from datetime import date

import pytest
from fde_exam_solution import (
    ApprovalGate,
    SafeSQLGateway,
    SecurityViolationError,
    SimulatedOAGateway,
    calculate_reimbursement,
    run_traced_workflow,
)


def test_old_policy_calculation_is_deterministic():
    result = calculate_reimbursement(
        ticket_id="EXP20240220-03",
        invoice_date=date(2024, 2, 20),
        days=2,
        claimed_amount=1800.0,
    )
    assert result.daily_limit == 600.0
    assert result.approved_amount == 1200.0
    assert result.overage_amount == 600.0


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM tb_travel_expense; DROP TABLE tb_travel_expense",
        "SELECT * FROM tb_executive_salary",
        "DELETE FROM tb_travel_expense",
    ],
)
def test_sql_ast_blocks_unsafe_queries(sql):
    with pytest.raises(SecurityViolationError):
        SafeSQLGateway().validate(sql)


def test_sql_ast_injects_limit():
    safe_sql, rows = SafeSQLGateway().execute("SELECT * FROM tb_travel_expense")
    assert "LIMIT 100" in safe_sql.upper()
    assert len(rows) == 1


def test_hitl_blocks_write_until_valid_resume():
    gateway = SimulatedOAGateway()
    gate = ApprovalGate("exam-secret-key-at-least-24-characters", gateway)
    suspended = gate.suspend(ticket_id="EXP20240220-03", clawback_amount=600.0)
    assert suspended["status"] == "SUSPENDED"
    assert gateway.calls == []

    resumed = gate.resume(suspended["token"], approver="测试审批人")
    assert resumed["status"] == "RESUMED"
    assert len(gateway.calls) == 1
    with pytest.raises(SecurityViolationError, match="禁止重放"):
        gate.resume(suspended["token"], approver="测试审批人")


def test_trace_contains_required_metrics_and_spans():
    summary = run_traced_workflow()["trace"]
    assert len(summary["spans"]) >= 3
    assert summary["total_latency_ms"] >= 0
    assert summary["total_tokens"] >= 0
    assert summary["total_cost_usd"] >= 0
