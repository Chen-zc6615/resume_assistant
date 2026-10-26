#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
执行链路：岗位描述检索简历切片 → 唯一标识查询数据库事实 →
LLM 生成辅助复核意见 → HR 审批 → 模拟面试邀约。

自动淘汰只读取数据库中已有的确定性筛选结果；LLM 不产生 PASS/REJECT。
"""

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "services" / "app" / "src"))
sys.path.insert(0, str(WORKSPACE_ROOT))

load_dotenv(WORKSPACE_ROOT / ".env")

from app_service.db.session import SessionLocal
from app_service.models.db_models import (
    FilterResult,
    FilterRun,
    Job,
    JobResumeGroup,
    Resume,
)

KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "http://127.0.0.1:8001")
LLM_API_KEY = os.environ["DASHSCOPE_API_KEY"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_MODEL = f"openai/{os.environ['LLM_MODEL']}"
HITL_SECRET_KEY = os.environ["HITL_SECRET_KEY"]


# ==============================================================================
# 第一部分：APM 链路追踪
# ==============================================================================

class LangfuseTraceRecord:
    """轻量级 APM 遥测追踪记录器 (承接 Day 17 APM 规范)。"""

    def __init__(self, trace_id: str, name: str):
        self.trace_id = trace_id
        self.name = name
        self.spans: List[Dict[str, Any]] = []
        self.start_time = time.time()
        self.total_tokens = 0
        self.total_cost = 0.0

    def log_span(self, span_name, span_type, input_data, output_data, duration_ms, tokens=None):
        tok = tokens or {"input_tokens": 0, "output_tokens": 0}
        in_t = tok.get("input_tokens", 0)
        out_t = tok.get("output_tokens", 0)
        step_cost = (in_t * 0.00015 + out_t * 0.0006) / 1000.0  # 参照 Qwen 生产费率
        self.total_tokens += in_t + out_t
        self.total_cost += step_cost
        self.spans.append({
            "name": span_name,
            "type": span_type,
            "duration_ms": round(duration_ms, 2),
            "input": input_data,
            "output": output_data,
            "tokens": {"input": in_t, "output": out_t, "total": in_t + out_t},
            "cost_usd": round(step_cost, 6),
        })

    def print_trace_summary(self):
        total_time = (time.time() - self.start_time) * 1000
        print(f"\n📊 [APM 链路追踪拓扑] TraceID: {self.trace_id} | 业务流: {self.name}")
        print(f"┌{'─'*30}┬{'─'*12}┬{'─'*12}┬{'─'*14}┬{'─'*16}┐")
        print(f"│ {'阶段执行节点 (Span Name)':<28} │ {'节点类型':<10} │ {'耗时 (ms)':<10} │ {'Token 消耗':<12} │ {'预估成本 ($)':<14} │")
        print(f"├{'─'*30}┼{'─'*12}┼{'─'*12}┼{'─'*14}┼{'─'*16}┤")
        for s in self.spans:
            print(f"│ {s['name']:<28} │ {s['type']:<10} │ {s['duration_ms']:<10.1f} │ {s['tokens']['total']:<12} │ ${s['cost_usd']:<13.6f} │")
        print(f"└{'─'*30}┴{'─'*12}┴{'─'*12}┴{'─'*14}┴{'─'*16}┘")
        print(f"   ⏱️ 链路总延迟: {total_time:.2f} ms | 累计 Token: {self.total_tokens} | 累计成本: ${self.total_cost:.6f}")


# ==============================================================================
# 第二部分：三大支撑网关
# ==============================================================================

class SafeDatabaseGateway:
    """只读数据库网关：SQLAlchemy ORM 查询，不接受模型生成的 SQL。"""

    def __init__(self):
        self.db: Session = SessionLocal()

    def close(self) -> None:
        self.db.close()

    def query_resume(self, resume_id: int) -> Optional[Dict[str, Any]]:
        """查询简历事实、归一化画像及各岗位最新筛选结果。"""
        resume = self.db.get(Resume, resume_id)
        if resume is None:
            return None

        rows = self.db.execute(
            select(FilterResult, FilterRun, Job)
            .join(FilterRun, FilterRun.run_id == FilterResult.run_id)
            .join(Job, Job.job_id == FilterRun.job_id)
            .join(
                JobResumeGroup,
                (JobResumeGroup.job_id == Job.job_id)
                & (JobResumeGroup.resume_id == FilterResult.resume_id),
            )
            .where(FilterResult.resume_id == resume_id)
            .order_by(FilterResult.result_id.desc())
        ).all()

        # 同一岗位可能重筛多次；按 result_id 倒序只保留每个岗位的最新结果。
        latest: Dict[int, Dict[str, Any]] = {}
        for result, run, job in rows:
            if job.job_id in latest:
                continue
            latest[job.job_id] = {
                "result_id": result.result_id,
                "run_id": run.run_id,
                "job_id": job.job_id,
                "job_name": job.job_name,
                "result": result.result,
                "reasons": result.reasons or [],
                "rules_snapshot": run.rules_snapshot,
            }

        profile = resume.profile
        return {
            "resume_id": resume.resume_id,
            "file_name": resume.original_file_name,
            "status": resume.status,
            "failure_reason": resume.failure_reason,
            "profile": None if profile is None else {
                "profile_id": profile.profile_id,
                "name": profile.name,
                "phone": profile.phone,
                "email": profile.email,
                "highest_education": profile.highest_education,
                "graduation_institution": profile.graduation_institution,
                "total_work_months": profile.total_work_months,
                "skills": [s.skill_name for s in profile.skills],
            },
            "screening_results": list(latest.values()),
        }


class KnowledgeBaseGateway:
    """知识库查询网关。"""

    def __init__(self, base_url: str = KNOWLEDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def search(
        self,
        query: str,
        document_types: List[str],
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        """检索并返回带引用的结果。"""
        response = httpx.post(
            f"{self.base_url}/api/v1/search",
            json={
                "query": query,
                "document_types": document_types,
                "metadata_filter": metadata_filter,
                "top_k": top_k,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "query": data["query"],
            "citations": [
                {
                    "talent_card_id": item["talent_card_id"],
                    "chunk_id": item["chunk_id"],
                    "document_type": item["document_type"],
                    "content": item["content"],
                    "score": item["rerank_score"],
                    "metadata": item["metadata"],
                }
                for item in data["results"]
            ],
            "latency_ms": data["latency_ms"],
        }


class ExternalRecruitmentGateway:
    """外部动作网关：HR 确认后生成模拟邀约回执，真实 API 后续接入。"""

    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []

    def dispatch_interview_invitation(
        self,
        resume_id: int,
        approver_name: str = "HR",
    ) -> Dict[str, Any]:
        """模拟创建面试邀约；回执记录授权人以保证审计可追责。"""
        record = {
            "success": True,
            "action": "CREATE_INTERVIEW_INVITATION",
            "resume_id": resume_id,
            "approver": approver_name,
            "status": "SIMULATED",
            "receipt_id": f"SIM-INTERVIEW-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": time.time(),
        }
        self.call_history.append(record)
        return record


# ==============================================================================
# 第三部分：Pydantic 契约与防篡改签名令牌 (HITL Core)
# ==============================================================================

class JobDecisionPayload(BaseModel):
    """单个岗位的确定性初筛结果。"""

    job_id: int = Field(..., gt=0)
    job_name: str = Field(..., min_length=1)
    result: Literal["PASS", "REJECT", "PENDING_REVIEW"]
    reasons: List[Dict[str, Any]] = Field(default_factory=list)
    rules_snapshot: Dict[str, Any] = Field(default_factory=dict)


class ResumeDecisionPayload(BaseModel):
    """整份简历的多岗位筛选与后续动作契约。

    screening_status 是 overall_result 的序列化别名：
    输出 dict 仍可通过 model_validate 往返校验，不破坏契约单向性。
    """

    model_config = ConfigDict(populate_by_name=True)

    resume_id: int = Field(..., gt=0)
    profile_id: Optional[int] = None
    # 简历未归一化时为 None，严禁为通过校验而编造姓名。
    candidate_name: Optional[str] = None
    resume_status: int = Field(..., ge=0, le=10)
    contact_complete: bool
    overall_result: Literal["PASS", "REJECT", "PENDING_REVIEW", "NO_RESULT"] = Field(
        alias="screening_status",
    )
    job_results: List[JobDecisionPayload] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="知识库检索引用，仅用于解释，不参与淘汰判断",
    )
    action_required: Literal["NONE", "REQUIRE_HUMAN_APPROVAL"]
    proposed_action: Literal["NONE", "CREATE_INTERVIEW_INVITATION"]


class LLMReviewPayload(BaseModel):
    """LLM 仅用于解释和辅助复核，结构上无法表达淘汰结论。"""

    matched_requirements: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    review_suggestion: Literal["RECOMMEND_HR_REVIEW", "INSUFFICIENT_EVIDENCE"]
    # LLM 失败或输出不符契约时降级，不影响确定性决策与 HITL 门禁。
    degraded: bool = Field(default=False)
    degraded_reason: Optional[str] = None


class SignedApprovalTokenManager:
    """HMAC-SHA256 人工审批令牌管理器：签名 + TTL + 防重放一次性消费。"""

    def __init__(self, secret_key: str, default_ttl_sec: int = 3600):
        if len(secret_key) < 24:
            raise ValueError("HITL 签名密钥长度不能少于 24 个字符")
        self.secret_key = secret_key.encode("utf-8")
        self.default_ttl_sec = default_ttl_sec
        # 仅用于演示；生产环境应使用 PostgreSQL 或 Redis 持久化。
        self.snapshot_store: Dict[str, Dict[str, Any]] = {}
        self.consumed_tokens: set[str] = set()

    def generate_token(self, resume_id: int, action_type: str, payload: Dict[str, Any]) -> str:
        """为待 HR 审批的操作生成签名 Token。签名覆盖审批内容哈希。"""
        token_id = f"TOKEN-HITL-{uuid.uuid4().hex[:8].upper()}"
        expires_at = int(time.time()) + self.default_ttl_sec

        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        sign_payload = f"{token_id}|{resume_id}|{action_type}|{expires_at}|{payload_hash}"
        signature = hmac.new(
            self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        full_token = f"{token_id}.{signature}"

        self.snapshot_store[token_id] = {
            "token_id": token_id,
            "resume_id": resume_id,
            "action_type": action_type,
            "expires_at": expires_at,
            "payload_hash": payload_hash,
            "payload": json.loads(payload_json),
            "created_at": int(time.time()),
            "status": "PENDING",
        }
        return full_token

    def verify_and_consume(self, full_token: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """校验签名、Payload 哈希、有效期，并执行一次性消费。"""
        try:
            token_id, provided_signature = full_token.rsplit(".", 1)
        except ValueError:
            return False, "【认证失败】审批令牌格式错误！", None

        if token_id in self.consumed_tokens:
            return False, "【安全违规】审批令牌已被消费，禁止重复提交！", None

        snapshot = self.snapshot_store.get(token_id)
        if snapshot is None:
            return False, "【认证失败】审批令牌不存在或已被销毁！", None

        if time.time() > snapshot["expires_at"]:
            snapshot["status"] = "EXPIRED"
            return False, "【安全超时】审批令牌已超过有效期限！", None

        payload_json = json.dumps(
            snapshot["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        actual_payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_payload_hash, snapshot["payload_hash"]):
            return False, "【安全违规】审批内容已被篡改！", None

        sign_payload = (
            f"{token_id}|{snapshot['resume_id']}|{snapshot['action_type']}|"
            f"{snapshot['expires_at']}|{actual_payload_hash}"
        )
        expected_signature = hmac.new(
            self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(provided_signature, expected_signature):
            return False, "【认证失败】审批令牌签名无效！", None

        self.consumed_tokens.add(token_id)
        snapshot["status"] = "CONSUMED"
        return True, "验证通过", snapshot


# ==============================================================================
# 第四部分：智能简历协同 Agent 核心
# ==============================================================================

class ResumeAgent:
    """
    Day 18 智能简历协同 Agent：
      - 通道 1 (Knowledge RAG): 按岗位描述检索简历切片
      - 通道 2 (Database): 根据切片唯一标识读取简历事实与已有初筛结果
      - 通道 3 (LLM + HITL): 生成辅助复核意见，面试邀约必须人工审批
    """

    def __init__(self):
        self.db_gateway = SafeDatabaseGateway()
        self.action_gateway = ExternalRecruitmentGateway()
        self.token_manager = SignedApprovalTokenManager(HITL_SECRET_KEY)
        self.knowledge_gateway = KnowledgeBaseGateway()

    def close(self) -> None:
        self.db_gateway.close()

    # --- 第一阶：规则认知 (Knowledge RAG) ---
    def _stage1_knowledge_rag(
        self,
        candidate_name: Optional[str],
        job_requirements: str,
    ) -> Dict[str, Any]:
        """检索简历切片。top_k 取 10：平台检索有轻微非确定性，扩容稳定覆盖。"""
        query = job_requirements
        if candidate_name:
            query = f"候选人：{candidate_name}\n岗位要求：{job_requirements}"
        return self.knowledge_gateway.search(
            query=query,
            document_types=["talent_profile"],
            top_k=10,
        )

    # --- 第二阶：事实还原 (Database) ---
    def _stage2_database_text2sql(self, resume_id: int) -> Tuple[Optional[Dict[str, Any]], float]:
        """读取简历事实和确定性初筛结果。"""
        t0 = time.time()
        fact = self.db_gateway.query_resume(resume_id)
        return fact, (time.time() - t0) * 1000

    # --- 第三阶：交叉裁决与 LLM 辅助复核 ---
    def _stage3_cross_reasoning(
        self,
        fact: Dict[str, Any],
        knowledge_result: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], float]:
        """汇总各岗位确定性结果：PASS > PENDING_REVIEW > REJECT > NO_RESULT。"""
        t0 = time.time()

        profile = fact.get("profile") or {}
        contact_complete = bool(profile.get("phone") and profile.get("email"))
        statuses = {item.get("result") for item in fact.get("screening_results", [])}
        if "PASS" in statuses:
            overall_result = "PASS"
        elif "PENDING_REVIEW" in statuses:
            overall_result = "PENDING_REVIEW"
        elif statuses == {"REJECT"}:
            overall_result = "REJECT"
        else:
            overall_result = "NO_RESULT"
        can_prepare_invitation = overall_result == "PASS" and contact_complete

        payload = ResumeDecisionPayload(
            resume_id=fact["resume_id"],
            profile_id=profile.get("profile_id"),
            candidate_name=profile.get("name"),
            resume_status=fact["status"],
            contact_complete=contact_complete,
            overall_result=overall_result,
            job_results=fact.get("screening_results", []),
            citations=knowledge_result.get("citations", []),
            action_required=(
                "REQUIRE_HUMAN_APPROVAL" if can_prepare_invitation else "NONE"
            ),
            proposed_action=(
                "CREATE_INTERVIEW_INVITATION" if can_prepare_invitation else "NONE"
            ),
        )
        return payload.model_dump(by_alias=True), (time.time() - t0) * 1000

    def _stage3_llm_review(
        self,
        job_requirements: str,
        fact: Dict[str, Any],
        citations: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], float, Dict[str, int]]:
        """LLM 生成辅助复核意见；失败降级为 INSUFFICIENT_EVIDENCE，不中断流程。"""
        t0 = time.time()
        profile = fact.get("profile") or {}
        evidence = [item["content"] for item in citations]

        try:
            response = completion(
                model=LLM_MODEL,
                api_key=LLM_API_KEY,
                api_base=LLM_BASE_URL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是招聘复核助手。只能根据输入事实和简历证据进行解释，"
                            "不得编造信息，不得直接决定淘汰，也不得修改数据库筛选结果。"
                            "只输出一个 JSON 对象，且必须包含且仅包含以下字段："
                            '{"matched_requirements": ["..."], '
                            '"missing_requirements": ["..."], '
                            '"evidence": ["..."], '
                            '"review_suggestion": "RECOMMEND_HR_REVIEW 或 INSUFFICIENT_EVIDENCE"}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "job_requirements": job_requirements,
                                "profile": profile,
                                "screening_results": fact.get("screening_results", []),
                                "resume_chunks": evidence,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
            review = LLMReviewPayload.model_validate_json(
                response.choices[0].message.content
            )
            usage = getattr(response, "usage", None)
            tokens = {
                "input_tokens": getattr(usage, "prompt_tokens", 0),
                "output_tokens": getattr(usage, "completion_tokens", 0),
            }
        except Exception as exc:  # 网络/限流/契约校验失败统一降级
            review = LLMReviewPayload(
                review_suggestion="INSUFFICIENT_EVIDENCE",
                degraded=True,
                degraded_reason=f"{type(exc).__name__}: {exc}",
            )
            tokens = {"input_tokens": 0, "output_tokens": 0}
            print(f"   ⚠️ LLM 辅助复核降级（不影响确定性决策）：{review.degraded_reason[:120]}")

        return review.model_dump(), (time.time() - t0) * 1000, tokens

    # --- 第四阶：业务闭环与人机回环门禁 (HITL Action Gate) ---
    def execute_resume_screening(
        self,
        candidate_name: Optional[str],
        job_requirements: str,
    ) -> Dict[str, Any]:
        """按“知识库→数据库→LLM辅助复核→HR审批”执行 Agent 流程。"""
        trace = LangfuseTraceRecord(
            trace_id=f"TR-{uuid.uuid4().hex[:8].upper()}",
            name="Resume_Interview_Pipeline",
        )

        # 知识库是候选人的唯一发现入口，不可用时结构化失败。
        try:
            knowledge_result = self._stage1_knowledge_rag(
                candidate_name=candidate_name,
                job_requirements=job_requirements,
            )
        except Exception as exc:
            return {
                "success": False,
                "error_code": "KNOWLEDGE_BASE_UNAVAILABLE",
                "message": f"知识库检索失败，流程未产生任何动作：{type(exc).__name__}: {exc}",
            }
        trace.log_span(
            "Stage1_ResumeChunks",
            "KNOWLEDGE_RAG",
            {"candidate_name": candidate_name, "job_requirements": job_requirements},
            knowledge_result,
            knowledge_result["latency_ms"],
        )

        candidate_ids = list(dict.fromkeys(
            int(item["metadata"]["source_resume_id"])
            for item in knowledge_result["citations"]
            if item["metadata"].get("source_resume_id") is not None
        ))
        candidates = []
        for resume_id in candidate_ids:
            # 单个候选人失败只跳过自身，不拖垮整批。
            try:
                fact, db_ms = self._stage2_database_text2sql(resume_id)
                if fact is None:
                    continue
                trace.log_span(
                    "Stage2_ResumeFact", "DB_QUERY",
                    {"resume_id": resume_id}, fact, db_ms,
                )

                profile = fact.get("profile") or {}
                if candidate_name and profile.get("name") != candidate_name:
                    continue

                candidate_citations = [
                    item
                    for item in knowledge_result["citations"]
                    if item["metadata"].get("source_resume_id") is not None
                    and int(item["metadata"]["source_resume_id"]) == resume_id
                ]
                verdict, reasoning_ms = self._stage3_cross_reasoning(
                    fact, {"citations": candidate_citations},
                )
                llm_review, llm_ms, llm_tokens = self._stage3_llm_review(
                    job_requirements=job_requirements,
                    fact=fact,
                    citations=candidate_citations,
                )

                approval_token = None
                if verdict["proposed_action"] == "CREATE_INTERVIEW_INVITATION":
                    # Token 快照携带决策上下文，HR 审批时无需回查数据库。
                    approval_token = self.token_manager.generate_token(
                        resume_id=resume_id,
                        action_type="CREATE_INTERVIEW_INVITATION",
                        payload={
                            "resume_id": resume_id,
                            "candidate_name": verdict["candidate_name"],
                            "overall_result": verdict["screening_status"],
                            "job_results": [
                                {
                                    "job_id": item["job_id"],
                                    "job_name": item["job_name"],
                                    "result": item["result"],
                                }
                                for item in verdict["job_results"]
                            ],
                            "llm_review": llm_review,
                        },
                    )

                trace.log_span(
                    "Stage3_InterviewReview", "LLM_ASSISTED_REVIEW",
                    {"resume_id": resume_id},
                    {"deterministic": verdict, "llm_review": llm_review},
                    reasoning_ms + llm_ms, tokens=llm_tokens,
                )
                trace.log_span(
                    "Stage4_ActionGate", "HITL_GATE",
                    {"resume_id": resume_id},
                    {
                        "action_required": verdict["action_required"],
                        "approval_token_created": approval_token is not None,
                    },
                    0.0,
                )
                candidates.append({
                    "resume_id": resume_id,
                    "decision": verdict,
                    "llm_review": llm_review,
                    "approval_token": approval_token,
                })
            except Exception as exc:
                trace.log_span(
                    "Stage2_ResumeFact", "DB_QUERY",
                    {"resume_id": resume_id},
                    {"skipped_error": f"{type(exc).__name__}: {exc}"},
                    0.0,
                )
                print(f"   ⚠️ 候选人 {resume_id} 处理失败，已跳过：{type(exc).__name__}: {exc}")
                continue

        trace.print_trace_summary()

        return {
            "success": True,
            "candidates": candidates,
        }

    def resume_human_approval(
        self,
        approval_token: str,
        approve: bool,
        approver_name: str = "HR",
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """验签并消费 Token 后执行决定；一次决定终结流程，审批人落痕可审计。"""
        valid, message, snapshot = self.token_manager.verify_and_consume(approval_token)
        if not valid:
            return {
                "success": False,
                "error_code": "TOKEN_VERIFICATION_FAILED",
                "message": message,
            }

        if not approve:
            return {
                "success": True,
                "status": "REJECTED_BY_HUMAN",
                "approver": approver_name,
                "message": (
                    f"{approver_name} 已拒绝面试邀约。"
                    + (f"理由：{rejection_reason}" if rejection_reason else "")
                ),
            }

        payload = snapshot["payload"]
        receipt = self.action_gateway.dispatch_interview_invitation(
            resume_id=payload["resume_id"],
            approver_name=approver_name,
        )
        return {
            "success": True,
            "status": "INTERVIEW_INVITATION_SIMULATED",
            "approver": approver_name,
            "receipt": receipt,
            "message": f"{approver_name} 已批准，模拟面试邀约动作执行完成。",
        }


# ==============================================================================
# 第五部分：端到端验收演练
# ==============================================================================

def run_auto_reject_case(agent: ResumeAgent, candidate_name: str, job_requirements: str) -> Dict[str, Any]:
    """验收场景 1：确定性初筛拒绝，不进入人工审批。"""
    print("\n" + "▶" * 4 + " 【验收场景 1】候选人自动拒绝")
    print(f"👤 候选人：{candidate_name}")
    print(f"📋 岗位要求：{job_requirements}")

    result = agent.execute_resume_screening(
        candidate_name=candidate_name,
        job_requirements=job_requirements,
    )
    assert result["success"] is True
    assert result["candidates"]

    candidate = result["candidates"][0]
    decision = candidate["decision"]
    assert decision["screening_status"] == "REJECT"
    assert decision["action_required"] == "NONE"
    assert candidate["approval_token"] is None

    print(f"📚 知识库：检索到 {len(decision['citations'])} 个简历切片")
    print("🗄️ 数据库：读取到确定性初筛结果 REJECT")
    print(f"🤖 LLM：辅助复核意见 {candidate['llm_review']}")
    print("🚫 最终结果：自动拒绝，不进入人工审批")
    return result


def run_human_approval_case(agent: ResumeAgent, job_requirements: str) -> Dict[str, Any]:
    """验收场景 2：岗位检索命中已通过候选人，触发 HR 审批。"""
    print("\n" + "▶" * 4 + " 【验收场景 2】候选人面试邀约人工审批")
    print(f"📋 岗位要求：{job_requirements}")

    result = agent.execute_resume_screening(
        candidate_name=None,
        job_requirements=job_requirements,
    )
    assert result["success"] is True

    candidate = next(
        (item for item in result["candidates"] if item["approval_token"] is not None),
        None,
    )
    assert candidate is not None, "没有找到可进入人工审批的 PASS 候选人"
    decision = candidate["decision"]

    assert decision["screening_status"] == "PASS"
    assert decision["action_required"] == "REQUIRE_HUMAN_APPROVAL"
    assert decision["proposed_action"] == "CREATE_INTERVIEW_INVITATION"

    print(f"📚 知识库：检索到 {len(decision['citations'])} 个简历切片")
    print(f"👤 候选人：{decision['candidate_name'] or '（简历未归一化）'}")
    print("🗄️ 数据库：确认候选人已通过确定性初筛")
    print(f"🤖 LLM：辅助复核意见 {candidate['llm_review']}")
    print(f"🔑 审批 Token：{candidate['approval_token']}")
    print("⏸️ 当前状态：等待 HR 人工审批")
    return candidate


def run_token_security_case(agent: ResumeAgent, approval_token: str) -> Dict[str, Any]:
    """验收场景 3：有效审批、防重放、伪造/错签名/内容篡改五重拦截。"""
    print("\n" + "▶" * 4 + " 【验收场景 3】Token 安全攻防")

    approval_result = agent.resume_human_approval(
        approval_token=approval_token,
        approve=True,
        approver_name="李敏 (HR 总监)",
    )
    assert approval_result["success"] is True
    assert approval_result["approver"] == "李敏 (HR 总监)"
    assert approval_result["receipt"]["approver"] == "李敏 (HR 总监)"
    print(f"✅ 首次审批结果：{approval_result['message']}")

    print("   [攻击模拟 A] 重复提交已经消费的 Token")
    replay_result = agent.resume_human_approval(approval_token=approval_token, approve=True)
    assert replay_result["success"] is False
    print(f"🛡️ 防重放拦截：{replay_result['message']}")

    print("   [攻击模拟 B] 提交伪造 Token")
    forged_result = agent.resume_human_approval(
        approval_token="TOKEN-HITL-FAKED001.invalid-signature", approve=True,
    )
    assert forged_result["success"] is False
    print(f"🛡️ 伪造 Token 拦截：{forged_result['message']}")

    print("   [攻击模拟 C] 令牌存在但签名被篡改（触发 HMAC 验签分支）")
    valid_token = agent.token_manager.generate_token(
        resume_id=1,
        action_type="CREATE_INTERVIEW_INVITATION",
        payload={"resume_id": 1, "candidate_name": "攻击样本"},
    )
    valid_id, _ = valid_token.rsplit(".", 1)
    bad_signature_result = agent.resume_human_approval(
        approval_token=f"{valid_id}.{'0' * 64}", approve=True,
    )
    assert bad_signature_result["success"] is False
    assert "签名无效" in bad_signature_result["message"]
    print(f"🛡️ 签名校验拦截：{bad_signature_result['message']}")

    print("   [攻击模拟 D] 快照审批内容被篡改（触发 payload_hash 防篡改分支）")
    tampered_token = agent.token_manager.generate_token(
        resume_id=1,
        action_type="CREATE_INTERVIEW_INVITATION",
        payload={"resume_id": 1, "candidate_name": "原始内容"},
    )
    tampered_id, _ = tampered_token.rsplit(".", 1)
    agent.token_manager.snapshot_store[tampered_id]["payload"]["candidate_name"] = "被篡改内容"
    tampered_result = agent.resume_human_approval(
        approval_token=tampered_token, approve=True,
    )
    assert tampered_result["success"] is False
    assert "篡改" in tampered_result["message"]
    print(f"🛡️ 防篡改拦截：{tampered_result['message']}")

    return {
        "approval": approval_result,
        "replay": replay_result,
        "forged": forged_result,
        "bad_signature": bad_signature_result,
        "tampered": tampered_result,
    }


def run_human_rejection_case(agent: ResumeAgent, candidate: Dict[str, Any]) -> Dict[str, Any]:
    """验收场景 4：HR 驳回面试邀约，驳回后令牌不可再批准。"""
    print("\n" + "▶" * 4 + " 【验收场景 4】HR 驳回面试邀约")
    decision = candidate["decision"]
    print(f"👤 候选人：{decision['candidate_name'] or '（简历未归一化）'}")

    rejection_token = agent.token_manager.generate_token(
        resume_id=candidate["resume_id"],
        action_type="CREATE_INTERVIEW_INVITATION",
        payload={
            "resume_id": candidate["resume_id"],
            "candidate_name": decision["candidate_name"],
        },
    )
    calls_before_rejection = len(agent.action_gateway.call_history)
    rejection_result = agent.resume_human_approval(
        approval_token=rejection_token,
        approve=False,
        approver_name="张明 (HR 副总监)",
        rejection_reason="候选人薪资期望超出岗位预算，本期不予邀约。",
    )
    assert rejection_result["status"] == "REJECTED_BY_HUMAN"
    assert rejection_result["approver"] == "张明 (HR 副总监)"
    assert len(agent.action_gateway.call_history) == calls_before_rejection, (
        "驳回分支不得触发外部邀约动作"
    )
    print(f"❌ 驳回结果：{rejection_result['message']}")

    print("   [攻击模拟] 驳回后试图用同一 Token 再批准")
    replay_after_reject = agent.resume_human_approval(
        approval_token=rejection_token, approve=True,
    )
    assert replay_after_reject["success"] is False
    print(f"🛡️ 令牌已消费拦截：{replay_after_reject['message']}")
    return rejection_result


def run_enterprise_triad_showcase():
    """依次运行自动拒绝、人工审批、Token 安全攻防和人工驳回四个场景。

    用例参数内联（原先经 DAY18_* 环境变量注入，但 shell export 的旧值
    优先级高于 .env，且需按向量库/数据库中的真实筛选结果校准）：
    - REJECT 用例：周晓东（后端年限不足，两岗硬性初筛 REJECT），
      检索词取其简历特征「后端实习生」以稳定命中知识库切片；
    - PASS 审批用例：电商前端岗位要求，命中已通过且联系方式完整的候选人。
    """
    candidate_name = "周晓东"
    reject_job_requirements = "后端实习生"
    approval_job_requirements = "电商前端"

    print("=" * 88)
    print(
        "🚀 Day 18 智能简历协同 Agent "
        "(知识库 + 数据库 + LLM + API + HITL) 全链路验收"
    )
    print("=" * 88)

    agent = ResumeAgent()
    try:
        run_auto_reject_case(
            agent=agent,
            candidate_name=candidate_name,
            job_requirements=reject_job_requirements,
        )
        approval_candidate = run_human_approval_case(
            agent=agent,
            job_requirements=approval_job_requirements,
        )
        run_token_security_case(
            agent=agent,
            approval_token=approval_candidate["approval_token"],
        )
        run_human_rejection_case(
            agent=agent,
            candidate=approval_candidate,
        )
    finally:
        agent.close()

    print("\n" + "=" * 88)
    print("🏁 四个场景全部完成：自动拒绝、人工审批、Token 安全攻防、人工驳回")
    print("=" * 88)


if __name__ == "__main__":
    run_enterprise_triad_showcase()
