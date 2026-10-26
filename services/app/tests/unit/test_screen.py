"""初筛测试：三态规则引擎（S01 通过 / S02 学历一票否决 / S03 信息不足待复核 / S04 缺失不编造）。"""

from __future__ import annotations

import pytest

from app_service.models.db_models import ResumeProfile
from app_service.models.schemas import FilterRule
from app_service.services.screen_service import _skill_matches, evaluate_profile


def make_profile(**kw) -> ResumeProfile:
    defaults = dict(
        resume_id=1,
        name="测试候选人",
        gender=None,
        phone=None,
        email=None,
        highest_education="本科",
        graduation_institution=None,
        total_work_months=72,
    )
    defaults.update(kw)
    return ResumeProfile(**defaults)


BASE_RULES = FilterRule(min_degree="本科", min_exp_years=3, required_skills=["Java", "Spring Boot", "MySQL"])


def test_s01_perfect_match_pass():
    """S01：硬性条件全满足 -> PASS。"""
    profile = make_profile(highest_education="硕士", total_work_months=72)
    result, reasons = evaluate_profile(BASE_RULES, profile, ["Java", "Spring Boot", "MySQL", "Redis"])
    assert result == "PASS"
    assert all(r.passed for r in reasons)


def test_s02_degree_veto_reject():
    """S02：学历不达标一票否决——即使 8 年经验技能全匹配。"""
    profile = make_profile(highest_education="大专", total_work_months=96)
    result, reasons = evaluate_profile(BASE_RULES, profile, ["Java", "Spring Boot", "MySQL"])
    assert result == "REJECT"
    degree = next(r for r in reasons if r.rule == "最低学历")
    assert degree.passed is False
    assert "一票否决" in degree.detail


def test_s02_degree_order_masters_above_bachelor():
    profile = make_profile(highest_education="硕士")
    result, _ = evaluate_profile(BASE_RULES, profile, ["Java", "Spring Boot", "MySQL"])
    assert result == "PASS"


def test_s03_exp_months_null_pending_review():
    """S03：工作年限无法推算（模糊表述）-> PENDING_REVIEW，不得直接判不合格。"""
    profile = make_profile(total_work_months=None)
    result, reasons = evaluate_profile(BASE_RULES, profile, ["Java", "Spring Boot", "MySQL"])
    assert result == "PENDING_REVIEW"
    exp = next(r for r in reasons if r.rule == "最低工作年限")
    assert exp.passed is None
    assert "待人工复核" in exp.detail


def test_s03_exp_months_below_reject():
    profile = make_profile(total_work_months=20)  # < 36 个月
    result, reasons = evaluate_profile(BASE_RULES, profile, ["Java", "Spring Boot", "MySQL"])
    assert result == "REJECT"
    exp = next(r for r in reasons if r.rule == "最低工作年限")
    assert exp.passed is False


def test_s04_missing_skill_reject():
    """必备技能缺失 -> REJECT。"""
    profile = make_profile()
    result, reasons = evaluate_profile(BASE_RULES, profile, ["Java", "MySQL"])  # 缺 Spring Boot
    assert result == "REJECT"
    skills = next(r for r in reasons if r.rule == "必备技能")
    assert "Spring Boot" in skills.detail


def test_skill_fuzzy_match():
    """技能近似匹配：大小写/写法差异不误杀。"""
    profile = make_profile()
    result, _ = evaluate_profile(
        BASE_RULES, profile, ["JAVA", "spring boot", "MySql管理"]
    )
    assert result == "PASS"


def test_skill_alias_match():
    """技能别名归一：J2EE 等旧写法不漏筛（S07 部分场景的前置化解）。"""
    profile = make_profile()
    result, _ = evaluate_profile(
        BASE_RULES, profile, ["J2EE 技术体系", "Spring全家桶", "MySQL调优"]
    )
    assert result == "PASS"


def test_no_education_info_pending_review():
    """学历信息缺失 -> 待复核（信息不足≠不合格）。"""
    profile = make_profile(highest_education=None)
    result, reasons = evaluate_profile(BASE_RULES, profile, ["Java", "Spring Boot", "MySQL"])
    assert result == "PENDING_REVIEW"


def test_optional_rules_all_pass():
    """不限学历/年限/技能 -> PASS。"""
    profile = make_profile(highest_education=None, total_work_months=None)
    result, _ = evaluate_profile(FilterRule(), profile, [])
    assert result == "PASS"


def test_reject_beats_pending_review():
    """既有不达标又有信息不足 -> 一票否决优先。"""
    profile = make_profile(highest_education="高中", total_work_months=None)
    result, _ = evaluate_profile(BASE_RULES, profile, ["Java"])
    assert result == "REJECT"


# --- 已知缺陷固化：_skill_matches 双向子串兜底导致不同语言互撞 ---
# 修复 _skill_matches 后这两个用例会转绿，strict 将其报为 XPASS 错误，
# 提醒移除 xfail 标记；正向用例锁定子串兜底的合理方向，防止收紧时误伤。


@pytest.mark.xfail(
    reason="已知缺陷：java 是 javascript 的子串，双向子串兜底误命中（会 Java ≠ 会 JavaScript）",
    strict=True,
)
def test_skill_java_must_not_match_javascript():
    """两种不同语言不得因子串关系互撞（周晓东案：会 Java 被判掌握 JavaScript）。"""
    assert not _skill_matches("JavaScript", ["Java", "MySQL", "Spring Boot"])


@pytest.mark.xfail(
    reason="已知缺陷：c 是 c++/c# 的子串，双向子串兜底误命中（会 C ≠ 会 C++/C#）",
    strict=True,
)
def test_skill_c_must_not_match_cpp_or_csharp():
    """会 C 不等于会 C++/C#，同族不同语言不得互撞。"""
    assert not _skill_matches("C++", ["C"])
    assert not _skill_matches("C#", ["C"])


def test_skill_substring_safe_directions_still_work():
    """子串兜底的合理方向必须保留：要求名短于候选名（缩写/基础名命中全称）。"""
    assert _skill_matches("js", ["JavaScript"])              # 要求缩写、候选全称
    assert _skill_matches("JavaScript", ["JavaScript ES6"])  # 要求基础名、候选带版本修饰
    assert _skill_matches("SQL", ["MySQL"])                  # 会 MySQL 视为掌握 SQL
