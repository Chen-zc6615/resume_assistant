"""招聘 Agent API：仅开放受控的只读问答。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app_service.db.session import get_db
from app_service.models.schemas import AgentChatRequest, AgentChatResponse
from app_service.services import agent_service

router = APIRouter()


@router.post("/chat", response_model=AgentChatResponse)
def chat(req: AgentChatRequest, db: Session = Depends(get_db)) -> AgentChatResponse:
    try:
        return agent_service.chat(db, req.message)
    except agent_service.AgentUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except agent_service.AgentProtocolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
