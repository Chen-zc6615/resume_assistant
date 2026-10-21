from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app_service.db.base import Base

# PostgreSQL 使用 BIGINT 自增主键。
IntPK = BigInteger()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class UserAccount(Base, TimestampMixin):
    __tablename__ = "user_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('normal', 'disabled')",
            name="ck_user_accounts_status",
        ),
        CheckConstraint(
            "failed_login_count >= 0",
            name="ck_user_accounts_failed_login_count",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        IntPK,
        primary_key=True,
        autoincrement=True,
    )
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="normal",
        nullable=False,
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AuthSession(Base):
    """服务端登录会话，数据库只保存令牌哈希。"""

    __tablename__ = "auth_sessions"

    session_id: Mapped[int] = mapped_column(
        IntPK,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_accounts.user_id"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    csrf_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
    )

    user: Mapped[UserAccount] = relationship(
        back_populates="sessions",
    )


# ------------------------- 需求域 -------------------------


class Requirement(Base, TimestampMixin):
    """招聘需求：岗位的集合容器（自身不带筛选条件）。

    业务流：HR 创建需求 → 需求下建岗位 → 一批简历挂需求池 →
    归一化后按简历内容分配到需求下的岗位（一份可多岗）→ 按岗初筛。
    """

    __tablename__ = "requirements"

    requirement_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    requirement_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 用人部门 / 截止日期（YYYY-MM-DD），可空
    dept: Mapped[str | None] = mapped_column(String(100))
    deadline: Mapped[str | None] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    # 0-进行中 1-已关闭
    status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="requirement")
    resume_groups: Mapped[list["RequirementResumeGroup"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan"
    )


class RequirementResumeGroup(Base, TimestampMixin):
    """需求池：简历 → 需求的多对多关联（一批简历挂一个需求）。

    一份简历可被归入多个需求池，各组独立流转互不影响。
    """

    __tablename__ = "requirement_resume_groups"
    __table_args__ = (UniqueConstraint("requirement_id", "resume_id", name="uq_requirement_resume"),)

    id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.requirement_id"), nullable=False
    )
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.resume_id"), nullable=False)
    added_by: Mapped[str] = mapped_column(String(50), nullable=False)

    requirement: Mapped["Requirement"] = relationship(back_populates="resume_groups")
    resume: Mapped["Resume"] = relationship(back_populates="requirement_groups")


# ------------------------- 岗位域 -------------------------


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    job_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    # 所属需求（岗位必属一个需求）
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.requirement_id"), nullable=False
    )
    # 岗位编号（如"G岗位"）/ 招聘人数 / 专业方向，可空
    job_code: Mapped[str | None] = mapped_column(String(20))
    headcount: Mapped[int | None] = mapped_column(Integer)
    major: Mapped[str | None] = mapped_column(String(200))
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_jd: Mapped[str] = mapped_column(Text, nullable=False)
    # 最低学历（大专/本科/硕士/博士），NULL=不限
    job_min_degree: Mapped[str | None] = mapped_column(String(20))
    # 最低工作年限（年），NULL=不限
    job_min_exp_years: Mapped[int | None] = mapped_column(SmallInteger)
    job_required_skills: Mapped[list | None] = mapped_column(JSON, default=list)
    job_optional_skills: Mapped[list | None] = mapped_column(JSON, default=list)
    # 非技能加分项 [{"label": "行业经验", "value": "..."}, ...]（与加分技能区分）
    bonus_items: Mapped[list | None] = mapped_column(JSON, default=list)
    # 0-草稿 1-开放 2-关闭
    job_status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    job_created_by: Mapped[str] = mapped_column(String(50), nullable=False)

    requirement: Mapped["Requirement"] = relationship(back_populates="jobs")
    templates: Mapped[list["FilterTemplate"]] = relationship(back_populates="job")


# ------------------------- 简历文件域 -------------------------


