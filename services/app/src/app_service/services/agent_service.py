"""只读招聘 Agent：通过受控工具查询业务事实并生成可追踪答复。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app_service.core.config import get_settings
from app_service.core.logger import get_logger
from app_service.models.db_models import (
    FilterResult,
    FilterRun,
    Job,
    ProfileSkill,
    Requirement,
    RequirementResumeGroup,
    Resume,
    ResumeProfile,
)
from app_service.models.schemas import AgentChatResponse, AgentToolTrace
from app_service.services.llm import get_client
from app_service.services.upload_service import STATUS_LABELS

logger = get_logger(__name__)

MAX_TOOL_STEPS = 4
MAX_RESULT_ROWS = 20


class AgentUnavailableError(RuntimeError):
    """模型服务不可用或未配置。"""


class AgentProtocolError(RuntimeError):
    """模型未能在受控轮次内给出有效答复。"""


class _StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _EmptyArgs(_StrictArgs):
    pass


class _ListRequirementsArgs(_StrictArgs):
    status: int | None
    limit: int = Field(ge=1, le=MAX_RESULT_ROWS)


class _RequirementOverviewArgs(_StrictArgs):
    requirement_id: int = Field(gt=0)


class _SearchCandidatesArgs(_StrictArgs):
    name: str | None
    skill: str | None
    status: int | None
    limit: int = Field(ge=1, le=MAX_RESULT_ROWS)


class _ResumeDetailArgs(_StrictArgs):
    resume_id: int = Field(gt=0)


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_summary",
            "description": "查询简历状态分布、进行中需求数、开放岗位数和最近筛选任务。",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_requirements",
            "description": "列出招聘需求及其岗位数、需求池简历数。status：0进行中，1已关闭。",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": ["integer", "null"], "enum": [0, 1, None]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULT_ROWS},
                },
                "required": ["status", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_requirement_overview",
            "description": "按需求ID查询需求详情、岗位硬条件和需求池简历状态汇总。",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"requirement_id": {"type": "integer", "minimum": 1}},
                "required": ["requirement_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_candidates",
            "description": (
                "按姓名、技能或简历状态查询候选人；条件可为空。"
                "status取值：0上传失败、1解析失败、2归一化失败、3初筛不通过、4已完成、"
                "5待补录、6待人工复核、7待解析、8待归一化、9待初筛、10待审核入库。"
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "skill": {"type": ["string", "null"]},
                    "status": {"type": ["integer", "null"], "minimum": 0, "maximum": 10},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULT_ROWS},
                },
                "required": ["name", "skill", "status", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_resume_screening_detail",
            "description": "按简历ID查询候选人归一化字段和已有的确定性初筛结果及逐条原因。",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"resume_id": {"type": "integer", "minimum": 1}},
                "required": ["resume_id"],
                "additionalProperties": False,
            },
        },
    },
]


SYSTEM_PROMPT = """你是智能简历筛选助手中的 HR 只读查询 Agent。

