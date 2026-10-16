"""批次编排：上传后自动串联 解析 -> 归一化 -> 岗位分配 -> 按岗初筛（PRD 状态机）。

批次进度存内存（MVP），供前端进度条轮询。
"""

from __future__ import annotations

import threading

from sqlalchemy.orm import Session

from app_service.clients import parser_client
from app_service.core.logger import get_logger
from app_service.db.session import SessionLocal
from app_service.models.db_models import Job, Requirement, Resume
from app_service.services.assign_service import assign_resumes
from app_service.services.normalize_service import normalize_resume
from app_service.services.screen_service import create_run_from_job
from app_service.services.upload_service import (
    STATUS_NORMALIZE_FAILED,
    STATUS_NORMALIZED,
    STATUS_PARSE_FAILED,
    STATUS_PARSED,
    STATUS_PENDING_COMPLETION,
    STATUS_UPLOADED,
    upload_file_path,
)

logger = get_logger(__name__)

# batch_id -> 进度快照
_batches: dict[str, dict] = {}
_lock = threading.Lock()


def register_batch(
    batch_id: str,
    resume_ids: list[int],
    requirement_id: int | None,
    display_ids: list[int] | None = None,
) -> None:
    """登记批次。

    resume_ids：需要处理的（新上传）简历；
    display_ids：进度列表展示全集（含 SHA256 重复复用的已有记录），
    不传时与 resume_ids 一致。重复项 stage 直接置 done 并预置 finished。
    """
    display = display_ids if display_ids is not None else resume_ids
    process_set = set(resume_ids)
    with _lock:
        _batches[batch_id] = {
            "total": len(display),
            "resume_ids": display,
            "requirement_id": requirement_id,
            "finished": len(display) - len(resume_ids),
            "failed": 0,
            "parse_success": 0,
            "normalize_success": 0,
            # 重复复用的简历无需处理，直接 done；新简历从 parsing 开始
            "stages": {rid: ("parsing" if rid in process_set else "done") for rid in display},
        }


def get_batch_status(batch_id: str) -> dict | None:
    with _lock:
        return dict(_batches.get(batch_id)) if batch_id in _batches else None


def _record(batch_id: str, key: str, delta: int = 1) -> None:
    with _lock:
        if batch_id in _batches:
            _batches[batch_id][key] += delta


def _set_stage(batch_id: str, resume_id: int, stage: str) -> None:
    with _lock:
        if batch_id in _batches and resume_id in _batches[batch_id]["stages"]:
            _batches[batch_id]["stages"][resume_id] = stage


def _set_stages(batch_id: str, resume_ids: list[int], stage: str) -> None:
    with _lock:
        if batch_id in _batches:
            for rid in resume_ids:
                if rid in _batches[batch_id]["stages"]:
                    _batches[batch_id]["stages"][rid] = stage


def process_batch(batch_id: str, resume_ids: list[int], requirement_id: int | None) -> None:
    """后台任务入口（FastAPI BackgroundTasks，线程池中同步执行）。

    流程：逐份 解析->归一化；批次内归一化成功的简历统一做岗位分配
    （确定性规则，一份可入多岗）→ 对每个命中岗位各跑一次硬性初筛
    （F-03 归一化成功自动触发），落 filter_runs/results 留痕。
    """
    db: Session = SessionLocal()
    normalized_ids: list[int] = []
    try:
        for resume_id in resume_ids:
            resume = db.get(Resume, resume_id)
            if resume is None:
                continue
            _set_stage(batch_id, resume_id, "parsing")
            ok = _process_one(db, batch_id, resume)
            if ok:
                normalized_ids.append(resume_id)
            # 将参与分配/初筛的简历停在归一化阶段，等批次末统一处理后再置 done
            if not (ok and requirement_id is not None):
                _set_stage(batch_id, resume_id, "done")
            _record(batch_id, "finished")
        # 岗位分配 + 按岗初筛：对批次内归一化成功的简历统一执行（规则快照落 run）
        if requirement_id is not None and normalized_ids:
            _set_stages(batch_id, normalized_ids, "screening")
            requirement = db.get(Requirement, requirement_id)
            if requirement is not None:
                assignments = assign_resumes(db, requirement, normalized_ids)
                for job_id, rids in assignments.items():
                    job = db.get(Job, job_id)
                    if job is not None:
                        create_run_from_job(db, job, resume_ids=rids)
            _set_stages(batch_id, normalized_ids, "done")
    finally:
        db.close()
    logger.info("批次 %s 处理完成", batch_id)


def _process_one(db: Session, batch_id: str, resume: Resume) -> bool:
    """处理单份简历：解析 -> 归一化。返回是否归一化成功（可参与初筛）。"""
    resume_id = resume.resume_id

    # ---- 阶段1：解析（7 -> 8），经解析服务 ----
    if resume.status in (STATUS_UPLOADED,):
        try:
            result = parser_client.parse_resume_via_service(upload_file_path(resume))
            resume.raw_text = result.text
            resume.status = STATUS_PARSED
            resume.failure_reason = None
            db.commit()
            _record(batch_id, "parse_success")
        except Exception as e:  # noqa: BLE001
            resume.status = STATUS_PARSE_FAILED
            resume.failure_reason = f"解析失败：{e}"
            db.commit()
            _record(batch_id, "failed")
            logger.warning("resume_id=%s 解析失败: %s", resume_id, e)
            return False

    # ---- 阶段2：归一化（8 -> 9/5）----
    if resume.status == STATUS_PARSED:
        _set_stage(batch_id, resume_id, "normalizing")
        try:
            profile_data = normalize_resume(db, resume)
        except Exception as e:  # noqa: BLE001
            resume.status = STATUS_NORMALIZE_FAILED
            resume.failure_reason = f"归一化失败：{e}"
            db.commit()
            _record(batch_id, "failed")
            logger.warning("resume_id=%s 归一化失败: %s", resume_id, e)
            return False
        _record(batch_id, "normalize_success")
        # 联系方式缺失 -> 待补录（S04：字段缺失≠整体失败，不编造）
        if profile_data.phone is None or profile_data.email is None:
            resume.status = STATUS_PENDING_COMPLETION
            resume.failure_reason = "关键字段缺失（电话/邮箱待 HR 补录）"
        else:
            resume.status = STATUS_NORMALIZED
            resume.failure_reason = None
        db.commit()

    # 可参与初筛：归一化成功或仅待补录
    return resume.status in (STATUS_NORMALIZED, STATUS_PENDING_COMPLETION)


def reparse_resume(resume_id: int) -> None:
    """单份重解析（API 触发）。"""
    db: Session = SessionLocal()
    try:
        resume = db.get(Resume, resume_id)
        if resume is None:
            return
        resume.status = STATUS_UPLOADED
        resume.failure_reason = None
        db.commit()
        process_batch(f"reparse-{resume_id}", [resume_id], None)
    finally:
        db.close()
