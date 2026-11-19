from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

RelationType = Literal["HAS_SKILL", "WORKED_AT", "STUDIED_AT"]
TailType = Literal["Skill", "Company", "School"]

RELATION_TAIL: dict[str, TailType] = {
    "HAS_SKILL": "Skill",
    "WORKED_AT": "Company",
    "STUDIED_AT": "School",
}

# 名称类型：字符串，先去首尾空白，且长度 1~100
# 防止 LLM 输出空串、纯空格或超长的整段文字当作实体名
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# 年月类型：严格匹配 YYYY-MM，月份限定 01~12（与 app 服务的 YearMonth 格式一致）
YearMonth = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]


class ResumeTriple(BaseModel):
    """(Candidate) -[relation]-> (tail)。头实体恒为候选人，所以不设 head 字段。"""

    # extra="forbid"：LLM 多吐出任何未声明字段都直接报错，而不是悄悄忽略
    model_config = ConfigDict(extra="forbid")

    # 关系类型，只能是白名单内的三个值之一
    relation: RelationType
    # 尾实体类型，只能是 Skill/Company/School
    tail_type: TailType
    # 尾实体名称；Field(...) 表示必填；description 会进入 JSON Schema，帮助 LLM 理解
    tail_name: Name = Field(..., description="简历原文中的名称，不得改写")
    ## 原文佐证句：必填。后续在 services 层核对它是否真在简历里，用来防编造
    context_snippet: Name = Field(..., description="简历中支撑该关系的原句，必填")
    # 职位：仅 WORKED_AT 用；简历没写就是 None（红线：未提及一律 null）
    position: str | None = Field(default=None, description="仅 WORKED_AT")
    # 专业：仅 STUDIED_AT 用；同样没写就是 None
    major: str | None = Field(default=None, description="仅 STUDIED_AT")
    # 起止年月：可选，格式已由 YearMonth 保证
    start_date: YearMonth | None = None
    end_date: YearMonth | None = None

    # mode="after"：所有字段各自校验通过后再执行，此时可以放心使用 self.xxx
    @model_validator(mode="after")
    def check_consistency(self):
        # 关系和尾实体类型必须配套，例如拒绝 WORKED_AT -> Skill
        if RELATION_TAIL[self.relation] != self.tail_type:
            raise ValueError(f"{self.relation} 的尾实体必须是 {RELATION_TAIL[self.relation]}")
        # position 只属于工作经历，出现在别的关系上说明 LLM 串字段了
        if self.relation != "WORKED_AT" and self.position is not None:
            raise ValueError("position 只能出现在 WORKED_AT")
        # major 只属于教育经历，同理
        if self.relation != "STUDIED_AT" and self.major is not None:
            raise ValueError("major 只能出现在 STUDIED_AT")
        # 两个日期都有时才比较；"YYYY-MM" 是定长数字串，字符串比较等价于时间比较
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始时间不能晚于结束时间")
        # after 模式的校验器必须返回 self
        return self


class GraphExtractionResult(BaseModel):
    """LLM 一次抽取的整体输出，对应一份简历。"""

    model_config = ConfigDict(extra="forbid")

    # 三元组列表；简历里抽不到任何东西时为空列表，而不是编造
    # default_factory=list：每个实例各自新建列表，避免多个实例共用同一个可变默认值
    triples: list[ResumeTriple] = Field(default_factory=list)
