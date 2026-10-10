# AGENTS.md — 项目宪法

面向 AI 编码代理（与人类开发者）的上下文领航协议。开始任何工作前先读本文件。

## 项目一句话

智能简历筛选助手：批量上传 PDF 简历 → 解析 → LLM 归一化 → 硬性规则初筛 → HR 审核入库。

## 真理之源（改动前必读）

| 文件 | 内容 |
|---|---|
| `specs/PRD.md` | 业务功能、状态机、界面交互（唯一业务基准） |
| `specs/SPEC_DATA_MODELS.md` | 13 张表结构、Pydantic 契约、JSON Schema、降级策略 |
| `specs/EVAL_PROTOCOL.md` | 验收指标、黄金样本 S01-S10 预期结果 |

## 四层架构（严禁跨层调用）

```
src/api/        路由暴露层（FastAPI，参数校验后调 services）
src/services/   业务逻辑与状态机（upload/parse/normalize/screen/pipeline）
src/models/     ORM（db_models）与 Pydantic 契约（schemas）
src/core/       配置、安全、日志
src/db/         引擎与会话（SQLite WAL）
src/web/        Vue3 + Element Plus 前端（独立 npm 项目）
```

## 硬性纪律

1. **红线（业务）**：
   - LLM 输出必须过 JSON Schema + Pydantic 双校验才可落库
   - 淘汰决策只能由确定性规则产生，LLM 不得参与
   - 简历未提及的字段一律 null，严禁编造
   - 信息不足 ≠ 不合格 → 待人工复核（不得直接 REJECT）
2. **红线（工程）**：
   - 不跨层：api 不直接摸 ORM 之外的 SQL，services 不碰 HTTP 细节
   - 所有表结构改动先改 `db_models.py` 并同步 `SPEC_DATA_MODELS.md`
   - 契约（schemas.py / RESUME_EXTRACT_SCHEMA）改动必须跑 `pytest tests/`
   - `.env`（API key）严禁提交
3. **本期裁剪**：AI 打分（match_score/语义召回/证据审计）不做，勿自行恢复

## 常用命令

```bash
# 后端（Windows，.venv 已就绪）
.venv/Scripts/python.exe -m pytest tests/ -v        # 测试
.venv/Scripts/python.exe -m uvicorn src.app:create_app --factory --reload  # 起服务 :8000

# 前端
cd src/web && npm run dev     # :5173，代理 /api -> :8000
cd src/web && npm run build   # vue-tsc 类型检查 + 构建

# 启用 git 钩子
git config core.hooksPath .githooks
```

## 状态机速查（resumes.status）

0 上传失败 / 1 解析失败 / 2 归一化失败 / 3 初筛不通过 / 4 已完成 / 5 待补录 / 6 待人工复核 / 7 待解析 / 8 待归一化 / 9 待初筛 / 10 待审核入库
