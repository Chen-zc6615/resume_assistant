"""把脱敏的归一化人才数据渲染为知识库 Wiki 卡片。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from knowledge_service.models.schemas import (
    TalentEducation,
    TalentProfileUpsert,
    TalentProject,
    TalentWork,
)


@dataclass(frozen=True)
class WikiCard:
    document_id: str
    content: str
    metadata: dict[str, str | int | list[str]]


def _inline(value: str) -> str:
    """把来源文本限制在一行，避免其改变 Markdown 标题层级。"""

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


def _summary(profile: TalentProfileUpsert) -> str:
    """从白名单字段确定性拼接一句话摘要（同输入永远同输出，不调用 LLM）。"""

    parts: list[str] = []
    if profile.highest_education or profile.graduation_institution:
        edu = "、".join(x for x in (profile.highest_education, profile.graduation_institution) if x)
        parts.append(f"{edu}背景")
    if profile.total_work_months is not None:
        parts.append(f"{_work_months_label(profile.total_work_months)}工作经验")
    if profile.work_experiences:
        latest = profile.work_experiences[0]
        parts.append(f"现任/曾任 {_heading(latest.company, latest.position)}")
    if profile.skills:
        shown = "、".join(s.strip() for s in profile.skills[:6] if s.strip())
        if len(profile.skills) > 6:
            shown += " 等"
        parts.append(f"核心技能：{shown}")
    return "；".join(parts) + "。" if parts else "暂无可概述信息。"


def _entities(profile: TalentProfileUpsert, skills: list[str]) -> list[str]:
    """确定性提炼 3~6 个核心关键词（职位方向 + 技能 + 学历背景）。"""

    entities: list[str] = []
    if profile.work_experiences:
        latest = profile.work_experiences[0]
        if latest.position:
            entities.append(_inline(latest.position))
    entities.extend(skills[:3])
    if profile.graduation_institution and len(entities) < 5:
        entities.append(_inline(profile.graduation_institution))
    if profile.highest_education and len(entities) < 5:
        entities.append(_inline(profile.highest_education))
    unique: list[str] = []
    for entity in entities:
        if entity not in unique:
            unique.append(entity)
    return unique[:6]


def build_talent_wiki_card(document_id: str, profile: TalentProfileUpsert) -> WikiCard:
    """确定性生成卡片；不调用 LLM，也不接收电话、邮箱或简历原文。

    Frontmatter 字段对齐 Day11 企业 Wiki 卡片规范（id/title/category/
    department/version/entities/summary）；effective_date 与 replaces 为
    制度文档专属概念，人才卡片无对应事实，按「不编造」红线省略。
    """

    if not re.fullmatch(r"talent-[1-9]\d*", document_id):
        raise ValueError("人才卡片 document_id 必须为 talent-{正整数}")

    title = f"候选人知识卡片：{_inline(profile.name)}"
    skills = [_inline(skill) for skill in profile.skills if skill.strip()]
    metadata: dict[str, str | int | list[str]] = {
        # ---- Day11 Wiki 卡片规范字段 ----
        "id": profile.source_resume_id,
        "title": title,
        "category": "人才库/候选人画像",
        "department": "人力资源/招聘人才库",
        "version": "v1.0",
        "summary": _summary(profile),
        # ---- 人才卡片专有字段（检索链路依赖，勿删） ----
        "document_id": document_id,
        "document_type": "talent_profile",
        "source_resume_id": profile.source_resume_id,
    }
    entities = _entities(profile, skills)
    if entities:
        metadata["entities"] = entities
    if profile.source_profile_id is not None:
        metadata["source_profile_id"] = profile.source_profile_id
    gender = {0: "男", 1: "女"}.get(profile.gender)
    if gender:
        metadata["gender"] = gender
    if profile.highest_education:
        metadata["highest_education"] = _inline(profile.highest_education)
    if profile.graduation_institution:
        metadata["graduation_institution"] = _inline(profile.graduation_institution)
    if profile.total_work_months is not None:
        metadata["total_work_months"] = profile.total_work_months
        metadata["total_work_years"] = _work_months_label(profile.total_work_months)
    if skills:
        metadata["skills"] = skills
        metadata["skill_count"] = len(skills)

    frontmatter = ["---"]
    for key, value in metadata.items():
        if isinstance(value, str):
            encoded = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, list):
            encoded = json.dumps(value, ensure_ascii=False)
        else:
            encoded = str(value)
        frontmatter.append(f"{key}: {encoded}")
    frontmatter.extend(["---", ""])

    lines = [*frontmatter, f"# {title}", "", "## 基本信息", "", f"- 姓名：{_inline(profile.name)}"]
    gender = {0: "男", 1: "女"}.get(profile.gender)
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
        document_id=document_id,
        content="\n".join(lines).rstrip() + "\n",
        metadata=metadata,
    )
