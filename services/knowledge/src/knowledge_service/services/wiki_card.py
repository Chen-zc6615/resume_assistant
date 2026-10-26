"""把脱敏的归一化人才数据渲染为知识库 Wiki 卡片。

entities/summary 由 LLM 生成（输出必须过 Pydantic 契约校验，连续
失败降级为确定性拼接）；其余字段与正文全部来自传入的数据库事实。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import litellm
from litellm import completion
from litellm.types.utils import ModelResponse
from pydantic import BaseModel, ConfigDict, Field

from knowledge_service.core.config import get_settings

# 屏蔽 litellm 异常时的调试信息横幅，避免污染服务日志
litellm.suppress_debug_info = True
from knowledge_service.models.schemas import (
    TalentEducation,
    TalentProfileUpsert,
    TalentProject,
    TalentWork,
)

logger = logging.getLogger(__name__)


class CardContentGenerationError(RuntimeError):
    """卡片展示字段（entities/summary）LLM 生成失败；同步应标记 failed 由人工重试。"""


class _CardKeywords(BaseModel):
    """LLM 卡片展示字段输出契约；校验失败即重试，连续失败阻断同步。"""

    model_config = ConfigDict(extra="forbid")

    entities: list[str] = Field(min_length=1, max_length=6)
    summary: str = Field(min_length=1, max_length=200)


_CARD_KEYWORDS_PROMPT = (
    "你为候选人知识卡片提炼两个展示字段。只允许基于给定的归一化事实，"
    "禁止编造或推测事实中不存在的信息，不出现电话、邮箱等联系方式。"
    '仅返回 JSON 对象：{"entities": ["3~6 个核心关键词"],'
    ' "summary": "100 字以内的一句话候选人画像"}'
)


def _generate_card_content(profile: TalentProfileUpsert) -> dict[str, Any]:
    """LLM 生成卡片 entities/summary；输出必须过 Pydantic 校验，连续失败抛异常阻断本次同步。"""

    settings = get_settings()
    payload = json.dumps(
        profile.model_dump(exclude_none=True, mode="json"), ensure_ascii=False
    )
    attempts = settings.card_llm_retries + 1
    for _ in range(attempts):
        try:
            response = completion(
                model=f"openai/{settings.card_llm_model}",
                api_key=settings.model_api_key,
                api_base=settings.model_base_url,
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=settings.model_timeout_seconds,
                messages=[
                    {"role": "system", "content": _CARD_KEYWORDS_PROMPT},
                    {"role": "user", "content": payload},
                ],
            )
            # litellm 类型重载含流式/协程分支，同步调用显式收窄为 ModelResponse
            if not isinstance(response, ModelResponse) or not response.choices:
                raise ValueError("卡片展示字段模型返回格式异常")
            content = response.choices[0].message.content
            if not content:
                raise ValueError("卡片展示字段模型返回空内容")
            card = _CardKeywords.model_validate_json(content)
            return {"entities": card.entities, "summary": card.summary}
        except Exception:
            logger.warning("卡片展示字段 LLM 生成失败，准备重试", exc_info=True)
    raise CardContentGenerationError(
        f"卡片展示字段 LLM 生成失败（已尝试 {attempts} 次），请稍后重试同步"
    )


@dataclass(frozen=True)
class WikiCard:
    content: str
    metadata: dict[str, str | int | list[str] | None]


def _inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _period(start_date: str | None, end_date: str | None, is_current: bool | None) -> str | None:
    if start_date is None and end_date is None and is_current is not True:
        return None
    if start_date and is_current is True:
        return f"{start_date} 至今"
    if start_date and end_date:
        return f"{start_date} 至 {end_date}"
    if start_date:
        return start_date
    if end_date:
        return f"截至 {end_date}"
    return "至今"


def _work_months_label(months: int) -> str:
    years, remainder = divmod(months, 12)
    if years and remainder:
        return f"{years}年{remainder}个月"
    if years:
        return f"{years}年"
    return f"{remainder}个月"


def _heading(*parts: str | None) -> str:
    return " · ".join(_inline(part) for part in parts if part and part.strip())


def _append_education(lines: list[str], item: TalentEducation) -> None:
    lines.extend(["", f"### {_heading(item.school, item.major)}"])
    if item.education_level:
        lines.append(f"- 学历：{_inline(item.education_level)}")
    period = _period(item.start_date, item.end_date, item.is_current)
    if period:
        lines.append(f"- 时间：{period}")


def _append_work(lines: list[str], item: TalentWork) -> None:
    lines.extend(["", f"### {_heading(item.company, item.position)}"])
    period = _period(item.start_date, item.end_date, item.is_current)
    if period:
        lines.append(f"- 时间：{period}")
    if item.description:
        lines.append(f"- 工作内容：{_inline(item.description)}")


def _append_project(lines: list[str], item: TalentProject) -> None:
    lines.extend(["", f"### {_heading(item.project_name)}"])
    if item.role:
        lines.append(f"- 担任角色：{_inline(item.role)}")
    period = _period(item.start_date, item.end_date, False)
    if period:
        lines.append(f"- 时间：{period}")
    if item.description:
        lines.append(f"- 项目描述：{_inline(item.description)}")


def build_talent_wiki_card(profile: TalentProfileUpsert) -> WikiCard:
    """渲染人读的知识卡片；不接收电话、邮箱或简历原文。

    Frontmatter 仅含五个展示字段。entities/summary 由 LLM 生成（必须
    过 Pydantic 契约校验，连续失败抛 CardContentGenerationError 阻断
    同步，不做次品降级）；id/name/create_date 为传入的数据库事实。
    检索层消费的系统键与过滤键由入库层（KnowledgeService）装配，
    不在卡片上出现。
    """

    title = _inline(profile.name)
    skills = [_inline(skill) for skill in profile.skills if skill.strip()]
    # create_date 为主服务传入的入库时间（数据库事实）；
    # entities/summary 必须来自 LLM 并过校验，失败即抛错阻断同步。
    create_date = profile.create_date
    llm_content = _generate_card_content(profile)
    entities = llm_content["entities"]
    summary = llm_content["summary"]

    metadata: dict[str, str | int | list[str] | None] = {
        # ---- HR Wiki 卡片展示字段（必填；检索键由入库层装配）----
        "id": profile.source_resume_id,
        "name": title,
        "create_date": create_date,
        "entities": entities,
        "summary": summary,
    }

    frontmatter = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list) and value:
            frontmatter.append(f"{key}:")
            frontmatter.extend(
                f"  - {json.dumps(item, ensure_ascii=False)}" for item in value
            )
        elif isinstance(value, list):
            frontmatter.append(f"{key}: []")
        elif value is None:
            frontmatter.append(f"{key}: null")
        elif isinstance(value, str):
            frontmatter.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            frontmatter.append(f"{key}: {value}")
    frontmatter.extend(["---", ""])

    lines = [*frontmatter, f"# {title}", "", "## 基本信息", "", f"- 姓名：{_inline(profile.name)}"]
    gender = None if profile.gender is None else {0: "男", 1: "女"}[profile.gender]
    if gender:
        lines.append(f"- 性别：{gender}")
    if profile.highest_education:
        lines.append(f"- 最高学历：{_inline(profile.highest_education)}")
    if profile.graduation_institution:
        lines.append(f"- 毕业院校：{_inline(profile.graduation_institution)}")
    if profile.total_work_months is not None:
        lines.append(f"- 总工作年限：{_work_months_label(profile.total_work_months)}")

    if profile.education_experiences:
        lines.extend(["", "## 教育经历"])
        for item in profile.education_experiences:
            _append_education(lines, item)

    if profile.work_experiences:
        lines.extend(["", "## 工作经历"])
        for item in profile.work_experiences:
            _append_work(lines, item)

    if profile.project_experiences:
        lines.extend(["", "## 项目经历"])
        for item in profile.project_experiences:
            _append_project(lines, item)

    skills = [_inline(skill) for skill in profile.skills if skill.strip()]
    if skills:
        lines.extend(["", "## 专业技能", ""])
        lines.extend(f"- {skill}" for skill in skills)

    return WikiCard(
        content="\n".join(lines).rstrip() + "\n",
        metadata=metadata,
    )
