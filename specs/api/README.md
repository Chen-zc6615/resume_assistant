# API 文档

本文档描述仓库当前代码已经实现的 HTTP API。业务目标与未来设计仍以
[`../PRD.md`](../PRD.md) 和 [`../function_specs/`](../function_specs/) 为准；目标规格中出现、但代码尚未实现的接口不会被写成可用接口。

## 服务入口

| 服务 | 默认地址 | 职责 | 接口文档 |
| --- | --- | --- | --- |
| 主服务 `resume-app-service` | `http://localhost:8000` | 需求、岗位、简历流水线、筛选、审核、面试与人才库 | [app-service.md](app-service.md) |
| 解析服务 `resume-parser-service` | `http://localhost:8002` | PDF 校验、文本提取与 OCR | [parser-service.md](parser-service.md) |
| 知识库服务 `resume-knowledge-service` | `http://localhost:8001` | 文档索引、人才画像索引与检索 | [knowledge-service.md](knowledge-service.md) |

各服务均由 FastAPI 提供运行时文档：

- Swagger UI：`<服务地址>/docs`
- ReDoc：`<服务地址>/redoc`
- OpenAPI JSON：`<服务地址>/openapi.json`

公共响应格式、状态枚举、认证现状和调用边界见 [conventions.md](conventions.md)。

## 调用关系

```text
Web / API 调用方
       |
       v
主服务 :8000 ---- PDF ----> 解析服务 :8002
       |
       +---- 脱敏人才画像 ----> 知识库服务 :8001
```

浏览器业务请求应以主服务为入口。解析服务和知识库服务是内部服务接口，不应让前端绕过主服务直接写入。

## 当前实现边界

- 登录、服务端会话、Cookie/CSRF 和 `/api/auth/*` 尚未实现；当前接口不能视为已经具备生产级访问控制。
- 主服务的部分旧写接口仍接受 `hr_id`、`created_by` 或 `job_created_by`。人才库和面试写接口已使用服务端配置的过渡期操作人。完整迁移目标见登录规格。
- 归一化由 LLM 提取，但落库前必须通过 JSON Schema/Pydantic 校验；淘汰决定只由确定性硬规则产生。
- 运行时 OpenAPI 是字段类型的最终机器可读参考；本文补充业务语义、副作用和当前限制。

## 更新规则

新增、删除或修改路由时，应同时更新对应服务分册。修改 Pydantic 请求/响应模型时，还应核对示例和公共字段说明；不要提前记录尚未落地的目标接口。
