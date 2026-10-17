"""人才库记录与知识库索引之间的同步服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app_service.clients import knowledge_client
from app_service.clients.knowledge_client import DocumentWriteResult, KnowledgeServiceError
from app_service.models.db_models import ResumeProfile, TalentPool


class TalentKnowledgeDataError(RuntimeError):
    """人才记录缺少可同步的已归一化数据。"""


def _education_payload(item) -> dict[str, Any]:
    return {
        "school": item.school,
        "major": item.major,
        "education_level": item.education_level,
        "start_date": item.start_date,
        "end_date": item.end_date,
        "is_current": item.is_current,
    }


def _work_payload(item) -> dict[str, Any]:
    return {
        "company": item.company,
        "position": item.position,
        "start_date": item.start_date,
        "end_date": item.end_date,
        "is_current": item.is_current,
        "description": item.description,
    }


def _project_payload(item) -> dict[str, Any]:
    return {
        "project_name": item.project_name,
        "role": item.role,
        "start_date": item.start_date,
        "end_date": item.end_date,
        "description": item.description,
    }


def build_knowledge_profile(db: Session, resume_id: int) -> dict[str, Any]:
    """读取归一化简历并构造显式白名单的脱敏传输数据。"""

    profile = db.scalar(
        select(ResumeProfile)
        .where(ResumeProfile.resume_id == resume_id)
        .options(
            selectinload(ResumeProfile.skills),
            selectinload(ResumeProfile.education_experiences),
            selectinload(ResumeProfile.work_experiences),
            selectinload(ResumeProfile.project_experiences),
        )
    )
    if profile is None:
        raise TalentKnowledgeDataError("该简历没有已入库的归一化数据")

    education = sorted(
        profile.education_experiences,
        key=lambda item: (item.start_date or "", item.education_id),
        reverse=True,
    )
    works = sorted(
        profile.work_experiences,
        key=lambda item: (item.start_date or "", item.work_id),
        reverse=True,
    )
    projects = sorted(
        profile.project_experiences,
        key=lambda item: (item.start_date or "", item.project_id),
        reverse=True,
    )

    # 电话、邮箱、PDF 原文/路径、HR 备注不在白名单中，不能进入知识库请求。
    return {
        "source_resume_id": profile.resume_id,
        "source_profile_id": profile.profile_id,
        "name": profile.name,
        "gender": profile.gender,
        "highest_education": profile.highest_education,
        "graduation_institution": profile.graduation_institution,
        "total_work_months": profile.total_work_months,
        "skills": sorted(
            (item.skill_name for item in profile.skills),
            key=str.casefold,
        ),
        "education_experiences": [_education_payload(item) for item in education],
        "work_experiences": [_work_payload(item) for item in works],
        "project_experiences": [_project_payload(item) for item in projects],
    }


def sync_talent_to_knowledge(db: Session, entry: TalentPool) -> DocumentWriteResult:
    """把一条已提交的人才库记录同步到 knowledge 服务。"""

    if entry.pool_id is None:
        raise TalentKnowledgeDataError("人才库记录尚未提交，无法同步")
    document_id = f"talent-{entry.pool_id}"
    entry.knowledge_sync_status = "syncing"
    entry.knowledge_document_id = document_id
    entry.knowledge_sync_error = None
    db.commit()

    try:
        profile = build_knowledge_profile(db, entry.resume_id)
        result = knowledge_client.upsert_talent_profile(
            document_id=document_id,
            profile=profile,
        )
    except TalentKnowledgeDataError:
        _mark_sync_failed(db, entry, "缺少可同步的归一化数据")
        raise
    except KnowledgeServiceError:
        _mark_sync_failed(db, entry, "知识库服务不可用或拒绝了同步请求")
        raise

    entry.knowledge_sync_status = "success"
    entry.knowledge_document_id = result.document_id
    entry.knowledge_chunk_count = result.chunk_count
    entry.knowledge_sync_error = None
    entry.knowledge_synced_at = datetime.now(UTC)
    db.commit()
    db.refresh(entry)
    return result


def _mark_sync_failed(db: Session, entry: TalentPool, message: str) -> None:
    entry.knowledge_sync_status = "failed"
    entry.knowledge_chunk_count = None
    entry.knowledge_sync_error = message[:500]
    entry.knowledge_synced_at = None
    db.commit()
    db.refresh(entry)


def delete_talent_from_knowledge(pool_id: int) -> None:
    """删除人才库记录对应的知识库文档。"""

    knowledge_client.delete_document(f"talent-{pool_id}")
