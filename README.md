# 智能简历筛选助手（SmartResume）

批量上传 PDF 简历 → 自动解析 → LLM 归一化 → 确定性硬性条件初筛 → HR 审核入库 → 人才库沉淀与知识检索。

- **提取与决策分离**：LLM 只做归一化字段提取（JSON Schema + Pydantic 双校验），淘汰决策 100% 由确定性规则产生，全程可审计（规则快照 + 逐条判定原因留痕）
- **不编造**：简历未提及的字段一律 null；信息不足 → 待人工复核，而非直接淘汰
- **三态初筛**：通过 / 不通过 / 待人工复核，逐岗位独立判定，一份简历可同时参与多岗位评估
- **人才知识库**：沉淀候选人时自动生成脱敏 Wiki 卡片（YAML frontmatter + Markdown），切片入向量库支持混合检索，同时落盘 `data/wiki/` 供人工阅读

## 架构

uv workspace monorepo，三个后端服务 + 公共包：

| 服务 | 端口 | 职责 |
|---|---|---|
| `services/app`（resume-app-service） | :8000 | 业务主线：上传/归一化/分配/初筛/审核/人才库/Agent + 托管前端构建产物 |
| `services/parser`（resume-parser-service） | :8002 | PDF → 文本：PyMuPDF → pdfplumber → OCR 三级兜底 |
| `services/knowledge`（resume-knowledge-service） | :8001 | Wiki 卡片索引与混合检索（BM25 + 向量 RRF + Rerank） |
| `packages/shared`（resume-shared） | — | 公共代码（PDF 校验等） |
| PostgreSQL 17 | :5432 / 测试库 :55432 | 结构化数据（17 张表） |
| 前端 `services/app/web` | dev :5173 | Vue 3 + TypeScript + Element Plus + Tailwind CSS 4 |

```
services/app/
  src/app_service/
    api/        路由层（7 个 router，42 个端点）
    services/   业务与状态机（upload/normalize/assign/screen/pipeline/agent/talent_knowledge）
    clients/    跨服务 HTTP 客户端（parser_client / knowledge_client）
    models/     ORM（db_models）与 Pydantic 契约（schemas）
    core/       配置、安全、日志、身份
    db/         引擎与会话
  web/          Vue3 前端（独立 npm 项目）
  tests/        单元 + 集成测试
services/parser/       解析服务
services/knowledge/    知识库服务
packages/shared/       公共包
specs/                 PRD / 技术架构 / 部署 / 8 份功能规格（见下文文档索引）
evals/                 评测数据（24 份黄金样本 PDF、检索问答集、筛选预期表）
.agents/skills/        按业务域组织的编码 SOP（4 个技能包）
data/                  运行时数据（uploads/ 原始 PDF、wiki/ 知识卡片副本）
```

## 快速开始

### 1. 配置密钥

```bash
cp .env.example .env
# 编辑 .env：填 PostgreSQL 密码与模型网关 Key（严禁提交到 git）
```

模型网关分工（两组凭据）：

| 变量 | 用途 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL` | 主服务归一化提取（qwen-plus）与招聘 Agent | DashScope 兼容网关 |
| `MODEL_API_KEY` + `MODEL_BASE_URL` | parser 与 knowledge 共用 | 端点需提供 `OCR_MODEL`（视觉）、`EMBEDDING_MODEL`、`RERANK_MODEL` |

> 培训环境使用金山云 kspmas 网关（见《服务器与大模型配置帮助文档.md》，Key 不要写入任何提交文件）。若网关无视觉模型，扫描件 OCR 将按设计降级进失败列表。

### 2. 启动 PostgreSQL

```bash
docker compose up -d db
```

### 3. 一键容器化（推荐）

```bash
docker compose up -d --build     # app 映射 127.0.0.1:18085，parser :8002，knowledge :8001
```

或本地逐服务开发：

```bash
uv sync --all-packages

# 主服务（:8000）
uv run uvicorn app_service.app:create_app --factory \
    --app-dir services/app/src --reload
# 解析服务（:8002）
uv run uvicorn parser_service.app:create_app --factory \
    --app-dir services/parser/src --reload
# 知识库服务（:8001）
uv run uvicorn knowledge_service.app:create_app --factory \
    --app-dir services/knowledge/src --reload
```

### 4. 前端（开发模式）

```bash
cd services/app/web
npm install
npm run dev     # :5173，已代理 /api → 127.0.0.1:8000
npm run build   # vue-tsc 类型检查 + 构建；产物由主服务 SPAStaticFiles 托管
```

前端 7 个页面（主导航 5 个）：工作台 / 需求岗位管理 / 简历上传 / 筛选结果查看 / 人才库管理；`/library` 简历库与 `/screening` 筛选配置为 URL 直达的保留页。

## 业务流程

```
上传 PDF（≤5M，SHA256 去重，加密/损坏友好拒收，必须选定招聘需求）
  → 解析（PyMuPDF → pdfplumber → OCR 扫描件兜底；HTTP 失败重试 1 次）
  → 归一化（qwen-plus 提取，双校验，校验失败重试 ≤2 次；落 5 张画像表）
  → 岗位分配（确定性规则，幂等分配到需求下全部开放岗位，一份可多岗）
  → 按岗硬性初筛（学历 / 总工作月数 / 必备技能；三态 + 逐条原因 + 规则快照留痕）
  → HR 复核（字段修正 / 确认入库 / 人工筛除 / 恢复待筛）
  → 人才库沉淀（可选，触发知识库同步）
