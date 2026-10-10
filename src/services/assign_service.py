"""岗位分配服务：把需求池的简历分配到需求下全部开放岗位。

需求级初筛语义（业务基准）：每份简历面对需求下**所有**开放岗位筛选，
任一岗位通过即留下、全部岗位都不满足才出局（多岗归并取最优实现）。
因此分配不做技能门槛预筛——技能是否满足由初筛三态规则判定
（缺技能 -> 该岗 REJECT；信息不足 -> 待复核），match_detail 只做命中留痕。
确定性规则（无 LLM、无打分）：全部开放岗位、幂等、关闭岗位不参与。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.models.db_models import Job, JobResumeGroup, Requirement, Resume
from src.services.screen_service import _skill_matches

logger = get_logger(__name__)

# 自动分配来源标记（added_by），与 HR 手动调整区分审计
AUTO_ASSIGNED_BY = "auto:assignment"


def _job_match_detail(job: Job, skills: list[str]) -> dict:
    """技能命中明细（信息性留痕，不作为分配门槛——需求级初筛让所有岗位参与判定）。"""
    required = job.job_required_skills or []
    optional = job.job_optional_skills or []
    detail = {
        "required_hits": [r for r in required if _skill_matches(r, skills)],
        "optional_hits": [o for o in optional if _skill_matches(o, skills)],
    }
    if not required and not optional:
        detail["note"] = "岗位未配置技能"
    return detail


def assign_resumes(
    db: Session, requirement: Requirement, resume_ids: list[int]
) -> dict[int, list[int]]:
    """把一批归一化简历分配到需求下全部开放岗位，返回 job_id -> [resume_id]。

    全量分配（不设技能门槛）：任一岗位是否满足由初筛判定，避免"技能预筛
    漏掉可能满足其他岗位的简历"。仅开放（job_status=1）岗位参与；
    已有分组（自动或手动）幂等跳过；需求下没有开放岗位时提示待人工分岗。
    """
    jobs = db.scalars(
        select(Job).where(Job.requirement_id == requirement.requirement_id, Job.job_status == 1)
    ).all()
    assignments: dict[int, list[int]] = {}
    if not jobs:
        logger.info("需求 %s 下没有开放岗位，全部简历待人工分岗", requirement.requirement_id)
        for resume_id in resume_ids:
            resume = db.get(Resume, resume_id)
            if resume is not None and resume.profile is not None:
                resume.failure_reason = "需求下没有开放岗位，待人工分岗"
        db.commit()
        return assignments

    for resume_id in resume_ids:
        resume = db.get(Resume, resume_id)
        if resume is None or resume.profile is None:
            continue
        skills = [s.skill_name for s in resume.profile.skills]
        for job in jobs:
            exists = db.scalar(
                select(JobResumeGroup).where(
                    JobResumeGroup.job_id == job.job_id, JobResumeGroup.resume_id == resume_id
                )
            )
            if not exists:
                db.add(
                    JobResumeGroup(
                        job_id=job.job_id,
                        resume_id=resume_id,
                        added_by=AUTO_ASSIGNED_BY,
                        match_detail=_job_match_detail(job, skills),
                    )
                )
            assignments.setdefault(job.job_id, []).append(resume_id)
    db.commit()
    for job_id, rids in assignments.items():
        logger.info(
            "需求 %s 全量分配：岗位 %s <- %s 份简历", requirement.requirement_id, job_id, len(rids)
        )
    return assignments
