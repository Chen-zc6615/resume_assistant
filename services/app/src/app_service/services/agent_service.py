"""招聘只读 Agent：封闭意图路由、安全 Text2SQL、确定性规则判定。"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from enum import StrEnum
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app_service.clients import knowledge_client
from app_service.core.config import get_settings
from app_service.core.logger import get_logger
from app_service.models.schemas import AgentChatResponse, AgentToolTrace, FilterRule
from app_service.services.llm import get_client
from app_service.services.safe_text2sql import UnsafeSQL, execute_readonly, schema_prompt
from app_service.services.screen_service import evaluate_profile

logger = get_logger(__name__)
MAX_TOOL_STEPS = 6


class AgentUnavailableError(RuntimeError):
    pass


class AgentProtocolError(RuntimeError):
    pass


class AgentIntent(StrEnum):
    DASHBOARD_QUERY = "DASHBOARD_QUERY"
    REQUIREMENT_QUERY = "REQUIREMENT_QUERY"
    CANDIDATE_SEARCH = "CANDIDATE_SEARCH"
    SCREENING_QUERY = "SCREENING_QUERY"
    JOB_MATCH = "JOB_MATCH"
    GENERAL_HELP = "GENERAL_HELP"
    UNSUPPORTED = "UNSUPPORTED"


class _StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _QueryArgs(_StrictArgs):
    sql: str = Field(min_length=8, max_length=8000)
    purpose: str = Field(min_length=2, max_length=200)


class _KnowledgeArgs(_StrictArgs):
    query: str = Field(min_length=2, max_length=200)
    top_k: int = Field(default=5, ge=1, le=10)


class _JobMatchArgs(_StrictArgs):
    candidate_sql: str = Field(min_length=8, max_length=8000)
    job_sql: str = Field(min_length=8, max_length=8000)


QUERY_TOOL = {"type": "function", "function": {
    "name": "query_recruitment_database",
    "description": "执行只读招聘数据查询。SQL 会经过 AST、表字段白名单、敏感字段和 LIMIT 校验。",
    "strict": True,
    "parameters": {"type": "object", "properties": {
        "sql": {"type": "string"}, "purpose": {"type": "string"}},
        "required": ["sql", "purpose"], "additionalProperties": False},
}}
KNOWLEDGE_TOOL = {"type": "function", "function": {
    "name": "search_talent_knowledge", "description": "语义检索人才知识库，返回可引用的候选人资料切片。",
    "strict": True,
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 10}},
        "required": ["query", "top_k"], "additionalProperties": False},
}}
JOB_MATCH_TOOL = {"type": "function", "function": {
    "name": "evaluate_candidate_for_job",
    "description": (
        "用两条只读 SQL 获取候选人与开放岗位，再由服务端确定性规则判断。"
        "candidate_sql 只返回一名候选人的 resume_id, name, highest_education, "
        "total_work_months, contact_complete, has_skill_signal, profile_updated_at, skills；"
        "job_sql 只返回一个岗位的 job_id, job_name, job_min_degree, job_min_exp_years, "
        "job_required_skills, job_updated_at, job_status, requirement_status。"),
    "strict": True,
    "parameters": {"type": "object", "properties": {
        "candidate_sql": {"type": "string"}, "job_sql": {"type": "string"}},
        "required": ["candidate_sql", "job_sql"], "additionalProperties": False},
}}
AGENT_TOOLS = [QUERY_TOOL, KNOWLEDGE_TOOL, JOB_MATCH_TOOL]

_INTENT_TOOL_NAMES: dict[AgentIntent, frozenset[str]] = {
    AgentIntent.DASHBOARD_QUERY: frozenset({"query_recruitment_database"}),
    AgentIntent.REQUIREMENT_QUERY: frozenset({"query_recruitment_database"}),
    AgentIntent.CANDIDATE_SEARCH: frozenset({"query_recruitment_database", "search_talent_knowledge"}),
    AgentIntent.SCREENING_QUERY: frozenset({"query_recruitment_database"}),
    AgentIntent.JOB_MATCH: frozenset({"evaluate_candidate_for_job"}),
    AgentIntent.GENERAL_HELP: frozenset(), AgentIntent.UNSUPPORTED: frozenset(),
}

INTENT_ROUTER_PROMPT = """你是招聘助手的意图分类器，只能输出以下一个标签，不得解释：
DASHBOARD_QUERY：统计、看板、数量和趋势；
REQUIREMENT_QUERY：招聘需求或岗位查询；
CANDIDATE_SEARCH：候选人搜索、经历或技能查询；
SCREENING_QUERY：筛选任务、结果和失败原因；
JOB_MATCH：判断某候选人与某岗位是否匹配，或建议是否邀约；
GENERAL_HELP：询问本助手能力、用法；
UNSUPPORTED：写入、删除、绕过审批、非招聘问题，或意图不明确。"""

SYSTEM_PROMPT = """你是企业招聘只读数据助手。
1. 业务事实必须先调用工具，不能凭记忆或猜测；未成功调用工具时禁止直接终答。
2. 生成 PostgreSQL 单条 SELECT；禁止 SELECT *、写入、注释、跨 schema 和未公开字段。
3. 只查询回答问题所需字段，默认 LIMIT 20；聚合列必须给别名。
4. 不得输出手机号、邮箱、简历原文、文件地址或认证数据。
5. 岗位匹配必须调用 evaluate_candidate_for_job；判定只能引用工具结果。
6. 结论给来源标记：[来源: DB:表名] 或 [来源: KB:document_id#chunk_id]。
7. 工具失败时说明限制，不得伪造。"""


def _completion_with_retry(client: Any, settings: Any, **kwargs: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(settings.agent_llm_max_retries + 1):
        try:
            return client.chat.completions.create(timeout=settings.llm_timeout_seconds, **kwargs)
        except Exception as exc:
            last_error = exc
            if attempt < settings.agent_llm_max_retries:
                time.sleep(settings.agent_llm_retry_backoff_seconds * (attempt + 1))
    raise AgentUnavailableError("Agent 模型服务暂不可用") from last_error


def _route_intent(client: Any, message: str, settings: Any, history: list[dict[str, str]] | None) -> AgentIntent:
    messages: list[dict[str, str]] = [{"role": "system", "content": INTENT_ROUTER_PROMPT}]
    messages.extend({"role": x["role"], "content": x["content"]} for x in (history or [])[-6:]
                    if x.get("role") in {"user", "assistant"} and x.get("content"))
    messages.append({"role": "user", "content": message})
    response = _completion_with_retry(client, settings, model=settings.llm_model, messages=messages, temperature=0)
    label = (response.choices[0].message.content or "").strip().upper()
    try:
        return AgentIntent(label)
    except ValueError:
        logger.warning("意图分类器返回非法标签: %s", label)
        return AgentIntent.UNSUPPORTED


def _fixed_answer(intent: AgentIntent) -> str | None:
    if intent == AgentIntent.GENERAL_HELP:
        return "我可以查询招聘看板、需求岗位、候选人和筛选结果，也能按确定性规则评估人岗匹配；所有查询均为只读。"
    if intent == AgentIntent.UNSUPPORTED:
        return "这个请求不属于当前招聘只读助手的能力范围；我不会直接修改、删除数据或绕过 HR 审批。"
    return None


def _tools_for_intent(intent: AgentIntent) -> list[dict[str, Any]]:
    allowed = _INTENT_TOOL_NAMES[intent]
    return [tool for tool in AGENT_TOOLS if tool["function"]["name"] in allowed]


def _query_database(db: Session, args: _QueryArgs) -> dict[str, Any]:
    result = execute_readonly(db, args.sql)
    result["purpose"] = args.purpose
    return result


def _search_knowledge(_db: Session, args: _KnowledgeArgs) -> dict[str, Any]:
    results = knowledge_client.search_documents(query=args.query, top_k=args.top_k)
    safe, sources = [], []
    for item in results:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        doc = str(
            item.get("talent_card_id")
            or meta.get("talent_card_id")
            or item.get("document_id")
            or meta.get("document_id")
            or "unknown"
        )
        chunk = str(item.get("chunk_id") or meta.get("chunk_id") or "unknown")
        source = f"KB:{doc}#{chunk}"
        sources.append(source)
        safe.append({"content": item.get("content") or item.get("text") or "", "score": item.get("score"),
                     "metadata": {k: v for k, v in meta.items() if k not in {"phone", "email", "raw_text", "file_key"}},
                     "source": source})
    return {"results": safe, "sources": sources}


def _truthy(value: Any) -> bool:
    return value.strip().lower() in {"1", "true", "t", "yes", "y"} if isinstance(value, str) else bool(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return _string_list(json.loads(value))
        except json.JSONDecodeError:
            return [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _evaluate_job_match(db: Session, args: _JobMatchArgs) -> dict[str, Any]:
    candidate_result, job_result = execute_readonly(db, args.candidate_sql), execute_readonly(db, args.job_sql)
    if len(candidate_result["rows"]) != 1 or len(job_result["rows"]) != 1:
        return {"found": False, "error": "候选人和岗位查询都必须唯一命中一条记录",
                "sources": candidate_result["sources"] + job_result["sources"]}
    candidate, job = candidate_result["rows"][0], job_result["rows"][0]
    candidate_required = {"resume_id", "name", "highest_education", "total_work_months",
                          "contact_complete", "has_skill_signal", "profile_updated_at", "skills"}
    job_required = {"job_id", "job_name", "job_min_degree", "job_min_exp_years", "job_required_skills",
                    "job_updated_at", "job_status", "requirement_status"}
    missing = sorted((candidate_required - candidate.keys()) | (job_required - job.keys()))
    if missing:
        return {"found": False, "error": f"查询缺少约定字段：{', '.join(missing)}"}
    if int(job["job_status"]) != 1 or int(job["requirement_status"]) != 0:
        return {"found": False, "error": "岗位或招聘需求当前未开放"}
    rules = FilterRule(min_degree=job["job_min_degree"], min_exp_years=job["job_min_exp_years"],
                       required_skills=_string_list(job["job_required_skills"]))
    profile = SimpleNamespace(highest_education=candidate["highest_education"],
                              total_work_months=candidate["total_work_months"],
                              work_experiences=[object()] if _truthy(candidate["has_skill_signal"]) else [],
                              project_experiences=[])
    result, reasons = evaluate_profile(rules, profile, _string_list(candidate["skills"]))
    contact = _truthy(candidate["contact_complete"])
    proposal = None
    if result == "PASS" and contact:
        proposal = {"action_type": "CREATE_INTERVIEW_INVITATION", "resume_id": candidate["resume_id"],
                    "job_id": job["job_id"], "candidate_name": candidate["name"], "job_name": job["job_name"],
                    "profile_updated_at": str(candidate["profile_updated_at"]),
                    "job_updated_at": str(job["job_updated_at"]), "rules_snapshot": rules.model_dump()}
    return {"found": True, "resume_id": candidate["resume_id"], "candidate_name": candidate["name"],
            "job_id": job["job_id"], "job_name": job["job_name"], "result": result,
            "contact_complete": contact, "reasons": [x.model_dump() for x in reasons],
            "action_proposal": proposal,
            "sources": sorted(set(candidate_result["sources"] + job_result["sources"]))}


ToolHandler = tuple[type[_StrictArgs], Callable[[Session, Any], dict[str, Any]]]
_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "query_recruitment_database": (_QueryArgs, _query_database),
    "search_talent_knowledge": (_KnowledgeArgs, _search_knowledge),
    "evaluate_candidate_for_job": (_JobMatchArgs, _evaluate_job_match),
}


def execute_tool(db: Session, name: str, arguments: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    entry = _TOOL_HANDLERS.get(name)
    if entry is None:
        return False, {"error": "未知或未授权的工具"}
    try:
        return True, entry[1](db, entry[0].model_validate(arguments))
    except ValidationError as exc:
        return False, {"error": "工具参数校验失败", "details": exc.errors(include_url=False)}
    except UnsafeSQL as exc:
        return False, {"error": "SQL 安全校验失败", "details": str(exc)}
    except knowledge_client.KnowledgeServiceError as exc:
        return False, {"error": "知识库暂不可用", "details": str(exc)}
    except Exception:
        logger.exception("Agent 工具执行失败: %s", name)
        return False, {"error": "工具执行失败"}


def _ensure_citations(answer: str, traces: list[AgentToolTrace]) -> str:
    sources: set[str] = set()
    for trace in traces:
        values = (trace.result or {}).get("sources", []) if trace.success else []
        if isinstance(values, list):
            sources.update(str(x) for x in values)
    if not sources or "[来源:" in answer:
        return answer
    return answer.rstrip() + "\n\n" + " ".join(f"[来源: {x}]" for x in sorted(sources))


def _messages(intent: AgentIntent, message: str, history: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n当前意图：{intent.value}\n{schema_prompt()}"}]
    result.extend({"role": x["role"], "content": x["content"]} for x in (history or [])[-20:]
                  if x.get("role") in {"user", "assistant"} and x.get("content"))
    result.append({"role": "user", "content": message})
    return result


def _make_response(answer: str, traces: list[AgentToolTrace], intent: AgentIntent,
                   trace_id: str, metrics: dict[str, Any]) -> AgentChatResponse:
    return AgentChatResponse(answer=_ensure_citations(answer, traces), tool_traces=traces,
                             intent=intent.value, trace_id=trace_id, metrics=metrics)


def chat(db: Session, message: str, *, client: Any | None = None,
         history: list[dict[str, str]] | None = None) -> AgentChatResponse:
    settings, trace_id = get_settings(), uuid.uuid4().hex
    llm = client or get_client()
    intent = _route_intent(llm, message, settings, history)
    metrics = {"trace_id": trace_id, "llm_calls": 1, "tool_calls": 0, "successful_tools": 0}
    if (fixed := _fixed_answer(intent)) is not None:
        return _make_response(fixed, [], intent, trace_id, metrics)
    messages, traces, allowed = _messages(intent, message, history), [], _INTENT_TOOL_NAMES[intent]
    for _ in range(MAX_TOOL_STEPS):
        response = _completion_with_retry(llm, settings, model=settings.llm_model, messages=messages,
                                          tools=_tools_for_intent(intent), tool_choice="auto",
                                          parallel_tool_calls=False, temperature=0.1)
        metrics["llm_calls"] += 1
        assistant = response.choices[0].message
        messages.append(assistant.model_dump(exclude_none=True))
        calls = assistant.tool_calls or []
        if not calls:
            answer = (assistant.content or "").strip()
            if not answer:
                raise AgentProtocolError("模型返回空答复")
            if not any(x.success for x in traces):
                messages.append({"role": "system", "content": "必须先成功调用工具查询事实，不得直接作答。"})
                continue
            return _make_response(answer, traces, intent, trace_id, metrics)
        for call in calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError
            except (json.JSONDecodeError, ValueError):
                arguments, success, result = {}, False, {"error": "工具参数不是有效 JSON 对象"}
            else:
                success, result = execute_tool(db, name, arguments) if name in allowed else (False, {"error": "当前意图不允许调用该工具"})
            metrics["tool_calls"] += 1
            metrics["successful_tools"] += int(success)
            traces.append(AgentToolTrace(tool=name, arguments=arguments, success=success, result=result))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
    raise AgentProtocolError("Agent 超过最大工具调用轮次")


def chat_stream(db: Session, message: str, *, client: Any | None = None,
                history: list[dict[str, str]] | None = None):
    settings, trace_id = get_settings(), uuid.uuid4().hex
    llm = client or get_client()
    intent = _route_intent(llm, message, settings, history)
    metrics = {"trace_id": trace_id, "llm_calls": 1, "tool_calls": 0, "successful_tools": 0}
    yield {"type": "intent", "intent": intent.value}
    if (fixed := _fixed_answer(intent)) is not None:
        yield {"type": "delta", "text": fixed}
        yield {"type": "final", "response": _make_response(fixed, [], intent, trace_id, metrics)}
        return
    messages, traces, allowed = _messages(intent, message, history), [], _INTENT_TOOL_NAMES[intent]
    for _ in range(MAX_TOOL_STEPS):
        stream = _completion_with_retry(llm, settings, model=settings.llm_model, messages=messages,
                                        tools=_tools_for_intent(intent), tool_choice="auto",
                                        parallel_tool_calls=False, temperature=0.1, stream=True)
        metrics["llm_calls"] += 1
        parts: list[str] = []
        accumulator: dict[int, dict[str, str]] = {}
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                parts.append(delta.content)
                yield {"type": "delta", "text": delta.content}
            for call in delta.tool_calls or []:
                acc = accumulator.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                if call.id:
                    acc["id"] = call.id
                if call.function:
                    acc["name"] = call.function.name or acc["name"]
                    acc["arguments"] += call.function.arguments or ""
        if not accumulator:
            answer = "".join(parts).strip()
            if not answer:
                raise AgentProtocolError("模型返回空答复")
            if not any(x.success for x in traces):
                messages.extend([{"role": "assistant", "content": answer},
                                 {"role": "system", "content": "必须先成功调用工具查询事实，不得直接作答。"}])
                continue
            cited = _ensure_citations(answer, traces)
            if cited != answer:
                yield {"type": "delta", "text": cited[len(answer):]}
            yield {"type": "final", "response": _make_response(answer, traces, intent, trace_id, metrics)}
            return
        ordered = [accumulator[x] for x in sorted(accumulator)]
        messages.append({"role": "assistant", "content": "".join(parts) or None,
                         "tool_calls": [{"id": x["id"], "type": "function", "function": {"name": x["name"], "arguments": x["arguments"]}} for x in ordered]})
        for item in ordered:
            name = item["name"]
            try:
                arguments = json.loads(item["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError
            except (json.JSONDecodeError, ValueError):
                arguments, success, result = {}, False, {"error": "工具参数不是有效 JSON 对象"}
            else:
                success, result = execute_tool(db, name, arguments) if name in allowed else (False, {"error": "当前意图不允许调用该工具"})
            metrics["tool_calls"] += 1
            metrics["successful_tools"] += int(success)
            traces.append(AgentToolTrace(tool=name, arguments=arguments, success=success, result=result))
            yield {"type": "tool", "name": name, "success": success}
            messages.append({"role": "tool", "tool_call_id": item["id"], "content": json.dumps(result, ensure_ascii=False, default=str)})
    raise AgentProtocolError("Agent 超过最大工具调用轮次")
