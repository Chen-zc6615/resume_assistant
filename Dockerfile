FROM node:24 AS frontend-builder
WORKDIR /build
COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci
COPY src/web/ ./
RUN npm run build

FROM python:3.12 AS application
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY main.py ./
COPY src ./src
RUN pip install --no-cache-dir
COPY --from=frontend-builder /build/dist ./src/web/dist
RUN mkdir -p /app/date/uploads
EXPOSE 8000
HEALTHCHECK \
	--interval=30s \
	--timeout=5s \
	--start-period=15s \
	--retries=3 \
	CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/resumes/stats', timeout=3)"
CMD ["python", "-m", "uvicorn", "src.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

