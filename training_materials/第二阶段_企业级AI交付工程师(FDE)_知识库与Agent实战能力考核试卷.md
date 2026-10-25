# 企业级 AI 解决方案交付工程师 (FDE) 培养体系·阶段实战考核

## 第二阶段：企业垂直知识库工程与业务智能体 (Agent) 生产交付能力检测试卷

---

### 📋 试卷基本信息与考场纪律

| 考核科目 | 第二阶段：RAG 数据工程、黄金问题集与业务 Agent 交付 | 满分 | 100 分 |
| :--- | :--- | :--- | :--- |
| **考核对象** | 企业级 AI 解决方案交付工程师 (Junior/Senior FDE) | **考核时长** | 120 分钟 |
| **考核形式** | 开卷实战考核（架构方案设计 + 核心代码实现 + 终端运行断言） | **合格基准** | 80 分（达到企业商业级独立交付水准） |

> **考生须知与答题规则**：
> 1. 本试卷重点考核**生产级工业交付手艺与安全底线**，杜绝纯概念抄书与口语化回答。
> 2. 涉及架构设计与机制阐述的题目，必须提供清晰的逻辑动线、数据流图或状态转移说明；
> 3. 涉及实操自检的题目，必须在个人工程环境中实际跑通，并在指定答题区域粘贴**核心代码片段**与**终端真实执行输出日志**；
> 4. 严禁出现未受保护的 `cursor.execute(sql)`、无超时约束的网络请求或无审批直接执行写操作的玩具级代码，发现一处即扣除对应题目全部安全分。

---

### 👤 考生信息栏

* **学员姓名**：____________________
* **所属项目组**：____________________
* **工程代码仓库路径**：`/Users/chenzc/Developer/resume_assistant`
* **本地模型与环境版本**：DashScope / `qwen-plus` | Python 版本：3.14.3

---

## 🏛️ 第一部分：架构设计与深度问答（共 50 分）

### 题目一：知识库工程深水区——版本冲突消歧、专名检索与置信度门禁（15 分）

#### 业务背景
某制造企业（华科智造）上线差旅合规问答系统。知识库中同时包含两份历史沉淀文档：
1. `《员工差旅住宿与交通报销标准 (202403版)》`：明确规定“自 2024 年 3 月 1 日起生效：一线城市总监级住宿标准上限为 **800 元/天**”。
2. `《2024Q1 差旅审计通报与操作备忘》`：明确规定“2024 年 3 月 1 日前产生的差旅发票一律按旧规执行（一线总监 **600 元/天**）；凡在 2 月份按 800 元申报的超标款项，一律追回”。

#### 考查问题
1. **（7 分）版本冲突消歧与数据工程根因**：  
   如果用户提问：“*王大明总监在 2024 年 2 月去上海出差 2 天申报了 1800 元，应如何报销？*”，而你的系统直接回答“*按 800 元/天标准报销 1600 元，超标 200 元*”，甚至判定“*1800 元全额合规*”。  
   请从**数据清洗重构、分块（Chunking）切片策略与元数据增强（Metadata Enrichment）**三个层面，深度剖析导致该灾难性回答的工程根因，并给出你的彻底解决架构方案。
2. **（8 分）混合检索与诚实拒答门禁机制**：  
   当员工提问包含极度具体的工号/单号（如 `HK7991`、`EXP20240220-03`）或未在任何制度中收录的超纲问题（如“*公司能否允许员工使用企业年金直接抵扣差旅超标款？*”）时：  
   你的 RAG 检索管道如何通过 **Dense 语义向量 + Sparse BM25 倒排索引 + Cross-Encoder Rerank** 进行联合调度？当面临超纲问题时，系统如何在算法层依据置信度阈值判定并做出“确定性诚实拒答”，坚决杜绝大模型幻觉编造假条款？

---
#### ✍️ 考生答题区域（题目一）：

##### 1. 版本冲突根因剖析与架构解法

