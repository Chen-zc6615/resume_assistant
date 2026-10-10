"""归一化服务（F-02）：文本预处理 -> LLM 结构化提取 -> 双重校验 -> 六表落库。

校验链（SPEC 维度二）：LLM 输出必须先过 JSON Schema 校验，再过 Pydantic 实体校验；
不合格触发重试（最多 2 次），仍失败 -> 归一化失败列表，提示 HR 人工归一化。
红线：字段缺失返回 null，不得编造。
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime

from jsonschema import ValidationError, validate
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.models.db_models import (
    EducationExperience,
    ProfileSkill,
    ProjectExperience,
    Resume,
    ResumeProfile,
    WorkExperience,
)
from src.models.schemas import ResumeProfileData
from src.services import llm
from src.services.skill_dict import canonical_skills

logger = get_logger(__name__)

GENDER_MAP = {"男": 0, "女": 1}

# SPEC 维度二：归一化提取 Agent 的 JSON Schema（strict）
RESUME_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"], "description": "候选人姓名"},
        "gender": {"type": ["string", "null"], "enum": ["男", "女", None], "description": "候选人性别"},
        "phone": {"type": ["string", "null"], "description": "电话号码"},
        "email": {"type": ["string", "null"], "description": "邮箱地址"},
        "highest_education": {
            "type": ["string", "null"],
            "enum": ["大专", "本科", "硕士", "博士", None],
            "description": "最高学历",
        },
        "graduation_institution": {"type": ["string", "null"], "description": "最高学历院校名称"},
        "total_work_months": {
            "type": ["integer", "null"],
            "minimum": 0,
            "description": "总工作月数，根据工作经历起止时间推算，应届生为0或null",
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": '技能列表，如 ["Java","Spring Boot","MySQL"]',
        },
        "education_experiences": {
            "type": "array",
            "items": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {
                            "school": {"type": "string", "description": "学校名称"},
                            "major": {"type": ["string", "null"], "description": "专业名称"},
                            "education_level": {
                                "type": ["string", "null"],
                                "enum": ["初中", "高中", "大专", "本科", "硕士", "博士", None],
                                "description": "学历层次",
                            },
                            "start_date": {
                                "type": ["string", "null"],
                                "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$",
                                "description": "入学时间，格式 YYYY-MM",
                            },
                            "end_date": {
                                "type": ["string", "null"],
                                "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$",
                                "description": "毕业时间，格式 YYYY-MM，在读时为空",
                            },
                            "is_current": {"type": ["boolean", "null"], "description": "是否在读"},
                        },
                        "required": ["school", "major", "education_level", "start_date", "end_date", "is_current"],
                        "additionalProperties": False,
                    },
                    {
                        "if": {
                            "properties": {"is_current": {"const": True}},
                            "required": ["is_current"],
                        },
                        "then": {"properties": {"end_date": {"type": "null"}}},
                    },
                ]
            },
        },
        "work_experiences": {
            "type": "array",
            "items": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {
                            "company": {"type": "string", "description": "公司名称"},
                            "position": {"type": "string", "description": "职位名称"},
                            "start_date": {
                                "type": ["string", "null"],
                                "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$",
                                "description": "入职时间，格式 YYYY-MM",
                            },
                            "end_date": {
                                "type": ["string", "null"],
                                "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$",
                                "description": "离职时间，格式 YYYY-MM，在职时为空",
                            },
                            "is_current": {"type": ["boolean", "null"], "description": "是否在职"},
                            "description": {"type": ["string", "null"], "description": "工作描述"},
                        },
                        "required": ["company", "position", "start_date", "end_date", "is_current", "description"],
                        "additionalProperties": False,
                    },
                    {
                        "if": {
                            "properties": {"is_current": {"const": True}},
                            "required": ["is_current"],
                        },
                        "then": {"properties": {"end_date": {"type": "null"}}},
                    },
                ]
            },
        },
        "project_experiences": {
            "type": "array",
            "items": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {
                            "project_name": {"type": "string", "description": "项目名称"},
                            "role": {"type": ["string", "null"], "description": "项目中担任角色"},
                            "start_date": {
                                "type": ["string", "null"],
                                "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$",
                                "description": "项目开始年月，格式 YYYY-MM",
                            },
                            "end_date": {
                                "type": ["string", "null"],
                                "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$",
                                "description": "项目结束年月，格式 YYYY-MM",
                            },
                            "description": {"type": ["string", "null"], "description": "项目描述"},
                        },
                        "required": ["project_name", "role", "start_date", "end_date", "description"],
                        "additionalProperties": False,
                    },
                    {
                        "if": {
                            "properties": {"is_current": {"const": True}},
                            "required": ["is_current"],
                        },
                        "then": {"properties": {"end_date": {"type": "null"}}},
                    },
                ]
            },
        },
    },
    "required": [
        "name",
        "gender",
        "phone",
        "email",
        "highest_education",
        "graduation_institution",
        "total_work_months",
        "skills",
        "education_experiences",
        "work_experiences",
        "project_experiences",
    ],
    "additionalProperties": False,
}

EXTRACT_SYSTEM_PROMPT = f"""你是简历归一化提取引擎。输入是简历解析后的纯文本，输出严格的 JSON 对象。
必须遵守：
1. 只输出 JSON，结构与下面的 JSON Schema 完全一致，不添加任何多余字段。
2. 所有字段必须出现在输出中；简历未提及的信息一律填 null，严禁编造或猜测。
3. 日期统一为 YYYY-MM（如 2014-09），"至今"对应 is_current=true 且 end_date=null。
4. total_work_months 按工作经历起止时间推算总月数（在职经历算到当前月份），应届生为 0，无法推算为 null。
5. skills 中的空字符串一律剔除。
6. 学历判定规则（招聘硬性条件口径）：highest_education 与 graduation_institution 只取最高的
   **全日制**学历（统招大专/本科/硕士/博士）。专升本、函授、自考、成人教育、网络教育、在职
   研究生等**非全日制学历不计入** highest_education；此类经历必须照实写入
   education_experiences（education_level 按毕业层次填），并在 major 中保留原始描述
   （如"计算机科学与技术（专升本·函授）"），不得丢弃学历性质信息。
