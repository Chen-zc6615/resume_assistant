# ---------- 前端构建 ----------
FROM node:24-alpine AS frontend-builder
WORKDIR /build
COPY services/app/web/package.json services/app/web/package-lock.json ./
RUN npm ci
COPY services/app/web/ ./
RUN npm run build

# ---------- 运行镜像 ----------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# workspace 清单（先拷贝以利用构建缓存）
COPY pyproject.toml uv.lock ./
COPY services/app/pyproject.toml ./services/app/pyproject.toml
COPY services/parser/pyproject.toml ./services/parser/pyproject.toml
COPY services/knowledge/pyproject.toml ./services/knowledge/pyproject.toml
COPY packages/shared/pyproject.toml ./packages/shared/pyproject.toml

# 本服务与共享包源码
COPY packages/shared/src ./packages/shared/src
COPY services/app/src ./services/app/src
COPY services/app/main.py ./services/app/main.py

# 仅安装本服务及其依赖（uv workspace 解析 resume-shared）
RUN uv sync --frozen --no-dev --package resume-app-service

# 前端构建产物（app.py 经 services/app/web/dist 挂载）
COPY --from=frontend-builder /build/dist ./services/app/web/dist
RUN mkdir -p /app/data/uploads

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/resumes/stats', timeout=3)"
CMD ["uvicorn", "app_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
