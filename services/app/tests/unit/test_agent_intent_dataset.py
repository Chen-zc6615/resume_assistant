from __future__ import annotations

import json
from pathlib import Path

from app_service.services.agent_service import AgentIntent


def test_intent_golden_dataset_covers_closed_world_labels():
    path = Path(__file__).parents[2] / "evals" / "agent_intents" / "golden.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) >= 10
    labels = {row["intent"] for row in rows}
    assert labels == {intent.value for intent in AgentIntent}
    assert all(row["text"].strip() for row in rows)
