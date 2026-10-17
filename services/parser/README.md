# Resume Parser Service

独立的 PDF 简历解析服务，依次尝试 PyMuPDF、pdfplumber 和视觉模型 OCR。

## 接口

- `GET /health`
- `POST /api/v1/parse`，使用 `multipart/form-data` 上传字段 `file`

## 本地启动

配置统一读取仓库根目录的 `.env`（可从根目录 `.env.example` 复制）。

```bash
uv run --package resume-parser-service uvicorn parser_service.app:create_app \
  --factory --app-dir services/parser/src --port 8002
```

Swagger：http://127.0.0.1:8002/docs