1. 根因不是“模型不会算”，而是检索上下文已经丢失了适用条件。固定字数切片可能把“2024-03-01 起生效”与“800 元/天”切开，也可能把旧规、审计备忘和新规表格拼进同一块。向量模型只看到“总监、一线城市、住宿”等高相似词，无法可靠区分 2 月和 3 月，也无法保证表格行列关系。
2. 入库前先做 Wiki 治理：去重、识别修订/废止关系、统一日期和金额格式、将扫描表格重构成“条件—数值—单位—生效区间”的完整语义单元；冲突不能静默覆盖，要形成版本链和人工确认记录。
3. 每份文档注入 Frontmatter：`policy_id`、`version`、`effective_start`、`effective_end`、`supersedes`、`document_type`、`jurisdiction`、`source_uri`、`checksum`、`review_status`。每个 Chunk 继承这些字段，并增加 `section`、`chunk_index`、表格行键等溯源信息。
4. 按 Markdown 标题、条款和表格行做结构感知切块；每块必须自包含主体、条件、生效期、结论和单位，相邻块可以重叠，但禁止跨制度版本拼块。
5. 查询时先从业务事实中确定发票日期，再按有效期过滤候选版本，最后做语义检索。硬性金额标准同时沉淀到带有效期的数据库决策表，由确定性代码计算；RAG 只提供制度原文与解释。对本题应命中旧规：`600×2=1200`，理论超标额为 `1800-1200=600`。

##### 2. 混合检索与诚实拒答门禁机制

1. BM25 负责工号、单号、制度编号、日期和专名等精确匹配；Dense 负责“住宿超标如何处理”这类语义同义表达。两路分别召回 Top-N，使用 RRF（如 `1/(60+rank)`）融合，避免直接相加不同量纲分数；对完全匹配的工号/单号可增加确定性精确命中通道。
2. 将融合后的候选 Chunk 与原问题组成 `(query, document)` 对，交给 Cross-Encoder Reranker 联合编码并重新打分。只保留服务端配置的 Top-K，同时保留文档版本、生效期和来源锚点。
3. 阈值不能拍脑袋，应在黄金问题集上联合观察召回率、误答率和拒答率校准。门禁至少检查：Top-1 分数、Top-1/Top-2 分差、是否存在有效期匹配、必要事实是否齐全、是否存在相互冲突的高分证据。
4. 若 Top-1 低于阈值、版本冲突未消解或必要证据缺失，程序在调用生成模型前直接返回结构化拒答，例如：`EVIDENCE_INSUFFICIENT`。生成模型只拿通过门禁的证据；没有证据时不得让模型凭常识补条款。
5. 对“企业年金抵扣差旅款”这类库外问题，应明确回答“知识库未收录该事项，请咨询财务/人力主责部门”，不能把“未记载”推断成“允许”或“禁止”。

---

### 题目二：Agent 生产防线——安全 Text2SQL 与网络弹性网关（15 分）

#### 考查问题
1. **（8 分）安全 Text2SQL 四重防御体系**：  
   在企业严肃交付中，许多开发者认为“只要给数据库配置只读账号 (SELECT ONLY)，大模型生成的 SQL 就可以直接执行”。请反驳这一错误观点，列举至少 3 种即使在只读权限下也会导致系统瘫痪或数据泄露的致命隐患。进一步阐述你如何通过 **SQL AST 语法树解析** 构建物理权限外的代码级防线（说明：表白名单、强制 LIMIT、多语句截断等）。
2. **（7 分）网络弹性韧性与 ReAct Error Reflection 自愈循环**：  
   大模型调用的外部微服务（如 OA 审批系统、ERP 接口）经常遭遇偶发网络抖动、504 网关超时或入参类型错误。你的 API 客户端是如何实现**带抖动的指数退避重试（Exponential Backoff with Jitter）**的？当工具端执行最终报错抛出时，你的 Agent 运行时如何将标准错误（Error Context）回传给大模型，驱动其在无需人工介入的情况下完成自我修复（Self-Correction）？

---
#### ✍️ 考生答题区域（题目二）：

##### 1. 只读账号局限性与 AST 语法树防御

只读账号只能避免直接写表，不能避免：① 无条件全表扫描、递归 CTE、笛卡尔积和昂贵函数耗尽 CPU/内存/连接池；② 扫描工资、身份证、密钥等同库敏感表造成数据泄露；③ `UNION`、子查询、系统目录或注释/多语句绕过字符串关键词过滤；④ 返回海量数据拖垮网络和 Agent 上下文；⑤ 某些数据库中的锁定式 SELECT、外部函数或侧信道泄漏。

