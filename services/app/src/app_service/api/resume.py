"""简历接口：上传、列表、详情、PDF预览、审核编辑、确认入库、重解析、删除。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_service.core.config import get_settings
from app_service.db.session import get_db
from app_service.models.db_models import (
    ProfileSkill,
    Requirement,
    RequirementResumeGroup,
    Resume,
    ResumeProfile,
)
from app_service.models.schemas import (
    InterviewStatusRequest,
    ManualRejectRequest,
    ProfileUpdateRequest,
    ResumeBrief,
    ResumeDetail,
    ResumeProfileData,
    UploadResponse,
)
from app_service.services import pipeline, upload_service
from app_service.services.screen_service import passed_job_names
from app_service.services.upload_service import (
    STATUS_DONE,
    STATUS_LABELS,
    new_batch_id,
    save_upload,
    upload_file_path,
)

router = APIRouter()


def brief_from(resume: Resume) -> ResumeBrief:
    return ResumeBrief(
        resume_id=resume.resume_id,
        original_file_name=resume.original_file_name,
        name=resume.profile.name if resume.profile else None,
        status=resume.status,
        status_label=STATUS_LABELS.get(resume.status, "未知"),
        failure_reason=resume.failure_reason,
        interview_status=resume.interview_status,
        uploaded_by=resume.uploaded_by,
        created_at=str(resume.created_at) if resume.created_at else None,
    )


def profile_to_data(profile: ResumeProfile) -> ResumeProfileData:
    return ResumeProfileData(
        profile_id=profile.profile_id,
        resume_id=profile.resume_id,
        name=profile.name,
        gender=profile.gender,
        phone=profile.phone,
        email=profile.email,
        highest_education=profile.highest_education,
        graduation_institution=profile.graduation_institution,
        total_work_months=profile.total_work_months,
        skills=[s.skill_name for s in profile.skills],
        education_experiences=[
            {
                "education_id": e.education_id,
                "profile_id": e.profile_id,
                "school": e.school,
                "major": e.major,
                "education_level": e.education_level,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "is_current": e.is_current,
            }
            for e in profile.education_experiences
        ],
        work_experiences=[
            {
                "work_id": w.work_id,
                "profile_id": w.profile_id,
                "company": w.company,
                "position": w.position,
                "start_date": w.start_date,
                "end_date": w.end_date,
                "is_current": w.is_current,
                "description": w.description,
            }
            for w in profile.work_experiences
        ],
        project_experiences=[
            {
                "project_id": p.project_id,
                "profile_id": p.profile_id,
                "project_name": p.project_name,
                "role": p.role,
                "start_date": p.start_date,
                "end_date": p.end_date,
                "description": p.description,
            }
            for p in profile.project_experiences
        ],
    )


@router.post("/upload", response_model=UploadResponse)
async def upload(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    files: list[UploadFile] = File(...),
    hr_id: str = Form(default=None),
    requirement_id: int = Form(...),
):
    """批量上传 PDF（F-01）：校验 -> 去重 -> 落盘 -> 后台自动解析/归一化/岗位分配/按岗初筛。

    必须选定需求：本批简历挂入需求池，归一化后按简历内容分配到需求下的岗位。
    """
    if db.get(Requirement, requirement_id) is None:
        raise HTTPException(404, "需求不存在，请先创建需求")
    hr = hr_id or get_settings().default_hr_id
    batch_id = new_batch_id()
    items = []
    display_ids: list[int] = []   # 进度列表展示集（含重复复用的已有记录）
    process_ids: list[int] = []   # 需要处理的（新上传）
    for f in files:
        content = await f.read()
        item = save_upload(db, f.filename or "unknown.pdf", content, hr)
        items.append(item)
        if item.accepted:
            display_ids.append(item.resume_id)
            if not item.duplicated:
                process_ids.append(item.resume_id)

    # 简历归入需求池（含重复复用的已有记录，幂等跳过已在池中的）
    for rid in display_ids:
        exists = db.scalar(
            select(RequirementResumeGroup).where(
                RequirementResumeGroup.requirement_id == requirement_id,
                RequirementResumeGroup.resume_id == rid,
            )
        )
        if not exists:
            db.add(
                RequirementResumeGroup(
                    requirement_id=requirement_id, resume_id=rid, added_by=hr
                )
            )
    db.commit()

    # 重复简历也进批次展示（标已复用、立即完成态），进度列表不"少人"
    pipeline.register_batch(batch_id, process_ids, requirement_id, display_ids)
    if process_ids:
        background_tasks.add_task(pipeline.process_batch, batch_id, process_ids, requirement_id)
    return UploadResponse(batch_id=batch_id, items=items)


@router.get("", response_model=list[ResumeBrief])
def list_resumes(
    db: Session = Depends(get_db),
    status: int | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
):
    stmt = select(Resume).order_by(Resume.resume_id.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Resume.status == status)
    return [brief_from(r) for r in db.scalars(stmt)]


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """统计字段：各状态数量（PRD 界面统计区）。"""
    counts: dict[int, int] = {}
    for r in db.scalars(select(Resume)):
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "total": sum(counts.values()),
        "by_status": {STATUS_LABELS.get(k, k): v for k, v in sorted(counts.items())},
    }


@router.get("/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    profile = resume.profile
    return ResumeDetail(
        resume_id=resume.resume_id,
        original_file_name=resume.original_file_name,
        status=resume.status,
        status_label=STATUS_LABELS.get(resume.status, "未知"),
        failure_reason=resume.failure_reason,
        interview_status=resume.interview_status,
        uploaded_by=resume.uploaded_by,
        created_at=str(resume.created_at) if resume.created_at else None,
        profile=profile_to_data(profile) if profile else None,
    )


@router.get("/{resume_id}/file")
def get_resume_file(resume_id: int, db: Session = Depends(get_db)):
    """原始 PDF（页面内联预览；Content-Disposition 用 inline 而非 attachment，
    否则浏览器触发下载而不是显示）。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    path = upload_file_path(resume)
    if not path.exists():
        raise HTTPException(404, "原始文件缺失")
    encoded_name = quote(resume.original_file_name)
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            # 文件内容不变时浏览器会复用旧缓存响应（含修复前的 attachment 头），
            # 禁止缓存确保 disposition 变更即时生效
            "Cache-Control": "no-store",
        },
    )


