"""归一化测试：预处理、月份推算、Schema 红绿灯（SPEC 维度二）、实体契约。"""

from __future__ import annotations

import pytest
from app_service.models.schemas import ResumeProfileData
from app_service.services.normalize_service import (
    RESUME_EXTRACT_SCHEMA,
    build_profile_data,
    compute_total_work_months,
    preprocess_text,
)
from jsonschema import ValidationError, validate

# SPEC 示例：张三完整归一化数据（绿灯基准）
GREEN = {
    "name": "张三",
    "gender": "男",
    "phone": "13800001111",
    "email": "zhangsan@email.com",
    "highest_education": "硕士",
    "graduation_institution": "北京大学",
    "total_work_months": 110,
    "skills": ["Java", "Spring Boot", "MySQL"],
    "education_experiences": [
        {
            "school": "北京大学",
            "major": "计算机科学与技术",
            "education_level": "硕士",
            "start_date": "2014-09",
            "end_date": "2017-06",
            "is_current": False,
        }
    ],
    "work_experiences": [
        {
            "company": "字节跳动",
            "position": "高级工程师",
            "start_date": "2021-03",
            "end_date": None,
            "is_current": True,
            "description": "负责核心模块开发",
        }
    ],
    "project_experiences": [],
}


def test_schema_green_light():
    """绿灯：合法简历数据通过 Schema 校验。"""
    validate(instance=GREEN, schema=RESUME_EXTRACT_SCHEMA)


def test_schema_red_light_bad_degree_enum():
    """红灯：学历填枚举外值（如「研究生」）必须被拦截。"""
    bad = {**GREEN, "highest_education": "研究生"}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=RESUME_EXTRACT_SCHEMA)


def test_schema_red_light_bad_date_pattern():
    """红灯：日期格式不符 YYYY-MM 被拦截。"""
    bad = {**GREEN}
    bad["education_experiences"] = [
        {**GREEN["education_experiences"][0], "start_date": "2014.09"}
    ]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=RESUME_EXTRACT_SCHEMA)


def test_schema_red_light_extra_field():
    """红灯：additionalProperties=false，多余字段被拦截。"""
    bad = {**GREEN, "age": 28}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=RESUME_EXTRACT_SCHEMA)


def test_build_profile_data_maps_gender_and_validates():
    data = build_profile_data(1, GREEN)
    assert data.name == "张三"
    assert data.gender == 0  # 男 -> 0
    assert data.highest_education == "硕士"
    assert data.total_work_months == 110
    assert data.work_experiences[0].is_current is True


def test_build_profile_data_missing_name_rejected():
    """姓名缺失（null）不编造：实体契约必填校验拒绝。"""
    bad = {**GREEN, "name": None}
    with pytest.raises(Exception):
        build_profile_data(1, bad)


def test_preprocess_text_nfkc():
    # 全角字母/数字 -> 半角
    assert preprocess_text("２０１４年") == "2014年"
    assert preprocess_text("Ｊａｖａ工程师") == "Java工程师"
    # 控制字符剔除
    assert "\x00" not in preprocess_text("姓名\x00张三")
    # 多空白压缩
    assert preprocess_text("张  三\n\n\n\n男") == "张 三\n\n男"


def test_compute_total_work_months():
    from datetime import datetime

    now = datetime.now()
    # 一段在职（算到当前月）+ 一段完整经历
    months = compute_total_work_months(
        [
            {"start_date": "2021-03", "end_date": None, "is_current": True},
            {"start_date": "2017-07", "end_date": "2021-02", "is_current": False},
        ]
    )
    current = (now.year - 2021) * 12 + (now.month - 3)
    expected = max(current, 0) + (2021 - 2017) * 12 + (2 - 7)
    assert months == expected

    # 全部缺日期 -> None（S03 模糊年限场景）
    assert compute_total_work_months([{"start_date": None, "end_date": None}]) is None
    assert compute_total_work_months([]) is None


def test_resume_profile_data_forbid_extra():
    with pytest.raises(Exception):
        ResumeProfileData.model_validate(
            {"resume_id": 1, "name": "张三", "unknown_field": 1}
        )
