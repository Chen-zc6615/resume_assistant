# 解析服务 API

默认地址：`http://localhost:8002`

解析服务只负责 PDF 安全校验、文本提取和必要时的 OCR，不保存招聘业务状态。主服务通过 HTTP 客户端调用它。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查及 OCR 模型信息 |
| `POST` | `/api/v1/parse` | 上传并解析单个 PDF |

## `GET /health`

成功响应：

```json
{
  "status": "healthy",
  "ocr_model": "qwen-vl-max"
}
```

该接口只说明 HTTP 进程可响应并返回当前模型配置，不会主动调用模型验证 API Key 或上游服务可用性。

## `POST /api/v1/parse`

请求使用 `multipart/form-data`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | 单个 PDF 文件 |

示例：

```bash
curl -X POST http://localhost:8002/api/v1/parse \
  -F 'file=@resume.pdf;type=application/pdf'
```

成功响应：

```json
{
  "file_name": "resume.pdf",
  "text": "候选人简历文本……",
  "parse_method": "pymupdf",
  "page_count": 2,
  "used_ocr": false,
  "effective_chars": 1380,
  "warnings": []
}
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `text` | 清洗后的解析文本 |
| `parse_method` | 实际采用的提取方法 |
| `page_count` | PDF 页数 |
| `used_ocr` | 是否调用视觉模型 OCR |
| `effective_chars` | 有效字符数量 |
| `warnings` | 降级或质量提示；有提示不一定代表解析失败 |

服务最多读取 `MAX_UPLOAD_SIZE_MB + 1 byte` 用于大小校验，默认限制为 5 MB。文件过大、不是有效 PDF、加密或损坏等校验失败返回 `422`：

```json
{"detail": "文件校验失败原因"}
```

OCR 仅用于文本层不足时的降级提取。解析结果是后续归一化的输入，不应直接当作已校验候选人事实。
