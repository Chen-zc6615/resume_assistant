# 主服务 API

默认地址：`http://localhost:8000`

主服务是前端和外部调用方的业务入口。除特别说明外，请求和响应均为 JSON。公共错误、认证现状和状态值见 [conventions.md](conventions.md)。

## 接口一览

### 简历与处理批次

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/resumes/upload` | 批量上传 PDF 并启动处理流水线 |
| `GET` | `/api/resumes` | 查询简历列表 |
| `GET` | `/api/resumes/stats` | 按状态统计简历 |
| `GET` | `/api/resumes/{resume_id}` | 查询简历及归一化画像 |
| `GET` | `/api/resumes/{resume_id}/file` | 内联预览原始 PDF |
| `PATCH` | `/api/resumes/{resume_id}/profile` | 人工修改归一化字段 |
| `POST` | `/api/resumes/{resume_id}/reject` | 人工筛除整份简历 |
| `POST` | `/api/resumes/{resume_id}/confirm` | 确认本次筛选完成 |
| `POST` | `/api/resumes/{resume_id}/interview-status` | 修改简历面试状态 |
| `POST` | `/api/resumes/{resume_id}/restore` | 将初筛不通过恢复为待初筛 |
| `POST` | `/api/resumes/{resume_id}/reparse` | 后台重新解析简历 |
| `DELETE` | `/api/resumes/{resume_id}` | 删除简历、关联数据及原文件 |
| `GET` | `/api/parse/{batch_id}/status` | 查询上传批次进度 |

### 需求与需求池

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/requirements` | 创建招聘需求 |
| `GET` | `/api/requirements` | 查询需求列表 |
| `GET` | `/api/requirements/{requirement_id}` | 查询需求详情 |
| `PUT` | `/api/requirements/{requirement_id}` | 全量更新需求 |
| `DELETE` | `/api/requirements/{requirement_id}` | 删除需求及岗位筛选关联数据 |
| `GET` | `/api/requirements/{requirement_id}/resumes` | 查询需求池简历 |
| `POST` | `/api/requirements/{requirement_id}/resumes` | 把已有简历加入需求池 |
| `DELETE` | `/api/requirements/{requirement_id}/resumes/{resume_id}` | 从需求池移除简历 |
| `POST` | `/api/requirements/{requirement_id}/reassign` | 重新全量分配并筛选可筛简历 |

### 岗位与岗位组

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/jobs` | 创建岗位 |
| `GET` | `/api/jobs` | 查询岗位列表 |
| `GET` | `/api/jobs/{job_id}` | 查询岗位详情 |
| `PUT` | `/api/jobs/{job_id}` | 全量更新岗位 |
| `DELETE` | `/api/jobs/{job_id}` | 删除岗位 |
| `GET` | `/api/jobs/{job_id}/resumes` | 查询岗位组简历和分配依据 |
| `POST` | `/api/jobs/{job_id}/resumes` | 手动加入岗位组 |
| `DELETE` | `/api/jobs/{job_id}/resumes/{resume_id}` | 移出岗位组 |
| `POST` | `/api/jobs/{job_id}/screen` | 按岗位当前硬条件筛选组内简历 |

### 筛选任务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/screening/templates` | 创建筛选模板 |
| `GET` | `/api/screening/templates` | 查询筛选模板 |
| `DELETE` | `/api/screening/templates/{template_id}` | 删除模板，保留历史任务快照 |
| `POST` | `/api/screening/runs` | 使用模板执行筛选 |
| `GET` | `/api/screening/runs` | 查询最近筛选任务 |
| `GET` | `/api/screening/runs/{run_id}/results` | 查询任务结果 |
| `GET` | `/api/screening/runs/{run_id}/export.csv` | 导出任务结果 CSV |

### 面试与人才库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/talent/interviews` | 创建面试邀约并标记为已邀请 |
| `GET` | `/api/talent/interviews` | 查询面试邀约 |
| `POST` | `/api/talent/pool?resume_id={id}` | 沉淀候选人才库并尝试同步知识库 |
| `GET` | `/api/talent/pool` | 查询沉淀人才库 |
| `DELETE` | `/api/talent/pool/{pool_id}` | 移出人才库并尝试删除知识索引 |
| `POST` | `/api/talent/pool/{pool_id}/sync-knowledge` | 手动重试知识库同步 |

## 简历上传与查询

### 批量上传

`POST /api/resumes/upload` 使用 `multipart/form-data`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `files` | binary[] | 是 | 一个或多个 PDF |
| `requirement_id` | integer | 是 | 简历归属的招聘需求 |
| `hr_id` | string | 否 | 过渡期上传人；为空时取服务端默认值 |

