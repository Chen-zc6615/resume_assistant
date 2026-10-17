# 评测数据目录

- `resume_processing/resumes/`：PDF 解析、OCR 与归一化黄金样本。
- `screening/`：岗位分配和硬条件筛选的预期结果。
- `knowledge_retrieval/`：知识库检索黄金问题集。
- `baselines/`：需要纳入版本控制的正式基准指标和验收报告。

程序每次运行生成的普通报告写入仓库根目录 `artifacts/reports/`，不提交 Git。
