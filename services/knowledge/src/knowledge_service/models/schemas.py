from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DocumentType = Literal["talent_profile", "job_doc", "policy", "other"]


class DocumentUpsert(BaseModel):
    document_type: DocumentType
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentWriteResponse(BaseModel):
    talent_card_id: str
    chunk_count: int


class TalentEducation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school: str = Field(min_length=1)
    major: str | None = None
    education_level: str | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    is_current: bool | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.is_current is True and self.end_date is not None:
            raise ValueError("仍在读时结束时间必须为空")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("入学时间不能晚于毕业时间")
        return self


class TalentWork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1)
    position: str = Field(min_length=1)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    is_current: bool | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.is_current is True and self.end_date is not None:
            raise ValueError("在职经历的结束时间必须为空")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("工作开始时间不能晚于结束时间")
        return self


class TalentProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(min_length=1)
    role: str | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    description: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("项目开始时间不能晚于结束时间")
        return self


class TalentProfileUpsert(BaseModel):
    """app 发给知识库的脱敏归一化简历；契约中不存在联系方式字段。"""

    model_config = ConfigDict(extra="forbid")

    source_resume_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    gender: Literal[0, 1] | None = None
    highest_education: str | None = None
    graduation_institution: str | None = None
    total_work_months: int | None = Field(default=None, ge=0)
    skills: list[str] = Field(default_factory=list)
    education_experiences: list[TalentEducation] = Field(default_factory=list)
    work_experiences: list[TalentWork] = Field(default_factory=list)
    project_experiences: list[TalentProject] = Field(default_factory=list)
    create_date: str | None = None


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SearchResult(BaseModel):
    chunk_id: str
    talent_card_id: str
    document_type: str
    content: str
    metadata: dict[str, Any]
    rerank_score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    latency_ms: float

