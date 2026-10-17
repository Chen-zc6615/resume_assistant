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
    metadata: dict[str, str | int]


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


def build_talent_wiki_card(document_id: str, profile: TalentProfileUpsert) -> WikiCard:
    """确定性生成卡片；不调用 LLM，也不接收电话、邮箱或简历原文。"""

    if not re.fullmatch(r"talent-[1-9]\d*", document_id):
        raise ValueError("人才卡片 document_id 必须为 talent-{正整数}")

    title = f"候选人知识卡片：{_inline(profile.name)}"
    metadata: dict[str, str | int] = {
        "document_id": document_id,
        "document_type": "talent_profile",
        "source_resume_id": profile.source_resume_id,
    }
    if profile.source_profile_id is not None:
        metadata["source_profile_id"] = profile.source_profile_id

    frontmatter = ["---"]
    for key, value in metadata.items():
        encoded = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)
        frontmatter.append(f"{key}: {encoded}")
    frontmatter.extend([f"title: {json.dumps(title, ensure_ascii=False)}", "---", ""])

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