@router.patch("/{resume_id}/profile", response_model=ResumeProfileData)
def update_profile(resume_id: int, req: ProfileUpdateRequest, db: Session = Depends(get_db)):
    """HR 人工审核编辑归一化字段（F-04）。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    profile = resume.profile
    if profile is None:
        raise HTTPException(400, "简历尚未归一化，无归一化数据可编辑")
    profile.name = req.name
    profile.gender = req.gender
    profile.phone = req.phone
    profile.email = req.email
    profile.highest_education = req.highest_education
    profile.graduation_institution = req.graduation_institution
    profile.total_work_months = req.total_work_months
    # 技能全量替换
    db.query(ProfileSkill).filter(ProfileSkill.profile_id == profile.profile_id).delete()
    for s in req.skills:
        if s.strip():
            db.add(ProfileSkill(profile_id=profile.profile_id, skill_name=s.strip()))
    # 待补录态且已补全 -> 进入待审核
    if resume.status == upload_service.STATUS_PENDING_COMPLETION and req.phone and req.email:
        resume.status = upload_service.STATUS_SCREEN_PASSED
        resume.failure_reason = None
    db.commit()
    db.refresh(profile)
    return profile_to_data(profile)


@router.post("/{resume_id}/reject")
def reject_resume(resume_id: int, req: ManualRejectRequest, db: Session = Depends(get_db)):
    """人工筛除：原因必填留痕（区别于规则淘汰的 HR 干预）。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    resume.status = upload_service.STATUS_SCREEN_REJECTED
    resume.failure_reason = f"人工筛除：{req.reason}"
    db.commit()
    return {"ok": True, "resume_id": resume_id, "reason": req.reason}


@router.post("/{resume_id}/confirm")
def confirm_resume(resume_id: int, db: Session = Depends(get_db)):
    """确认入库（F-04 后半段）：status=4 已完成，并标记入库岗位。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    if resume.profile is None:
        raise HTTPException(400, "无归一化数据，无法入库")
    resume.status = STATUS_DONE
    # 入库岗位标记：在组岗位中初筛通过的岗位（决策依据随简历留痕展示）
    passed_jobs = passed_job_names(db, resume)
    resume.failure_reason = f"已入库（岗位：{'、'.join(passed_jobs)}）" if passed_jobs else None
    db.commit()
    return {"ok": True, "resume_id": resume_id, "status": STATUS_LABELS[STATUS_DONE]}


@router.post("/{resume_id}/interview-status")
def set_interview_status(resume_id: int, req: InterviewStatusRequest, db: Session = Depends(get_db)):
    """标记候选人面试状态（人才库页）：0 待面试 / 1 已邀请 / 2 面试中 / 3 已入职 / 4 暂不跟进。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    resume.interview_status = req.status
    db.commit()
    return {"ok": True, "resume_id": resume_id, "interview_status": req.status}


@router.post("/{resume_id}/restore")
def restore_resume(resume_id: int, db: Session = Depends(get_db)):
    """恢复待筛：初筛不通过（出局）-> 待初筛，供 HR 在规则修正后重新分组/重筛。

    仅允许从 status=3 恢复；已完成入库（4）为终态不可恢复。
    历史岗位组保留（重筛时各岗最新 run 刷新归并结果）。
    """
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    if resume.status != upload_service.STATUS_SCREEN_REJECTED:
        raise HTTPException(400, "仅初筛不通过的简历可恢复待筛")
    resume.status = upload_service.STATUS_NORMALIZED
    resume.failure_reason = None
    db.commit()
    return {"ok": True, "resume_id": resume_id, "status": STATUS_LABELS[upload_service.STATUS_NORMALIZED]}


@router.post("/{resume_id}/reparse")
def reparse(resume_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    background_tasks.add_task(pipeline.reparse_resume, resume_id)
    return {"ok": True, "resume_id": resume_id, "message": "已触发重新解析"}


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    """删除简历及全部关联数据（归一化、需求池/岗位组、初筛结果），并清理磁盘文件。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    path = upload_file_path(resume)
    # 级联（ORM cascade）：profile / results / 需求池 / 岗位组关联行一并清理
    db.delete(resume)
    db.commit()
    # 物理文件随记录删除（sha256 全局唯一，记录删后必无引用；失败不阻断响应）
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}
