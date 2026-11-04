"""人才域接口：面试邀约、沉淀候选人才库（人才库管理页）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_service.api.resume import brief_from
from app_service.clients.knowledge_client import KnowledgeServiceError
from app_service.core.identity import get_trusted_actor
from app_service.core.logger import get_logger
from app_service.db.session import get_db
from app_service.models.db_models import Interview, Job, Requirement, Resume, TalentPool
from app_service.models.schemas import InterviewCreate, InterviewOut, TalentPoolIn, TalentPoolOut
from app_service.services.talent_knowledge_service import (
    TalentKnowledgeDataError,
    delete_talent_from_knowledge,
    sync_talent_to_knowledge,
)

router = APIRouter()
logger = get_logger(__name__)


# ---------------------- 面试邀约 ----------------------


@router.post("/interviews", response_model=InterviewOut)
def create_interview(
    req: InterviewCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    """发起面试邀约（留痕；同时把简历标记为「已邀请面试」）。"""
    resume = db.get(Resume, req.resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    if req.job_id is not None and db.get(Job, req.job_id) is None:
        raise HTTPException(404, "关联岗位不存在")
    interview = Interview(
        resume_id=req.resume_id,
        job_id=req.job_id,
        interview_time=req.interview_time,
        way=req.way,
        interviewer=req.interviewer,
        note=req.note,
        notify_way=req.notify_way,
        created_by=actor,
    )
    db.add(interview)
    resume.interview_status = 1  # 已邀请面试
    db.commit()
    db.refresh(interview)
    return _interview_out(db, interview)


@router.get("/interviews", response_model=list[InterviewOut])
def list_interviews(
    resume_id: int | None = Query(default=None), db: Session = Depends(get_db)
):
    """面试邀约列表（可按简历过滤）。"""
    stmt = select(Interview).order_by(Interview.interview_id.desc())
    if resume_id is not None:
        stmt = stmt.where(Interview.resume_id == resume_id)
    return [_interview_out(db, i) for i in db.scalars(stmt)]


def _interview_out(db: Session, interview: Interview) -> InterviewOut:
    out = InterviewOut.model_validate(interview)
    if interview.job_id is not None:
        job = db.get(Job, interview.job_id)
        if job is not None:
            out.job_name = job.job_name
    return out


# ---------------------- 沉淀候选人才库 ----------------------


@router.post("/pool", response_model=TalentPoolOut)
def add_to_pool(
    req: TalentPoolIn,
    resume_id: int = Query(...),
    db: Session = Depends(get_db),
    actor: str = Depends(get_trusted_actor),
):
    """把简历沉淀入候选人才库（HR 复核后长期储备；一份简历一条，重复入库 409）。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    exists = db.scalar(select(TalentPool).where(TalentPool.resume_id == resume_id))
    if exists is not None:
        raise HTTPException(409, "该简历已在沉淀候选人才库中")
    if req.source_requirement_id is not None and db.get(Requirement, req.source_requirement_id) is None:
        raise HTTPException(404, "来源需求不存在")
    if req.source_job_id is not None and db.get(Job, req.source_job_id) is None:
        raise HTTPException(404, "来源岗位不存在")
    entry = TalentPool(
        resume_id=resume_id,
        source_requirement_id=req.source_requirement_id,
        source_job_id=req.source_job_id,
        note=req.note,
        created_by=actor,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    try:
        sync_talent_to_knowledge(db, entry)
    except (KnowledgeServiceError, TalentKnowledgeDataError) as exc:
        # 人才库沉淀已经成功；外部知识库故障不能回滚独立的业务事务。
        logger.warning(
            "人才已沉淀但知识库同步失败 pool_id=%s resume_id=%s: %s",
            entry.pool_id,
            entry.resume_id,
            exc,
        )
    return _pool_out(db, entry)


@router.get("/pool", response_model=list[TalentPoolOut])
def list_pool(db: Session = Depends(get_db)):
    """沉淀候选人才库列表（含简历信息与来源）。"""
    entries = db.scalars(select(TalentPool).order_by(TalentPool.pool_id.desc())).all()
    return [_pool_out(db, e) for e in entries]


@router.delete("/pool/{pool_id}")
def remove_from_pool(pool_id: int, db: Session = Depends(get_db)):
    """移出沉淀库（简历记录保留，仅解除沉淀标记）。"""
    entry = db.get(TalentPool, pool_id)
    if entry is None:
        raise HTTPException(404, "该记录不在沉淀库中")
    db.delete(entry)
    db.commit()
    try:
        delete_talent_from_knowledge(pool_id)
    except KnowledgeServiceError as exc:
        # 数据库是业务真理之源；索引删除失败留日志，允许后续重复删除。
        logger.warning("人才已移出但知识库删除失败 pool_id=%s: %s", pool_id, exc)
    return {"ok": True}


@router.post("/pool/{pool_id}/sync-knowledge")
def retry_pool_knowledge_sync(pool_id: int, db: Session = Depends(get_db)):
    """手动重试人才 Wiki 生成与知识库索引。"""

    entry = db.get(TalentPool, pool_id)
    if entry is None:
        raise HTTPException(404, "该记录不在沉淀库中")
    try:
        result = sync_talent_to_knowledge(db, entry)
    except TalentKnowledgeDataError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KnowledgeServiceError as exc:
        raise HTTPException(503, "知识库同步失败，请稍后重试") from exc
    return {
        "ok": True,
        "talent_card_id": result.talent_card_id,
        "chunk_count": result.chunk_count,
    }


def _pool_out(db: Session, entry: TalentPool) -> TalentPoolOut:
    # 显式构造（不用 model_validate：from_attributes 会把 ORM 的 resume 关系对象
    # 误灌进嵌套的 ResumeBrief，触发校验错误）
    out = TalentPoolOut(
        pool_id=entry.pool_id,
        resume_id=entry.resume_id,
        source_requirement_id=entry.source_requirement_id,
        source_job_id=entry.source_job_id,
        note=entry.note,
        created_by=entry.created_by,
        created_at=str(entry.created_at) if entry.created_at else None,
        knowledge_sync_status=entry.knowledge_sync_status,
        knowledge_talent_card_id=entry.knowledge_talent_card_id,
        knowledge_chunk_count=entry.knowledge_chunk_count,
        knowledge_sync_error=entry.knowledge_sync_error,
        knowledge_synced_at=(
            str(entry.knowledge_synced_at) if entry.knowledge_synced_at else None
        ),
    )
    resume = db.get(Resume, entry.resume_id)
    if resume is not None:
        out.resume = brief_from(resume)
    if entry.source_requirement_id is not None:
        r = db.get(Requirement, entry.source_requirement_id)
        if r is not None:
            out.source_requirement_name = r.requirement_name
    if entry.source_job_id is not None:
        j = db.get(Job, entry.source_job_id)
        if j is not None:
            out.source_job_name = j.job_name
    return out