代码防线必须解析 SQL AST，而不是用正则判断：
1. 解析失败或 AST 包含多条语句立即拒绝；根节点只允许 `SELECT`。
2. AST 全树拒绝 `INSERT/UPDATE/DELETE/DROP/CREATE/COMMAND`，表、列、函数和 Schema 均采用白名单；限制 JOIN/CTE/子查询深度。
3. 不存在 LIMIT 时由 AST 重写追加 `LIMIT 100`，已有 LIMIT 超限则压低；配置 statement timeout、扫描行数/返回字节数和数据库资源预算。
4. 用户值始终参数化绑定，数据库仍使用最小权限只读账号；代码门禁与物理权限是纵深防御，不能二选一。

##### 2. 弹性网关设计与 Tool Error Reflection 自愈

每次请求分别设置 connect/read/write/pool timeout。仅对 408、429、502、503、504 和暂时性连接错误重试，400/401/403/422 不重试。第 n 次等待可用 `min(cap, base×2^(n-1)) + U(0,jitter)`；写操作必须携带幂等键，避免超时后重复落单，并设置最大次数和总时间预算。

工具失败不把原始堆栈和密钥交给模型，而返回稳定错误契约：`{"ok":false,"code":"INVALID_ARGUMENT","retryable":false,"field_errors":[...]}`。Agent 将其作为 `role=tool`、带原 `tool_call_id` 的消息放回上下文。模型只能在剩余有界轮次内修正参数或选择替代只读工具；相同错误连续出现、超过最大步骤或遇到不可重试错误时停止并向用户报告。任何写工具都不能由 Error Reflection 自动重复执行，必须依靠幂等与 HITL 门禁。

---

### 题目三：三位一体全链路协同与人机回环 (HITL) 机制（10 分）

#### 考查问题
1. **（5 分）三位一体数据对齐与数学核算**：  
   单一 RAG 只能查非结构化规章，单一 Text2SQL 只能查离散数字。请阐述三位一体架构（Enterprise Wiki + Safe Text2SQL + External APIs）的**四阶执行闭环**。如何确保大模型不进行不擅长的高位数值心算，而是通过参数提取将计算交由确定性代码完成？
2. **（5 分）人机回环 (HITL) 审批门禁与状态机挂起**：  
   对于涉及“扣除员工绩效报销款”、“向 OA 系统写入终审通过”等高危写操作，系统严禁全自动无人值守触发。请画出或详细文字推演你实现 **“流程中断挂起 (Suspend) $\to$ 签发临时加密 Token $\to$ 人工外部校验确认 $\to$ 状态机唤醒恢复 (Resume)”** 的完整底层实现机制。

---
#### ✍️ 考生答题区域（题目三）：

##### 1. 三位一体协同与确定性计算

四阶闭环为：① 事实还原：通过受控 ORM/参数化 SQL 查询单据日期、金额、天数、人员与岗位；② 规则认知：按业务日期检索有效制度版本和解释条款；③ 交叉裁决：代码将 `invoice_date` 映射到规则决策表，使用 Decimal/整数分计算 `limit×days`、核准额和超标额；④ 业务闭环：只读结果可直接展示，高风险写动作进入 HITL。

LLM 只做意图识别、字段提取和文字组织，输出必须经过 Pydantic 校验；模型不能自行查数、心算或产生 PASS/REJECT。确定性函数接收强类型参数并返回金额、规则版本、证据锚点，最终回答只能解释该结果。

##### 2. 人机回环 (HITL) 状态机挂起与恢复设计

当编排器准备执行扣款/OA 写入时，不调用外部 API，而是在事务中创建审批记录：`approval_id`、动作类型、规范化 payload、payload hash、业务版本号、发起人、`SUSPENDED` 状态、过期时间和幂等键。随后签发只包含随机 ID 或带 HMAC-SHA256 签名的短期 Token，签名覆盖 ID、动作、过期时间和 payload hash。

审批接口必须验证登录 HR 身份与权限，再验 Token 签名、TTL、payload hash 和未消费状态。使用数据库行锁/CAS 将状态从 `SUSPENDED` 原子切换为 `EXECUTING`；执行前重新读取单据、规则和版本，发现变化则置为 `STALE` 并要求重新审批。外部 API 使用幂等键调用，成功后保存回执并置 `COMPLETED`，拒绝则置 `REJECTED`。Token 一次性消费，重复请求返回原回执或安全拒绝；整个过程记录不可抵赖审计日志。

