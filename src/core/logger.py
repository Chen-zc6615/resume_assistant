"""日志：统一格式 + 批次链路追踪。"""

from __future__ import annotations

import logging
import sys

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=_FMT, stream=sys.stdout, force=True)
    # 收敛三方库噪音
    for noisy in ("httpx", "httpcore", "openai", "pdfminer", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
