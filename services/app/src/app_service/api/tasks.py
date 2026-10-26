"""ChatGPT 风格的持久化任务与具体动作审批接口。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app_service.core.identity import get_trusted_actor
from app_service.core.logger import get_logger
from app_service.db.session import get_db
from app_service.models.schemas import (
    AgentActionDecision,
    AgentActionOut,
    AgentMessageOut,
    AgentTaskCreate,
    AgentTaskDetail,
    AgentTaskMessageCreate,
    AgentTaskMessageResponse,
    AgentTaskOut,
    AgentTaskUpdate,
)
from app_service.services import agent_service, task_service

router = APIRouter()
logger = get_logger(__name__)


def _sse(event: dict) -> str:
    """把事件 dict 编码为一条 SSE 帧。"""
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("", response_model=AgentTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    req: AgentTaskCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    return task_service.create_task(db, actor, req.title)


@router.get("", response_model=list[AgentTaskOut])
def list_tasks(
    db: Session = Depends(get_db), actor: str = Depends(get_trusted_actor)
):
    return task_service.list_tasks(db, actor)


@router.get("/{task_id}", response_model=AgentTaskDetail)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    try:
        return task_service.get_task(db, task_id, actor)
    except task_service.TaskNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/{task_id}", response_model=AgentTaskOut)
def rename_task(
    task_id: int,
    req: AgentTaskUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    try:
        return task_service.rename_task(db, task_id, actor, req.title)
    except task_service.TaskNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    try:
        task_service.delete_task(db, task_id, actor)
    except task_service.TaskNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/messages", response_model=AgentTaskMessageResponse)
def send_message(
    task_id: int,
    req: AgentTaskMessageCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    try:
        user_message, assistant_message, actions = task_service.send_message(
            db, task_id, actor, req.message
        )
        return AgentTaskMessageResponse(
            user_message=user_message,
            assistant_message=assistant_message,
            new_actions=actions,
        )
    except task_service.TaskNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except agent_service.AgentUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except agent_service.AgentProtocolError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/{task_id}/messages/stream")
def send_message_stream(
    task_id: int,
    req: AgentTaskMessageCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    """SSE 流式发消息：delta 打字机事件 + 工具执行事件 + done 终态（完整落库结果）。

    404（任务不存在）在流打开前以 HTTP 状态返回；运行期异常以
    {"type": "error"} 事件下发（连接此时已建立，无法再改状态码）。
    """
    # 先校验任务存在，避免 404 深入流内
    try:
        task_service.get_task(db, task_id, actor)
    except task_service.TaskNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    def event_stream():
        try:
            for event in task_service.send_message_stream(
                db, task_id, actor, req.message
            ):
                if event["type"] == "done":
                    payload = AgentTaskMessageResponse(
                        user_message=AgentMessageOut.model_validate(
                            event["user_message"]
                        ),
                        assistant_message=AgentMessageOut.model_validate(
                            event["assistant_message"]
                        ),
                        new_actions=[
                            AgentActionOut.model_validate(a) for a in event["actions"]
                        ],
                    ).model_dump(mode="json")
                    yield _sse({"type": "done", "payload": payload})
                else:
                    yield _sse(event)
        except agent_service.AgentUnavailableError as exc:
            yield _sse({"type": "error", "detail": str(exc), "status": 503})
        except agent_service.AgentProtocolError as exc:
            yield _sse({"type": "error", "detail": str(exc), "status": 502})
        except Exception as exc:  # noqa: BLE001 —— SSE 已建立，兜底转为错误事件
            logger.exception("任务流式响应中断")
            yield _sse({"type": "error", "detail": str(exc), "status": 500})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{task_id}/actions/{action_id}/decision", response_model=AgentActionOut)
def decide_action(
    task_id: int,
    action_id: int,
    req: AgentActionDecision,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    try:
        return task_service.decide_action(
            db,
            task_id,
            action_id,
            actor,
            approved=req.approved,
            reason=req.reason,
        )
    except (task_service.TaskNotFoundError, task_service.ActionNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except (task_service.ActionConflictError, task_service.StaleActionError) as exc:
        raise HTTPException(409, str(exc)) from exc