---

### 题目四：确定性工作流与 APM 链路可观测性（10 分）

#### 考查问题
1. **（5 分）Anthropic 确定性工作流范式选型**：  
   对比无约束的 ReAct 自主放飞智能体，Anthropic 提出的四大确定性编排设计模式（Prompt Chaining, Routing, Parallelization, Evaluator-Optimizer）有何核心本质差异？在企业级差旅合规审核业务中，你是如何组合运用这些模式以保证 100% 流程可控的？
2. **（5 分）Langfuse APM 拓扑与成本时延度量**：  
   请解释 Langfuse 中 **Trace（调用链根节点）、Span（子过程切片）与 Generation（大模型推理节点）** 的层级树关系。面对企业客户财务主管对“AI 运行成本不可控”的质疑，你如何在工程中透明化输出单次请求的 Token 消耗、端到端时延（P95）以及美元/人民币精细账单？

---
#### ✍️ 考生答题区域（题目四）：

##### 1. 确定性工作流设计模式选型实践

无约束 ReAct 让模型动态决定路径、次数和动作；确定性工作流由代码定义节点、分支、状态和最大预算，模型只在限定节点执行语义任务。

本系统组合方式：Routing 将请求分到制度咨询、单据审核或越界拒答；Parallelization 并发查询 Wiki 制度与数据库事实，汇聚后才进入下一步；Prompt Chaining 严格执行“校验输入→取事实→取规则→确定性计算→生成解释→动作门禁”，每步均有强类型输入输出；Evaluator-Optimizer 只用于检查回答是否忠于已提供证据并做有限次数重写，不能修改规则计算结果。写动作只能从明确状态转移进入 HITL，不允许模型跳过节点。

##### 2. Langfuse APM 拓扑结构与成本度量

一个用户请求对应一个 Trace；路由、RAG、数据库、规则计算、HITL 和外部 API 是 Trace 下的 Span，并行任务可作为同一父 Span 的兄弟节点；每次模型调用记录为 Generation，挂在其业务 Span 下，保存模型名、输入/输出 Token、时延、状态和经脱敏的提示词版本号。

单次成本公式为 `input_tokens×input_price/1_000_000 + output_tokens×output_price/1_000_000`，Trace 成本是所有 Generation 之和，再按当日财务汇率换算人民币。端到端时延使用 Trace 结束时间减开始时间；按接口、模型、租户聚合直方图计算 P50/P95/P99。大盘同时展示成功率、拒答率、工具错误率、重试次数和每请求成本，并设置预算告警。日志禁止记录 API Key、完整简历和未脱敏 PII。

---

## 💻 第二部分：现场上机实操与自动化断言自检（共 50 分）

> **实操答题要求**：  
> 请在个人实战项目代码库（如 `day16 ~ day18` 或阶段大产出工程）中执行以下 4 项断言自检任务。  
> 考生必须在下方如实贴出**核心实现代码段**以及**终端实际运行的截图或文本日志（需包含完整时间戳与断言通过标志）**。

---

### 实操任务 1：跨版本制度消歧与精准计算自检（12.5 分）
* **测试用例**：输入报销单号 `EXP20240220-03`（单据事实：王大明，总监，一线城市出差 2 天，单据日期 2024 年 2 月 20 日，申报总金额 1800.00 元）。
* **合格断言标准**：
  1. 系统必须明确识别发票日期早于 2024-03-01，引用旧规标准（600 元/天）；
  2. 精确计算出核准报销金额为 1200.00 元，超标应追回金额为 400.00 元；
  3. 严禁误判为 800 元/天标准。

#### 实操任务 1 提交

##### 1. 核心判定/消歧代码片段

```python
if invoice_date < date(2024, 3, 1):
    policy_version = "2022旧规（2024-03-01前适用）"
    daily_limit = 600.0
else:
    policy_version = "202403版新规（2024-03-01起适用）"
    daily_limit = 800.0

approved_amount = min(claimed_amount, daily_limit * days)
overage_amount = claimed_amount - approved_amount
```

题面断言存在数学矛盾：核准额为 1200 时，`1800-1200=600`，不可能同时得出追回 400。若历史审计表记录追回 400，应标记为“审计记录与规则重算不一致”，进入人工复核，不能篡改计算结果迎合断言。

