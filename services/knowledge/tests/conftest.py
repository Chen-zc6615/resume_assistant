"""知识库服务测试夹具：隔离临时 chroma 目录 + dummy 模型配置。

Settings 在 app lifespan 里经 get_settings() 构造（lru_cache），
此处在导入期注入环境变量即可；本组测试均不触发真实模型调用。
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="knowledge_test_")
os.environ.setdefault("KNOWLEDGE_DATA_DIR", _TMP)
os.environ.setdefault("MODEL_API_KEY", "test-dummy")
os.environ.setdefault("MODEL_BASE_URL", "http://127.0.0.1:9")  # 不可达即可，离线用例不调用
os.environ.setdefault("EMBEDDING_MODEL", "test-embed")
os.environ.setdefault("RERANK_MODEL", "test-rerank")
