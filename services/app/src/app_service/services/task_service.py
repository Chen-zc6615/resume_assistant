"""持久化 Agent 任务、消息与 HR 动作审批。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app_service.models.db_models import (
    AgentAction,
    AgentMessage,
    AgentTask,
    Interview,
    Job,
    Resume,
)
from app_service.models.schemas import AgentChatResponse
from app_service.services import agent_service
from app_service.services.screen_service import evaluate_profile, rules_from_job


class TaskNotFoundError(RuntimeError):
    pass


class ActionNotFoundError(RuntimeError):
    pass


class ActionConflictError(RuntimeError):
    pass


class StaleActionError(RuntimeError):
    pass


def list_tasks(db: Session, actor: str) -> list[AgentTask]:
    return list(
        db.scalars(
            select(AgentTask)
            .where(AgentTask.created_by == actor)
            .order_by(AgentTask.updated_at.desc(), AgentTask.task_id.desc())
        )
    )


def create_task(db: Session, actor: str, title: str | None = None) -> AgentTask:
    task = AgentTask(title=(title or "新任务").strip() or "新任务", created_by=actor)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int, actor: str) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None or task.created_by != actor:
        raise TaskNotFoundError("任务不存在")
    return task


def rename_task(db: Session, task_id: int, actor: str, title: str) -> AgentTask:
    task = get_task(db, task_id, actor)
    task.title = title.strip()
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: int, actor: str) -> None:
    task = get_task(db, task_id, actor)
    db.delete(task)
    db.commit()


def _create_actions_from_response(
    db: Session, task: AgentTask, response: AgentChatResponse
) -> list[AgentAction]:
    created: list[AgentAction] = []
    for trace in response.tool_traces:
        proposal = (trace.result or {}).get("action_proposal")
        if not trace.success or not isinstance(proposal, dict):
            continue
        if proposal.get("action_type") != "CREATE_INTERVIEW_INVITATION":
            continue
        pending_actions = db.scalars(
            select(AgentAction).where(
                AgentAction.task_id == task.task_id,
                AgentAction.action_type == "CREATE_INTERVIEW_INVITATION",
                AgentAction.status == "pending",
            )
        ).all()
        if any(
            existing.payload.get("resume_id") == proposal.get("resume_id")
            and existing.payload.get("job_id") == proposal.get("job_id")
            for existing in pending_actions
        ):
            continue
        action = AgentAction(
            task_id=task.task_id,
            action_type="CREATE_INTERVIEW_INVITATION",
            status="pending",
            payload=proposal,
        )
        db.add(action)
        created.append(action)
    return created


def send_message(
    db: Session,
    task_id: int,
    actor: str,
    message: str,
    *,
    completion_fn: Callable[..., Any] | None = None,
) -> tuple[AgentMessage, AgentMessage, list[AgentAction]]:
    """发送消息并持久化 Agent 回答；completion_fn 缺省时走 model_client Agent 通道。"""
    task = get_task(db, task_id, actor)
    history = [
        {"role": item.role, "content": item.content}
        for item in task.messages[-20:]
    ]
    user_message = AgentMessage(
        task_id=task.task_id, role="user", content=message.strip(), tool_traces=[]
    )
    db.add(user_message)
    db.flush()

    response = agent_service.chat(db, message.strip(), completion_fn=completion_fn, history=history)
    assistant_message = AgentMessage(
        task_id=task.task_id,
        role="assistant",
        content=response.answer,
        tool_traces=[trace.model_dump(mode="json") for trace in response.tool_traces],
        intent=response.intent,
        trace_id=response.trace_id,
        metrics=response.metrics,
    )
    db.add(assistant_message)
    actions = _create_actions_from_response(db, task, response)
    if task.title == "新任务":
        task.title = message.strip()[:120]
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    for action in actions:
        db.refresh(action)
    return user_message, assistant_message, actions


def send_message_stream(
    db: Session,
    task_id: int,
    actor: str,
    message: str,
    *,
    completion_fn: Callable[..., Any] | None = None,
):
    """send_message 的流式版本：转发 agent 事件，落库契约与同步版一致。

    事件流（供 SSE 端点序列化）：
      {"type": "delta", "text": str}
      {"type": "tool", "name": str, "success": bool}
      {"type": "done", "user_message": ORM, "assistant_message": ORM, "actions": [ORM]}
    done 事件携带 ORM 对象，由路由层用 Out 模型序列化后再下发。
    """
    task = get_task(db, task_id, actor)  # 404 语义异常在生成器首次推进时抛出
    history = [
        {"role": item.role, "content": item.content}
        for item in task.messages[-20:]
    ]
    user_message = AgentMessage(
        task_id=task.task_id, role="user", content=message.strip(), tool_traces=[]
    )
    db.add(user_message)
    db.flush()

    final = None
    for event in agent_service.chat_stream(
        db, message.strip(), completion_fn=completion_fn, history=history
    ):
        if event["type"] == "final":
            final = event["response"]
        else:
            yield event

    assistant_message = AgentMessage(
        task_id=task.task_id,
        role="assistant",
        content=final.answer,
        tool_traces=[trace.model_dump(mode="json") for trace in final.tool_traces],
        intent=final.intent,
        trace_id=final.trace_id,
        metrics=final.metrics,
    )
    db.add(assistant_message)
    actions = _create_actions_from_response(db, task, final)
    if task.title == "新任务":
        task.title = message.strip()[:120]
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    for action in actions:
        db.refresh(action)
    yield {
        "type": "done",
        "user_message": user_message,
        "assistant_message": assistant_message,
        "actions": actions,
    }


def decide_action(
    db: Session,
    task_id: int,
    action_id: int,
    actor: str,
    *,
    approved: bool,
    reason: str | None = None,
) -> AgentAction:
    task = get_task(db, task_id, actor)
    action = db.scalar(
        select(AgentAction)
        .where(AgentAction.action_id == action_id, AgentAction.task_id == task.task_id)
        .with_for_update()
    )
    if action is None:
        raise ActionNotFoundError("待审批动作不存在")
    if action.status != "pending":
        raise ActionConflictError("该动作已经处理，不能重复审批")
    if not approved:
        if not reason or not reason.strip():
            raise ActionConflictError("驳回原因不能为空")
        action.status = "rejected"
        action.decision_reason = reason.strip()
        action.decided_by = actor
        action.decided_at = datetime.now()
        task.updated_at = datetime.now()
        db.commit()
        db.refresh(action)
        return action

    if action.action_type != "CREATE_INTERVIEW_INVITATION":
        raise ActionConflictError("不支持的动作类型")
    payload = action.payload
    resume = db.get(Resume, payload.get("resume_id"))
    job = db.get(Job, payload.get("job_id"))
    if resume is None or job is None or job.job_status != 1 or job.requirement.status != 0:
        raise StaleActionError("候选人或岗位已失效，请重新执行任务")
    profile = resume.profile
    current_rules = rules_from_job(job)
    if (
        profile is None
        or str(profile.updated_at) != payload.get("profile_updated_at")
        or str(job.updated_at) != payload.get("job_updated_at")
        or current_rules.model_dump() != payload.get("rules_snapshot")
    ):
        raise StaleActionError("简历或岗位规则已更新，请重新执行任务")
    result, _ = evaluate_profile(
        current_rules, profile, [skill.skill_name for skill in profile.skills]
    )
    if result != "PASS" or not (profile.phone and profile.email):
        raise StaleActionError("当前规则结果或联系方式已不满足邀约条件")

    interview = Interview(
        resume_id=resume.resume_id,
        job_id=job.job_id,
        note=f"由任务 #{task.task_id} 经 HR 批准创建",
        created_by=actor,
    )
    db.add(interview)
    db.flush()
    resume.interview_status = 1
    action.status = "executed"
    action.decision_reason = reason.strip() if reason else None
    action.decided_by = actor
    action.decided_at = datetime.now()
    action.result = {"interview_id": interview.interview_id}
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(action)
    return action