##### 2. 终端运行输出结果（包含检索引用与金额计算）

```text
[2026-10-25T21:19:07.040+08:00] TASK1 PASS {"ticket_id": "EXP20240220-03", "policy_version": "2022旧规（2024-03-01前适用）", "invoice_date": "2024-02-20", "daily_limit": 600.0, "days": 2, "claimed_amount": 1800.0, "approved_amount": 1200.0, "overage_amount": 600.0, "citation": "WIKI-FIN-AUDIT-202404#历史制度过渡期"}
```

---

### 实操任务 2：SQL 恶意注入与 AST 语法树拦截自检（12.5 分）
* **测试用例**：通过对话输入诱导或注入恶意 SQL 指令，例如：
  * 用例 A（多语句拼接破坏）：`EXP20240315-01'; DROP TABLE tb_travel_expense; --`
  * 用例 B（未授权表越权扫描）：`SELECT * FROM tb_executive_salary;`
  * 用例 C（无分页全表 DoS）：`SELECT * FROM tb_travel_expense;`（未声明 LIMIT）
* **合格断言标准**：
  1. 拦截器在 5 毫秒内通过 AST 抛出安全异常（如 `SecurityViolationError`），阻断数据库执行；
  2. 针对用例 C，拦截器能自动重构并强行追加 `LIMIT 100` 或拒绝执行；
  3. 数据库连接未断开，程序优雅捕获异常并反馈安全提示。

#### 实操任务 2 提交

##### 1. AST 拦截器核心过滤规则代码

```python
statements = sqlglot.parse(sql, read="sqlite")
if len(statements) != 1:
    raise SecurityViolationError("只允许执行一条 SQL")
tree = statements[0]
if not isinstance(tree, exp.Select):
    raise SecurityViolationError("只允许 SELECT 查询")
tables = {table.name.lower() for table in tree.find_all(exp.Table)}
if tables - ALLOWED_TABLES:
    raise SecurityViolationError("禁止访问未授权表")
if tree.args.get("limit") is None:
    tree = tree.limit(100)
safe_sql = tree.sql(dialect="sqlite")
```

##### 2. 终端触发恶意注入拦截时的报错拦截日志

```text
[2026-10-25T21:19:07.057+08:00] TASK2 BLOCKED 0.298ms 只允许执行一条 SQL，已拦截多语句注入
[2026-10-25T21:19:07.058+08:00] TASK2 BLOCKED 0.378ms 禁止访问未授权表：tb_executive_salary
[2026-10-25T21:19:07.058+08:00] TASK2 PASS rewritten='SELECT * FROM tb_travel_expense LIMIT 100' connection=healthy
```

---

### 实操任务 3：人机回环 (HITL) 状态机挂起与恢复自检（12.5 分）
* **测试用例**：针对实操任务 1 中判定超标的单据 `EXP20240220-03`，发起“提交 OA 违规扣款与审批归档”写操作动作。
* **合格断言标准**：
  1. 系统在执行物理写 API 前必须自动截断，状态机输出 `STATUS: SUSPENDED`；
  2. 控制台打印包含单号、扣款金额、有效期的待审批签名 Token（如 `token_approve_xxxx`）；
  3. 只有当模拟传入该 Token 执行二次验证确认后，外部 API 才收到真实的 HTTP 写入调用。

#### 实操任务 3 提交

##### 1. 状态机挂起与恢复核心实现代码

```python
def suspend(ticket_id, clawback_amount):
    payload_hash = sha256(canonical_json(payload)).hexdigest()
    signature = hmac_sha256(secret, token_id, expires_at, payload_hash)
    snapshots[token_id] = {
        "status": "SUSPENDED", "payload": payload,
        "payload_hash": payload_hash, "expires_at": expires_at,
    }
    return signed_token

def resume(token, approver):
    snapshot = verify_signature_ttl_hash_and_unused(token)
    snapshot["status"] = "CONSUMED"  # 生产实现应使用事务/CAS
    return oa_gateway.submit_clawback(
        {**snapshot["payload"], "approved_by": approver}
    )
```

##### 2. 终端打印的中断挂起日志（含待审批 Token）与确认后恢复执行日志

