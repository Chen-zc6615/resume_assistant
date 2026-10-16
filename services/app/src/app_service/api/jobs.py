"""岗位接口：CRUD、状态管理、简历分组、按组执行硬性初筛。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_service.api.resume import brief_from
from app_service.api.screen import _run_out
from app_service.db.session import get_db
from app_service.models.db_models import Job, JobResumeGroup, Requirement, Resume
from app_service.models.schemas import (
    FilterRunOut,
    JobOut,
)
from app_service.models.schemas import (
    Job as JobCreate,
)
from app_service.services.screen_service import SCREENABLE_STATUSES, create_run_from_job

router = APIRouter()


def _requirement_or_404(db: Session, requirement_id: int) -> Requirement:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, f"需求 {requirement_id} 不存在")
    return requirement


# ---------------------- 分组管理 ----------------------


class GroupAddRequest(BaseModel):
    resume_ids: list[int] = Field(min_length=1)


class GroupResumeBrief(BaseModel):
    """组内简历 + 分配依据（自动分配的命中技能 / 手动添加标记）。"""

    resume_id: int
    original_file_name: str
    status: int
    status_label: str
    failure_reason: str | None
    uploaded_by: str
    created_at: str | None
    added_by: str
    match_detail: dict | None


@router.get("/{job_id}/resumes", response_model=list[GroupResumeBrief])
def list_group_resumes(job_id: int, db: Session = Depends(get_db)):
    """岗位组内简历列表（含分配依据，自动分配与手动调整可区分）。"""
    if db.get(Job, job_id) is None:
        raise HTTPException(404, "岗位不存在")
    rows = db.execute(
        select(JobResumeGroup, Resume)
        .join(Resume, JobResumeGroup.resume_id == Resume.resume_id)
        .where(JobResumeGroup.job_id == job_id)
    ).all()
    out = []
    for group, resume in rows:
        brief = brief_from(resume)
        out.append(
            GroupResumeBrief(
                **brief.model_dump(),
                added_by=group.added_by,
                match_detail=group.match_detail,
            )
        )
    return out


@router.post("/{job_id}/resumes")
def add_resumes_to_group(job_id: int, req: GroupAddRequest, db: Session = Depends(get_db)):
    """把简历分入岗位组（可多组；重复分入幂等跳过）。"""
    if db.get(Job, job_id) is None:
        raise HTTPException(404, "岗位不存在")
    added, skipped = 0, 0
    for rid in req.resume_ids:
        resume = db.get(Resume, rid)
        if resume is None:
            raise HTTPException(404, f"简历 {rid} 不存在")
        exists = db.scalar(
            select(JobResumeGroup).where(
                JobResumeGroup.job_id == job_id, JobResumeGroup.resume_id == rid
            )
        )
        if exists:
            skipped += 1
            continue
        db.add(JobResumeGroup(job_id=job_id, resume_id=rid, added_by="hr_admin"))
        added += 1
    db.commit()
    return {"ok": True, "added": added, "skipped_duplicated": skipped}


@router.delete("/{job_id}/resumes/{resume_id}")
def remove_resume_from_group(job_id: int, resume_id: int, db: Session = Depends(get_db)):
    """把简历移出岗位组。"""
    row = db.scalar(
        select(JobResumeGroup).where(
            JobResumeGroup.job_id == job_id, JobResumeGroup.resume_id == resume_id
        )
    )
    if row is None:
        raise HTTPException(404, "该简历不在此岗位组中")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{job_id}/screen", response_model=FilterRunOut)
def screen_group(job_id: int, db: Session = Depends(get_db)):
    """对该岗位组执行硬性条件初筛（手动触发，JD 规则快照留痕）。

    组内可筛简历参与（初筛不通过/已入库的出局简历排除）；
    三态结果与多岗归并同现有初筛逻辑。
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    rows = db.scalars(select(JobResumeGroup).where(JobResumeGroup.job_id == job_id)).all()
    resume_ids = [r.resume_id for r in rows]
    if not resume_ids:
        raise HTTPException(400, "岗位组内没有简历，请先分组再执行初筛")
    selectable = db.scalars(
        select(Resume.resume_id).where(
            Resume.resume_id.in_(resume_ids),
            Resume.status.in_(SCREENABLE_STATUSES),
        )
    ).all()
    if not selectable:
        raise HTTPException(400, "组内简历均已出局（初筛不通过/已入库），无可筛简历")
    run = create_run_from_job(db, job, resume_ids=selectable)
    db.refresh(run)
    return _run_out(db, run)


@router.post("", response_model=JobOut)
def create_job(req: JobCreate, db: Session = Depends(get_db)):
    _requirement_or_404(db, req.requirement_id)
    job = Job(
        requirement_id=req.requirement_id,
        job_code=req.job_code,
        job_name=req.job_name,
        headcount=req.headcount,
        major=req.major,
        job_jd=req.job_jd,
        job_min_degree=req.job_min_degree,
        job_min_exp_years=req.job_min_exp_years,
        job_required_skills=req.job_required_skills,
        job_optional_skills=req.job_optional_skills,
        bonus_items=req.bonus_items,
        job_status=req.job_status,
        job_created_by=req.job_created_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.job_id.desc())).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    return job


@router.put("/{job_id}", response_model=JobOut)
def update_job(job_id: int, req: JobCreate, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    _requirement_or_404(db, req.requirement_id)
    job.requirement_id = req.requirement_id
    job.job_code = req.job_code
    job.job_name = req.job_name
    job.headcount = req.headcount
    job.major = req.major
    job.job_jd = req.job_jd
    job.job_min_degree = req.job_min_degree
    job.job_min_exp_years = req.job_min_exp_years
    job.job_required_skills = req.job_required_skills
    job.job_optional_skills = req.job_optional_skills
    job.bonus_items = req.bonus_items
    job.job_status = req.job_status
    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    db.delete(job)
    db.commit()
    return {"ok": True}
