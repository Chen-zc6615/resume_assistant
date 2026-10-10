"""解析批次接口：进度轮询（前端进度条）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.resume import brief_from
from src.db.session import SessionLocal
from src.models.schemas import ParseStatusResponse, ResumeStageBrief
from src.services.pipeline import get_batch_status

router = APIRouter()


@router.get("/{batch_id}/status", response_model=ParseStatusResponse)
def batch_status(batch_id: str):
    snapshot = get_batch_status(batch_id)
    if snapshot is None:
        raise HTTPException(404, "批次不存在")
    db = SessionLocal()
    try:
        from sqlalchemy import select

        from src.models.db_models import Resume

        resumes = db.scalars(
            select(Resume).where(Resume.resume_id.in_(snapshot["resume_ids"]))
        ).all()
        stages: dict = snapshot.get("stages", {})
        stage_counts = {"parsing": 0, "normalizing": 0, "screening": 0}
        for st in stages.values():
            if st in stage_counts:
                stage_counts[st] += 1
        return ParseStatusResponse(
            batch_id=batch_id,
            total=snapshot["total"],
            finished=snapshot["finished"],
            failed=snapshot["failed"],
            parse_success=snapshot["parse_success"],
            normalize_success=snapshot["normalize_success"],
            parsing=stage_counts["parsing"],
            normalizing=stage_counts["normalizing"],
            screening=stage_counts["screening"],
            per_resume=[
                ResumeStageBrief(
                    **brief_from(r).model_dump(),
                    stage=stages.get(r.resume_id),
                )
                for r in resumes
            ],
        )
    finally:
        db.close()
