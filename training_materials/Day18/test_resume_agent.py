#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resume_agent.py 全链路验收测试。

依赖真实环境：知识库(:8001) + PostgreSQL(:5432)；LLM 失败自动降级不阻塞验收。
覆盖四个验收场景：
  1. 确定性初筛拒绝（不进入人工审批）
  2. PASS 候选人触发 HR 审批
  3. Token 安全攻防（重放/伪造/错签名/内容篡改）
  4. HR 驳回邀约（驳回后令牌不可再批准）

运行：uv run pytest 培训文档/Day18/test_resume_agent.py -v
"""

import sys
from pathlib import Path

DAY18_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DAY18_DIR))

import httpx
import pytest

import resume_agent as ra


def _env_ready() -> bool:
    try:
        httpx.get(ra.KNOWLEDGE_BASE_URL, timeout=2)
    except Exception:
        return False
    try:
        from sqlalchemy import text

        db = ra.SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        return False
    return True


ENV_READY = _env_ready()


@pytest.mark.skipif(
    not ENV_READY,
    reason="知识库(:8001) 或 PostgreSQL(:5432) 不可达，跳过全链路验收",
)
class TestFullPipelineAcceptance:

    def test_scenario_1_auto_reject(self):
        """场景 1：确定性初筛拒绝，不进入人工审批。"""
        agent = ra.ResumeAgent()
        try:
            ra.run_auto_reject_case(
                agent=agent,
                candidate_name="周晓东",
                job_requirements="后端实习生",
            )
        finally:
            agent.close()

    def test_scenarios_2_3_4_approval_security_rejection(self):
        """场景 2/3/4：人工审批 → Token 攻防 → 人工驳回。"""
        agent = ra.ResumeAgent()
        try:
            candidate = ra.run_human_approval_case(
                agent=agent,
                job_requirements="电商前端",
            )
            ra.run_token_security_case(
                agent=agent,
                approval_token=candidate["approval_token"],
            )
            ra.run_human_rejection_case(
                agent=agent,
                candidate=candidate,
            )
        finally:
            agent.close()
