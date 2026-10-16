"""测试夹具：隔离的临时数据库与上传目录。

必须在导入任何 src 模块之前设置环境变量（engine 在 import 时创建）。
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="smartresume_test_")
os.environ.setdefault("DATA_DIR", _TMP)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://resume_test:resume_test@127.0.0.1:55432/resume_test",
)
os.environ.setdefault("UPLOAD_DIR", os.path.join(_TMP, "uploads"))

# 黄金数据集路径（tests/conftest.py -> 仓库根/evals/...）
GOLDEN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "evals", "golden_datasets", "resumes"
)


def golden(sample_file: str) -> str:
    """黄金样本绝对路径。"""
    path = os.path.abspath(os.path.join(GOLDEN_DIR, sample_file))
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path
