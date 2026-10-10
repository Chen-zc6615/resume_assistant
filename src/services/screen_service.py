"""初筛服务（F-03）：纯确定性规则引擎，SQL/规则判定，LLM 不得参与淘汰决策。

三态：PASS / REJECT / PENDING_REVIEW（信息不足 ≠ 不合格）。
逐条生成 reasons 明细，写入 filter_results。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.models.db_models import FilterResult, FilterRun, Job, JobResumeGroup, Resume, ResumeProfile
from src.models.schemas import FilterRule, ReasonItem
from src.services.skill_dict import canonical_skill
from src.services.upload_service import (
    STATUS_DONE,
    STATUS_NORMALIZED,
    STATUS_PENDING_COMPLETION,
    STATUS_PENDING_REVIEW,
    STATUS_SCREEN_PASSED,
    STATUS_SCREEN_REJECTED,
)

logger = get_logger(__name__)

# 参与筛选的简历状态：待初筛 / 待补录 / 待人工复核 / 待审核入库。
# 排除：初筛不通过（3，出局——不再进入任何后续筛选）、已完成入库（4，终态）、
# 无归一化数据的失败/进行态（0/1/2/7/8）。
SCREENABLE_STATUSES = (
    STATUS_NORMALIZED,
    STATUS_PENDING_COMPLETION,
    STATUS_PENDING_REVIEW,
    STATUS_SCREEN_PASSED,
)

# 学历序（一票否决用）：值越大学历越高
DEGREE_ORDER = {
    "初中": 1,
    "高中": 2,
    "中专": 2,
    "中技": 2,
    "大专": 3,
    "本科": 4,
    "学士": 4,
    "硕士": 5,
    "研究生": 5,
    "博士": 6,
}

SKILL_MATCH_SCORE = 90  # rapidfuzz ratio 阈值，视为同一技能

# 多岗初筛结果优先序（归并用）：通过 > 待复核 > 不通过，高者不被低者覆盖
_RESULT_PRIORITY = {"REJECT": 0, "PENDING_REVIEW": 1, "PASS": 2}
_RESULT_LABELS = {"PASS": "通过", "REJECT": "不通过", "PENDING_REVIEW": "待复核"}


def _skill_matches(required: str, owned: list[str]) -> bool:
    """技能匹配：整串归一 -> token 级归一 -> 子串/模糊兜底。

    token 级处理复合写法（"J2EE 技术体系" 的 J2EE 归一为 Java），
    整串匹配处理标准写法（"spring boot" 归一为 Spring Boot）。
    """
    req = canonical_skill(required)
    low_req = req.lower()
    for s in owned:
        cand = canonical_skill(s)
        if cand and cand == req:
            return True
        # token 级：复合短语中任一拉丁/数字片段归一后命中即视为掌握
        for token in re.findall(r"[a-z0-9]+", (s or "").lower()):
            if canonical_skill(token) == req:
                return True
        low_cand = (cand or s).lower()
        if low_req and low_cand and (low_req in low_cand or low_cand in low_req):
            return True
        if low_req and low_cand and fuzz.ratio(low_req, low_cand) >= SKILL_MATCH_SCORE:
            return True
    return False


def evaluate_profile(
    rules: FilterRule | dict[str, Any],
    profile: ResumeProfile,
    skills: list[str],
) -> tuple[str, list[ReasonItem]]:
    """对单份归一化简历执行硬性规则，返回 (结果, 逐条明细)。"""
    if isinstance(rules, dict):
        rules = FilterRule.model_validate(rules)

    reasons: list[ReasonItem] = []
    has_reject = False
    has_insufficient = False

    # --- 规则1：最低学历（一票否决）---
    if rules.min_degree is None:
        reasons.append(ReasonItem(rule="最低学历", passed=True, detail="岗位不限学历"))
    elif profile.highest_education is None:
        has_insufficient = True
        reasons.append(
            ReasonItem(rule="最低学历", passed=None, detail="简历未提供学历信息，无法判定，待人工复核")
        )
    elif DEGREE_ORDER.get(profile.highest_education, 0) >= DEGREE_ORDER.get(rules.min_degree, 99):
        reasons.append(
            ReasonItem(
                rule="最低学历",
                passed=True,
                detail=f"学历 {profile.highest_education} 满足 {rules.min_degree} 及以上",
            )
        )
    else:
        has_reject = True
        reasons.append(
            ReasonItem(
                rule="最低学历",
                passed=False,
                detail=f"学历 {profile.highest_education} 低于岗位要求 {rules.min_degree}（一票否决）",
            )
        )

    # --- 规则2：最低工作年限 ---
    if rules.min_exp_years is None:
        reasons.append(ReasonItem(rule="最低工作年限", passed=True, detail="岗位不限年限"))
    elif profile.total_work_months is None:
        has_insufficient = True
        reasons.append(
            ReasonItem(
                rule="最低工作年限",
                passed=None,
                detail="工作年限无法推算（经历时间模糊），待人工复核",
            )
        )
    elif profile.total_work_months >= rules.min_exp_years * 12:
        reasons.append(
            ReasonItem(
                rule="最低工作年限",
                passed=True,
                detail=f"工作 {profile.total_work_months} 个月 ≥ 要求 {rules.min_exp_years} 年",
            )
        )
    else:
        has_reject = True
        reasons.append(
            ReasonItem(
                rule="最低工作年限",
                passed=False,
                detail=f"工作 {profile.total_work_months} 个月 < 要求 {rules.min_exp_years} 年",
            )
        )

    # --- 规则3：必备技能 ---
    if not rules.required_skills:
        reasons.append(ReasonItem(rule="必备技能", passed=True, detail="岗位无必备技能"))
    else:
        missing = [r for r in rules.required_skills if not _skill_matches(r, skills)]
        if not skills and not profile_has_any_skill_signal(profile):
            has_insufficient = True
            reasons.append(
                ReasonItem(rule="必备技能", passed=None, detail="简历未提取到技能信息，待人工复核")
            )
        elif missing:
            has_reject = True
            reasons.append(
                ReasonItem(
                    rule="必备技能",
                    passed=False,
                    detail=f"缺少必备技能：{'、'.join(missing)}",
                )
            )
        else:
            reasons.append(ReasonItem(rule="必备技能", passed=True, detail="必备技能全部命中"))

    # --- 综合判定 ---
    if has_reject:
        result = "REJECT"
    elif has_insufficient:
        result = "PENDING_REVIEW"
    else:
        result = "PASS"
    return result, reasons


def profile_has_any_skill_signal(profile: ResumeProfile) -> bool:
    """工作/项目描述中是否有技能痕迹（宽松判断，避免误判技能缺失）。"""
    for we in profile.work_experiences:
        if we.description or we.position:
            return True
    for pe in profile.project_experiences:
        if pe.description or pe.role:
            return True
    return False


def rules_from_job(job: Job) -> FilterRule:
    """从岗位硬性条件派生筛选规则（上传带 job_id 时的自动初筛）。"""
    return FilterRule(
        min_degree=job.job_min_degree,
        min_exp_years=job.job_min_exp_years,
        required_skills=job.job_required_skills or [],
    )


def create_run_from_job(db: Session, job: Job, resume_ids: list[int] | None = None) -> FilterRun:
    """上传自动初筛：从岗位派生规则并快照落 run，随后执行。"""
    rules = rules_from_job(job)
    run = FilterRun(
        template_id=None,
        job_id=job.job_id,
        rules_snapshot=rules.model_dump(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    execute_run(db, run, resume_ids)
    return run


def execute_run(db: Session, run: FilterRun, resume_ids: list[int] | None = None) -> None:
    """执行一个筛选任务：逐份判定、写结果、更新计数与简历状态。

    只依据 run.rules_snapshot 判定（执行时刻快照），不回读模板 ——
    模板事后被修改不影响历史 run，且事后可审计当时的确切规则。
    resume_ids 为空时筛选 run 关联岗位组内的可筛简历（分配结果）。
    显式传入的 resume_ids 必筛、不做可筛状态过滤——多岗批次依次执行时，
    前一岗 REJECT 会把简历置为出局中间态，若此处再过滤，后续岗位将
    剥夺其判定机会（"任一岗通过即留下"被破坏）；出局排除由调用方控制
    （screen_group / reassign 已按 SCREENABLE_STATUSES 过滤）。
    """
    rules = FilterRule.model_validate(run.rules_snapshot)
    if resume_ids:
        resumes = db.scalars(
            select(Resume).where(Resume.resume_id.in_(resume_ids))
        ).all()
    else:
        resumes = db.scalars(
            select(Resume)
            .join(JobResumeGroup, JobResumeGroup.resume_id == Resume.resume_id)
            .where(
                JobResumeGroup.job_id == run.job_id,
                Resume.status.in_(SCREENABLE_STATUSES),
            )
        ).all()

    run.status = 1  # 运行中
    run.total = len(resumes)
    db.commit()

    for resume in resumes:
        profile = resume.profile
        if profile is None:
            db.add(
                FilterResult(
                    run_id=run.run_id,
                    resume_id=resume.resume_id,
                    profile_id=None,
                    result="PENDING_REVIEW",
                    reasons=[
                        ReasonItem(rule="归一化数据", passed=None, detail="简历无归一化结果，待人工复核").model_dump()
                    ],
                )
            )
            continue
        skills = [s.skill_name for s in profile.skills]
        result, reasons = evaluate_profile(rules, profile, skills)
        db.add(
            FilterResult(
                run_id=run.run_id,
                resume_id=resume.resume_id,
                profile_id=profile.profile_id,
                result=result,
                reasons=[r.model_dump() for r in reasons],
            )
        )
        # 简历状态不在循环内更新——多岗场景在批次末统一归并（见 _merge_and_summarize）

    # 计数（先 flush，让未提交的结果对查询可见）
    db.flush()
    # 多岗结果归并 + 汇总：status 取各岗最优，failure_reason 重建各岗明细
    for resume in resumes:
        _merge_and_summarize(db, resume)
    results = db.scalars(select(FilterResult).where(FilterResult.run_id == run.run_id)).all()
    run.passed = sum(1 for r in results if r.result == "PASS")
    run.rejected = sum(1 for r in results if r.result == "REJECT")
    run.pending_review = sum(1 for r in results if r.result == "PENDING_REVIEW")
    run.status = 2  # 完成
    run.finished_at = datetime.now()
    db.commit()
    logger.info("筛选任务 run_id=%s 完成：%s 通过 / %s 拒绝 / %s 待复核", run.run_id, run.passed, run.rejected, run.pending_review)


def passed_job_names(db: Session, resume: Resume) -> list[str]:
    """简历当前在组岗位中最新初筛结果为通过的岗位名（入库标记用）。

    口径与 _merge_and_summarize 一致：仅统计在组岗位、每岗取最新 run 结果。
    """
    stmt = (
        select(FilterResult.result, Job.job_id, Job.job_name)
        .join(FilterRun, FilterResult.run_id == FilterRun.run_id)
        .join(Job, FilterRun.job_id == Job.job_id)
        .join(
            JobResumeGroup,
            (JobResumeGroup.job_id == Job.job_id)
            & (JobResumeGroup.resume_id == FilterResult.resume_id),
        )
        .where(FilterResult.resume_id == resume.resume_id)
        .order_by(FilterResult.result_id.desc())
    )
    latest: dict[int, tuple[str, str]] = {}
    for result, job_id, job_name in db.execute(stmt):
        if job_id not in latest:
            latest[job_id] = (result, job_name)
    return [name for job_id, (_, name) in sorted(latest.items()) if latest[job_id][0] == "PASS"]


def _merge_and_summarize(db: Session, resume: Resume) -> None:
    """多岗初筛结果归并进简历（需求级初筛：全部岗位都不满足才出局）：

    - 只统计简历当前仍在岗位组内的结果（HR 移出某岗后，该岗历史结果不再拖累）；
    - status 取各岗最优（通过 > 待复核 > 不通过），任一岗通过即待审核入库；
    - failure_reason 重建各岗位最新结果汇总（重跑后自动刷新）；
    - 已入库（status=4）简历不再被初筛覆盖。
    """
    if resume.status == STATUS_DONE:
        return
    stmt = (
        select(FilterResult.result, FilterResult.reasons, Job.job_id, Job.job_name)
        .join(FilterRun, FilterResult.run_id == FilterRun.run_id)
        .join(Job, FilterRun.job_id == Job.job_id)
        # 仅统计仍在组内的岗位（当前投递范围）
        .join(
            JobResumeGroup,
            (JobResumeGroup.job_id == Job.job_id)
            & (JobResumeGroup.resume_id == FilterResult.resume_id),
        )
        .where(FilterResult.resume_id == resume.resume_id)
        .order_by(FilterResult.result_id.desc())
    )
    # 每岗位取最新一条结果（result_id 倒序首见）
    latest: dict[int, tuple[str, str, list]] = {}
    for result, reasons, job_id, job_name in db.execute(stmt):
        if job_id not in latest:
            latest[job_id] = (result, job_name, reasons or [])
    if not latest:
        return

    best = max((r for r, _, _ in latest.values()), key=lambda r: _RESULT_PRIORITY[r])
    resume.status = (
        STATUS_SCREEN_PASSED
        if best == "PASS"
        else (STATUS_PENDING_REVIEW if best == "PENDING_REVIEW" else STATUS_SCREEN_REJECTED)
    )
    parts = []
    for job_id in sorted(latest):
        result, job_name, reasons = latest[job_id]
        part = f"{job_name}={_RESULT_LABELS[result]}"
        if result == "REJECT":
            first_fail = next(
                (r.get("detail", "") for r in reasons if r.get("passed") is False), ""
            )
            if first_fail:
                part += f"（{first_fail}）"
        parts.append(part)
    resume.failure_reason = "岗位初筛汇总：" + "；".join(parts)
