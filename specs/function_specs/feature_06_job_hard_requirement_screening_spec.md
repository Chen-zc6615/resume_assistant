# 功能六 根据岗位硬性条件初筛

版本：v1.0 草案｜日期：2026-10-09。

## 1. 目标与输入

依据分配岗位的结构化硬条件，判断对应简历是否达到岗位要求，输出明确、可追溯的逐项结论。输入为有效 assignment_id、已校验的 ResumeProfile、岗位条件快照及各自版本。必须先完成有效需求初筛和岗位分配。

沿用 `src/services/screen_service.py` 的确定性规则。JD 不直接作为硬条件来源；加分技能不决定通过；不生成分数，不用模型判断替代结构化字段比较。

## 2. 规则契约

| 硬条件 | 判断规则 | 信息缺失处理 |
| --- | --- | --- |
| 最低学历 | 大专=1、本科=2、硕士=3、博士=4，简历等级不低于要求 | 未知/不可映射时不得通过 |
| 最低工作年限 | total_work_months ≥ job_min_exp_years × 12 | 未知时按结构化经历只读补算；仍未知则不得通过 |
| 必备技能 | job_required_skills 中每项均有命中 | 未发现技能证据则不通过，理由不得声称候选人不会 |
| 加分技能 | 可展示命中情况 | 不影响是否通过 |

最低学历为 null 表示不限；最低年限为 0 或 null 表示不限；必备技能为空表示不限技能。条件采用 AND，枚举全部未通过原因，不能只返回第一项。

技能比较先 casefold，去掉空格、点、下划线、斜杠和连字符，保留 `+` 与 `#`；按完整规范形及分词结果判断，不采用任意子串。沿用现有显式 SQL 别名族，包括 MySQL、MariaDB、PostgreSQL/Postgres、SQL Server/MSSQL、Oracle、SQLite、PLSQL、TSQL、HiveSQL、SparkSQL 与 SQL 的等价匹配。NoSQL 不命中 SQL，C、C++、C# 不能合并。别名族是当前产品规则，不表示技术能力普遍等价，修改时必须升级规则版本。

工作月数遵循功能三口径，计算记录基准月份；初筛补算不得回写简历事实。没有经历和时长不能按 0 处理后声称经验确定不足。

## 3. 输出契约与状态

JobScreenResult 包含 result_id、assignment_id、resume_id、job_id、normalization_version、job_version、rules_version、requirement_screen_result_id、result、checks、screened_at、is_stale。

result 为 passed / rejected / error。checks 每项包含 field、expected、actual、outcome（pass/fail/unknown）、reason_code、reason_text 和证据引用。任一 fail 或 unknown 均为 rejected，以兼容现有“未知硬条件不得通过”的规则；界面区分“明确未达标”和“信息不足”。error 专指执行异常。

分配有效 → job_screening → job_screen_passed / job_screen_rejected / job_screen_failed。passed 进入待审核；rejected 进入不通过列表并允许人工核对；error 进入失败队列。筛选通过不自动入库。

## 4. 版本、错误与接口

同一简历不同岗位分别保存结果；不能以 resumes.status 单字段表达全部岗位结论。规则、岗位或归一化版本变化后旧结果失效并保留；HR 修正事实后重筛相关的全部有效岗位组合。

目标接口：`POST /api/assignments/{assignment_id}/screen`、`GET /api/assignments/{assignment_id}/screen-results`。执行前与保存结果前均核对输入版本，变化则不提交为当前有效结论。无效关联返回 404，取消/失效/版本冲突返回 409；批量处理逐组合返回结果。执行失败不能复用先前通过结论作为本次成功。

本阶段无 AI 输出契约，判断由确定性服务执行。结果写入失败时不标记成功；重试必须防止重复结果，日志不记录完整简历。

## 5. 验收标准

- 本科对最低本科通过，大专不通过，未知学历不通过并显示信息不足。
- 24 个月对两年要求通过，23 个月不通过，0 年或空要求不限制。
- 要求 Python 与 SQL 时两项必须满足；MySQL 命中 SQL，NoSQL 不命中 SQL。
- 缺少加分技能仍通过；空硬条件通过且显示无配置限制。
- 同一简历两个岗位可分别通过/不通过，结果互不覆盖。
- 修改岗位规则或简历后旧结果失效；筛选不修改候选事实、不自动入库。

关联规格：[简历归一化](feature_03_resume_normalization_spec.md)、[岗位分配](feature_05_job_assignment_spec.md)、[审核与人才库](feature_07_resume_review_and_talent_pool_spec.md)。