```

### 简历状态机（`resumes.status`）

| 编码 | 状态 | 编码 | 状态 |
|---|---|---|---|
| 0 | 上传失败 | 6 | 待人工复核 |
| 1 | 解析失败 | 7 | 待解析 |
| 2 | 归一化失败 | 8 | 待归一化 |
| 3 | 初筛不通过 | 9 | 待初筛 |
| 4 | 已完成（终态） | 10 | 待审核入库 |
| 5 | 待补录 | | |

多岗位汇总规则：任一岗位 PASS 且电话邮箱完整 → 10；PASS 但缺联系方式 → 5；无 PASS 有待复核 → 6；全部不通过 → 3。面试进度走独立 `interview_status`，不占简历状态机。

## API 一览

| 前缀 | 能力 |
|---|---|
| `/api/resumes` | 上传/列表/详情/PDF 预览/字段修正/确认入库/人工筛除/恢复待筛/重解析/删除（13 端点） |
| `/api/parse` | 批次进度轮询 |
| `/api/requirements` | 需求 CRUD、需求池管理、重新分配并初筛 |
| `/api/jobs` | 岗位 CRUD（硬性条件）、岗位组管理、按组初筛 |
| `/api/screening` | 筛选模板 / 任务 / 结果明细 / CSV 导出 |
| `/api/talent` | 面试邀约、人才库沉淀（自动触发知识同步）、同步重试 |
| `/api/agent` | 只读招聘 Agent 问答 |

Swagger：`http://127.0.0.1:8000/docs`（容器化后为 `:18085/docs`）。

## 人才知识库与 Wiki 卡片

HR 沉淀候选人后自动执行：

```
归一化画像（白名单脱敏，电话/邮箱/PDF 原文不外传）
  → 确定性渲染 Wiki 卡片（YAML frontmatter + Markdown，id = resume_id 可直接反查数据库）
  → 章节切片 → embedding → Chroma 向量库（BM25 + Dense RRF + Rerank 混合检索）
  → 同步落盘 data/wiki/talent-{pool_id}_姓名.md
```

同步状态机（`talent_pool.knowledge_sync_status`）：pending → syncing → success / failed；失败可在人才库页手动重试。

## 招聘 Agent

- **在线**：`POST /api/agent/chat`，5 个只读工具（看板汇总/需求列表/需求概览/候选人检索/初筛明细），最多 4 轮工具调用，严格 Pydantic 参数校验，工具调用全程留痕。系统提示禁止 Agent 自行打分、改变初筛结论或声称执行写操作
- **Day18 演示**：`Day18/resume_agent.py` 三位一体全链路（知识库检索 → 数据库事实 → LLM 辅助复核 → HITL 人工审批），含 Token 防重放/防篡改攻防演练，`uv run python Day18/resume_agent.py` 运行

## 测试

```bash
docker compose up -d db-test      # 测试库 :55432（tmpfs，重建即清）

uv run pytest services/app/tests -v
uv run pytest services/parser/tests -v
uv run pytest services/knowledge/tests -v
uv run pytest packages/shared/tests -v
uv run ruff check services packages
uv run alembic upgrade head       # 迁移冒烟
```

> 每个包必须**分进程单独跑**（同名 `tests/conftest.py` 会冲突）。app 测试夹具会 `drop_all/create_all` 清库——conftest 已强制 `DATABASE_URL` 指向 55432 测试库并对非测试库地址直接拒绝执行，请勿绕过。

## 文档索引

| 文档 | 内容 |
|---|---|
| `specs/PRD.md` | 业务唯一基准：8 项功能（F-01~F-08）、双状态机、字段级交互规则 |
| `specs/TECH_ARCHITECTURE.md` | 技术选型与架构原则（注意：代码结构一节仍是拆分前旧布局） |
| `specs/DEPLOYMENT.md` | CI/CD 与生产部署（备份 → 迁移 → 同 SHA 三服务 → 健康检查 → 自动回滚） |
| `specs/function_specs/` | 8 份功能规格（登录/需求岗位/上传解析/归一化/分配/初筛/汇总/审核沉淀） |
| `.agents/skills/` | 4 个业务域编码 SOP（auth-feature / resume-processing / screening-pipeline / review-workflow） |
| `evals/` | 评测数据：24 份黄金样本 PDF（sample01-10 十类场景 + test_01-11 + 优秀简历）、20 条知识检索问答集、筛选预期表 |
| `AGENTS.md` | AI 代理工作宪法（分层纪律、红线、常用命令） |

## 进行中

- **F-01 登录（feature/agent 分支）**：`auth_service` / `auth_security` / 认证表与测试已就绪，API 路由尚未挂载；业务操作人暂用服务端配置身份（`DEFAULT_HR_ID`），认证落地后切换为会话用户
- 本期裁剪：AI 打分（match_score / 语义召回 / 证据审计）不做

## 部署

CI（`.github/workflows/ci.yml`）：ruff + alembic + 三服务测试 + 前端类型检查构建 + 三镜像构建。
CD（`.github/workflows/cd.yml`）：main 分支 CI 通过后发布 GHCR 镜像（SHA 不可变 tag）并 SSH 部署，详见 `specs/DEPLOYMENT.md`。
