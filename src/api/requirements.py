"""需求接口：CRUD、状态管理、需求池（简历归属）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.resume import brief_from
from src.db.session import get_db
from src.models.db_models import (
    FilterRun,
    FilterTemplate,
    Job,
    JobResumeGroup,
    Requirement,
    RequirementResumeGroup,
    Resume,
)
from src.models.schemas import Requirement as RequirementCreate
from src.models.schemas import RequirementOut, ResumeBrief
from src.services.assign_service import assign_resumes
from src.services.screen_service import SCREENABLE_STATUSES, create_run_from_job

router = APIRouter()


def _out_with_counts(db: Session, requirement: Requirement) -> RequirementOut:
    """填充需求下的岗位数与需求池简历数（展示统计）。"""
    out = RequirementOut.model_validate(requirement)
    out.job_count = db.scalar(
        select(func.count()).select_from(Job).where(Job.requirement_id == requirement.requirement_id)
    )
    out.resume_count = db.scalar(
        select(func.count())
        .select_from(RequirementResumeGroup)
        .where(RequirementResumeGroup.requirement_id == requirement.requirement_id)
    )
    return out


# ---------------------- 需求池 ----------------------


class PoolAddRequest(BaseModel):
    resume_ids: list[int] = Field(min_length=1)


@router.get("/{requirement_id}/resumes", response_model=list[ResumeBrief])
def list_pool_resumes(requirement_id: int, db: Session = Depends(get_db)):
    """需求池内简历列表（含各流转状态）。"""
    if db.get(Requirement, requirement_id) is None:
        raise HTTPException(404, "需求不存在")
    stmt = select(Resume).join(
        RequirementResumeGroup, RequirementResumeGroup.resume_id == Resume.resume_id
    ).where(RequirementResumeGroup.requirement_id == requirement_id)
    return [brief_from(r) for r in db.scalars(stmt)]


@router.post("/{requirement_id}/resumes")
def add_resumes_to_pool(requirement_id: int, req: PoolAddRequest, db: Session = Depends(get_db)):
    """把已有简历归入需求池（幂等；归入后需手动触发重筛或等待重跑分配）。"""
    if db.get(Requirement, requirement_id) is None:
        raise HTTPException(404, "需求不存在")
    added, skipped = 0, 0
    for rid in req.resume_ids:
        resume = db.get(Resume, rid)
        if resume is None:
            raise HTTPException(404, f"简历 {rid} 不存在")
        exists = db.scalar(
            select(RequirementResumeGroup).where(
                RequirementResumeGroup.requirement_id == requirement_id,
                RequirementResumeGroup.resume_id == rid,
            )
        )
        if exists:
            skipped += 1
            continue
        db.add(RequirementResumeGroup(requirement_id=requirement_id, resume_id=rid, added_by="hr_admin"))
        added += 1
    db.commit()
    return {"ok": True, "added": added, "skipped_duplicated": skipped}


@router.delete("/{requirement_id}/resumes/{resume_id}")
def remove_resume_from_pool(requirement_id: int, resume_id: int, db: Session = Depends(get_db)):
    """把简历移出需求池（岗位分组保留，仅解除需求归属）。"""
    row = db.scalar(
        select(RequirementResumeGroup).where(
            RequirementResumeGroup.requirement_id == requirement_id,
            RequirementResumeGroup.resume_id == resume_id,
        )
    )
    if row is None:
        raise HTTPException(404, "该简历不在此需求池中")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{requirement_id}/reassign")
def reassign_pool(requirement_id: int, db: Session = Depends(get_db)):
    """把需求池内可筛简历重新全量分配到各开放岗位并执行初筛。

    场景：上传后又新增/开放了岗位（如后建的产品经理岗），存量简历
    不会自动进新岗位组——一键补分配并按岗重筛。幂等：已在组内的跳过。
    """
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, "需求不存在")
    resume_ids = db.scalars(
        select(Resume.resume_id)
        .join(RequirementResumeGroup, RequirementResumeGroup.resume_id == Resume.resume_id)
        .where(
            RequirementResumeGroup.requirement_id == requirement_id,
            Resume.status.in_(SCREENABLE_STATUSES),
        )
    ).all()
    if not resume_ids:
        raise HTTPException(400, "需求池内没有可筛简历（出局/已入库/未归一化的除外）")
    assignments = assign_resumes(db, requirement, resume_ids)
    for job_id, rids in assignments.items():
        job = db.get(Job, job_id)
        if job is not None:
            create_run_from_job(db, job, resume_ids=rids)
    return {
        "ok": True,
        "assigned_jobs": len(assignments),
        "runs": len(assignments),
        "total_resumes": len(resume_ids),
    }


# ---------------------- CRUD ----------------------


@router.post("", response_model=RequirementOut)
def create_requirement(req: RequirementCreate, db: Session = Depends(get_db)):
    requirement = Requirement(
        requirement_name=req.requirement_name,
        dept=req.dept,
        deadline=req.deadline,
        description=req.description,
        status=req.status,
        created_by=req.created_by,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return _out_with_counts(db, requirement)


@router.get("", response_model=list[RequirementOut])
def list_requirements(db: Session = Depends(get_db)):
    requirements = db.scalars(select(Requirement).order_by(Requirement.requirement_id.desc())).all()
    return [_out_with_counts(db, r) for r in requirements]


@router.get("/{requirement_id}", response_model=RequirementOut)
def get_requirement(requirement_id: int, db: Session = Depends(get_db)):
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, "需求不存在")
    return _out_with_counts(db, requirement)


@router.put("/{requirement_id}", response_model=RequirementOut)
def update_requirement(requirement_id: int, req: RequirementCreate, db: Session = Depends(get_db)):
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, "需求不存在")
    requirement.requirement_name = req.requirement_name
    requirement.dept = req.dept
    requirement.deadline = req.deadline
    requirement.description = req.description
    requirement.status = req.status
    db.commit()
    db.refresh(requirement)
    return _out_with_counts(db, requirement)


@router.delete("/{requirement_id}")
def delete_requirement(requirement_id: int, db: Session = Depends(get_db)):
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, "需求不存在")
    # 级联清理：岗位（及其模板/筛选任务/结果/分组）+ 需求池
    # 外键约束下顺序：先删 runs（带 results 级联）、模板、分组，再删岗位，最后需求；
    # 用 ORM 对象级删除（不用 bulk delete）——否则 relationship 集合与 session 脱钩，
    # flush 时 ORM 对已删子对象置空 NOT NULL 外键，反而触发约束失败
    jobs = db.scalars(select(Job).where(Job.requirement_id == requirement_id)).all()
    for job in jobs:
        for run in db.scalars(select(FilterRun).where(FilterRun.job_id == job.job_id)).all():
            db.delete(run)  # FilterRun.results 级联删 results
        for tpl in db.scalars(
            select(FilterTemplate).where(FilterTemplate.job_id == job.job_id)
        ).all():
            db.delete(tpl)
        for grp in db.scalars(
            select(JobResumeGroup).where(JobResumeGroup.job_id == job.job_id)
        ).all():
            db.delete(grp)
        db.delete(job)
    db.delete(requirement)  # resume_groups relationship 级联删需求池关联
    db.commit()
    return {"ok": True}
