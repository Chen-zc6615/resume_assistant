"""Pydantic v2 契约：SPEC 实体契约 + API 请求/响应模型。

实体契约部分（Job/EducationExperience/ProjectExperience/WorkExperience/
ResumeProfile/ResumeProcessingResult）源自《技术SPEC架构说明书》维度一，保持校验规则不变。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

PositiveId = Annotated[int, Field(strict=True, gt=0)]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def reject_zero_year(value: str) -> str:
    if value.startswith("0000"):
        raise ValueError("年份不能为 0000")
    return value


YearMonth = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=7,
        max_length=7,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    ),
    AfterValidator(reject_zero_year),
]

DEGREE_LEVELS = ("大专", "本科", "硕士", "博士")


# ======================= SPEC 实体契约 =======================


class Job(BaseModel):
    """岗位信息（创建请求）；ID 由数据库生成。"""

    model_config = ConfigDict(extra="forbid")

    requirement_id: PositiveId = Field(..., description="所属需求 ID")
    job_code: str | None = Field(default=None, description="岗位编号，如 G岗位")
    job_name: NonEmptyText = Field(..., description="岗位名称")
    headcount: int | None = Field(default=None, strict=True, ge=1, description="招聘人数")
    major: str | None = Field(default=None, description="专业方向")
    job_jd: NonEmptyText = Field(..., description="岗位描述")
    job_min_degree: Literal["大专", "本科", "硕士", "博士"] | None = Field(
        default=None, description="最低学历，None 表示不限"
    )
    job_min_exp_years: int | None = Field(
        default=None, strict=True, ge=0, description="最低工作年限（年），None 表示不限"
    )
    job_required_skills: list[NonEmptyText] = Field(
        default_factory=list, description="必备技能，每项不能为空"
    )
    job_optional_skills: list[NonEmptyText] = Field(default_factory=list, description="加分技能")
    bonus_items: list[dict[str, str]] = Field(
        default_factory=list, description="非技能加分项 [{label,value}]：行业经验/语言能力等"
    )
    job_status: Literal[0, 1, 2] = Field(default=0, description="0-草稿，1-开放，2-关闭")
    job_created_by: NonEmptyText = Field(default="hr_admin", description="创建人")


class EducationExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    education_id: PositiveId | None = Field(default=None, description="入库前可为空")
    profile_id: PositiveId | None = Field(default=None, description="所属归一化简历 ID")
    school: NonEmptyText = Field(..., description="学校名称")
    major: str | None = Field(default=None, description="专业，未知为 None")
    education_level: str | None = Field(default=None, description="学历")
    start_date: YearMonth | None = Field(default=None, description="入学年月 YYYY-MM")
    end_date: YearMonth | None = Field(default=None, description="实际毕业年月 YYYY-MM")
    is_current: bool | None = Field(default=None, strict=True, description="是否在读，未知为 None")

    @model_validator(mode="after")
    def validate_dates(self):
        if self.is_current is True and self.end_date is not None:
            raise ValueError("仍在读时，实际毕业时间应为空")
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("入学时间不能晚于毕业时间")
        return self


class ProjectExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: PositiveId | None = Field(default=None, description="入库前可为空")
    profile_id: PositiveId | None = Field(default=None, description="所属归一化简历 ID")
    project_name: NonEmptyText = Field(..., description="项目名称")
    role: str | None = Field(default=None, description="担任角色")
    start_date: YearMonth | None = Field(default=None, description="开始年月 YYYY-MM")
    end_date: YearMonth | None = Field(default=None, description="结束年月 YYYY-MM")
    description: str | None = Field(default=None, description="项目描述及本人职责")

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("项目开始时间不能晚于结束时间")
        return self


class WorkExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_id: PositiveId | None = Field(default=None, description="入库前可为空")
    profile_id: PositiveId | None = Field(default=None, description="所属归一化简历 ID")
    company: NonEmptyText = Field(..., description="公司名称")
    position: NonEmptyText = Field(..., description="职位名称")
    start_date: YearMonth | None = Field(default=None, description="开始年月 YYYY-MM")
    end_date: YearMonth | None = Field(default=None, description="结束年月 YYYY-MM")
    is_current: bool | None = Field(default=None, strict=True, description="是否在职，未知为 None")
    description: str | None = Field(default=None, description="工作内容")

    @model_validator(mode="after")
    def validate_dates(self):
        if self.is_current is True and self.end_date is not None:
            raise ValueError("仍在职时，结束时间应为空")
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("工作开始时间不能晚于结束时间")
        return self


class ResumeProfileData(BaseModel):
    """归一化简历数据（LLM 提取结果 / 详情响应 / HR 审核编辑载体）。"""

    model_config = ConfigDict(extra="forbid")

    profile_id: PositiveId | None = Field(default=None, description="由数据库生成，入库前可为空")
    resume_id: PositiveId = Field(..., description="对应原始简历 ID")
    name: NonEmptyText = Field(..., description="姓名，不能为空或仅包含空白")
    gender: int | None = Field(default=None, description="性别 0-男 1-女，未知为 None")
    phone: str | None = Field(default=None, description="联系电话，保留国际号码与分机写法")
    email: str | None = Field(
        default=None,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        description="邮箱；仅校验基本格式，不验证地址存在性",
    )
    highest_education: str | None = Field(default=None, description="最高学历")
    graduation_institution: str | None = Field(default=None, description="最高学历院校名称")
    total_work_months: int | None = Field(
        default=None, strict=True, ge=0, description="工作月数，None 表示未知"
    )
    skills: list[str] = Field(default_factory=list, description="技能列表")
    education_experiences: list[EducationExperience] = Field(default_factory=list)
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    project_experiences: list[ProjectExperience] = Field(default_factory=list)


class ResumeProcessingResult(BaseModel):
    """前序阶段结果，供审核与入库使用；不包含审核与入库结果。"""

    model_config = ConfigDict(extra="forbid")

    batch_id: NonEmptyText = Field(..., description="批次 ID")
    parse_success_ids: list[PositiveId] = Field(default_factory=list)
    parse_failures: dict[Annotated[int, Field(gt=0)], str] = Field(default_factory=dict)
    normalize_success_ids: list[PositiveId] = Field(default_factory=list)
    normalize_failures: dict[Annotated[int, Field(gt=0)], str] = Field(default_factory=dict)
    screen_pass_ids: list[PositiveId] = Field(default_factory=list)
    screen_rejections: dict[Annotated[int, Field(gt=0)], str] = Field(default_factory=dict)
    screen_errors: dict[Annotated[int, Field(gt=0)], str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_results(self):
        for name in ("parse_success_ids", "normalize_success_ids", "screen_pass_ids"):
            ids = getattr(self, name)
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} 不允许重复 ID")

        stages = (
            ("解析", set(self.parse_success_ids), set(self.parse_failures)),
            ("归一化", set(self.normalize_success_ids), set(self.normalize_failures)),
            (
                "初筛",
                set(self.screen_pass_ids),
                set(self.screen_rejections),
                set(self.screen_errors),
            ),
        )
        for stage, *groups in stages:
            seen: set[int] = set()
            for group in groups:
                if seen & group:
                    raise ValueError(f"{stage}阶段同一简历不能同时存在于多个结果集合")
                seen.update(group)
        return self


# ======================= API 请求/响应模型 =======================


class JobOut(BaseModel):
    job_id: int
    requirement_id: int
    job_code: str | None
    job_name: str
    headcount: int | None
    major: str | None
    job_jd: str
    job_min_degree: str | None
    job_min_exp_years: int | None
    job_required_skills: list[str]
    job_optional_skills: list[str]
    bonus_items: list[dict]
    job_status: int
    job_created_by: str

    model_config = ConfigDict(from_attributes=True)


class Requirement(BaseModel):
    """招聘需求（创建请求）：岗位的集合容器，自身不带筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    requirement_name: NonEmptyText = Field(..., description="需求名称")
    dept: str | None = Field(default=None, description="用人部门")
    deadline: str | None = Field(default=None, description="招聘截止日期 YYYY-MM-DD")
    description: str | None = Field(default=None, description="需求说明")
    status: Literal[0, 1] = Field(default=0, description="0-进行中，1-已关闭")
    created_by: NonEmptyText = Field(default="hr_admin", description="创建人")


