# SPEC — 数据模型与实体契约（技术基准）

> 来源：《6〈技术SPEC架构说明书〉.docx》+ PRD 数据库表图。列名以 snake_case 为准（PRD 图中驼峰命名如 job_minDegree 统一为 job_min_degree）。

## 一、数据库表（SQLite，WAL 模式）

ORM 定义：`src/models/db_models.py`（15 张表）

| 表 | 说明 | 关键字段 |
|---|---|---|
| requirements | 招聘需求（岗位集合容器，不带筛选条件） | requirement_id 自增；requirement_name NOT NULL；dept 用人部门；deadline 截止日期；description；status 0进行中/1已关闭；created_by |
| jobs | 岗位（必属一个需求） | requirement_id FK NOT NULL；job_code 岗位编号；headcount 招聘人数；major 专业方向；job_name/jd NOT NULL；min_degree 枚举 大专/本科/硕士/博士；min_exp_years；required/optional skills JSON；bonus_items JSON 非技能加分项[{label,value}]；status 0草稿/1开放/2关闭 |
| requirement_resume_groups | 需求池（简历 → 需求多对多） | requirement_id + resume_id 唯一约束；added_by；一批简历挂一个需求，一份简历可入多个需求池 |
| resumes | 简历文件 | original_file_name、file_key（uploads/<sha256>.pdf）、sha256 UNIQUE 去重、raw_text、status、failure_reason、interview_status（面试流程，NULL=未进入）、uploaded_by |
| resume_profiles | 归一化简历 | resume_id FK UNIQUE、name NOT NULL、gender int(0男/1女/NULL未知)、phone、email、highest_education、graduation_institution、total_work_months（NULL=未知） |
| profile_skills | 技能 | profile_id FK、skill_name VARCHAR(80) |
| education_experiences | 教育经历 | school NOT NULL、major、education_level、start/end_date VARCHAR(7) YYYY-MM、is_current |
| work_experiences | 工作经历 | company/position NOT NULL、start/end_date、is_current、description |
| project_experiences | 项目经历 | project_name NOT NULL、role、start/end_date、description |
| job_resume_groups | 岗位分配结果（简历 → 岗位多对多） | job_id + resume_id 唯一约束；added_by（"auto:assignment" 自动分配 / HR 用户名手动调整）；match_detail JSON 分配依据 {required_hits, optional_hits} |
| filter_templates | 筛选模板 | template_name、job_id FK、rules JSON（min_degree/min_exp_years/required_skills） |
| filter_runs | 筛选任务 | template_id FK **可空**（自动初筛无模板）、job_id FK NOT NULL、**rules_snapshot JSON**（执行时刻规则快照）、status 0待/1运行/2完成/3失败、passed/rejected/pending_review 计数 |
| filter_results | 筛选结果 | run_id FK、resume_id FK、result PASS/REJECT/PENDING_REVIEW、reasons JSON 明细 |
| interviews | 面试邀约 | resume_id FK、job_id FK 可空、interview_time/way/interviewer/note/notify_way、created_by；一份简历可多次邀约留痕 |
| talent_pool | 沉淀候选人才库 | resume_id FK UNIQUE（一份一条）、source_requirement_id/source_job_id 来源、note、created_by |

**业务流**：HR 创建需求 → 需求下建岗位 → 上传简历挂需求池 → 自动 解析/归一化 → **全量分配** → 各岗位独立硬性初筛 → 多岗归并（**全部岗位都不满足才出局**）→ HR 审核入库。

**岗位分配规则**（`src/services/assign_service.py`，无 LLM、无打分）——**全量分配**：
- 需求池内归一化成功的简历进入需求下**全部开放（job_status=1）岗位**组，**不做技能门槛预筛**——需求级初筛要求每份简历面对所有岗位筛选，技能是否满足由初筛三态规则判定（缺技能 → 该岗 REJECT；信息不足 → 待复核），避免技能预筛漏掉可能满足其他岗位的简历
- match_detail 只做技能命中留痕（required_hits/optional_hits；无技能岗标注"岗位未配置技能"），供 HR 参考
- 一份简历进多个岗位组；已有分组幂等跳过（手动分组不被自动分配覆盖）；关闭/草稿岗位不参与
- 需求下没有开放岗位 → 简历停 status=9 + failure_reason 提示待人工分岗
- 上传后新增岗位：`POST /api/requirements/{id}/reassign` 一键把池内可筛简历补分配到各开放岗位并按岗初筛
- 恢复待筛：`POST /api/resumes/{id}/restore`，仅 status=3（初筛不通过）→ 9 待初筛，供规则修正后重新分组/重筛；已完成入库（4）为终态不可恢复