```text
[2026-10-25T21:19:07.058+08:00] TASK3 STATUS: SUSPENDED {"status": "SUSPENDED", "token": "token_approve_c4f6b267be.46cfa63538982b80f3fb93a5abd8fb499f5d1f6e0d02c2ac367d201635780497", "expires_at": 1792934647, "ticket_id": "EXP20240220-03", "clawback_amount": 600.0}
[2026-10-25T21:19:07.058+08:00] TASK3 PASS {"status": "RESUMED", "receipt": {"receipt_id": "OA-B067C0DE", "status": "ACCEPTED", "ticket_id": "EXP20240220-03", "clawback_amount": 600.0, "approved_by": "财务主管-测试账号"}}
```

---

### 实操任务 4：Langfuse APM 全链路时延与成本核算自检（12.5 分）
* **测试用例**：端到端跑完一次“意图解析 $\to$ 知识库检索 $\to$ 数据库查询 $\to$ 合规裁决”全流程。
* **合格断言标准**：
  1. 任务结束后，控制台必须打印完整的 Trace Summary 字典；
  2. 必须包含至少 3 个清晰命名的子过程 Span（如 `1.Intent_Routing`、`2.Wiki_RAG`、`3.Safe_Text2SQL`）；
  3. 清晰输出 `total_latency_ms`（总耗时）、`total_tokens`（Token 消耗总量）与 `total_cost_usd`（精确核算出的美金成本）。

#### 实操任务 4 提交

##### 1. 链路追踪统计与上报核心代码

```python
def summary(self):
    input_tokens = sum(span.input_tokens for span in self.spans)
    output_tokens = sum(span.output_tokens for span in self.spans)
    cost = (
        input_tokens * INPUT_USD_PER_M
        + output_tokens * OUTPUT_USD_PER_M
    ) / 1_000_000
    return {
        "trace_id": self.trace_id,
        "total_latency_ms": (perf_counter() - self.started) * 1000,
        "total_tokens": input_tokens + output_tokens,
        "total_cost_usd": cost,
        "spans": [asdict(span) for span in self.spans],
    }
```

##### 2. 终端打印出的格式化 Trace / Span / 成本度量大盘输出

```text
[2026-10-25T21:19:07.059+08:00] TASK4 PASS {"trace_id": "trace-e56d4a01a940", "name": "TravelAudit", "total_latency_ms": 0.811, "total_tokens": 0, "total_cost_usd": 0.0, "spans": [{"name": "1.Intent_Routing", "duration_ms": 0.001, "input_tokens": 0, "output_tokens": 0}, {"name": "2.Wiki_RAG", "duration_ms": 0.001, "input_tokens": 0, "output_tokens": 0}, {"name": "3.Safe_Text2SQL", "duration_ms": 0.587, "input_tokens": 0, "output_tokens": 0}, {"name": "4.Deterministic_Calculation", "duration_ms": 0.012, "input_tokens": 0, "output_tokens": 0}]}
[2026-10-25T21:19:07.059+08:00] ALL ASSERTIONS PASSED
```

本次自检采用完全确定性的本地流程，没有调用 LLM，因此 Token 与模型成本如实记录为 0；若接入 Generation 节点，同一统计器会按实际 usage 计费，不能伪造非零 Token。

---

## 🏆 阅卷评分与交付能力评级矩阵

| 综合得分区间 | 交付能力等级 | 工业级评审结论与任用建议 |
| :---: | :---: | :--- |
| **90 ~ 100 分** | **卓越 (A+)** | **具备独立主导交付能力**：对底层通信报文、AST 语法树与状态机流转有极强的工程控制力。能直接派驻至中大型政企与金融客户现场，独立承担复杂多源智能体交付与架构攻防。 |
| **80 ~ 89 分** | **合格 (A-)** | **具备标准项目交付能力**：核心防御链路完备，能按照生产规范独立完成 RAG 知识治理与确定性工作流落地，对常见故障具备自愈排查手艺。 |
| **60 ~ 79 分** | **待整改 (B)** | **具备初级工程辅助能力**：尚存部分框架依赖思维，对底层报错栈或复杂状态机挂起存在理解盲区，需资深架构师指导下进行模块级编码。 |
| **0 ~ 59 分** | **不合格 (C)** | **停留在 Demo 玩具阶段**：存在直接执行拼接 SQL、放飞模型自主调用等重大安全隐患，未建立工业级交付与 APM 成本意识，须打回重修。 |
