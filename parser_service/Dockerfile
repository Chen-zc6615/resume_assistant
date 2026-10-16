FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8002
CMD ["python", "-m", "uvicorn", "parser_service.app:create_app", "--factory", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8002"]