class RequirementOut(BaseModel):
    requirement_id: int
    requirement_name: str
    dept: str | None
    deadline: str | None
    description: str | None
    status: int
    created_by: str
    # 展示统计（list 接口填充）
    job_count: int = 0
    resume_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeBrief(BaseModel):
    resume_id: int
    original_file_name: str
    name: str | None = None
    status: int
    status_label: str
    failure_reason: str | None
    interview_status: int | None = None
    uploaded_by: str
    created_at: str | None

    model_config = ConfigDict(from_attributes=True)


class ResumeDetail(BaseModel):
    resume_id: int
    original_file_name: str
    status: int
    status_label: str
    failure_reason: str | None
    interview_status: int | None = None
    uploaded_by: str
    created_at: str | None
    profile: ResumeProfileData | None = None


class InterviewCreate(BaseModel):
    """面试邀约创建。"""

    resume_id: int
    job_id: int | None = None
    interview_time: str | None = None
    way: str | None = None
    interviewer: str | None = None
    note: str | None = None
    notify_way: str | None = None


class InterviewOut(BaseModel):
    interview_id: int
    resume_id: int
    job_id: int | None
    job_name: str | None = None
    interview_time: str | None
    way: str | None
    interviewer: str | None
    note: str | None
    notify_way: str | None
    created_by: str

    model_config = ConfigDict(from_attributes=True)


