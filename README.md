# 智能简历筛选助手（SmartResume）

批量上传 PDF 简历 → 自动解析 → LLM 归一化 → 硬性条件初筛 → HR 审核入库。

## 架构

- **后端**：Python + FastAPI + Pydantic v2 + SQLAlchemy（SQLite WAL）
- **前端**：Vue3 + TypeScript + Element Plus + Vite
- **大模型**：通义千问 DashScope（qwen-plus 归一化提取；qwen-vl-max 扫描件 OCR）
- **PDF 解析**：PyMuPDF → pdfplumber → OCR 三级兜底

```
src/api/        FastAPI 路由（resume / parse / jobs / screen）
src/services/   业务逻辑（upload / parse / normalize / screen / pipeline）
src/models/     ORM + Pydantic 契约
src/core/       配置 / 安全 / 日志
src/web/        Vue3 前端
specs/          PRD / 数据契约 / 验收协议（真理之源）
evals/          黄金样本 S01-S10
tests/          单测 + 集成测试
.agents/skills/ 解析 / 归一化 / 初筛三个技能包 SOP
```

详细规范见 [AGENTS.md](AGENTS.md)。

## 快速开始

### 1. 配置密钥

```bash
cp .env.example .env
# 编辑 .env 填入 DASHSCOPE_API_KEY
```

### 2. 启动后端（:8000）

```bash
.venv/Scripts/python.exe -m uvicorn src.app:create_app --factory --reload
```

Swagger 文档：http://127.0.0.1:8000/docs

### 3. 启动前端（:5173，已代理 /api）

```bash
cd src/web
npm install
npm run dev
```

### 4. 测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

## 业务流程

1. **上传**：简历库页/上传页批量拖入 PDF（≤5M）；SHA256 自动去重；加密/损坏文件友好拒绝
2. **解析**：PyMuPDF → pdfplumber → OCR（扫描件）三级兜底，失败重试 2 次进失败列表
3. **归一化**：qwen-plus 结构化提取，JSON Schema + Pydantic 双校验，落 6 张表；字段缺失不编造（待补录）
4. **初筛**：上传时关联岗位自动触发，或筛选配置页手动执行；学历/年限/技能三态判定（通过/不通过/待人工复核）
5. **审核入库**：左侧原始 PDF 预览 + 右侧字段修正，保存后入库

## 状态机

`待解析 → 待归一化 → 待初筛 → 待审核入库 → 已完成`；
异常态：上传失败 / 解析失败 / 归一化失败 / 初筛不通过 / 待补录 / 待人工复核（均可人工兜底）。


##陈伟-test