class Resume(Base, TimestampMixin):
    __tablename__ = "resumes"

    resume_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 相对存储路径（uploads/<sha256>.pdf）
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    # 0-上传失败 1-解析失败 2-归一化失败 3-筛选失败
    # 4-已完成 5-待补录(字段缺失) 6-待人工复核(筛选信息不足)
    status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    # 面试流程状态（人才库页）：NULL=未进入流程
    # 0-待面试 1-已邀请面试 2-面试中 3-已入职 4-暂不跟进
    interview_status: Mapped[int | None] = mapped_column(SmallInteger)
    uploaded_by: Mapped[str] = mapped_column(String(50), nullable=False)

    profile: Mapped["ResumeProfile | None"] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    results: Mapped[list["FilterResult"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    # 需求池 / 岗位组关联行随简历删除级联清理（否则外键约束导致删除失败）
    requirement_groups: Mapped[list["RequirementResumeGroup"]] = relationship(
        cascade="all, delete-orphan"
    )
    job_groups: Mapped[list["JobResumeGroup"]] = relationship(
        cascade="all, delete-orphan"
    )


# ------------------------- 归一化简历域 -------------------------


class ResumeProfile(Base, TimestampMixin):
    __tablename__ = "resume_profiles"

    profile_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.resume_id"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 0-男 1-女，NULL=未知（简历未写不编造）
    gender: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(100))
    highest_education: Mapped[str | None] = mapped_column(String(20))
    graduation_institution: Mapped[str | None] = mapped_column(String(100))
    # 总工作月数，NULL=未知
    total_work_months: Mapped[int | None] = mapped_column(Integer)

    resume: Mapped["Resume"] = relationship(back_populates="profile")
    skills: Mapped[list["ProfileSkill"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    education_experiences: Mapped[list["EducationExperience"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    work_experiences: Mapped[list["WorkExperience"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    project_experiences: Mapped[list["ProjectExperience"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ProfileSkill(Base):
    __tablename__ = "profile_skills"

    id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("resume_profiles.profile_id"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(80), nullable=False)

    profile: Mapped["ResumeProfile"] = relationship(back_populates="skills")


class EducationExperience(Base):
    __tablename__ = "education_experiences"

    education_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("resume_profiles.profile_id"), nullable=False
    )
    school: Mapped[str] = mapped_column(String(100), nullable=False)
    major: Mapped[str | None] = mapped_column(String(100))
    # 初中/高中/大专/本科/硕士/博士
    education_level: Mapped[str | None] = mapped_column(String(20))
    start_date: Mapped[str | None] = mapped_column(String(7))  # YYYY-MM
    end_date: Mapped[str | None] = mapped_column(String(7))
    is_current: Mapped[bool | None] = mapped_column(Boolean)

    profile: Mapped["ResumeProfile"] = relationship(back_populates="education_experiences")


class WorkExperience(Base):
    __tablename__ = "work_experiences"

    work_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("resume_profiles.profile_id"), nullable=False
    )
    company: Mapped[str] = mapped_column(String(150), nullable=False)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(7))
    end_date: Mapped[str | None] = mapped_column(String(7))
    is_current: Mapped[bool | None] = mapped_column(Boolean)
    description: Mapped[str | None] = mapped_column(Text)

    profile: Mapped["ResumeProfile"] = relationship(back_populates="work_experiences")


class ProjectExperience(Base):
    __tablename__ = "project_experiences"

    project_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("resume_profiles.profile_id"), nullable=False
    )
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[str | None] = mapped_column(String(7))
    end_date: Mapped[str | None] = mapped_column(String(7))
    description: Mapped[str | None] = mapped_column(Text)

    profile: Mapped["ResumeProfile"] = relationship(back_populates="project_experiences")


# ------------------------- 岗位分组域 -------------------------


class JobResumeGroup(Base, TimestampMixin):
    """岗位简历分组（分配结果）：简历 → 岗位的多对多关联。

    业务流：上传挂需求 → 归一化后按简历内容自动分配（确定性规则，
    一份简历可入多个岗位组）→ 按岗位 JD 硬性条件初筛。
    HR 也可手动增删分组（调整分配结果后可重筛），added_by 区分来源：
    "auto:assignment"（规则自动分配）或 HR 用户名（手动调整）。
    """

    __tablename__ = "job_resume_groups"
    __table_args__ = (UniqueConstraint("job_id", "resume_id", name="uq_job_resume"),)

    id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.resume_id"), nullable=False)
    added_by: Mapped[str] = mapped_column(String(50), nullable=False)
    # 自动分配依据留痕：{"required_hits": [...], "optional_hits": [...]}
    match_detail: Mapped[dict | None] = mapped_column(JSON, default=dict)

    job: Mapped["Job"] = relationship()
    resume: Mapped["Resume"] = relationship(back_populates="job_groups")


# ------------------------- 面试与人才沉淀域 -------------------------


class Interview(Base, TimestampMixin):
    """面试邀约（人才库页发起）：一份简历可多次邀约，全部留痕。"""

    __tablename__ = "interviews"

    interview_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.resume_id"), nullable=False)
    # 邀约针对的岗位（可空：不针对具体岗位的沟通）
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.job_id"))
    interview_time: Mapped[str | None] = mapped_column(String(30))  # 面试时间
    way: Mapped[str | None] = mapped_column(String(50))  # 面试方式
    interviewer: Mapped[str | None] = mapped_column(String(100))  # 面试官
    note: Mapped[str | None] = mapped_column(Text)  # 备注
    notify_way: Mapped[str | None] = mapped_column(String(30))  # 通知方式
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)

    resume: Mapped["Resume"] = relationship()
    job: Mapped["Job | None"] = relationship()


class TalentPool(Base, TimestampMixin):
    """沉淀候选人才库：HR 复核后暂不匹配但值得长期储备的候选人（一份简历一条）。"""

    __tablename__ = "talent_pool"
    __table_args__ = (
        CheckConstraint(
            "knowledge_sync_status IN ('pending', 'syncing', 'success', 'failed')",
            name="ck_talent_pool_knowledge_sync_status",
        ),
    )

    pool_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.resume_id"), unique=True, nullable=False
    )
    source_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirements.requirement_id")
    )
    source_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.job_id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)
    knowledge_sync_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    knowledge_document_id: Mapped[str | None] = mapped_column(String(100))
    knowledge_chunk_count: Mapped[int | None] = mapped_column(Integer)
    knowledge_sync_error: Mapped[str | None] = mapped_column(String(500))
    knowledge_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resume: Mapped["Resume"] = relationship()
    source_requirement: Mapped["Requirement | None"] = relationship()
    source_job: Mapped["Job | None"] = relationship()


# ------------------------- 初筛域（架构图：模板/任务/结果） -------------------------


class FilterTemplate(Base, TimestampMixin):
    __tablename__ = "filter_templates"

    template_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    # 结构化硬性规则（学历/年限/必备技能），供 screen_service 执行
    rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)

    job: Mapped["Job"] = relationship(back_populates="templates")
    # 不级联删 run：filter_runs 是审计记录（rules_snapshot 自含），模板删除后 run 保留
    runs: Mapped[list["FilterRun"]] = relationship(back_populates="template")


class FilterRun(Base, TimestampMixin):
    __tablename__ = "filter_runs"

    run_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    # 显式模板筛选时指向模板；上传自动初筛直接从岗位派生规则，可为空
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("filter_templates.template_id")
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    # 执行时刻的规则快照（审计依据）：模板事后被改不影响历史 run 的判定依据
    rules_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # 0-待处理 1-运行中 2-完成 3-失败
    status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    pending_review: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    template: Mapped["FilterTemplate"] = relationship(back_populates="runs")
    results: Mapped[list["FilterResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class FilterResult(Base):
    __tablename__ = "filter_results"

    result_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("filter_runs.run_id"), nullable=False)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.resume_id"), nullable=False
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_profiles.profile_id")
    )
    # PASS / REJECT / PENDING_REVIEW
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    # 逐条规则判定明细：[{rule, passed, detail}...]
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    run: Mapped["FilterRun"] = relationship(back_populates="results")
    resume: Mapped["Resume"] = relationship(back_populates="results")
