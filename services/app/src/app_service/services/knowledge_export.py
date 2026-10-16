"""知识库沉淀导出：把业务数据导出为 Dify 知识库可导入的 markdown 文档。

两个使用方向（2026-10 与需求方确认）：
1. 简历评分：job_docs（岗位基准：JD+硬性条件+技能）+ talent_profiles（候选人技能维度）
2. 人才匹配：talent_profiles 作语义语料（经历/项目描述完整入库不截断，
   保留"支付清结算"这类领域关键词，保证语义检索命中）

- talent_profiles/：人才画像（含姓名便于检索；电话/邮箱不入库——
  泄露危害最大且检索用不上，编号↔联系方式映射单独输出 index_pii.csv 仅 HR 留档）
- job_docs/：岗位 JD 文档（JD 全文 + 硬性条件，评分基准）
- 判定判例（verdict_docs）已移除：筛选结果页 UI 已覆盖该信息，知识库无检索场景

红线：知识库内容只用于 HR 检索/评分参考/排序展示，不回流初筛的淘汰决策。

用法：
    python -m app_service.services.knowledge_export [--out data/knowledge_export]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app_service.db.session import engine

# resumes.status 标签（与 upload_service.STATUS_LABELS 一致）
STATUS_LABELS = {
    0: "上传失败", 1: "解析失败", 2: "归一化失败", 3: "初筛不通过",
    4: "已完成", 5: "待补录", 6: "待人工复核", 7: "待解析", 8: "待归一化",
    9: "待初筛", 10: "待审核入库",
}
RESULT_LABELS = {"PASS": "通过", "REJECT": "不通过", "PENDING_REVIEW": "待复核"}


def _rows(
    db: Connection,
    sql: str,
    params: dict | None = None,
) -> list[dict]:
    result = db.execute(text(sql), params or {})
    return [dict(row) for row in result.mappings()]


def _months_label(months: int | None) -> str:
    if months is None:
        return "年限未知"
    return f"{months // 12} 年{months % 12} 个月" if months % 12 else f"{months // 12} 年"


def export_talent_profiles(db: Connection, out: Path) -> None:
    """脱敏人才画像：每份归一化简历一篇。"""
    profiles = _rows(
        db,
        "SELECT p.*, r.status, r.failure_reason, p.resume_id AS rid "
        "FROM resume_profiles p JOIN resumes r ON r.resume_id = p.resume_id",
    )
    out.mkdir(parents=True, exist_ok=True)
    index_path = out.parent / "index_pii.csv"
    with open(index_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["talent_id", "姓名", "电话", "邮箱", "resume_id"])
        for i, p in enumerate(profiles, start=1):
            writer.writerow([f"T{i:03d}", p["name"], p["phone"] or "", p["email"] or "", p["rid"]])
            p["talent_id"] = f"T{i:03d}"

    for p in profiles:
        skills = [r["skill_name"] for r in _rows(
            db,
            "SELECT skill_name FROM profile_skills WHERE profile_id = :profile_id",
            {"profile_id": p["profile_id"]},
        )]
        works = _rows(
            db,
            "SELECT company, position, start_date, end_date, is_current, description "
            "FROM work_experiences WHERE profile_id = :profile_id ORDER BY start_date DESC",
            {"profile_id": p["profile_id"]},
        )
        projects = _rows(
            db,
            "SELECT project_name, role, description "
            "FROM project_experiences WHERE profile_id = :profile_id",
            {"profile_id": p["profile_id"]},
        )
        # 各岗最新初筛结果（仅统计在组岗位，口径同 screen_service._merge_and_summarize）
        verdicts = _rows(
            db,
            """
            SELECT j.job_name, fr.result, fr.reasons FROM filter_results fr
            JOIN filter_runs run ON run.run_id = fr.run_id
            JOIN jobs j ON j.job_id = run.job_id
            JOIN job_resume_groups g ON g.job_id = j.job_id AND g.resume_id = fr.resume_id
            WHERE fr.resume_id = :resume_id
            ORDER BY fr.result_id DESC
            """,
            {"resume_id": p["rid"]},
        )
        latest: dict[str, dict] = {}
        for v in verdicts:
            latest.setdefault(v["job_name"], v)
        verdict_lines = []
        for job_name, v in sorted(latest.items()):
            reason = ""
            try:
                reasons = v["reasons"] or []
                if isinstance(reasons, str):
                    reasons = json.loads(reasons)
                fails = [
                    item.get("detail", "")
                    for item in reasons
                    if item.get("passed") is False
                ]
                reason = fails[0] if fails else "硬性条件全部满足"
            except (ValueError, TypeError, IndexError):
                pass
            verdict_lines.append(f"- {job_name}：{RESULT_LABELS.get(v['result'], v['result'])}（{reason}）")

        lines = [
            f"# 人才画像 {p['talent_id']} · {p['name']}",
            "",
            f"- 姓名：{p['name']}",
            f"- 学历：{p['highest_education'] or '未知'}"
            + (f"（{p['graduation_institution']}）" if p["graduation_institution"] else ""),
            f"- 总工作年限：{_months_label(p['total_work_months'])}",
            f"- 当前状态：{STATUS_LABELS.get(p['status'], p['status'])}",
            f"- 技能：{'、'.join(skills) if skills else '未提取到'}",
            "",
            "## 工作经历",
        ]
        for w in works:
            period = "至今" if w["is_current"] else (w["end_date"] or "—")
            lines.append(
                f"- {w['start_date'] or '?'} ~ {period}　{w['company']}　{w['position']}"
                + (f"：{w['description'] or ''}" if w["description"] else "")
            )
        if not works:
            lines.append("- 无工作经历记录")
        if projects:
            lines += ["", "## 项目经历"]
            lines += [
                f"- {pr['project_name']}"
                + (f"（{pr['role']}）" if pr["role"] else "")
                + (f"：{pr['description'] or ''}" if pr["description"] else "")
                for pr in projects
            ]
        if verdict_lines:
            lines += ["", "## 各岗位初筛结果"] + verdict_lines
        (out / f"{p['talent_id']}.md").write_text("\n".join(lines), encoding="utf-8")


def export_job_docs(db: Connection, out: Path) -> None:
    """岗位 JD 文档：每个岗位一篇（含所属需求与硬性条件）。"""
    jobs = _rows(
        db,
        "SELECT j.*, r.requirement_name FROM jobs j "
        "JOIN requirements r ON r.requirement_id = j.requirement_id",
    )
    out.mkdir(parents=True, exist_ok=True)
    for i, j in enumerate(jobs, start=1):
        lines = [
            f"# 岗位：{j['job_name']}",
            "",
            f"- 所属需求：{j['requirement_name']}",
            f"- 状态：{'草稿' if j['job_status'] == 0 else '开放' if j['job_status'] == 1 else '关闭'}",
            f"- 最低学历：{j['job_min_degree'] or '不限'}",
            f"- 最低工作年限：{j['job_min_exp_years'] if j['job_min_exp_years'] is not None else '不限'}"
            + (" 年" if j["job_min_exp_years"] is not None else ""),
            f"- 必备技能：{'、'.join(j['job_required_skills'] or []) or '无'}",
            f"- 加分技能：{'、'.join(j['job_optional_skills'] or []) or '无'}",
            "",
            "## JD 全文",
            "",
            j["job_jd"],
        ]
        (out / f"J{i:02d}_{j['job_name']}.md").write_text("\n".join(lines), encoding="utf-8")


def export_all(out_dir: str) -> dict[str, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with engine.connect() as db:
        export_talent_profiles(db, out / "talent_profiles")
        export_job_docs(db, out / "job_docs")
    counts = {
        "talent_profiles": len(list((out / "talent_profiles").glob("*.md"))),
        "job_docs": len(list((out / "job_docs").glob("*.md"))),
    }
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库沉淀导出")
    parser.add_argument("--out", default="data/knowledge_export", help="输出目录")
    args = parser.parse_args()
    counts = export_all(args.out)
    for k, v in counts.items():
        print(f"{k}: {v} 篇")
    print(f"输出目录：{args.out}（PII 映射在 index_pii.csv，不入知识库）")


if __name__ == "__main__":
    main()
