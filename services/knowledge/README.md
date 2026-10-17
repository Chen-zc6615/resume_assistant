# Resume Knowledge Service

独立的简历知识库微服务，负责文档切块、Embedding、Chroma、BM25、Rerank、语义检索和带来源的抽取式回答。

## 本地启动

配置统一读取仓库根目录的 `.env`（可从根目录 `.env.example` 复制）。

```bash
uv run --package resume-knowledge-service uvicorn knowledge_service.app:create_app \
  --factory --app-dir services/knowledge/src --port 8001
```

接口文档：`http://127.0.0.1:8001/docs`

知识库结果仅用于检索和排序参考，不参与简历淘汰决策。