```bash
curl -X POST http://localhost:8000/api/resumes/upload \
  -F requirement_id=12 \
  -F 'files=@resume-a.pdf;type=application/pdf' \
  -F 'files=@resume-b.pdf;type=application/pdf'
```

```json
{
  "batch_id": "a1b2c3d4e5f6",
  "items": [
    {
      "resume_id": 42,
      "original_file_name": "resume-a.pdf",
      "duplicated": false,
      "accepted": true,
      "reason": null
    }
  ]
}
```

请求返回后，解析、归一化、全开放岗位分配和确定性初筛在进程内后台执行。单个文件校验失败会作为 `accepted=false` 出现在响应中，不一定使整个请求失败；重复文件复用已有记录。

### 列表、统计和详情

- `GET /api/resumes?status=10&limit=200`：`status` 可选；`limit` 默认 200、最大 1000。
- `GET /api/resumes/stats`：返回 `{"total": 10, "by_status": {"待审核入库": 3}}`。
- `GET /api/resumes/{resume_id}`：返回基础信息及可选 `profile`。

简历摘要字段包括 `resume_id`、`original_file_name`、`name`、`status`、`status_label`、`failure_reason`、`interview_status`、`uploaded_by`、`created_at`。

归一化画像包含姓名、性别、电话、邮箱、最高学历、毕业院校、工作月数、技能，以及教育/工作/项目经历。未知事实允许为 `null`；不得为了满足字段而编造。

### PDF 预览

`GET /api/resumes/{resume_id}/file` 返回 `application/pdf`，并使用 `Content-Disposition: inline` 和 `Cache-Control: no-store`。记录或磁盘文件不存在均返回 `404`。

### 批次进度

`GET /api/parse/{batch_id}/status` 返回总数、完成数、失败数、解析/归一化成功数，各阶段进行中数量，以及逐简历状态：

```json
{
  "batch_id": "a1b2c3d4e5f6",
  "total": 2,
  "finished": 1,
  "failed": 0,
  "parse_success": 2,
  "normalize_success": 1,
  "parsing": 0,
  "normalizing": 1,
  "screening": 0,
  "per_resume": []
}
```

批次状态仅保存在当前应用进程内，进程重启后查询可能返回 `404`。

## 人工处理动作

### 修改画像

`PATCH /api/resumes/{resume_id}/profile`

```json
{
  "name": "张三",
  "gender": 0,
  "phone": "13800000000",
  "email": "zhangsan@example.com",
  "highest_education": "本科",
  "graduation_institution": "示例大学",
  "total_work_months": 48,
  "skills": ["Python", "FastAPI"]
}
```

当前接口只更新画像基础字段并全量替换技能，不接受教育、工作、项目经历修改。待补录简历补齐电话和邮箱后会转为待审核入库。当前实现尚无 `expected_normalization_version`，也不会自动让旧筛选结果失效，这是与目标审核规格之间的已知缺口。

### 筛除、确认、恢复与重解析

- `POST /api/resumes/{id}/reject`，请求 `{"reason":"原因"}`：整份简历转为初筛不通过。
- `POST /api/resumes/{id}/confirm`：画像存在即转为已完成，并记录当前通过岗位名称。当前代码尚未强制校验版本和完整的确认前置条件。
- `POST /api/resumes/{id}/restore`：仅允许状态 `3`，恢复到状态 `9`，不会自动执行重筛。
- `POST /api/resumes/{id}/reparse`：立即返回已触发，后台重新处理。
- `DELETE /api/resumes/{id}`：删除简历、级联业务数据和原始 PDF；该操作不可通过 API 撤销。

`POST /api/resumes/{id}/interview-status` 请求 `{"status": 1}`，取值范围 0 至 4。

## 需求 API

创建和全量更新使用同一请求模型：

```json
{
  "requirement_name": "2026 后端工程师招聘",
  "dept": "研发部",
  "deadline": "2026-12-31",
  "description": "补充后端研发人员",
  "status": 0,
  "created_by": "hr_admin"
}
```

`requirement_name` 非空；`status` 为 `0` 进行中或 `1` 已关闭。响应增加 `requirement_id`、`job_count` 和 `resume_count`。更新时 `created_by` 虽仍在请求模型中，但当前代码不修改已有创建人。

需求池加入请求为：

```json
{"resume_ids": [42, 43]}
```

