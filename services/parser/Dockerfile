FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# workspace 清单
COPY pyproject.toml uv.lock ./
COPY services/app/pyproject.toml ./services/app/pyproject.toml
COPY services/parser/pyproject.toml ./services/parser/pyproject.toml
COPY services/knowledge/pyproject.toml ./services/knowledge/pyproject.toml
COPY packages/shared/pyproject.toml ./packages/shared/pyproject.toml

# 本服务与共享包源码
COPY packages/shared/src ./packages/shared/src
COPY services/parser/src ./services/parser/src

RUN uv sync --frozen --no-dev --package resume-parser-service

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=3)"
CMD ["uvicorn", "parser_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8002"]
