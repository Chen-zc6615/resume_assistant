"""测试夹具：隔离的临时数据库与上传目录。

必须在导入任何 src 模块之前设置环境变量（engine 在 import 时创建）。
"""

from __future__ import annotations

import os
import sys
import tempfile

# 测试库地址。drop_all/create_all 夹具会清库，绝不允许指向开发/生产库。
TEST_DATABASE_URL = "postgresql+psycopg://resume_test:resume_test@127.0.0.1:55432/resume_test"

_TMP = tempfile.mkdtemp(prefix="smartresume_test_")
os.environ.setdefault("DATA_DIR", _TMP)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL  # 强制覆盖（setdefault 会被 shell export 的生产库变量穿透）
os.environ.setdefault("UPLOAD_DIR", os.path.join(_TMP, "uploads"))

_injected = os.environ["DATABASE_URL"]
if not (_injected.startswith("postgresql+psycopg://resume_test@") or ":55432/" in _injected):
    print(
        f"FATAL: 测试 DATABASE_URL 指向了非测试库 {_injected!r}，"
        "集成测试会 drop_all 清库，拒绝执行。",
        file=sys.stderr,
    )
    raise SystemExit(1)

# 简历处理黄金样本路径（tests/conftest.py -> 仓库根/evals/...）
GOLDEN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "evals", "resume_processing", "resumes"
)


def golden(sample_file: str) -> str:
    """黄金样本绝对路径。"""
    path = os.path.abspath(os.path.join(GOLDEN_DIR, sample_file))
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path
