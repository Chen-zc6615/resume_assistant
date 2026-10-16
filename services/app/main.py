"""开发入口：python main.py 或 uvicorn app_service.app:create_app --factory。

在仓库根目录运行：.venv/bin/python -m uvicorn app_service.app:create_app \
    --factory --app-dir services/app/src --reload
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许直接 `python main.py` 运行（无需先安装本包）
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import uvicorn
from app_service.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app_service.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=True,
        app_dir="src",
    )
