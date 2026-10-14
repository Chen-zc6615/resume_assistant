# 功能四 根据需求简历初筛

版本：v1.0 草案｜日期：2026-10-09｜实现状态：新增目标设计。

## 1. 目标与边界

对已归一化的简历，依据所属招聘需求的已确认结构化条件判断是否进入岗位分配。此阶段不选择具体岗位，不替代岗位硬条件筛选，不改写简历事实，也不生成匹配评分。

输入必须有 requirement_id、requirement_version、resume_id、normalization_version；需求必须启用，简历必须有合法完整草稿。阶段失败与条件不满足分别表示，不能把程序异常当成不合格。

## 2. 条件与判断规则

| 条件 | 允许运算 | 判断口径 |
| --- | --- | --- |
| highest_education | min_degree | 大专 < 本科 < 硕士 < 博士；未知或不可比较值为 unknown |
| total_work_months | gte | 已声明口径的非负月数与需求下限比较；未知为 unknown |
| skills | contains_all | 全部必备技能命中才通过，采用功能六统一的规范形和显式别名规则 |

条件之间采用 AND。已知值低于要求为 fail；没有原文技能命中时该技能为 unknown，并提示“未发现必备技能证据”，不声称候选人实际不会该技能。未配置条件视为不限制，并明确记录“需求未设置筛选条件”。不支持的字段或运算符拒绝保存或执行，不采用模型自由判断兜底。

总体结果：任一 fail → rejected；无 fail 但有 unknown → needs_review；全部 pass 或条件为空 → passed。unknown 不能视为满足条件。不同于现有岗位筛选二值结果，这是新增需求阶段的结果契约。

## 3. 结果契约

RequirementScreenResult 包含 result_id、requirement_id、requirement_version、resume_id、normalization_version、rules_version、result、checks、screened_at、is_stale。checks 的每项包含 criterion_id、field、operator、expected、actual、outcome（pass/fail/unknown）、reason_code、reason_text 和证据引用。

result 取 passed / rejected / needs_review / error；error 使用独立 error_code 和可读描述。历史结果同时保存需求条件快照，不能只引用随时可变的需求。

## 4. 状态与人工处理

normalized → requirement_screening → requirement_passed / requirement_rejected / requirement_needs_review / requirement_screen_failed。

passed 进入功能五；rejected 保留原因并允许 HR 查看；needs_review 进入人工核对。HR 只能依据原文补充事实或修订经确认的条件，然后重新筛选；不通过强制覆盖结论进入自动分配。若后续需要例外放行，应另行定义授权和审计规则。

归一化、需求条件或规则版本变化后，历史结果标记过期；未重新筛选前不允许作为新的岗位分配依据。计算错误可重试，输入不合法须先修正，同批简历独立执行。

## 5. 接口与界面

目标接口：`POST /api/requirements/{requirement_id}/screen`，请求含 resume_ids、expected_requirement_version；`GET /api/requirements/{requirement_id}/screen-results` 查询结果。每个简历返回独立结果及输入版本，批次部分失败不抹掉成功项。重复执行同一版本可以复用结果，但应保证响应一致。

界面分别展示通过、不通过、待核对、执行失败，并展示“需求条件—简历事实—判断原因”。与岗位筛选结果分栏，避免用户误认为已满足某个岗位。

## 6. 验收标准

- 同一需求关联多个岗位时，需求初筛结果不因岗位不同而变化。
- 条件为空可进入分配，提示未设置条件；自然语言描述不会自动产生条件。
- 学历不足为 rejected；学历缺失为 needs_review；服务异常为 error。
- AND 组合及 fail 优先规则正确，结果列出全部检查项。
- 修改需求或简历后旧结果可读但不能用于新的分配。
- 本功能不写人才库，不生成岗位分数或候选人排名。

关联规格：[需求与岗位管理](feature_01_requirements_and_jobs_management_spec.md)、[岗位分配](feature_05_job_assignment_spec.md)。
