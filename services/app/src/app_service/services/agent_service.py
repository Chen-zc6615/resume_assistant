"""招聘只读 Agent：四标签意图路由（kb/sql/action/refuse）、安全 Text2SQL、确定性规则判定。"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from enum import StrEnum
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app_service.clients import knowledge_client, model_client
from app_service.core.config import get_settings
from app_service.core.logger import get_logger
from app_service.models.schemas import AgentChatResponse, AgentToolTrace, FilterRule
from app_service.services.safe_text2sql import UnsafeSQL, execute_readonly, schema_prompt
from app_service.services.screen_service import evaluate_profile

logger = get_logger(__name__)
MAX_TOOL_STEPS = 6


class AgentUnavailableError(RuntimeError):
    pass


class AgentProtocolError(RuntimeError):
    pass


class AgentIntent(StrEnum):
    INTENT_KB = "kb"
    INTENT_SQL = "sql"
    INTENT_ACTION = "action"
    INTENT_REFUSE = "refuse"


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

# 意图 → 可用工具白名单：kb 画像检索为主（DB 兜底查基础档案）；sql 一读取数+匹配判定；
# action 查实体+生成待审批的操作建议（不直接执行写操作）；refuse 不进工具循环。
_INTENT_TOOL_NAMES: dict[AgentIntent, frozenset[str]] = {
    AgentIntent.INTENT_KB: frozenset({"search_talent_knowledge", "query_recruitment_database"}),
    AgentIntent.INTENT_SQL: frozenset({"query_recruitment_database", "evaluate_candidate_for_job"}),
    AgentIntent.INTENT_ACTION: frozenset({"query_recruitment_database", "evaluate_candidate_for_job"}),
    AgentIntent.INTENT_REFUSE: frozenset(),
}

INTENT_ROUTER_PROMPT = """你是招聘数据助手的意图分类器。给定 HR 的一句话，判断应交给哪个通道处理：

【kb = 候选人画像检索】：关于"候选人个人"的档案细节问题——某人的学历、工作经历、技能、
项目等画像内容，以及跨候选人的画像类问题。典型判例：
- "张三做过哪些项目？" → kb
- "李雷使用过 TypeScript 吗？" → kb
- "哪几位候选人有 B 端产品经验？" → kb（跨候选人但问的是画像内容）

【sql = 数据查询与分析】：一切"读数据"的问题——数量统计、状态分布、清单查询、初筛结果、
人岗匹配结论，以及综合分析类问句（为什么/总结——由查询取数后解读）。典型判例：
- "现在有多少份待审核简历？" → sql
- "各初筛状态的简历分别有多少份？" → sql
- "查一下简历 23 的初筛结果" → sql（祈使句式也是查询）
- "李雷和高级后端工程师岗位匹配吗？" → sql（问匹配结论＝读数据后判断）
- "为什么最近一次初筛有三个人待复核？" → sql（分析＝读数据后解读）

【action = 业务操作】：指令要求**修改数据或执行操作**——标记/变更状态、确认入库、
发面试邀约、同步、移出。"匹配后要求邀约/操作"的祈使句也归 action。典型判例：
- "如果匹配就帮李雷发面试邀约" → action（匹配是前提，邀约是指令）
- "把简历 23 的初筛状态标记为通过" → action
- "确认这份简历入库" → action

【refuse = 拒答】：与招聘业务无关的问题——闲聊、天气、新闻、写代码等系统能力之外的请求。
典型判例：
- "今天天气怎么样？" → refuse
- "帮我写一段 Python 排序算法" → refuse

