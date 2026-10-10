"""开发入口：python main.py 或 uvicorn src.app:create_app --factory。"""

from __future__ import annotations

import uvicorn

from src.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("src.app:create_app", factory=True, host="127.0.0.1", port=8000, reload=True)
