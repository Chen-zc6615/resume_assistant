---
name: screening-spec
description: 简历硬性初筛技能：确定性规则引擎三态判定（通过/不通过/待人工复核），LLM 不得参与淘汰决策
---

# 简历初筛技能包（F-03）

## 职责

按岗位硬性条件对归一化简历做批量初筛，输出三态结果与逐条规则明细。

## 规则（SOP）

代码：`src/services/screen_service.py::evaluate_profile`

1. **学历（一票否决）**：DEGREE_ORDER 序（初中1<高中/中专2<大专3<本科4<硕士5<博士6）；
   不达标 → REJECT；学历未知 → 待人工复核
2. **年限**：total_work_months ≥ min_exp_years×12 通过；为 NULL（经历模糊）→ 待人工复核
3. **必备技能**：精确匹配（大小写/包含）或 rapidfuzz ratio ≥90；缺失 → REJECT；
   技能信息完全缺失 → 待人工复核
4. **综合**：任一 REJECT → REJECT；无 REJECT 但有信息不足 → PENDING_REVIEW；否则 PASS

## 红线

- **淘汰决策必须是确定性规则，LLM 不得自由判断**
- **信息不足 ≠ 不合格**：无法判定的一律进待人工复核（S03）
- 每条规则必须输出明细 reasons（rule / passed / detail）

## 状态联动

PASS → 简历 status=10 待审核入库；REJECT → 3；PENDING_REVIEW → 6

## 脚本

- `scripts/screen_check.py`：对 JSON 简历数据按规则跑三态判定