成功返回新增和跳过数量。移出需求池只解除需求归属，当前实现会保留已有岗位组。`POST /api/requirements/{id}/reassign` 会把池中可筛简历幂等分配到该需求的全部开放岗位，并为每个岗位同步执行初筛；没有可筛简历返回 `400`。

删除需求会级联删除其岗位、岗位组、筛选模板、筛选任务与结果，以及需求池关系，但不会删除简历本身。

## 岗位 API

创建和全量更新示例：

```json
{
  "requirement_id": 12,
  "job_code": "BE-01",
  "job_name": "后端工程师",
  "headcount": 2,
  "major": "计算机相关",
  "job_jd": "负责后端服务开发",
  "job_min_degree": "本科",
  "job_min_exp_years": 2,
  "job_required_skills": ["Python", "SQL"],
  "job_optional_skills": ["FastAPI"],
  "bonus_items": [{"label": "行业经验", "value": "招聘系统"}],
  "job_status": 1,
  "job_created_by": "hr_admin"
}
```

`job_status` 为 `0` 草稿、`1` 开放、`2` 关闭；最低学历可取大专、本科、硕士、博士或 `null`；最低年限必须为非负整数。自动分配只处理开放岗位。

岗位组加入请求同样为 `{"resume_ids":[42,43]}`。列表响应在简历摘要之外包含：

- `added_by`：`auto:assignment` 或人工添加标识；
- `match_detail`：技能命中说明，仅作参考，不代表筛选通过。

`POST /api/jobs/{job_id}/screen` 对组内可筛简历执行岗位硬规则，保存规则快照并同步返回筛选任务。空岗位组或全部已出局时返回 `400`。

## 筛选 API

### 模板

`POST /api/screening/templates`

```json
{
  "template_name": "后端工程师硬条件",
  "job_id": 8,
  "rules": {
    "min_degree": "本科",
    "min_exp_years": 2,
    "required_skills": ["Python", "SQL"]
  },
  "created_by": "hr_admin"
}
```

删除模板会把历史任务的 `template_id` 置空，但保留任务、结果和 `rules_snapshot`。

### 执行与结果

`POST /api/screening/runs`

```json
{
  "template_id": 3,
  "resume_ids": [42, 43]
}
```

`resume_ids` 不传或为 `null` 时由筛选服务选择全部可筛简历。当前执行是同步完成后返回。任务响应包含 `run_id`、`template_id`、`job_id`、`status`、`total`、`passed`、`rejected`、`pending_review` 以及岗位/需求展示字段。

`GET /api/screening/runs?limit=10` 的 `limit` 范围为 1 至 100。结果接口中的每条原因结构为：

```json
{
  "rule": "最低学历",
  "passed": null,
  "detail": "学历信息缺失，待人工复核"
}
```

`passed=null` 表示信息不足。最终结果只可能是 `PASS`、`REJECT`、`PENDING_REVIEW`。筛选使用学历、工作月数和必备技能的确定性规则；加分技能/JD 不产生淘汰结论，LLM 不参与决策。

CSV 导出无结果时返回 `404`；成功响应带 UTF-8 BOM，便于 Excel 打开中文内容。

## 面试与人才库 API

### 面试邀约

`POST /api/talent/interviews`

```json
{
  "resume_id": 42,
  "job_id": 8,
  "interview_time": "2026-10-20 14:00",
  "way": "视频面试",
  "interviewer": "李经理",
  "note": "第一轮技术面",
  "notify_way": "电话"
}
```

成功创建后，简历的 `interview_status` 同时变为 `1`。`GET /api/talent/interviews?resume_id=42` 可选按简历过滤。

### 沉淀人才库

`POST /api/talent/pool?resume_id=42`

```json
{
  "source_requirement_id": 12,
  "source_job_id": 8,
  "note": "适合后续岗位"
}
```

业务记录提交后，主服务尝试把脱敏画像同步到知识库。同步失败不会回滚沉淀；响应中的 `knowledge_sync_status`、`knowledge_sync_error` 等字段反映同步状态。相同简历重复沉淀返回 `409`。

`POST /api/talent/pool/{pool_id}/sync-knowledge` 手动重试同步：画像数据不完整返回 `409`，下游故障返回 `503`。`DELETE /api/talent/pool/{pool_id}` 只解除人才沉淀关系并尝试删除知识索引，简历记录仍保留。

## 尚未实现的目标接口

以下接口在目标规格中有定义，但当前路由中不存在：

- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- 独立的 `POST /api/resumes/{resume_id}/normalize`

完整的可信审核身份、归一化版本冲突、审核记录和幂等确认也仍属于待完善能力。调用方不得假设这些安全与并发保障已经存在。
