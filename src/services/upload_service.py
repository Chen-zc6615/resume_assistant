"""上传服务：文件校验、SHA256 去重、落盘（F-01 前半段）。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.security import FileValidationError, validate_upload
from src.models.db_models import Resume
from src.models.schemas import UploadItem

logger = get_logger(__name__)

# 简历状态常量（PRD resumes.status 扩展态见 db_models 注释）
STATUS_UPLOAD_FAILED = 0
STATUS_PARSE_FAILED = 1
STATUS_NORMALIZE_FAILED = 2
STATUS_SCREEN_REJECTED = 3
STATUS_DONE = 4
STATUS_PENDING_COMPLETION = 5  # 待补录（关键字段缺失）
STATUS_PENDING_REVIEW = 6      # 待人工复核（初筛信息不足）
STATUS_UPLOADED = 7            # 已上传待解析
STATUS_PARSED = 8              # 解析成功待归一化
STATUS_NORMALIZED = 9          # 归一化成功待初筛
STATUS_SCREEN_PASSED = 10      # 初筛通过待 HR 审核入库

STATUS_LABELS = {
    0: "上传失败",
    1: "解析失败",
    2: "归一化失败",
    3: "初筛不通过",
    4: "已完成",
    5: "待补录",
    6: "待人工复核",
    7: "待解析",
    8: "待归一化",
    9: "待初筛",
    10: "待审核入库",
}


def new_batch_id() -> str:
    return uuid.uuid4().hex[:12]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_upload(db: Session, file_name: str, content: bytes, uploaded_by: str) -> UploadItem:
    """校验 -> 去重 -> 落盘 -> 建 resumes 记录。

    校验失败的文件不落盘不建记录（HR 需重新上传）；
    重复文件按哈希去重复用已有记录。
    """
    # 1. 校验链：大小 / 魔数 / 加密损坏
    try:
        validate_upload(content)
    except FileValidationError as e:
        logger.warning("上传校验失败 %s: %s", file_name, e.reason)
        return UploadItem(
            resume_id=0, original_file_name=file_name, accepted=False, reason=e.reason
        )

    # 2. SHA256 去重
    digest = _sha256(content)
    existing = db.scalar(select(Resume).where(Resume.sha256 == digest))
    if existing is not None:
        logger.info("重复简历 %s（sha256=%s），复用 resume_id=%s", file_name, digest[:12], existing.resume_id)
        return UploadItem(
            resume_id=existing.resume_id,
            original_file_name=file_name,
            duplicated=True,
        )

    # 3. 落盘：uploads/<sha256>.pdf
    upload_dir: Path = get_settings().upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{digest}.pdf"
    if not dest.exists():
        dest.write_bytes(content)

    # 4. 建记录（待解析态）
    record = Resume(
        original_file_name=file_name,
        file_key=f"{digest}.pdf",
        sha256=digest,
        status=STATUS_UPLOADED,
        uploaded_by=uploaded_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("简历落盘 %s -> resume_id=%s", file_name, record.resume_id)
    return UploadItem(resume_id=record.resume_id, original_file_name=file_name)


def upload_file_path(resume: Resume) -> Path:
    """原始 PDF 的绝对路径（含路径穿越防护）。"""
    from src.core.security import ensure_safe_file_key

    file_key = ensure_safe_file_key(resume.file_key)
    return get_settings().upload_dir / file_key
