"""诊断脚本：对 JSON 数据跑归一化 Schema + Pydantic 红绿灯校验。

用法：python .agents/skills/normalization-spec/scripts/normalize_check.py <json文件>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from jsonschema import ValidationError, validate

from src.services.normalize_service import RESUME_EXTRACT_SCHEMA, build_profile_data


def main(json_path: str) -> None:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    try:
        validate(instance=data, schema=RESUME_EXTRACT_SCHEMA)
        print("[1] JSON Schema：通过")
    except ValidationError as e:
        print(f"[1] JSON Schema：拦截 —— {e.message}")
        return
    try:
        profile = build_profile_data(1, data)
        print(f"[2] Pydantic 实体：通过（{profile.name}，{len(profile.skills)} 项技能）")
    except Exception as e:  # noqa: BLE001
        print(f"[2] Pydantic 实体：拦截 —— {e}")


if __name__ == "__main__":
    main(sys.argv[1])
