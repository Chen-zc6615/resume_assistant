# 知识库服务 API

默认地址：`http://localhost:8001`

知识库服务提供文档切分、向量索引、混合检索和重排。最终问答由主服务 Agent 根据检索结果生成；人才信息应优先通过主服务沉淀，由主服务发送脱敏画像。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查和索引统计 |
| `PUT` | `/api/v1/documents/{document_id}` | 新增或覆盖通用文档 |
| `PUT` | `/api/v1/talent-profiles/{document_id}` | 新增或覆盖脱敏人才画像 |
| `DELETE` | `/api/v1/documents/{document_id}` | 删除文档及其分块 |
| `POST` | `/api/v1/search` | 检索相关分块 |

## 健康检查

`GET /health` 返回：

```json
{
  "status": "healthy",
  "embedding_model": "text-embedding-model",
  "rerank_model": "rerank-model",
  "indexed_chunks": 128
}
```

该接口会读取本地向量集合计数，但不会完整验证模型提供商是否可调用。

## 写入通用文档

`PUT /api/v1/documents/{document_id}`

```json
{
  "document_type": "policy",
  "content": "文档正文……",
  "metadata": {
    "title": "招聘制度"
  }
}
```

`document_type` 可取 `talent_profile`、`job_doc`、`policy`、`other`。相同 `document_id` 会覆盖原索引。成功响应：

```json
{
  "document_id": "policy-2026",
  "chunk_count": 6
}
```

## 写入人才画像

`PUT /api/v1/talent-profiles/{document_id}`

请求模型禁止额外字段，且刻意不提供电话、邮箱字段：

```json
{
  "source_resume_id": 42,
  "source_profile_id": 40,
  "name": "张三",
  "gender": 0,
  "highest_education": "本科",
  "graduation_institution": "示例大学",
  "total_work_months": 48,
  "skills": ["Python", "FastAPI"],
  "education_experiences": [],
  "work_experiences": [],
  "project_experiences": []
}
```

经历字段的日期使用 `YYYY-MM`；在读/在职记录的 `is_current=true` 时，`end_date` 必须为空。响应与通用文档写入相同。

## 删除文档

`DELETE /api/v1/documents/{document_id}` 成功返回 `204 No Content`。人才画像也通过该通用删除接口移除。

## 检索

`POST /api/v1/search`

```json
{
  "query": "熟悉 Python 和 FastAPI 的候选人"
}
```

`query` 会去除首尾空白且不能为空。请求不接受额外字段；召回数量和最终返回数量统一由服务端配置。成功响应：

```json
{
  "query": "熟悉 Python 和 FastAPI 的候选人",
  "results": [
    {
      "chunk_id": "talent-8:0",
      "document_id": "talent-8",
      "document_type": "talent_profile",
      "content": "候选人：张三……",
      "metadata": {"source_resume_id": 42},
      "rerank_score": 0.87
    }
  ],
  "latency_ms": 83.4
}
```

知识库只返回检索证据，不生成自然语言回答。主服务 Agent 可以将这些结果作为只读工具输出，但不得用模型改变确定性硬条件初筛结论。
