#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "services" / "app" / "src"))
load_dotenv(WORKSPACE_ROOT / ".env")

from app_service.db.session import SessionLocal
from app_service.models.db_models import Job, Requirement, Resume, ResumeProfile
from app_service.services.screen_service import evaluate_profile, rules_from_job

KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "http://127.0.0.1:8001")
LLM_API_KEY = os.environ["DASHSCOPE_API_KEY"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_MODEL = f"openai/{os.environ['LLM_MODEL']}"
HITL_SECRET_KEY = os.environ["HITL_SECRET_KEY"]


class LangfuseTraceRecord:
    """本文件使用的轻量 APM 输出，保持 resume_agent 的控制台格式。"""

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
        step_cost = (in_t * 0.00015 + out_t * 0.0006) / 1000.0
        self.total_tokens += in_t + out_t
        self.total_cost += step_cost
        self.spans.append({
            "name": span_name,
            "type": span_type,
            "duration_ms": round(duration_ms, 2),
            "tokens": {"total": in_t + out_t},
            "cost_usd": round(step_cost, 6),
        })

    def print_trace_summary(self):
        total_time = (time.time() - self.start_time) * 1000
        print(f"\n📊 [APM 链路追踪拓扑] TraceID: {self.trace_id} | 业务流: {self.name}")
        print(f"┌{'─'*30}┬{'─'*12}┬{'─'*12}┬{'─'*14}┬{'─'*16}┐")
        print(f"│ {'阶段执行节点 (Span Name)':<28} │ {'节点类型':<10} │ {'耗时 (ms)':<10} │ {'Token 消耗':<12} │ {'预估成本 ($)':<14} │")
        print(f"├{'─'*30}┼{'─'*12}┼{'─'*12}┼{'─'*14}┼{'─'*16}┤")
        for span in self.spans:
            print(f"│ {span['name']:<28} │ {span['type']:<10} │ {span['duration_ms']:<10.1f} │ {span['tokens']['total']:<12} │ ${span['cost_usd']:<13.6f} │")
        print(f"└{'─'*30}┴{'─'*12}┴{'─'*12}┴{'─'*14}┴{'─'*16}┘")
        print(f"   ⏱️ 链路总延迟: {total_time:.2f} ms | 累计 Token: {self.total_tokens} | 累计成本: ${self.total_cost:.6f}")


class DatabaseGateway:
    """只读查询简历事实；数据库会话由当前文件管理。"""

    def __init__(self):
        self.db = SessionLocal()

    def close(self) -> None:
        self.db.close()

    def query_resume(self, resume_id: int) -> Optional[Dict[str, Any]]:
        resume = self.db.get(Resume, resume_id)
        if resume is None:
            return None
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
                "skills": [skill.skill_name for skill in profile.skills],
            },
            "screening_results": [],
        }


class KnowledgeBaseGateway:
    """按姓名检索知识库中的简历切片和来源简历 ID。"""

    def __init__(self, base_url: str = KNOWLEDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, document_types: List[str], top_k: int = 3) -> Dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/api/v1/search",
            json={"query": query, "document_types": document_types, "top_k": top_k},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "query": data["query"],
            "citations": [{
                "talent_card_id": item["talent_card_id"],
                "chunk_id": item["chunk_id"],
                "document_type": item["document_type"],
                "content": item["content"],
                "score": item["rerank_score"],
                "metadata": item["metadata"],
            } for item in data["results"]],
            "latency_ms": data["latency_ms"],
        }


class ExternalRecruitmentGateway:
    """HR 批准后只产生内存中的模拟邀约回执，不写真实面试记录。"""

    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []

    def dispatch_interview_invitation(self, resume_id: int, approver_name: str) -> Dict[str, Any]:
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


