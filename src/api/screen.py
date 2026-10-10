"""初筛接口：模板配置、任务执行、结果查询、CSV 导出。"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.models.db_models import FilterResult, FilterRun, FilterTemplate, Job, Requirement, Resume
from src.models.schemas import (
    FilterResultOut,
    FilterRunCreate,
    FilterRunOut,
    FilterTemplateCreate,
    FilterTemplateOut,
    ReasonItem,
)
from src.services.screen_service import execute_run

router = APIRouter()


def _run_out(db: Session, run: FilterRun) -> FilterRunOut:
    """FilterRun + 展示冗余（岗位名/所属需求）。"""
    out = FilterRunOut.model_validate(run)
    job = db.get(Job, run.job_id)
    if job is not None:
        out.job_name = job.job_name
        out.requirement_id = job.requirement_id
        requirement = db.get(Requirement, job.requirement_id)
        if requirement is not None:
            out.requirement_name = requirement.requirement_name
    return out


@router.post("/templates", response_model=FilterTemplateOut)
def create_template(req: FilterTemplateCreate, db: Session = Depends(get_db)):
    job = db.get(Job, req.job_id)
    if job is None:
        raise HTTPException(404, "关联岗位不存在")
    template = FilterTemplate(
        template_name=req.template_name,
        job_id=req.job_id,
        rules=req.rules.model_dump(),
        created_by=req.created_by,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("/templates", response_model=list[FilterTemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.scalars(select(FilterTemplate).order_by(FilterTemplate.template_id.desc())).all()


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    """删除筛选模板；历史 run 保留（template_id 置空，规则快照仍完整可审计）。"""
    template = db.get(FilterTemplate, template_id)
    if template is None:
        raise HTTPException(404, "筛选模板不存在")
    # 引用该模板的历史 run 解除关联（run 与 results 全部保留）
    db.query(FilterRun).filter(FilterRun.template_id == template_id).update(
        {FilterRun.template_id: None}, synchronize_session=False
    )
    db.delete(template)
    db.commit()
    return {"ok": True}


@router.post("/runs", response_model=FilterRunOut)
def create_run(
    req: FilterRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """执行筛选（F-03）：同步逐份判定（MVP 数据量小，直接跑完返回）。"""
    template = db.get(FilterTemplate, req.template_id)
    if template is None:
        raise HTTPException(404, "筛选模板不存在")
    # 规则快照：执行依据固化到 run，模板事后修改不影响本次判定
    run = FilterRun(
        template_id=template.template_id,
        job_id=template.job_id,
        rules_snapshot=template.rules,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    execute_run(db, run, req.resume_ids)
    db.refresh(run)
    return _run_out(db, run)


@router.get("/runs", response_model=list[FilterRunOut])
def list_runs(limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)):
    """最近的任务列表（默认 10 条，避免下拉无限增长）。"""
    rows = db.scalars(select(FilterRun).order_by(FilterRun.run_id.desc()).limit(limit)).all()
    return [_run_out(db, r) for r in rows]


@router.get("/runs/{run_id}/results", response_model=list[FilterResultOut])
def run_results(run_id: int, db: Session = Depends(get_db)):
    stmt = select(FilterResult).where(FilterResult.run_id == run_id)
    out = []
    for r in db.scalars(stmt):
        resume = db.get(Resume, r.resume_id)
        out.append(
            FilterResultOut(
                result_id=r.result_id,
                run_id=r.run_id,
                resume_id=r.resume_id,
                profile_id=r.profile_id,
                result=r.result,
                reasons=[ReasonItem.model_validate(x) for x in (r.reasons or [])],
                name=resume.profile.name if resume and resume.profile else None,
                original_file_name=resume.original_file_name if resume else None,
            )
        )
    return out


@router.get("/runs/{run_id}/export.csv")
def export_csv(run_id: int, db: Session = Depends(get_db)):
    """导出筛选结果 CSV（架构图 export 接口）。"""
    stmt = select(FilterResult).where(FilterResult.run_id == run_id)
    rows = db.scalars(stmt).all()
    if not rows:
        raise HTTPException(404, "筛选任务无结果")

    buf = io.StringIO()
    buf.write("﻿")  # BOM：Excel 中文兼容
    writer = csv.writer(buf)
    writer.writerow(["resume_id", "姓名", "原始文件名", "结果", "判定明细"])
    result_label = {"PASS": "通过", "REJECT": "不通过", "PENDING_REVIEW": "待人工复核"}
    for r in rows:
        resume = db.get(Resume, r.resume_id)
        name = resume.profile.name if resume and resume.profile else ""
        file_name = resume.original_file_name if resume else ""
        detail = "；".join(
            f"{x.get('rule', '')}：{x.get('detail', '')}" for x in (r.reasons or [])
        )
        writer.writerow([r.resume_id, name, file_name, result_label.get(r.result, r.result), detail])

    filename = f"screening_run_{run_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
