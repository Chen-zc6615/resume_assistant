# 功能三 简历归一化

版本：v1.0 草案｜日期：2026-10-09。

## 1. 目标与边界

把完整解析文本转换为统一的结构化简历草稿，供需求和岗位筛选使用。字段只从原文提取，未知标量保持 None（JSON 为 null）；没有可提取的列表内容时使用空数组，不代表候选人确定不具备该经历或技能。

以 `src/models/schemas.py` 的 ResumeProfile 为现有运行时契约。归一化成功只允许保存处理草稿，不等于人才入库。候选事实、规则判断和 HR 审核记录分别保存。

## 2. 字段契约

| 对象 | 字段 | 类型与约束 |
| --- | --- | --- |
| ResumeProfile | resume_id | 正整数，必须对应原文件 |
| ResumeProfile | profile_id | 入人才库前为 null，入库时数据库分配 |
| 基础信息 | name | 非空字符串；无法识别则归一化失败，交人工核对 |
| 基础信息 | gender | 男 / 女 / 其他 / null；只接受原文明示 |
| 基础信息 | phone、email | 字符串 / null，邮箱校验基础格式，电话保留国际号码和分机 |
| 教育摘要 | highest_education、graduation_institution | 字符串 / null，不从学校或职位推断学历 |
| 工作摘要 | total_work_months | 非负整数 / null，来源与计算口径可追溯 |
| 技能 | skills | 非空字符串数组，仅提取原文明示技能 |
| 教育经历 | school、major、education_level、start_date、end_date、is_current | school 必填，其他可为 null |
| 工作经历 | company、position、start_date、end_date、is_current、description | company、position 必填，其他可为 null |
| 项目经历 | project_name、role、start_date、end_date、description | project_name 必填，其他可为 null |
| 经历关联 | education_id / work_id / project_id、profile_id | 入库前为 null，不接受模型生成的数据库 ID |

所有对象禁止未声明字段；ID 与工作月数采用严格整数校验，布尔值不能当整数。日期为合法 `YYYY-MM`，拒绝 0000 年、非法月份和开始晚于结束。在读或在职为 true 时结束日期必须为 null。

## 3. 归一化规则

- 可以统一明确日期的分隔符，例如 `2020.03` → `2020-03`；仅有年份不补月份。
- 原文写“至今”才将对应经历 is_current 标记为 true；单纯缺少结束日期不能判断在职或在读。
- 不能根据姓名推断性别，不能根据职位推断技能，不能把“研究生”无依据转为硕士。
- 缺少经历必填字段时保留原文及校验问题，进入人工修正，不生成“未知公司”等占位事实。
- 技能可去除首尾空白、去重；技能匹配别名属于筛选规则，不应修改原始技能事实。

目标新增 NormalizationSnapshot：resume_id、normalization_version、source_parse_version、schema_version、model_version、status、profile_json、validation_errors、created_at。字段证据使用独立 evidence 数组保存字段路径、原文片段及可确认的页码，不直接添加到现有 ResumeProfile。证据页码缺失时保持 null，不编造。

## 4. 工作月数口径

现有 `work_months_service.compute_work_months` 按每段工作经历的年月差累计，月差不含尾月；`2020-01` 至 `2021-01` 为 12 个月。在职经历计算到处理时的当前月，不可计算的经历跳过，全部不可计算则结果为 None。现有逻辑不对重叠经历去重，应在结果中说明“按段累计”和不完整经历情况，不称其为已确认的实际工龄。

归一化与入库应以服务端可计算的经历结果为准；若全部无法计算，仅允许保留可验证的原文明确工作时长，不能保留模型猜测值。计算时记录基准月份，后续重筛可解释时长变化。是否合并重叠区间、是否计入实习或兼职、部分经历缺失时的最终口径待确认。

## 5. AI、状态与失败处理

输入仅为解析文本及固定字段规则，输出仅为结构化 JSON。以 Pydantic 生成的 JSON Schema 为权威校验来源，随后执行跨字段校验和来源核对；格式通过不能代替事实正确。

状态为 parsed → normalizing → normalized 或 normalize_failed。网络暂时异常、JSON 无效或校验失败可最多重试两次；超过配置超时或最终失败记录原因，保留原文进入人工队列。姓名缺失不能通过填造姓名解决。人工修正生成新版本，令依赖旧版本的两阶段筛选结果失效。

目标接口建议 `POST /api/resumes/{resume_id}/normalize`，查询返回归一化版本、草稿和校验错误；与现有批次处理接口集成时仍需独立暴露阶段结果。

## 6. 验收标准

- 电话、学历和日期缺失时保持 null，无工作经历时不能自动填 0 个月。
- 原文“研究生”、只有年份、缺少结束时间均不触发无依据推断。
- 无效邮箱、倒置日期、错误关联 ID、模型额外字段被拦截。
- 工作月数覆盖整年、同月、在职、不可计算及重叠经历样本，结果符合已声明口径。
- 校验失败不进入自动初筛；人工修正保留原版本与修改记录。

关联规格：[上传与解析](feature_02_resume_upload_and_parsing_spec.md)、[需求初筛](feature_04_requirement_level_screening_spec.md)。