class SignedApprovalTokenManager:
    """演示用 HMAC 审批令牌，签名、过期和防重放状态仅保存在进程内。"""

    def __init__(self, secret_key: str, default_ttl_sec: int = 3600):
        if len(secret_key) < 24:
            raise ValueError("HITL 签名密钥长度不能少于 24 个字符")
        self.secret_key = secret_key.encode("utf-8")
        self.default_ttl_sec = default_ttl_sec
        self.snapshot_store: Dict[str, Dict[str, Any]] = {}
        self.consumed_tokens: set[str] = set()

    def generate_token(self, resume_id: int, action_type: str, payload: Dict[str, Any]) -> str:
        token_id = f"TOKEN-HITL-{uuid.uuid4().hex[:8].upper()}"
        expires_at = int(time.time()) + self.default_ttl_sec
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        sign_payload = f"{token_id}|{resume_id}|{action_type}|{expires_at}|{payload_hash}"
        signature = hmac.new(self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        self.snapshot_store[token_id] = {
            "resume_id": resume_id,
            "action_type": action_type,
            "expires_at": expires_at,
            "payload_hash": payload_hash,
            "payload": json.loads(payload_json),
            "status": "PENDING",
        }
        return f"{token_id}.{signature}"

    def verify_and_consume(self, full_token: str):
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
        payload_json = json.dumps(snapshot["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        actual_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_hash, snapshot["payload_hash"]):
            return False, "【安全违规】审批内容已被篡改！", None
        sign_payload = f"{token_id}|{snapshot['resume_id']}|{snapshot['action_type']}|{snapshot['expires_at']}|{actual_hash}"
        expected = hmac.new(self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided_signature, expected):
            return False, "【认证失败】审批令牌签名无效！", None
        self.consumed_tokens.add(token_id)
        snapshot["status"] = "CONSUMED"
        return True, "验证通过", snapshot


class JobSelection(BaseModel):
    """模型只返回候选岗位 ID；不能返回简历筛选结论。"""

    model_config = ConfigDict(extra="forbid")

    job_id: int = Field(gt=0, strict=True)


class RuleReviewResumeAgent:
    """让模型选择岗位，让项目硬条件规则判断候选人。"""

    def __init__(self):
        self.db_gateway = DatabaseGateway()
        self.knowledge_gateway = KnowledgeBaseGateway()
        self.action_gateway = ExternalRecruitmentGateway()
        self.token_manager = SignedApprovalTokenManager(HITL_SECRET_KEY)

    def close(self) -> None:
        self.db_gateway.close()

    def _load_resume_fact(self, resume_id: int):
        started = time.time()
        fact = self.db_gateway.query_resume(resume_id)
        return fact, (time.time() - started) * 1000

    @staticmethod
    def _build_decision(fact: Dict[str, Any], knowledge_result: Dict[str, Any]):
        """只汇总当前选中岗位的确定性结果，不让 LLM 决定淘汰。"""
        started = time.time()
        profile = fact.get("profile") or {}
        contact_complete = bool(profile.get("phone") and profile.get("email"))
        job_results = fact.get("screening_results", [])
        statuses = {item["result"] for item in job_results}
        if "PASS" in statuses:
            overall_result = "PASS"
        elif "PENDING_REVIEW" in statuses:
            overall_result = "PENDING_REVIEW"
        elif statuses == {"REJECT"}:
            overall_result = "REJECT"
        else:
            overall_result = "NO_RESULT"
        can_invite = overall_result == "PASS" and contact_complete
        decision = {
            "resume_id": fact["resume_id"],
            "profile_id": profile.get("profile_id"),
            "candidate_name": profile.get("name"),
            "resume_status": fact["status"],
            "contact_complete": contact_complete,
            "screening_status": overall_result,
            "job_results": job_results,
            "citations": knowledge_result.get("citations", []),
            "action_required": "REQUIRE_HUMAN_APPROVAL" if can_invite else "NONE",
            "proposed_action": "CREATE_INTERVIEW_INVITATION" if can_invite else "NONE",
        }
        return decision, (time.time() - started) * 1000

    @staticmethod
    def build_rule_review(
        fact: Dict[str, Any], decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """原样整理本次规则计算结果，不让模型编写复核事实。"""
        job_reviews = []
        for item in fact.get("screening_results", []):
            reasons = []
            for reason in item.get("reasons") or []:
                if isinstance(reason, dict):
                    reasons.append({
                        "rule": reason.get("rule"),
                        "passed": reason.get("passed"),
                        "detail": reason.get("detail"),
                    })
                else:
                    reasons.append({"rule": None, "passed": None, "detail": str(reason)})

            job_reviews.append({
                "job_id": item["job_id"],
                "job_name": item["job_name"],
                "result_id": item["result_id"],
                "run_id": item["run_id"],
                "result": item["result"],
                "reasons": reasons,
                "rules_snapshot": item.get("rules_snapshot") or {},
            })

        return {
            "source": "CURRENT_JOB_HARD_RULES",
            "screening_status": decision["screening_status"],
            "job_reviews": job_reviews,
            "note": "按数据库当前岗位硬条件即时计算，未写入筛选结果表。",
        }

    def execute_resume_screening(
        self,
        candidate_name: str,
        job_description: str,
    ) -> Dict[str, Any]:
        """姓名定位简历，模型映射岗位，规则决定是否可进入 HR 邀约。"""
        candidate_name = candidate_name.strip()
        job_description = job_description.strip()
        if not candidate_name or not job_description:
            return {
                "success": False,
                "error_code": "MISSING_INPUT",
                "message": "候选人姓名和岗位描述均不能为空",
            }

        trace = LangfuseTraceRecord(
            trace_id=f"TR-{uuid.uuid4().hex[:8].upper()}",
            name="Resume_Name_To_Job_Review_Pipeline",
        )

        # 第一阶段：仅用姓名查知识库；检索文本不参与岗位选择或规则判定。
        try:
            knowledge_result = self.knowledge_gateway.search(
                query=candidate_name,
                document_types=["talent_profile"],
                top_k=20,
            )
        except Exception as exc:
            return {
                "success": False,
                "error_code": "KNOWLEDGE_BASE_UNAVAILABLE",
                "message": f"知识库检索失败：{type(exc).__name__}: {exc}",
            }
        trace.log_span(
            "Stage1_NameLookup", "KNOWLEDGE_RAG",
            {"candidate_name": candidate_name},
            knowledge_result, knowledge_result["latency_ms"],
        )

        candidate_ids: List[int] = []
        for citation in knowledge_result["citations"]:
            source_id = citation.get("metadata", {}).get("source_resume_id")
            try:
                resume_id = int(source_id)
            except (TypeError, ValueError):
                continue
            if resume_id > 0 and resume_id not in candidate_ids:
                candidate_ids.append(resume_id)

        if not candidate_ids:
            return {
                "success": False,
                "error_code": "CANDIDATE_NOT_FOUND",
                "message": f"知识库未找到姓名为 {candidate_name} 的简历 ID",
            }
        started = time.time()
        matched_ids = self.db_gateway.db.scalars(
            select(Resume.resume_id)
            .join(ResumeProfile, ResumeProfile.resume_id == Resume.resume_id)
            .where(
                Resume.resume_id.in_(candidate_ids),
                ResumeProfile.name == candidate_name,
            )
        ).all()
        trace.log_span(
            "Stage2_ResolveID", "DB_QUERY",
            {"candidate_name": candidate_name, "knowledge_ids": candidate_ids},
            {"matched_ids": matched_ids},
            (time.time() - started) * 1000,
        )
        if not matched_ids:
            return {
                "success": False,
                "error_code": "CANDIDATE_NOT_FOUND",
                "message": f"知识库命中结果中未找到姓名为 {candidate_name} 的数据库简历",
            }
        if len(matched_ids) != 1:
            return {
                "success": False,
                "error_code": "AMBIGUOUS_CANDIDATE",
                "message": f"姓名 {candidate_name} 对应多份简历，请先确认具体简历 ID",
                "resume_ids": matched_ids,
            }
        resume_id = matched_ids[0]
        fact, db_ms = self._load_resume_fact(resume_id)
        if fact is None:
            return {
                "success": False,
                "error_code": "CANDIDATE_NOT_FOUND",
                "message": f"数据库中未找到简历 ID {resume_id}",
            }
        trace.log_span(
            "Stage2_ResumeFact", "DB_QUERY",
            {"resume_id": resume_id},
            {"found": True, "name": (fact.get("profile") or {}).get("name")},
            db_ms,
        )

        # 第二阶段：从数据库读取开放岗位；模型仅从这些 ID 中选择一岗。
        jobs = self.db_gateway.db.scalars(
            select(Job)
            .join(Requirement, Requirement.requirement_id == Job.requirement_id)
            .where(Job.job_status == 1, Requirement.status == 0)
            .order_by(Job.job_id)
        ).all()
        if not jobs:
            return {
                "success": False,
                "error_code": "NO_OPEN_JOBS",
                "message": "数据库中没有进行中需求下的开放岗位",
            }
        job_options = [
            {"job_id": job.job_id, "job_name": job.job_name, "job_jd": job.job_jd}
            for job in jobs
        ]
        started = time.time()
        try:
            response = completion(
                model=LLM_MODEL,
                api_key=LLM_API_KEY,
                api_base=LLM_BASE_URL,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你只负责将用户输入的岗位描述映射到给定的开放岗位。"
                            "选择名称和岗位 JD 语义最接近的一项；不要评价候选人，"
                            "不要判断 PASS 或 REJECT，不要编造岗位。"
                            "仅返回 JSON 对象，例如 {\"job_id\": 1}。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"job_description": job_description, "open_jobs": job_options},
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
            selection = JobSelection.model_validate_json(
                response.choices[0].message.content
            )
        except Exception as exc:
            return {
                "success": False,
                "error_code": "JOB_SELECTION_FAILED",
                "message": f"岗位选择模型调用或输出校验失败：{type(exc).__name__}: {exc}",
            }
        selected_job = next(
            (job for job in jobs if job.job_id == selection.job_id), None
        )
        if selected_job is None:
            return {
                "success": False,
                "error_code": "INVALID_JOB_SELECTION",
                "message": f"模型选择的岗位 ID {selection.job_id} 不在开放岗位列表中",
            }
        usage = getattr(response, "usage", None)
        trace.log_span(
            "Stage3_SelectJob", "LLM_JOB_SELECTION",
            {"job_description": job_description, "job_options": job_options},
            {"job_id": selected_job.job_id, "job_name": selected_job.job_name},
            (time.time() - started) * 1000,
            tokens={
                "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
        )

        # 第三阶段：只运行现有硬性规则；模型输出不进入筛选函数。
        resume = self.db_gateway.db.get(Resume, resume_id)
        profile = resume.profile
        rules = rules_from_job(selected_job)
        started = time.time()
        if profile is None:
            result = "PENDING_REVIEW"
            reasons = [{
                "rule": "归一化数据",
                "passed": None,
                "detail": "简历无归一化结果，待人工复核",
            }]
        else:
            result, reason_items = evaluate_profile(
                rules, profile, [skill.skill_name for skill in profile.skills]
            )
            reasons = [item.model_dump() for item in reason_items]

        current_result = {
            "job_id": selected_job.job_id,
            "job_name": selected_job.job_name,
            "result_id": None,
            "run_id": None,
            "result": result,
            "reasons": reasons,
            "rules_snapshot": rules.model_dump(),
        }
        selected_fact = {**fact, "screening_results": [current_result]}
        citations = [
            item for item in knowledge_result["citations"]
            if item.get("metadata", {}).get("source_resume_id") == resume_id
        ]
        decision, _ = self._build_decision(
            selected_fact, {"citations": citations}
        )
        rule_review = self.build_rule_review(selected_fact, decision)
        trace.log_span(
            "Stage4_RuleReview", "DETERMINISTIC_REVIEW",
            {"resume_id": resume_id, "job_id": selected_job.job_id},
            {"decision": decision, "rule_review": rule_review},
            (time.time() - started) * 1000,
        )

        # 第四阶段：通过且联系方式完整时，仅创建待 HR 确认的 Token。
        approval_token = None
        if decision["proposed_action"] == "CREATE_INTERVIEW_INVITATION":
            approval_token = self.token_manager.generate_token(
                resume_id=resume_id,
                action_type="CREATE_INTERVIEW_INVITATION",
                payload={
                    "resume_id": resume_id,
                    "job_id": selected_job.job_id,
                    "job_name": selected_job.job_name,
                    "candidate_name": decision["candidate_name"],
                    "rules_snapshot": rules.model_dump(),
                    "profile_id": profile.profile_id,
                    "profile_updated_at": str(profile.updated_at),
                },
            )
        trace.log_span(
            "Stage5_ActionGate", "HITL_GATE",
            {"resume_id": resume_id, "job_id": selected_job.job_id},
            {"approval_token_created": approval_token is not None},
            0.0,
        )
        trace.print_trace_summary()
        return {
            "success": True,
            "candidates": [{
                "resume_id": resume_id,
                "selected_job": {
                    "job_id": selected_job.job_id,
                    "job_name": selected_job.job_name,
                },
                "decision": decision,
                "rule_review": rule_review,
                "approval_token": approval_token,
            }],
        }

    def resume_human_approval(
        self,
        approval_token: str,
        approve: bool,
        approver_name: str = "HR",
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """HR 确认时复核当前资料和岗位规则，再模拟邀约。"""
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
                "message": f"{approver_name} 已拒绝面试邀约。"
                + (f"理由：{rejection_reason}" if rejection_reason else ""),
            }

        payload = snapshot["payload"]
        resume = self.db_gateway.db.get(Resume, payload["resume_id"])
        job = self.db_gateway.db.get(Job, payload.get("job_id"))
        if resume is None or job is None or job.job_status != 1 or job.requirement.status != 0:
            return {
                "success": False,
                "error_code": "STALE_APPROVAL",
                "message": "候选人或岗位已失效，请重新匹配后审批",
            }
        profile = resume.profile
        if (
            profile is None
            or profile.profile_id != payload.get("profile_id")
            or str(profile.updated_at) != payload.get("profile_updated_at")
            or rules_from_job(job).model_dump() != payload.get("rules_snapshot")
        ):
            return {
                "success": False,
                "error_code": "STALE_APPROVAL",
                "message": "简历或岗位规则已更新，请重新匹配后审批",
            }
        result, _ = evaluate_profile(
            rules_from_job(job), profile,
            [skill.skill_name for skill in profile.skills],
        )
        if result != "PASS" or not (profile.phone and profile.email):
            return {
                "success": False,
                "error_code": "STALE_APPROVAL",
                "message": "当前规则结果或联系方式不满足邀约条件",
            }

        receipt = self.action_gateway.dispatch_interview_invitation(
            resume_id=resume.resume_id,
            approver_name=approver_name,
        )
        receipt["job_id"] = job.job_id
        receipt["job_name"] = job.job_name
        return {
            "success": True,
            "status": "INTERVIEW_INVITATION_SIMULATED",
            "approver": approver_name,
            "receipt": receipt,
            "message": f"{approver_name} 已批准，模拟面试邀约已为岗位 {job.job_name} 创建。",
        }


def print_rule_review(candidate: Dict[str, Any]) -> None:
    review = candidate["rule_review"]
    print(f"📑 规则复核意见：{review['screening_status']}")
    if not review["job_reviews"]:
        print("   暂无有效筛选依据，待人工复核")
    for job in review["job_reviews"]:
        print(f"   岗位：{job['job_name']}（ID {job['job_id']}）｜结果：{job['result']}")
        if not job["reasons"]:
            print("   数据库没有保存逐项判定原因")
        for reason in job["reasons"]:
            print(f"   - {reason['rule'] or '规则'}：{reason['detail'] or '无说明'}")


def run_auto_reject_case(
    agent: RuleReviewResumeAgent,
    candidate_name: str,
    job_description: str,
    expected_job_id: int,
) -> Dict[str, Any]:
    """场景 1：姓名定位简历，模型选岗，规则判定不合适。"""
    print("\n" + "▶" * 4 + " 【验收场景 1】候选人自动拒绝")
    print(f"👤 候选人：{candidate_name}")
    print(f"📋 岗位要求：{job_description}")
    result = agent.execute_resume_screening(candidate_name, job_description)
    assert result["success"] is True, f"场景 1 失败：{json.dumps(result, ensure_ascii=False, default=str)}"

    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    decision = candidate["decision"]
    assert candidate["selected_job"]["job_id"] == expected_job_id
    assert decision["screening_status"] == "REJECT"
    assert decision["action_required"] == "NONE"
    assert candidate["approval_token"] is None

    print(f"📚 知识库：检索到 {len(decision['citations'])} 个简历切片")
    print(f"🤖 LLM：从数据库岗位中选中 {candidate['selected_job']['job_name']}（ID {expected_job_id}）")
    print("🗄️ 数据库：读取简历并执行确定性初筛，结果 REJECT")
    print_rule_review(candidate)
    print("🚫 最终结果：自动拒绝，不进入人工审批")
    return result


def run_human_approval_case(
    agent: RuleReviewResumeAgent,
    candidate_name: str,
    job_description: str,
    expected_job_id: int,
) -> Dict[str, Any]:
    """场景 2：姓名定位简历，模型选岗，规则通过后等待 HR。"""
    print("\n" + "▶" * 4 + " 【验收场景 2】候选人面试邀约人工审批")
    print(f"👤 候选人：{candidate_name}")
    print(f"📋 岗位要求：{job_description}")
    result = agent.execute_resume_screening(candidate_name, job_description)
    assert result["success"] is True, f"场景 2 失败：{json.dumps(result, ensure_ascii=False, default=str)}"

    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    decision = candidate["decision"]
    assert candidate["selected_job"]["job_id"] == expected_job_id
    assert decision["screening_status"] == "PASS"
    assert decision["action_required"] == "REQUIRE_HUMAN_APPROVAL"
    assert decision["proposed_action"] == "CREATE_INTERVIEW_INVITATION"
    assert candidate["approval_token"] is not None

    print(f"📚 知识库：检索到 {len(decision['citations'])} 个简历切片")
    print(f"🤖 LLM：从数据库岗位中选中 {candidate['selected_job']['job_name']}（ID {expected_job_id}）")
    print("🗄️ 数据库：读取简历并执行确定性初筛，结果 PASS")
    print_rule_review(candidate)
    print("🔑 审批 Token：已生成（不在控制台显示）")
    print("⏸️ 当前状态：等待 HR 人工审批")
    return candidate


def run_token_security_case(agent: RuleReviewResumeAgent) -> Dict[str, Any]:
    """场景 3：只测试令牌门禁，不执行或冒充 HR 批准邀约。"""
    print("\n" + "▶" * 4 + " 【验收场景 3】Token 安全攻防")
    manager = agent.token_manager
    token = manager.generate_token(
        resume_id=1,
        action_type="SECURITY_TEST",
        payload={"purpose": "测试"},
    )
    valid, _, _ = manager.verify_and_consume(token)
    assert valid is True
    print("✅ 测试令牌首次验签及消费成功（未触发面试邀约）")

    print("   [攻击模拟 A] 重复提交已经消费的 Token")
    replay = agent.resume_human_approval(token, approve=True)
    assert replay["success"] is False
    print(f"🛡️ 防重放拦截：{replay['message']}")

    print("   [攻击模拟 B] 提交伪造 Token")
    forged = agent.resume_human_approval("TOKEN-HITL-FAKED001.invalid-signature", approve=True)
    assert forged["success"] is False
    print(f"🛡️ 伪造 Token 拦截：{forged['message']}")

    print("   [攻击模拟 C] 修改真实 Token 的签名")
    signed = manager.generate_token(1, "SECURITY_TEST", {"purpose": "签名测试"})
    signed_id, _ = signed.rsplit(".", 1)
    bad_signature = agent.resume_human_approval(f"{signed_id}.{'0' * 64}", approve=True)
    assert bad_signature["success"] is False
    assert "签名无效" in bad_signature["message"]
    print(f"🛡️ 签名校验拦截：{bad_signature['message']}")

    print("   [攻击模拟 D] 篡改待审批内容快照")
    tampered = manager.generate_token(1, "SECURITY_TEST", {"purpose": "原始内容"})
    tampered_id, _ = tampered.rsplit(".", 1)
    manager.snapshot_store[tampered_id]["payload"]["purpose"] = "被篡改内容"
    changed = agent.resume_human_approval(tampered, approve=True)
    assert changed["success"] is False
    assert "篡改" in changed["message"]
    print(f"🛡️ 内容防篡改拦截：{changed['message']}")
    return {
        "replay": replay,
        "forged": forged,
        "bad_signature": bad_signature,
        "tampered": changed,
    }


def run_showcase() -> None:
    """三个验收场景；邀约只在终端 HR 明确确认后模拟执行。"""
    print("=" * 88)
    print("🚀 Day 18 智能简历协同 Agent (知识库 + 数据库 + LLM + API + HITL) 全链路验收")
    print("=" * 88)
    agent = RuleReviewResumeAgent()
    try:
        run_auto_reject_case(agent, "周晓东", "后端实习生", expected_job_id=1)
        approval_candidate = run_human_approval_case(
            agent, "郑浩然", "电商前端开发，使用 Vue3 和 TypeScript", expected_job_id=2
        )
        run_token_security_case(agent)
        try:
            answer = input("\nHR 是否确认模拟面试邀约？输入 y 批准、n 驳回，直接回车暂缓：").strip().lower()
        except EOFError:
            answer = ""
        if answer in {"y", "n"}:
            try:
                approver_name = input("HR 姓名：").strip()
            except EOFError:
                approver_name = ""
            if not approver_name:
                print("⏸️ 未提供 HR 姓名，本次不执行邀约动作")
            else:
                approval = agent.resume_human_approval(
                    approval_token=approval_candidate["approval_token"],
                    approve=answer == "y",
                    approver_name=approver_name,
                )
                print(f"{'✅' if approval['success'] else '⚠️'} HR 审批结果：{approval['message']}")
        else:
            print("⏸️ 未获得 HR 确认，未执行邀约；本次演示结束后内存 Token 失效")
    finally:
        agent.close()

    print("\n🏁 三个场景验收结束：模型选岗、规则判断、Token 防护、HR 邀约门禁")


if __name__ == "__main__":
    run_showcase()