**多岗结果归并**（`screen_service._merge_and_summarize`）：需求级初筛——简历面对需求下所有（仍在组内的）岗位的初筛结果归并，status 取各岗最优（通过 10 > 待复核 6 > 不通过 3），**任一岗通过即待审核入库、全部岗位都不满足才出局**；只统计简历当前仍在岗位组内的结果（HR 移出某岗后该岗历史结果不再拖累）；failure_reason 重建「岗位初筛汇总：岗A=通过；岗B=不通过（学历...）」；重跑自动刷新；已入库（status=4）不被覆盖。

**初筛审计原则**：`execute_run` 只依据 `rules_snapshot` 判定（不回读模板）——模板/岗位事后修改不影响历史 run 的判定依据，事后可追问"当时按什么规则筛的"。上传自动初筛同样落 run + results，全程留痕。

**可筛状态集合（`SCREENABLE_STATUSES`）**：参与任何筛选（自动初筛/模板执行/按组重筛）的简历状态限于 待初筛(9)/待补录(5)/待人工复核(6)/待审核入库(10)。初筛不通过(3) 为出局态不再进入任何后续筛选；已完成入库(4) 为终态不再被筛；无归一化数据(0/1/2/7/8) 不参与。按组重筛时组内全部出局 → 400 友好拒绝。

**resumes.status 状态集**（PRD 0-4 + 扩展态）：
0 上传失败 / 1 解析失败 / 2 归一化失败 / 3 初筛不通过 / 4 已完成 / 5 待补录 / 6 待人工复核 / 7 待解析 / 8 待归一化 / 9 待初筛 / 10 待审核入库

## 二、Pydantic 实体契约

完整代码：`src/models/schemas.py`。要点：

- `NonEmptyText`：strip 后非空；`YearMonth`：`^\d{4}-(0[1-9]|1[0-2])$` 且年份非 0000
- 所有实体 `extra="forbid"`
- 跨字段校验：在读/在职时 end_date 必空；start_date ≤ end_date
- `ResumeProfileData`：name 必填（缺失 → 归一化失败，不得编造）；total_work_months ≥0 或 None
- `ResumeProcessingResult`：同一简历不允许出现在同阶段的多个结果集合

## 三、归一化 JSON Schema（LLM 输出契约）

完整 Schema：`src/services/normalize_service.py::RESUME_EXTRACT_SCHEMA`。要点：

- strict、`additionalProperties: false`、全部字段 required
- highest_education 枚举：大专/本科/硕士/博士/null
- 日期 pattern：`^[0-9]{4}-(0[1-9]|1[0-2])$`；「至今」→ is_current=true + end_date=null
- 校验失败自动重试，最多 2 次；仍失败 → 归一化失败列表
- **红线**：简历未提及的信息一律 null，严禁编造

## 四、容错与降级

| 场景 | 行为 |
|---|---|
| 解析超时 >10s / 宕机 | 重试 2 次 → 失败列表 |
| 归一化超 20s / 校验失败 | 归一化失败，失败列表，提示人工 |
| 文本有效字符 <50 | 触发 OCR 兜底（qwen-vl-max） |
| 加密/损坏 PDF | 上传或解析阶段友好拒绝：「文件已加密或损坏，请重新上传」 |

## 五、初筛实现策略（2026-09 评审结论 + 演进方向）

**当前实现（MVP，保留）**：SQL 集合取数（按 status 过滤候选集）→ 应用层规则引擎逐条判定（`evaluate_profile`）→ 三态结果 + 逐条 reasons 明细。

**为何不是纯 SQL WHERE**：三态判定（信息不足→待复核）、技能模糊/别名匹配（rapidfuzz，SQLite 无 fuzzy 函数）、逐条可解释 reasons，这三项是需求红线（S02/S03 用例），纯 SQL 表达会引入嵌套 CASE WHEN 与双份逻辑漂移。

**演进方向（数据量上万时启用）——两阶段混合**：
1. SQL 粗筛下推：学历（CASE 序映射）、年限（total_work_months 比较）、技能精确匹配（profile_skills EXISTS）直接进 WHERE，利用索引批量缩小候选集；
2. 应用层细筛：仅对粗筛结果集做三态归位（NULL→待复核）、模糊/别名匹配、生成 reasons。

**技能归一（已落地）**：`src/services/skill_dict.py` 别名字典（J2EE→Java、SpringBoot→Spring Boot、k8s→Kubernetes 等明确同义写法），归一化入库前统一 canonical 名，初筛匹配双方再各归一一次（token 级处理复合短语）。保守原则：不合并语义近义（"关系型数据库" ≠ "MySQL"）——语义召回属已裁剪的 C 域。

**人工筛除留痕（已落地）**：`POST /api/resumes/{id}/reject`，reason 必填（NonEmptyText），落 status=3 + failure_reason="人工筛除：{原因}"；规则淘汰与人工干预可区分审计。

**简历删除级联（已落地）**：`DELETE /api/resumes/{id}` 级联清理归一化数据（profile/经历/技能）、需求池与岗位组关联行、初筛结果（ORM cascade，外键约束不炸），并移除磁盘 PDF（sha256 全局唯一，记录删除后文件必无引用）。
