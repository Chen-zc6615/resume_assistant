---
name: screening-pipeline
description: 实现或审查招聘需求、岗位配置、全量岗位分配、确定性硬条件初筛和多岗位结果汇总。修改 F02、F05、F06、F07 或简历整体筛选状态时使用。
---

# 岗位配置、分配、筛选与汇总

## 必读资料

先读 `specs/PRD.md`，再按改动范围阅读：

- `specs/function_specs/feature_02_requirements_and_jobs_management_spec.md`
- `specs/function_specs/feature_05_job_assignment_spec.md`
- `specs/function_specs/feature_06_job_hard_requirement_screening_spec.md`
- `specs/function_specs/feature_07_multi_job_result_aggregation_spec.md`

然后检查相关 ORM、schemas、`assign_service.py`、`screen_service.py`、API、前端和测试。不要把“岗位配置、分配、单岗判断、跨岗汇总”混成一个不可验证步骤。

## 领域边界

- 招聘需求只是岗位集合容器，自身不保存学历、年限或技能筛选条件。
- 一个岗位只属于一个需求。只有岗位的结构化硬条件参与自动筛选；JD、加分技能和加分项不能产生淘汰结论。
- 修改当前岗位配置不得改写历史规则快照或历史筛选结果。
- 关闭需求或岗位阻止新的业务处理，但保留历史记录。

## 岗位分配

- 归一化通过后，将简历幂等分配到所属需求下的全部开放岗位。
- 分配阶段不得按技能、JD、相似度、模型评分或匹配分数提前淘汰。
- 同一“简历—岗位”组合唯一；技能命中明细仅用于解释。
- 没有开放岗位时保持待初筛并提示人工处理，不能报告虚假成功。
- 人工移出岗位后保留历史，但该岗位不再参加当前汇总。

## 单岗位硬筛

- 每个“简历—岗位”组合独立输出 `PASS`、`REJECT` 或 `PENDING_REVIEW`。
- 淘汰只能由确定性的学历、年限和必备技能规则产生，LLM 不得参与。
- 明确不满足才 `REJECT`；信息不足是 `PENDING_REVIEW`；系统异常不是业务不通过。
- 规则之间采用 AND，未配置的硬条件视为不限。每项规则保存结构化原因和执行时快照。
- 一个岗位不通过不能阻止同一简历在其他岗位继续执行。

## 多岗位汇总

只使用当前有效岗位关联的最新结果，优先级为：

```text
PASS > PENDING_REVIEW > REJECT
```

- 任一岗位通过且电话、邮箱完整 → status 10 待审核入库。
- 任一岗位通过但电话或邮箱缺失 → status 5 待补录。
- 无通过但存在待人工复核 → status 6 待人工复核。
- 当前有效岗位全部不通过 → status 3 初筛不通过。
- 无有效结果不得伪造通过或淘汰；status 4 已完成不能被普通重筛覆盖。

## 验证

覆盖需求/岗位归属、非法条件、全量和幂等分配、岗位关闭、学历与年限边界、技能完全缺失与部分缺失、多岗位结果顺序、联系方式守卫、移出岗位、仅取最新结果、无有效结果和已完成终态。