判别要点：含"标记/设置为/变更为/确认入库/移出/发/同步/推送"等**变更动词** → action；
问"匹配结论/查/看/统计/多少/为什么/总结" → sql；问个人档案细节 → kb；明显业务无关 → refuse。
**拿不准时选 kb**（画像通道有诚实拒答机制，误路由代价最小）。
只输出 JSON：{"intent": "kb/sql/action/refuse 之一", "reason": "一句话判定依据"}"""

SYSTEM_PROMPT = """你是企业招聘只读数据助手。
1. 业务事实必须先调用工具，不能凭记忆或猜测；未成功调用工具时禁止直接终答。
2. 生成 PostgreSQL 单条 SELECT；禁止 SELECT *、写入、注释、跨 schema 和未公开字段。
3. 只查询回答问题所需字段，默认 LIMIT 20；聚合列必须给别名。
4. 不得输出手机号、邮箱、简历原文、文件地址或认证数据。
5. 岗位匹配必须调用 evaluate_candidate_for_job；判定只能引用工具结果。被要求执行操作
（如发邀约）时不直接执行，给出操作建议并说明需经 HR 审批。
6. 结论给来源标记：[来源: DB:表名] 或 [来源: KB:document_id#chunk_id]。
7. 工具失败时说明限制，不得伪造。"""


def _completion_with_retry(completion_fn: Callable[..., Any], settings: Any, **kwargs: Any) -> Any:
    """包装注入的模型调用函数做重试；模型名/超时/密钥由 model_client 统一管理。"""
    last_error: Exception | None = None
    for attempt in range(settings.agent_llm_max_retries + 1):
        try:
            return completion_fn(**kwargs)
        except Exception as exc:  # noqa: BLE001 —— 网络/超时/限流统一重试
            last_error = exc
            if attempt < settings.agent_llm_max_retries:
                time.sleep(settings.agent_llm_retry_backoff_seconds * (attempt + 1))
    raise AgentUnavailableError("Agent 模型服务暂不可用") from last_error


# 规则兜底关键词：只保留强业务统计/流程信号 → sql；其余默认 kb。
# 不放"状态/多少/查一下"等宽词——"张三的工作年限是多少"这类个人画像问题会被误路由到
# sql 通道（宁走 kb：kb 有诚实拒答兜底；兜底是 LLM 挂掉后的降级路径，宁可保守归 kb
# 让通道内拒答，也不要误报统计答案）
_SQL_SIGNALS = re.compile(
    r"统计|多少份|几份|数量|分布|初筛|筛选结果|待审核|待初筛|需求池|有哪些需求|"
    r"多少岗位|几个岗位|岗位数|人才库|批次|看板|进度"
)


def _fallback_intent(message: str) -> tuple[AgentIntent, str]:
    """规则兜底：LLM 失败/输出非法时的确定性判定。永不返回 refuse（防误拒可回答的问题）。"""
    if _SQL_SIGNALS.search(message):
        return AgentIntent.INTENT_SQL, "规则兜底：命中业务统计/查询关键词"
    return AgentIntent.INTENT_KB, "规则兜底：默认走候选人画像检索"


def _route_intent(completion_fn: Callable[..., Any], message: str, settings: Any,
                  history: list[dict[str, str]] | None) -> tuple[AgentIntent, str]:
    """三段式意图路由：LLM 分类 → 枚举白名单校验 → 规则兜底；全程不抛异常（降级而非 500）。"""
    messages: list[dict[str, str]] = [{"role": "system", "content": INTENT_ROUTER_PROMPT}]
    messages.extend({"role": x["role"], "content": x["content"]} for x in (history or [])[-6:]
                    if x.get("role") in {"user", "assistant"} and x.get("content"))
    messages.append({"role": "user", "content": message})
    try:
        # ── 段 1：LLM 分类（JSON 强约束，response_format 由 model_client 透传）──
        response = _completion_with_retry(completion_fn, settings, messages=messages,
                                          response_format={"type": "json_object"}, temperature=0)
        data = json.loads(response.choices[0].message.content or "")
        # ── 段 2：枚举白名单校验，防 LLM 输出旧标签或编造值 ──
        label = str(data.get("intent", "")).strip().lower()
        reason = str(data.get("reason", ""))[:120]
        if label in frozenset(x.value for x in AgentIntent):
            return AgentIntent(label), reason
        logger.warning("意图分类器返回非法标签: %s", label)
    except Exception as exc:  # noqa: BLE001 —— LLM 网络/超时/输出不可解析，全走兜底
        logger.warning("意图分类调用失败（%s），走规则兜底", str(exc)[:80])
    # ── 段 3：规则兜底（确定性降级）：统计关键词 → sql，否则 → kb；永不返回 refuse ──
    return _fallback_intent(message)


_REFUSE_ANSWER = (
    "这个问题不在招聘数据助手的能力范围内。我可以查询招聘需求、岗位、候选人档案与初筛结果，"
    "检索候选人知识库，评估人岗匹配并生成待 HR 审批的邀约建议；所有数据操作均需经审批执行。"
)


def _fixed_answer(intent: AgentIntent) -> str | None:
    """仅 refuse 短路固定话术（带能力引导）；action 不短路——进工具循环产出待审批操作建议。"""
    if intent == AgentIntent.INTENT_REFUSE:
        return _REFUSE_ANSWER
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


# 意图语义注入 system 提示：让主循环模型知晓当前通道的职责边界
_INTENT_GUIDANCE: dict[AgentIntent, str] = {
    AgentIntent.INTENT_KB: "当前意图：kb（候选人画像）。优先检索人才知识库，基础档案字段可查数据库。",
    AgentIntent.INTENT_SQL: "当前意图：sql（数据查询与分析）。必须先用工具取数，解读只能基于工具结果。",
    AgentIntent.INTENT_ACTION: (
        "当前意图：action（业务操作）。不会直接执行任何写操作：先查证涉及的候选人与岗位，"
        "评估后给出操作建议；邀约等操作将生成待 HR 审批的提案，不得绕过审批。"),
    AgentIntent.INTENT_REFUSE: "当前意图：refuse。不调用任何工具。",
}


def _messages(intent: AgentIntent, message: str, history: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    guidance = _INTENT_GUIDANCE.get(intent, "")
    result: list[dict[str, Any]] = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n{guidance}\n{schema_prompt()}"}]
    result.extend({"role": x["role"], "content": x["content"]} for x in (history or [])[-20:]
                  if x.get("role") in {"user", "assistant"} and x.get("content"))
    result.append({"role": "user", "content": message})
    return result


def _make_response(answer: str, traces: list[AgentToolTrace], intent: AgentIntent,
                   trace_id: str, metrics: dict[str, Any]) -> AgentChatResponse:
    return AgentChatResponse(answer=_ensure_citations(answer, traces), tool_traces=traces,
                             intent=intent.value, trace_id=trace_id, metrics=metrics)


def _resolve_completion_fn(completion_fn: Callable[..., Any] | None) -> Callable[..., Any]:
    """缺省时取 model_client 的 Agent 通道；配置缺失归一为 503 语义异常。"""
    if completion_fn is not None:
        return completion_fn
    try:
        return model_client.get_agent_completion()
    except RuntimeError as exc:  # 未配置 DASHSCOPE_API_KEY
        raise AgentUnavailableError(str(exc)) from exc


def chat(db: Session, message: str, *, completion_fn: Callable[..., Any] | None = None,
         history: list[dict[str, str]] | None = None) -> AgentChatResponse:
    settings, trace_id = get_settings(), uuid.uuid4().hex
    llm = _resolve_completion_fn(completion_fn)
    intent, intent_reason = _route_intent(llm, message, settings, history)
    metrics = {"trace_id": trace_id, "intent_reason": intent_reason,
               "llm_calls": 1, "tool_calls": 0, "successful_tools": 0}
    if (fixed := _fixed_answer(intent)) is not None:
        return _make_response(fixed, [], intent, trace_id, metrics)
    messages, traces, allowed = _messages(intent, message, history), [], _INTENT_TOOL_NAMES[intent]
    for _ in range(MAX_TOOL_STEPS):
        response = _completion_with_retry(llm, settings, messages=messages,
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


def chat_stream(db: Session, message: str, *, completion_fn: Callable[..., Any] | None = None,
                history: list[dict[str, str]] | None = None):
    settings, trace_id = get_settings(), uuid.uuid4().hex
    llm = _resolve_completion_fn(completion_fn)
    intent, intent_reason = _route_intent(llm, message, settings, history)
    metrics = {"trace_id": trace_id, "intent_reason": intent_reason,
               "llm_calls": 1, "tool_calls": 0, "successful_tools": 0}
    yield {"type": "intent", "intent": intent.value}
    if (fixed := _fixed_answer(intent)) is not None:
        yield {"type": "delta", "text": fixed}
        yield {"type": "final", "response": _make_response(fixed, [], intent, trace_id, metrics)}
        return
    messages, traces, allowed = _messages(intent, message, history), [], _INTENT_TOOL_NAMES[intent]
    for _ in range(MAX_TOOL_STEPS):
        stream = _completion_with_retry(llm, settings, messages=messages,
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
