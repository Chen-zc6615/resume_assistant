"""岗位分配测试：全量分配（需求级初筛——所有开放岗位都参与，无技能门槛）。"""

from __future__ import annotations

import pytest
from app_service.db.base import Base
from app_service.db.session import SessionLocal, engine
from app_service.models.db_models import (
    Job,
    JobResumeGroup,
    ProfileSkill,
    Requirement,
    Resume,
    ResumeProfile,
)
from app_service.services.assign_service import assign_resumes
from app_service.services.upload_service import STATUS_NORMALIZED
from sqlalchemy import select


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()


def _mk_requirement(db) -> Requirement:
    r = Requirement(requirement_name="2026Q4 后端招聘", created_by="hr_test")
    db.add(r)
    db.commit()
    return r


def _mk_job(db, requirement_id: int, **kw) -> Job:
    defaults = dict(
        requirement_id=requirement_id,
        job_name="Java后端",
        job_jd="jd",
        job_min_degree=None,
        job_min_exp_years=None,
        job_required_skills=["Java", "Spring Boot"],
        job_optional_skills=["Redis"],
        job_status=1,
        job_created_by="hr_test",
    )
    defaults.update(kw)
    job = Job(**defaults)
    db.add(job)
    db.commit()
    return job


def _mk_resume(db, seq: int, skills: list[str]) -> Resume:
    """归一化完成的简历（status=9）+ profile + 技能。"""
    resume = Resume(
        original_file_name=f"r{seq}.pdf",
        file_key=f"uploads/r{seq}.pdf",
        sha256=f"{seq:064d}",
        status=STATUS_NORMALIZED,
        uploaded_by="hr_test",
    )
    db.add(resume)
    db.flush()
    profile = ResumeProfile(
        resume_id=resume.resume_id, name=f"候选人{seq}", highest_education="本科", total_work_months=72
    )
    db.add(profile)
    db.flush()
    for s in skills:
        db.add(ProfileSkill(profile_id=profile.profile_id, skill_name=s))
    db.commit()
    return resume


def _group_rows(db) -> list[JobResumeGroup]:
    return list(db.scalars(select(JobResumeGroup)))


def test_all_open_jobs_get_resume_regardless_of_skills(db):
    """全量分配：技能完全不命中的简历也进入每个开放岗位组
    （需求级初筛——是否满足由初筛判定，不做技能预筛漏掉可能满足其他岗的简历）。"""
    req = _mk_requirement(db)
    _mk_job(db, req.requirement_id, job_name="Java岗", job_required_skills=["Java", "Spring Boot"])
    _mk_job(db, req.requirement_id, job_name="产品经理岗", job_required_skills=["Axure", "数据分析"])
    _mk_job(db, req.requirement_id, job_name="无技能岗", job_required_skills=[], job_optional_skills=[])
    resume = _mk_resume(db, 1, ["Vue", "React"])  # 三个岗技能都不命中

    assignments = assign_resumes(db, req, [resume.resume_id])

    # 三个开放岗位全部进组（含无技能岗与技能不命中岗）
    assert set(assignments) == {1, 2, 3}
    assert len(_group_rows(db)) == 3


def test_match_detail_records_hits_and_note(db):
    """命中明细留痕：required/optional 命中列表；无技能岗标注说明。"""
    req = _mk_requirement(db)
    _mk_job(db, req.requirement_id, job_required_skills=["Java", "Spring Boot"], job_optional_skills=["Redis"])
    _mk_job(db, req.requirement_id, job_name="无技能岗", job_required_skills=[], job_optional_skills=[])
    resume = _mk_resume(db, 1, ["Java", "Redis"])

    assign_resumes(db, req, [resume.resume_id])

    rows = {r.job_id: r for r in _group_rows(db)}
    assert set(rows[1].match_detail["required_hits"]) == {"Java"}
    assert set(rows[1].match_detail["optional_hits"]) == {"Redis"}
    assert rows[2].match_detail["note"] == "岗位未配置技能"


def test_closed_jobs_excluded(db):
    """关闭/草稿岗位不参与分配。"""
    req = _mk_requirement(db)
    _mk_job(db, req.requirement_id, job_status=2, job_required_skills=["Java"])
    _mk_job(db, req.requirement_id, job_status=0, job_required_skills=["Java"])
    _mk_resume(db, 1, ["Java"])

    assignments = assign_resumes(db, req, [1])

    assert assignments == {}
    assert _group_rows(db) == []


def test_idempotent_existing_group_not_duplicated(db):
    """已有分组（自动或手动）幂等跳过，不产生重复行。"""
    req = _mk_requirement(db)
    _mk_job(db, req.requirement_id, job_required_skills=["Java"])
    resume = _mk_resume(db, 1, ["Java"])
    db.add(JobResumeGroup(job_id=1, resume_id=resume.resume_id, added_by="hr_admin"))
    db.commit()

    assign_resumes(db, req, [resume.resume_id])

    rows = [r for r in _group_rows(db) if r.resume_id == resume.resume_id]
    assert len(rows) == 1
    assert rows[0].added_by == "hr_admin"  # 手动分组不被自动分配覆盖


def test_no_open_jobs_marks_pending_manual(db):
    """需求下没有开放岗位：简历留待人工分岗提示。"""
    req = _mk_requirement(db)
    _mk_job(db, req.requirement_id, job_status=2, job_required_skills=["Java"])
    resume = _mk_resume(db, 1, ["Java"])

    assign_resumes(db, req, [resume.resume_id])

    db.refresh(resume)
    assert "待人工分岗" in (resume.failure_reason or "")