规则：
1. 涉及系统内需求、岗位、候选人或筛选结果的事实，必须先调用工具，不得凭空回答。
2. 只能解释工具返回的既有结果。不得自行打分、推断候选人是否合格、改变初筛结论或建议绕过硬性规则。
3. 信息缺失时明确说“系统暂无该信息”；信息不足不等于不合格。
4. 不得声称已经创建、修改、删除、筛选、入库或邀约；当前工具全部只读。
5. 用简洁中文回答。引用候选人时尽量带 resume_id，引用需求或岗位时带对应 ID。
"""


def _dashboard_summary(db: Session, _: _EmptyArgs) -> dict[str, Any]:
    status_rows = db.execute(
        select(Resume.status, func.count()).group_by(Resume.status).order_by(Resume.status)
    ).all()
    recent_runs = db.scalars(select(FilterRun).order_by(FilterRun.run_id.desc()).limit(5)).all()
    return {
        "resume_total": sum(count for _, count in status_rows),
        "resumes_by_status": {
            STATUS_LABELS.get(status, f"未知({status})"): count for status, count in status_rows
        },
        "active_requirements": db.scalar(
            select(func.count()).select_from(Requirement).where(Requirement.status == 0)
        )
        or 0,
        "open_jobs": db.scalar(select(func.count()).select_from(Job).where(Job.job_status == 1))
        or 0,
        "recent_screening_runs": [
            {
                "run_id": run.run_id,
                "job_id": run.job_id,
                "status": run.status,
                "total": run.total,
                "passed": run.passed,
                "rejected": run.rejected,
                "pending_review": run.pending_review,
            }
            for run in recent_runs
        ],
    }


def _list_requirements(db: Session, args: _ListRequirementsArgs) -> dict[str, Any]:
    stmt = select(Requirement).order_by(Requirement.requirement_id.desc()).limit(args.limit)
    if args.status is not None:
        stmt = stmt.where(Requirement.status == args.status)
    rows = db.scalars(stmt).all()
    items = []
    for requirement in rows:
        job_count = (
            db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.requirement_id == requirement.requirement_id)
            )
            or 0
        )
        resume_count = (
            db.scalar(
                select(func.count())
                .select_from(RequirementResumeGroup)
                .where(RequirementResumeGroup.requirement_id == requirement.requirement_id)
            )
            or 0
        )
        items.append(
            {
                "requirement_id": requirement.requirement_id,
                "name": requirement.requirement_name,
                "department": requirement.dept,
                "deadline": requirement.deadline,
                "status": "进行中" if requirement.status == 0 else "已关闭",
                "job_count": job_count,
                "resume_count": resume_count,
            }
        )
    return {"count": len(items), "items": items}


def _requirement_overview(db: Session, args: _RequirementOverviewArgs) -> dict[str, Any]:
    requirement = db.get(Requirement, args.requirement_id)
    if requirement is None:
        return {"found": False, "requirement_id": args.requirement_id}

    jobs = db.scalars(
        select(Job).where(Job.requirement_id == args.requirement_id).order_by(Job.job_id)
    ).all()
    status_rows = db.execute(
        select(Resume.status, func.count())
        .join(RequirementResumeGroup, RequirementResumeGroup.resume_id == Resume.resume_id)
        .where(RequirementResumeGroup.requirement_id == args.requirement_id)
        .group_by(Resume.status)
        .order_by(Resume.status)
    ).all()
    return {
        "found": True,
        "requirement": {
            "requirement_id": requirement.requirement_id,
            "name": requirement.requirement_name,
            "department": requirement.dept,
            "deadline": requirement.deadline,
            "description": requirement.description,
            "status": "进行中" if requirement.status == 0 else "已关闭",
        },
        "jobs": [
            {
                "job_id": job.job_id,
                "job_code": job.job_code,
                "name": job.job_name,
                "status": {0: "草稿", 1: "开放", 2: "关闭"}.get(job.job_status, "未知"),
                "minimum_education": job.job_min_degree,
                "minimum_experience_years": job.job_min_exp_years,
                "required_skills": job.job_required_skills or [],
            }
            for job in jobs
        ],
        "resumes_by_status": {
            STATUS_LABELS.get(status, f"未知({status})"): count for status, count in status_rows
        },
    }


def _search_candidates(db: Session, args: _SearchCandidatesArgs) -> dict[str, Any]:
    stmt = (
        select(Resume)
        .outerjoin(ResumeProfile, ResumeProfile.resume_id == Resume.resume_id)
        .order_by(Resume.resume_id.desc())
    )
    if args.name:
        stmt = stmt.where(ResumeProfile.name.ilike(f"%{args.name.strip()}%"))
    if args.skill:
        stmt = stmt.join(ProfileSkill, ProfileSkill.profile_id == ResumeProfile.profile_id).where(
            ProfileSkill.skill_name.ilike(f"%{args.skill.strip()}%")
        )
    if args.status is not None:
        stmt = stmt.where(Resume.status == args.status)
    rows = db.scalars(stmt.distinct().limit(args.limit)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "resume_id": resume.resume_id,
                "name": resume.profile.name if resume.profile else None,
                "file_name": resume.original_file_name,
                "status": resume.status,
                "status_label": STATUS_LABELS.get(resume.status, "未知"),
                "education": resume.profile.highest_education if resume.profile else None,
                "work_months": resume.profile.total_work_months if resume.profile else None,
                "skills": [skill.skill_name for skill in resume.profile.skills]
                if resume.profile
                else [],
            }
            for resume in rows
        ],
    }


def _resume_screening_detail(db: Session, args: _ResumeDetailArgs) -> dict[str, Any]:
    resume = db.get(Resume, args.resume_id)
    if resume is None:
        return {"found": False, "resume_id": args.resume_id}

    results = db.execute(
        select(FilterResult, FilterRun, Job)
        .join(FilterRun, FilterRun.run_id == FilterResult.run_id)
        .join(Job, Job.job_id == FilterRun.job_id)
        .where(FilterResult.resume_id == args.resume_id)
        .order_by(FilterResult.result_id.desc())
        .limit(MAX_RESULT_ROWS)
    ).all()
    profile = resume.profile
    return {
        "found": True,
        "resume": {
            "resume_id": resume.resume_id,
            "file_name": resume.original_file_name,
            "status": resume.status,
            "status_label": STATUS_LABELS.get(resume.status, "未知"),
            "failure_reason": resume.failure_reason,
        },
        "profile": None
        if profile is None
        else {
            "name": profile.name,
            "highest_education": profile.highest_education,
            "graduation_institution": profile.graduation_institution,
            "total_work_months": profile.total_work_months,
            "skills": [skill.skill_name for skill in profile.skills],
        },
        "screening_results": [
            {
                "result_id": result.result_id,
                "run_id": run.run_id,
                "job_id": job.job_id,
                "job_name": job.job_name,
                "result": result.result,
                "reasons": result.reasons or [],
            }
            for result, run, job in results
        ],
    }


ToolHandler = tuple[type[_StrictArgs], Callable[[Session, Any], dict[str, Any]]]
_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_dashboard_summary": (_EmptyArgs, _dashboard_summary),
    "list_requirements": (_ListRequirementsArgs, _list_requirements),
    "get_requirement_overview": (_RequirementOverviewArgs, _requirement_overview),
    "search_candidates": (_SearchCandidatesArgs, _search_candidates),
    "get_resume_screening_detail": (_ResumeDetailArgs, _resume_screening_detail),
}


def execute_tool(db: Session, name: str, arguments: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    handler_entry = _TOOL_HANDLERS.get(name)
    if handler_entry is None:
        return False, {"error": "未知或未授权的工具"}
    args_model, handler = handler_entry
    try:
        validated = args_model.model_validate(arguments)
        return True, handler(db, validated)
    except ValidationError as exc:
        return False, {"error": "工具参数校验失败", "details": exc.errors(include_url=False)}
    except Exception:
        logger.exception("Agent 只读工具执行失败: %s", name)
        return False, {"error": "工具执行失败"}


def chat(db: Session, message: str, *, client: Any | None = None) -> AgentChatResponse:
    """运行有界工具调用循环；所有系统事实只能来自只读工具。"""
    settings = get_settings()
    try:
        llm_client = client or get_client()
    except Exception as exc:
        raise AgentUnavailableError(str(exc)) from exc

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    traces: list[AgentToolTrace] = []

    for _ in range(MAX_TOOL_STEPS):
        try:
            response = llm_client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=AGENT_TOOLS,
                tool_choice="auto",
                parallel_tool_calls=False,
                temperature=0.1,
                timeout=settings.llm_timeout_seconds,
            )
        except Exception as exc:
            logger.exception("Agent 模型调用失败")
            raise AgentUnavailableError("Agent 模型服务暂不可用") from exc

        assistant = response.choices[0].message
        messages.append(assistant.model_dump(exclude_none=True))
        tool_calls = assistant.tool_calls or []
        if not tool_calls:
            answer = (assistant.content or "").strip()
            if not answer:
                raise AgentProtocolError("模型返回空答复")
            return AgentChatResponse(answer=answer, tool_traces=traces)

        for tool_call in tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须是 JSON 对象")
            except (json.JSONDecodeError, ValueError):
                arguments = {}
                success, result = False, {"error": "工具参数不是有效 JSON 对象"}
            else:
                success, result = execute_tool(db, name, arguments)

            traces.append(AgentToolTrace(tool=name, arguments=arguments, success=success))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    raise AgentProtocolError("Agent 超过最大工具调用轮次")
