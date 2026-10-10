"""诊断脚本：按硬性规则对候选人 JSON 数据做三态初筛判定。

用法：python .agents/skills/screening-spec/scripts/screen_check.py <json文件> [最低学历] [最低年限] [必备技能逗号分隔]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from src.models.db_models import ResumeProfile
from src.models.schemas import FilterRule
from src.services.screen_service import evaluate_profile


def main(json_path: str, degree: str = "本科", years: str = "3", skills: str = "Java,Spring Boot,MySQL") -> None:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    profile = ResumeProfile(
        profile_id=None, resume_id=1, name=data.get("name", ""),
        highest_education=data.get("highest_education"),
        total_work_months=data.get("total_work_months"),
    )
    rules = FilterRule(
        min_degree=degree or None,
        min_exp_years=int(years) if years else None,
        required_skills=[s for s in skills.split(",") if s.strip()],
    )
    result, reasons = evaluate_profile(rules, profile, data.get("skills", []))
    print(f"判定：{result}")
    for r in reasons:
        mark = "✓" if r.passed else ("✗" if r.passed is False else "?")
        print(f"  {mark} {r.rule}：{r.detail}")


if __name__ == "__main__":
    main(*sys.argv[1:])
