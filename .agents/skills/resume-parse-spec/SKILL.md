---
name: resume-parse-spec
description: PDF 简历解析技能：上传校验（魔数/加密/损坏）、三级文本提取（PyMuPDF→pdfplumber→OCR）、有效字符判定
---

# 简历解析技能包（F-01）

## 职责

接收 HR 上传的 PDF 简历，输出可归一化的纯文本（`resumes.raw_text`）。

## 规则（SOP）

1. **上传校验链**（`src/core/security.py::validate_upload`）：
   - 单文件 ≤5M、非空
   - 魔数嗅探 `%PDF-`（仅凭扩展名不可信）
   - pymupdf 试开：加密（needs_pass）与损坏 → 友好拒绝
2. **SHA256 去重**（`src/services/upload_service.py::save_upload`）：重复上传复用已有 resume 记录
3. **三级解析**（`src/services/parse_service.py::parse_pdf`）：
   - L1 PyMuPDF `get_text`；有效字符 ≥50 即通过
   - L2 pdfplumber（表格/布局）
   - L3 OCR 兜底：页转 150dpi PNG → qwen-vl-max，重试 2 次
4. **失败**：标记 status=1 解析失败 + failure_reason，进失败列表

## 判定阈值

- 有效字符 = 非空白可打印字符数（`effective_chars`）
- 解析超时 10s；OCR 重试 2 次

## 脚本

- `scripts/check_pdf.py`：单文件校验与解析诊断
