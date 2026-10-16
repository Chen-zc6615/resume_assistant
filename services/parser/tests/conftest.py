"""解析服务测试夹具：黄金样本路径。"""

from __future__ import annotations

import os

# Settings 不强制模型 key（OCR 路径才用到），注入占位即可
os.environ.setdefault("MODEL_API_KEY", "test-dummy")

# tests/conftest.py -> 仓库根/evals/...
GOLDEN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "evals", "golden_datasets", "resumes"
)


def golden(sample_file: str) -> str:
    """黄金样本绝对路径。"""
    path = os.path.abspath(os.path.join(GOLDEN_DIR, sample_file))
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path
