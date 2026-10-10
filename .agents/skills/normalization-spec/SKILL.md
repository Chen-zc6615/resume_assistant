---
name: normalization-spec
description: 简历归一化技能：文本预处理（NFKC/清洗）、LLM 结构化提取、JSON Schema + Pydantic 双重校验、六表落库
---

# 数据归一化技能包（F-02）

## 职责

将 `resumes.raw_text` 转换为严格结构化的归一化简历（resume_profiles + 四张明细表）。

## 规则（SOP）

1. **预处理**（`src/services/normalize_service.py::preprocess_text`）：NFKC 归一（全半角统一）→ 去控制字符 → 压缩空白
2. **LLM 提取**（`llm_extract`）：qwen-plus，system prompt 内嵌 JSON Schema，`response_format=json_object`，超时 20s
3. **双重校验**：
   - JSON Schema（`RESUME_EXTRACT_SCHEMA`）：枚举、日期 pattern、additionalProperties=false
   - Pydantic 实体（`build_profile_data`）：跨字段校验（在读→end_date 空；start≤end）
   - 校验失败重试最多 2 次，仍失败 → status=2 归一化失败
4. **落库**（`persist_profile`）：幂等（先删旧再插）
5. **派生字段**：total_work_months 按工作经历推算（在职算到当前月；LLM 已给则优先）

## 红线

- **简历未提及的信息一律 null，严禁编造**
- 姓名（必填）缺失 → 归一化失败（进失败列表提示人工）
- 电话/邮箱缺失 → 简历仍正常流转，标记「待补录」（S04）

## 枚举映射

- gender：男→0，女→1，未知→null
- highest_education：大专/本科/硕士/博士
- 日期：YYYY-MM；「至今」→ is_current=true + end_date=null

## 脚本

- `scripts/normalize_check.py`：对文本跑 Schema 红绿灯校验
