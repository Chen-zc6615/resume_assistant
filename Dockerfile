# SmartResume 后端镜像：Python 3.12-slim + uvicorn
FROM python:3.12-slim

WORKDIR /app

# 依赖层（单独 COPY 以利用缓存）
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic pydantic-settings "sqlalchemy>=2" httpx pymupdf pdfplumber openai jsonschema rapidfuzz dateparser python-multipart

# 源码层
COPY src ./src
COPY main.py ./

# 数据与上传目录（挂载点）
RUN mkdir -p data/uploads

# 生产启动：8000 端口，后台任务与 SQLite WAL 均在容器内运行
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
