from __future__ import annotations

import pytest
from app_service.db.base import Base
from app_service.db.session import SessionLocal, engine
from app_service.models.db_models import (
    AgentAction,
    Interview,
    Job,
    ProfileSkill,
    Requirement,
    Resume,
    ResumeProfile,
)
from app_service.models.schemas import AgentChatResponse, AgentToolTrace
from app_service.services import task_service
from app_service.services.screen_service import rules_from_job


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _seed_pass_candidate(db):
    requirement = Requirement(
        requirement_name="研发招聘", status=0, created_by="hr_admin"
    )
    db.add(requirement)
    db.flush()
    job = Job(
        requirement_id=requirement.requirement_id,
        job_name="Java后端",
        job_jd="Java、Spring Boot、MySQL",
        job_min_degree="本科",
        job_min_exp_years=3,
        job_required_skills=["Java"],
        job_optional_skills=[],
        bonus_items=[],
        job_status=1,
        job_created_by="hr_admin",
    )
    resume = Resume(
        original_file_name="candidate.pdf",
        file_key="uploads/candidate.pdf",
        sha256="a" * 64,
        status=10,
        uploaded_by="hr_admin",
    )
    db.add_all([job, resume])
    db.flush()
    profile = ResumeProfile(
        resume_id=resume.resume_id,
        name="测试候选人",
        phone="13800000000",
        email="candidate@example.com",
        highest_education="本科",
        total_work_months=48,
    )
    db.add(profile)
    db.flush()
    db.add(ProfileSkill(resume_id=profile.resume_id, skill_name="Java"))
    db.commit()
    db.refresh(job)
    db.refresh(profile)
    return resume, profile, job


def test_task_message_persists_and_creates_pending_action(db, monkeypatch):
    resume, profile, job = _seed_pass_candidate(db)
    proposal = {
        "action_type": "CREATE_INTERVIEW_INVITATION",
        "resume_id": resume.resume_id,
        "job_id": job.job_id,
        "candidate_name": profile.name,
        "job_name": job.job_name,
        "profile_updated_at": str(profile.updated_at),
        "job_updated_at": str(job.updated_at),
        "rules_snapshot": rules_from_job(job).model_dump(),
    }
    monkeypatch.setattr(
        task_service.agent_service,
        "chat",
        lambda db, message, completion_fn=None, history=None: AgentChatResponse(
            answer="规则结果为 PASS，等待 HR 确认。",
            tool_traces=[
                AgentToolTrace(
                    tool="evaluate_candidate_for_job",
                    arguments={"resume_id": resume.resume_id, "job_id": job.job_id},
                    success=True,
                    result={"result": "PASS", "action_proposal": proposal},
                )
            ],
        ),
    )

    task = task_service.create_task(db, "hr_admin")
    user_message, assistant_message, actions = task_service.send_message(
        db, task.task_id, "hr_admin", "测试候选人适合Java后端吗"
    )

    assert user_message.role == "user"
    assert assistant_message.role == "assistant"
    assert task_service.get_task(db, task.task_id, "hr_admin").title.startswith("测试候选人")
    assert len(actions) == 1
    assert actions[0].status == "pending"


def test_action_approval_rechecks_and_is_not_replayable(db):
    resume, profile, job = _seed_pass_candidate(db)
    task = task_service.create_task(db, "hr_admin", "审批测试")
    action = AgentAction(
        task_id=task.task_id,
        action_type="CREATE_INTERVIEW_INVITATION",
        status="pending",
        payload={
            "action_type": "CREATE_INTERVIEW_INVITATION",
            "resume_id": resume.resume_id,
            "job_id": job.job_id,
            "profile_updated_at": str(profile.updated_at),
            "job_updated_at": str(job.updated_at),
            "rules_snapshot": rules_from_job(job).model_dump(),
        },
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    decided = task_service.decide_action(
        db, task.task_id, action.action_id, "hr_admin", approved=True
    )
    assert decided.status == "executed"
    assert decided.result and decided.result["interview_id"]
    assert db.query(Interview).count() == 1
    assert db.get(Resume, resume.resume_id).interview_status == 1

    with pytest.raises(task_service.ActionConflictError):
        task_service.decide_action(
            db, task.task_id, action.action_id, "hr_admin", approved=True
        )


def test_action_reject_requires_reason_and_does_not_create_interview(db):
    task = task_service.create_task(db, "hr_admin", "驳回测试")
    action = AgentAction(
        task_id=task.task_id,
        action_type="CREATE_INTERVIEW_INVITATION",
        status="pending",
        payload={"resume_id": 1, "job_id": 1},
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    with pytest.raises(task_service.ActionConflictError):
        task_service.decide_action(
            db, task.task_id, action.action_id, "hr_admin", approved=False
        )
    rejected = task_service.decide_action(
        db,
        task.task_id,
        action.action_id,
        "hr_admin",
        approved=False,
        reason="岗位暂停招聘",
    )
    assert rejected.status == "rejected"
    assert db.query(Interview).count() == 0