7. 一致性约束（education / work / project 全部适用）：is_current=true（在读/在职/进行中）
   的经历，其 end_date 必须为 null；凡填了 end_date（实际结束时间）的经历，其 is_current
   必须为 false。二者只能取其一，严禁同时出现。若原文既写"至今/在读"又写了未到期的结束日
   期，以"在读/在职"为准（is_current=true 且 end_date=null）。
JSON Schema：
{json.dumps(RESUME_EXTRACT_SCHEMA, ensure_ascii=False)}"""


def preprocess_text(raw: str) -> str:
    """文本预处理：NFKC 归一（全半角统一）、去控制字符、压缩空白。"""
    text = unicodedata.normalize("NFKC", raw)
    text = "".join(ch for ch in text if ch.isprintable() or ch == "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compute_total_work_months(work_experiences: list[dict]) -> int | None:
    """按工作经历起止推算总月数（在职算到当前月）。全部经历缺日期则返回 None。"""
    now = datetime.now()
    total = 0
    has_any = False
    for we in work_experiences:
        start, end = we.get("start_date"), we.get("end_date")
        if not start:
            continue
        if we.get("is_current") or not end:
            end = f"{now.year:04d}-{now.month:02d}"
        try:
            sy, sm = int(start[:4]), int(start[5:7])
            ey, em = int(end[:4]), int(end[5:7])
        except (ValueError, IndexError):
            continue
        months = (ey - sy) * 12 + (em - sm)
        if months > 0:
            total += months
            has_any = True
    return total if has_any else None


def llm_extract(raw_text: str) -> dict:
    """LLM 提取 + JSON Schema 校验，失败重试（SPEC：最多 2 次）。"""
    settings = get_settings()
    text = preprocess_text(raw_text)
    last_error: Exception | None = None
    for attempt in range(1, settings.max_llm_retries + 2):  # 首次 + 2 次重试
        try:
            content = llm.chat_json(EXTRACT_SYSTEM_PROMPT, text)
            data = json.loads(content)
            validate(instance=data, schema=RESUME_EXTRACT_SCHEMA)
            return data
        except (json.JSONDecodeError, ValidationError, ValueError, Exception) as e:  # noqa: BLE001
            last_error = e
            logger.warning("归一化提取第 %s 次校验失败: %s", attempt, e)
    raise last_error or ValueError("归一化提取失败")


def build_profile_data(resume_id: int, data: dict) -> ResumeProfileData:
    """Schema 校验通过的数据 -> Pydantic 实体（第二重校验）。"""
    gender_raw = data.get("gender")
    months = data.get("total_work_months")
    if months is None:
        months = compute_total_work_months(data.get("work_experiences", []))

    payload = {
        "resume_id": resume_id,
        "name": data.get("name") or "",
        "gender": GENDER_MAP.get(gender_raw) if gender_raw in GENDER_MAP else None,
        "phone": data.get("phone"),
        "email": data.get("email"),
        "highest_education": data.get("highest_education"),
        "graduation_institution": data.get("graduation_institution"),
        "total_work_months": months,
        "skills": canonical_skills(data.get("skills", [])),
        "education_experiences": [
            {
                "school": e["school"],
                "major": e.get("major"),
                "education_level": e.get("education_level"),
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "is_current": e.get("is_current"),
            }
            for e in data.get("education_experiences", [])
        ],
        "work_experiences": [
            {
                "company": e["company"],
                "position": e["position"],
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "is_current": e.get("is_current"),
                "description": e.get("description"),
            }
            for e in data.get("work_experiences", [])
        ],
        "project_experiences": [
            {
                "project_name": e["project_name"],
                "role": e.get("role"),
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "description": e.get("description"),
            }
            for e in data.get("project_experiences", [])
        ],
    }
    return ResumeProfileData.model_validate(payload)


def persist_profile(db: Session, resume: Resume, profile_data: ResumeProfileData) -> ResumeProfile:
    """写入 resume_profiles + 四张明细表（幂等：先清旧）。"""
    old = db.query(ResumeProfile).filter(ResumeProfile.resume_id == resume.resume_id).first()
    if old is not None:
        db.delete(old)
        db.flush()

    profile = ResumeProfile(
        resume_id=profile_data.resume_id,
        name=profile_data.name,
        gender=profile_data.gender,
        phone=profile_data.phone,
        email=profile_data.email,
        highest_education=profile_data.highest_education,
        graduation_institution=profile_data.graduation_institution,
        total_work_months=profile_data.total_work_months,
    )
    db.add(profile)
    db.flush()

    for s in profile_data.skills:
        db.add(ProfileSkill(profile_id=profile.profile_id, skill_name=s))
    for e in profile_data.education_experiences:
        db.add(
            EducationExperience(
                profile_id=profile.profile_id,
                school=e.school,
                major=e.major,
                education_level=e.education_level,
                start_date=e.start_date,
                end_date=e.end_date,
                is_current=e.is_current,
            )
        )
    for w in profile_data.work_experiences:
        db.add(
            WorkExperience(
                profile_id=profile.profile_id,
                company=w.company,
                position=w.position,
                start_date=w.start_date,
                end_date=w.end_date,
                is_current=w.is_current,
                description=w.description,
            )
        )
    for p in profile_data.project_experiences:
        db.add(
            ProjectExperience(
                profile_id=profile.profile_id,
                project_name=p.project_name,
                role=p.role,
                start_date=p.start_date,
                end_date=p.end_date,
                description=p.description,
            )
        )
    db.commit()
    return profile


def normalize_resume(db: Session, resume: Resume) -> ResumeProfileData:
    """单份简历归一化全流程；失败抛异常（由上层标记状态）。"""
    if not resume.raw_text:
        raise ValueError("简历无解析文本，无法归一化")
    data = llm_extract(resume.raw_text)
    profile_data = build_profile_data(resume.resume_id, data)
    persist_profile(db, resume, profile_data)
    return profile_data