class InterviewStatusRequest(BaseModel):
    """标记候选人面试状态（0 待面试 / 1 已邀请 / 2 面试中 / 3 已入职 / 4 暂不跟进）。"""

    status: int = Field(ge=0, le=4)


class TalentPoolIn(BaseModel):
    """沉淀候选人才库入库。"""

    source_requirement_id: int | None = None
    source_job_id: int | None = None
    note: str | None = None


class TalentPoolOut(BaseModel):
    pool_id: int
    resume_id: int
    # 简历信息（list 接口填充）
    resume: ResumeBrief | None = None
    source_requirement_id: int | None
    source_requirement_name: str | None = None
    source_job_id: int | None
    source_job_name: str | None = None
    note: str | None
    created_by: str
    created_at: str | None
    knowledge_sync_status: Literal["pending", "syncing", "success", "failed"]
    knowledge_document_id: str | None
    knowledge_chunk_count: int | None
    knowledge_sync_error: str | None
    knowledge_synced_at: str | None

    model_config = ConfigDict(from_attributes=True)


class UploadItem(BaseModel):
    resume_id: int
    original_file_name: str
    duplicated: bool = False
    accepted: bool = True
    reason: str | None = None


class UploadResponse(BaseModel):
    batch_id: str
    items: list[UploadItem]


class ResumeStageBrief(ResumeBrief):
    """批次进度中的简历条目：DB 状态 + 实时处理阶段。"""

    stage: str | None = None  # parsing / normalizing / screening / done


class ParseStatusResponse(BaseModel):
    batch_id: str
    total: int
    finished: int
    failed: int
    parse_success: int
    normalize_success: int
    # 各阶段进行中的数量（供进度条/阶段徽章）
    parsing: int = 0
    normalizing: int = 0
    screening: int = 0
    per_resume: list[ResumeStageBrief]


class ProfileUpdateRequest(BaseModel):
    """HR 人工审核编辑归一化字段（F-04）。"""

    name: NonEmptyText
    gender: int | None = None
    phone: str | None = None
    email: str | None = None
    highest_education: str | None = None
    graduation_institution: str | None = None
    total_work_months: int | None = Field(default=None, ge=0)
    skills: list[str] = Field(default_factory=list)


class ManualRejectRequest(BaseModel):
    """人工筛除：原因必填留痕（区别于规则淘汰，HR 干预必须可审计）。"""

    reason: NonEmptyText


class FilterRule(BaseModel):
    """筛选模板的结构化硬性规则（从岗位派生或自定义）。"""

    min_degree: Literal["大专", "本科", "硕士", "博士"] | None = None
    min_exp_years: int | None = Field(default=None, ge=0)
    required_skills: list[NonEmptyText] = Field(default_factory=list)


class FilterTemplateCreate(BaseModel):
    template_name: NonEmptyText
    job_id: int
    rules: FilterRule
    created_by: NonEmptyText = "hr_admin"


class FilterTemplateOut(BaseModel):
    template_id: int
    template_name: str
    job_id: int
    rules: FilterRule
    created_by: str

    model_config = ConfigDict(from_attributes=True)


class FilterRunCreate(BaseModel):
    template_id: int
    resume_ids: list[int] | None = None  # 不传则筛选全部可筛简历


class ReasonItem(BaseModel):
    rule: str
    passed: bool | None  # None = 信息不足
    detail: str


class FilterResultOut(BaseModel):
    result_id: int
    run_id: int
    resume_id: int
    profile_id: int | None
    result: str
    reasons: list[ReasonItem]
    name: str | None = None
    original_file_name: str | None = None


class FilterRunOut(BaseModel):
    run_id: int
    template_id: int | None
    job_id: int
    status: int
    total: int
    passed: int
    rejected: int
    pending_review: int
    # 展示用冗余字段（list 接口经 job 反查填充）
    job_name: str | None = None
    requirement_id: int | None = None
    requirement_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
