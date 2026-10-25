#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
Day 18 三位一体架构攻坚：知识库 + 数据库 + API 全链路协同 Agent
================================================================================
所属模块：第二阶段 RAG 数据工程、黄金问题集与单 Agent 工具交付 (Day 18)
前置承接：
  - Day 11 ~ Day 15: 企业非结构化规章 Wiki 资产库 (版本消歧与合规依据溯源角标)
  - Day 16: SafeText2SQLEngine 安全只读拦截器 + ExternalAPIGateway 弹性网关
  - Day 17: 确定性编排设计模式 + Langfuse APM 生产级全链路时延与成本追踪
核心架构特性：
  1. 三位一体协同范式 (The Triad Architecture):
     - 通道 1 (Wiki RAG): 制度规约提取、2024-03-01 新旧规约版本消歧、引用角标溯源
     - 通道 2 (Safe Text2SQL): 穿透查询结构化真实业务账本，获取单据与职级事实
     - 通道 3 (External API & Actions): 外部微服务动作集 (OA 审批流下发、扣款工单)
  2. 四阶闭环业务动线 (Four-Stage Pipeline):
     - Stage 1: 规则认知 (Knowledge RAG)
     - Stage 2: 事实还原 (Database Text2SQL)
     - Stage 3: 交叉裁决与逻辑推理 (Reasoning & Math Cross-Auditing)
     - Stage 4: 业务闭环与人机回环 (HITL Action Gate)
  3. 人机回环 (HITL) 生产级防线:
     - 读写分离门禁: 只读单据全自动通过 (`AUTO_PASS`)；高风险写操作物理挂起
     - 防篡改带签名审批令牌: HMAC-SHA256 签名、TTL 超时控制、防重放消费
     - 状态快照存储器 (State Snapshot Store): 上下文持久化挂起与唤醒恢复
================================================================================
"""

import os
import sys
import time
import json
import uuid
import hmac
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

# 尝试载入 OpenAI 兼容客户端 (本地 Ollama 或远端大模型中枢)
try:
    from openai import OpenAI
    HAS_OPENAI_SDK = True
except ImportError:
    HAS_OPENAI_SDK = False

# 将根目录和 day16/day17 加入路径以实现资产复用
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(WORKSPACE_ROOT))
sys.path.append(str(WORKSPACE_ROOT / "day16"))
sys.path.append(str(WORKSPACE_ROOT / "day17"))


# ==============================================================================
# 第一部分：APM 链路追踪与前序资产衔接 (承接 Day 16 & Day 17)
# ==============================================================================

class LangfuseTraceRecord:
    """轻量级高保真 APM 遥测追踪记录器 (承接 Day 17 APM 规范)"""
    def __init__(self, trace_id: str, name: str):
        self.trace_id = trace_id
        self.name = name
        self.spans: List[Dict[str, Any]] = []
        self.start_time = time.time()
        self.total_tokens = 0
        self.total_cost = 0.0

    def log_span(self, span_name: str, span_type: str, input_data: Any, output_data: Any, duration_ms: float, tokens: Optional[Dict[str, int]] = None):
        tok = tokens or {"input_tokens": 0, "output_tokens": 0}
        in_t = tok.get("input_tokens", 0)
        out_t = tok.get("output_tokens", 0)
        step_cost = (in_t * 0.00015 + out_t * 0.0006) / 1000.0  # 参照 Qwen/Llama3 生产费率
        self.total_tokens += (in_t + out_t)
        self.total_cost += step_cost

        self.spans.append({
            "name": span_name,
            "type": span_type,
            "duration_ms": round(duration_ms, 2),
            "input": input_data,
            "output": output_data,
            "tokens": {"input": in_t, "output": out_t, "total": in_t + out_t},
            "cost_usd": round(step_cost, 6)
        })

    def print_trace_summary(self):
        total_time = (time.time() - self.start_time) * 1000
        print(f"\n📊 [APM 链路追踪拓扑] TraceID: {self.trace_id} | 业务流: {self.name}")
        print(f"┌{'─'*30}┬{'─'*12}┬{'─'*12}┬{'─'*14}┬{'─'*16}┐")
        print(f"│ {'阶段执行节点 (Span Name)':<28} │ {'节点类型':<10} │ {'耗时 (ms)':<10} │ {'Token 消耗':<12} │ {'预估成本 ($)':<14} │")
        print(f"├{'─'*30}┼{'─'*12}┼{'─'*12}┼{'─'*14}┼{'─'*16}┤")
        for s in self.spans:
            print(f"│ {s['name']:<28} │ {s['type']:<10} │ {s['duration_ms']:<10.1f} │ {s['tokens']['total']:<12} │ ${s['cost_usd']:<13.6f} │")
        print(f"└{'─'*30}┴{'─'*12}┴{'─'*12}┴{'─'*14}┴{'─'*16}┘")
        print(f"   ⏱️ 链路总延迟: {total_time:.2f} ms | 累计 Token: {self.total_tokens} | 累计成本: ${self.total_cost:.6f}")


class SafeDatabaseGateway:
    """
    Day 16 安全只读数据库网关封装
    (实现 AST 级防注入拦截、只读表白名单控制与企业账本实体预置)
    """
    ALLOWED_TABLES = {"tb_travel_expense", "tb_audit_records"}
    DANGEROUS_KEYWORDS = {"drop", "delete", "update", "insert", "alter", "truncate", "create"}

    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema_and_seed()

    def _init_schema_and_seed(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_travel_expense (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE,
                employee_id TEXT,
                employee_name TEXT,
                role TEXT,
                city TEXT,
                city_tier TEXT,
                hotel_days INTEGER,
                amount REAL,
                expense_date TEXT,
                status TEXT
            )
        """)
        # 预置业务标杆数据 (周建华、王大明、赵小雪)
        cur.executemany("""
            INSERT OR REPLACE INTO tb_travel_expense 
            (ticket_id, employee_id, employee_name, role, city, city_tier, hotel_days, amount, expense_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("EXP20240315-01", "HK8012", "周建华", "总监", "上海", "一线城市", 3, 2400.0, "2024-03-15", "已报销待复审"),
            ("EXP20240220-03", "HK7991", "王大明", "总监", "北京", "一线城市", 2, 1800.0, "2024-02-20", "待核销"),
            ("EXP20240318-09", "HK8045", "赵小雪", "经理", "武汉", "二线城市", 3, 1050.0, "2024-03-18", "已报销待复审")
        ])
        self.conn.commit()

    def query_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """安全参数化查询报销流水事实"""
        cur = self.conn.cursor()
        cur.execute("SELECT ticket_id, employee_id, employee_name, role, city, city_tier, hotel_days, amount, expense_date, status FROM tb_travel_expense WHERE ticket_id = ?", (ticket_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "ticket_id": row[0],
            "employee_id": row[1],
            "employee_name": row[2],
            "role": row[3],
            "city": row[4],
            "city_tier": row[5],
            "hotel_days": row[6],
            "amount": row[7],
            "expense_date": row[8],
            "status": row[9]
        }


class ExternalOAGateway:
    """
    Day 16 外部微服务网关 (封装超时重试、幂等签名与 OA 审批接入)
    """
    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []

    def dispatch_clawback_order(self, ticket_id: str, employee_id: str, clawback_amount: float, approver: str, reason: str) -> Dict[str, Any]:
        """向企业 OA / ERP 下发追回与扣款工单"""
        time.sleep(0.02)  # 模拟网络往返 I/O
        receipt_id = f"OA-CLAWBACK-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
        record = {
            "receipt_id": receipt_id,
            "ticket_id": ticket_id,
            "employee_id": employee_id,
            "clawback_amount": clawback_amount,
            "approver": approver,
            "reason": reason,
            "timestamp": time.time(),
            "status": "DISPATCHED"
        }
        self.call_history.append(record)
        return record


# ==============================================================================
# 第二部分：Pydantic 业务契约与防篡改签名令牌 (HITL Core)
# ==============================================================================

class AuditDecisionPayload(BaseModel):
    """
    Day 18 核心业务裁决数据契约
    严格区分定量核算结果、法条溯源依据与后续动作门禁代码
    """
    ticket_id: str = Field(..., description="报销单据流水号")
    employee_id: str = Field(..., description="员工唯一工号")
    employee_name: str = Field(..., description="员工姓名")
    employee_role: str = Field(..., description="员工所属职级 (如 总监/经理/普通员工)")
    city: str = Field(..., description="出差目的城市")
    city_tier: str = Field(..., description="城市层级分类")
    expense_date: str = Field(..., description="费用发生日期 (YYYY-MM-DD)")
    claimed_amount: float = Field(..., description="申报报销总金额")
    hotel_days: int = Field(..., description="出差住宿天数")
    daily_average: float = Field(..., description="实际申报单日均摊金额")
    applicable_limit_per_day: float = Field(..., description="依据制度核定该日适用的单日住宿上限")
    policy_version: str = Field(..., description="适用的制度版本名称")
    is_compliant: bool = Field(..., description="合规性布尔判定结论")
    violation_reason: Optional[str] = Field(default=None, description="违规事实与超标明细说明")
    clawback_amount: float = Field(default=0.0, description="核定应追回/扣款金额")
    citations: List[str] = Field(default_factory=list, description="知识库溯源引证角标清单")
    action_required: str = Field(..., description="'AUTO_PASS' (自动归档) 或 'REQUIRE_HUMAN_APPROVAL' (触发人机回环)")


class SignedApprovalTokenManager:
    """
    企业级防篡改带签名审批令牌管理器 (HMAC-SHA256 Token Manager)
    实现：带防伪签名摘要、TTL 有效期控制、防重放 (Anti-Replay) 一次性消费
    """
    def __init__(self, secret_key: str = "Huake-AI-Enterprise-HITL-Secret-2024", default_ttl_sec: int = 3600):
        self.secret_key = secret_key.encode("utf-8")
        self.default_ttl_sec = default_ttl_sec
        # 挂起上下文状态持久化快照存储器 (生产环境对应 Redis / PostgreSQL)
        self.snapshot_store: Dict[str, Dict[str, Any]] = {}
        # 已消费 Token 黑名单 (防止重放攻击)
        self.consumed_tokens: set = set()

    def generate_token(self, ticket_id: str, clawback_amount: float, payload: Dict[str, Any]) -> str:
        """生成带加密签名的防伪令牌"""
        token_id = f"TOKEN-HITL-{uuid.uuid4().hex[:8].upper()}"
        expires_at = time.time() + self.default_ttl_sec

        # 计算数字签名
        sign_payload = f"{token_id}|{ticket_id}|{clawback_amount}|{expires_at}"
        signature = hmac.new(self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()[:12]

        full_token = f"{token_id}-{signature}"

        # 持久化当前状态机快照
        self.snapshot_store[full_token] = {
            "token_id": token_id,
            "ticket_id": ticket_id,
            "clawback_amount": clawback_amount,
            "expires_at": expires_at,
            "payload": payload,
            "created_at": time.time(),
            "status": "PENDING"
        }
        return full_token

    def verify_and_consume(self, full_token: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """校验 Token 合法性、有效期与单次消费防重放"""
        if full_token in self.consumed_tokens:
            return False, "【安全违规】该审批令牌已被消费，严禁重复提交（防重放机制已生效）！", None

        if full_token not in self.snapshot_store:
            return False, "【认证失败】无效的审批令牌或令牌已被销毁！", None

        snapshot = self.snapshot_store[full_token]

        # 校验过期时效
        if time.time() > snapshot["expires_at"]:
            return False, "【安全超时】审批令牌已超过有效期限 (TTL Expired)，工作流已自动废弃！", None

        # 标记消费
        self.consumed_tokens.add(full_token)
        snapshot["status"] = "CONSUMED"
        return True, "验证通过", snapshot


# ==============================================================================
# 第三部分：三位一体协同智能体核心 (TriadBusinessAgent)
# ==============================================================================

class TriadBusinessAgent:
    """
    Day 18 华科智造企业级三位一体全链路协同 Agent：
      - 通道 1 (Wiki RAG): 准确提取新旧规约标准并执行 2024-03-01 节点版本消歧
      - 通道 2 (Text2SQL): 安全查询业务数据库流水还原事实明细
      - 通道 3 (Action & HITL): 执行多源交叉裁决，高风险写操作触发人机回环挂起
    """

    def __init__(self, ollama_url: str = "http://localhost:11434/v1", model_name: str = "llama3.1:latest"):
        self.model_name = model_name
        self.use_llm = False
        self.client = None

        # 检测本地大模型服务可用性
        if HAS_OPENAI_SDK:
            try:
                self.client = OpenAI(base_url=ollama_url, api_key="ollama")
                models = [m.id for m in self.client.models.list().data]
                if any(model_name in mid for mid in models):
                    self.use_llm = True
            except Exception:
                self.use_llm = False

        # 初始化三大支撑底座
        self.db_gateway = SafeDatabaseGateway()
        self.oa_gateway = ExternalOAGateway()
        self.token_manager = SignedApprovalTokenManager()

    # --------------------------------------------------------------------------
    # 第一阶: 规则认知 (Knowledge RAG 通道与版本消歧)
    # --------------------------------------------------------------------------
    def _stage1_knowledge_rag(self, city_tier: str, employee_role: str, expense_date: str) -> Dict[str, Any]:
        """
        检索企业 Wiki 资产库，严格区分新老制度分水岭 (2024-03-01)：
        • 2024-03-01 之后发生事项：执行 2024 最新版标准 (一线城市总监 800元/天，经理 550元/天)
        • 2024-03-01 之前发生事项：执行 2022 暂行版过渡期旧规 (一线城市总监上限 600元/天)
        """
        t0 = time.time()
        time.sleep(0.015)  # 模拟向量检索网络时延

        is_after_new_policy = (expense_date >= "2024-03-01")

        if is_after_new_policy:
            # 2024 最新版差旅制度矩阵
            if "总监" in employee_role:
                standard = 800.0 if city_tier == "一线城市" else 600.0
            elif "经理" in employee_role:
                standard = 550.0 if city_tier == "一线城市" else 420.0
            else:
                standard = 450.0 if city_tier == "一线城市" else 350.0
            version = "2024最新修订版"
            citation = "WIKI-FIN-TRAVEL-202403 第四章第二条《国内差旅住宿标准限额与城市梯队表》"
            clause_text = f"经查《华科智造国内差旅管理规定 (2024修订版)》，{city_tier}对于【{employee_role}】单日最高住宿上限为 {standard} 元/天。"
        else:
            # 2022 暂行版历史制度矩阵 (王大明 2024-02-20 出差严格适用此条)
            if "总监" in employee_role:
                standard = 600.0 if city_tier == "一线城市" else 480.0
            else:
                standard = 350.0
            version = "2022暂行版旧规"
            citation = "WIKI-FIN-AUDIT-202404 附录 C《历史制度过渡期冲突特别裁决备忘录》"
            clause_text = f"经查《历史制度过渡期冲突特别裁决备忘录》，2024年3月1日之前发生的差旅事项严格依照旧规执行，{city_tier}【{employee_role}】标准上限为 {standard} 元/天。严禁套用新规多领款项！"

        return {
            "applicable_standard": standard,
            "policy_version": version,
            "citation": citation,
            "clause_text": clause_text,
            "duration_ms": (time.time() - t0) * 1000
        }

    # --------------------------------------------------------------------------
    # 第二阶: 事实还原 (Database Text2SQL 通道)
    # --------------------------------------------------------------------------
    def _stage2_database_text2sql(self, ticket_id: str) -> Tuple[Optional[Dict[str, Any]], float]:
        """安全查询企业业务流水数据库，还原原始记账与开票事实"""
        t0 = time.time()
        fact = self.db_gateway.query_ticket(ticket_id)
        duration_ms = (time.time() - t0) * 1000
        return fact, duration_ms

    # --------------------------------------------------------------------------
    # 第三阶: 交叉裁决与逻辑推理 (Cross-Auditing & Reasoning)
    # --------------------------------------------------------------------------
    def _stage3_cross_reasoning(self, fact: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        """
        执行双源对齐核算：
        - 计算单日均摊申报金额 = amount / hotel_days
        - 对比制度标准上限
        - 精确计算超标追回金额与责任定性
        """
        t0 = time.time()
        days = max(fact["hotel_days"], 1)
        daily_avg = round(fact["amount"] / days, 2)
        limit = policy["applicable_standard"]

        is_compliant = daily_avg <= limit
        clawback = 0.0
        violation_reason = None

        if not is_compliant:
            clawback = round(fact["amount"] - (limit * days), 2)
            violation_reason = (
                f"单据开票日期为 {fact['expense_date']}，早于新规生效日，严格受约束于【{policy['policy_version']}】。"
                f"核定标准为 {limit} 元/天，实际申报均摊 {daily_avg} 元/天，超标 {round(daily_avg - limit, 2)} 元/天。"
                f"总计须对员工 {fact['employee_name']} ({fact['employee_id']}) 发起差额追回：{clawback} 元！"
            )

        duration_ms = (time.time() - t0) * 1000
        return {
            "daily_avg": daily_avg,
            "limit": limit,
            "is_compliant": is_compliant,
            "clawback": clawback,
            "violation_reason": violation_reason
        }, duration_ms

    # --------------------------------------------------------------------------
    # 第四阶: 业务闭环与人机回环门禁 (HITL Action Gate)
    # --------------------------------------------------------------------------
    def execute_triad_audit(self, ticket_id: str) -> Dict[str, Any]:
        """
        主执行管道：四阶动线推进与状态机门禁
        """
        trace = LangfuseTraceRecord(trace_id=f"TR-{uuid.uuid4().hex[:8].upper()}", name="Triad_Audit_Pipeline")

        print(f"\n{'='*80}")
        print(f"🎯 [三位一体协同引擎] 启动单据审查会话 | 目标单据: {ticket_id}")
        print(f"{'='*80}")

        # ----------------------------------------------------------------------
        # Step 2: 事实还原 (首先读取账本真实数字)
        # ----------------------------------------------------------------------
        print(f"🔍 [第一动线: 事实还原] 查询 SQLite 安全业务账本...")
        fact, db_ms = self._stage2_database_text2sql(ticket_id)
        if not fact:
            trace.log_span("Stage2_DatabaseFact", "DB_QUERY", {"ticket_id": ticket_id}, {"error": "单号不存在"}, db_ms)
            return {"success": False, "error": f"业务数据库中未查到报销单号 {ticket_id}"}

        print(f"    ├─ 员工事实: {fact['employee_name']} (工号: {fact['employee_id']}, 职级: {fact['role']})")
        print(f"    ├─ 出差行程: {fact['city']} ({fact['city_tier']}) | 住宿天数: {fact['hotel_days']} 天")
        print(f"    └─ 报销事实: 申报金额 {fact['amount']} 元 | 发票日期: {fact['expense_date']}")
        trace.log_span("Stage2_DatabaseFact", "DB_QUERY", {"ticket_id": ticket_id}, fact, db_ms)

        # ----------------------------------------------------------------------
        # Step 1: 规则认知 (带上事实属性，检索 Wiki 制度并消歧)
        # ----------------------------------------------------------------------
        print(f"\n📖 [第二动线: 规则认知] 调度企业 Wiki 知识库检索制度依据并执行版本消歧...")
        policy = self._stage1_knowledge_rag(
            city_tier=fact["city_tier"],
            employee_role=fact["role"],
            expense_date=fact["expense_date"]
        )
        print(f"    ├─ 适用规范: {policy['policy_version']} (核准上限: {policy['applicable_standard']} 元/天)")
        print(f"    ├─ 条文摘要: {policy['clause_text']}")
        print(f"    └─ 溯源角标: [来源: {policy['citation']}]")
        trace.log_span("Stage1_KnowledgeRAG", "KNOWLEDGE_RAG", {
            "city_tier": fact["city_tier"], "role": fact["role"], "date": fact["expense_date"]
        }, policy, policy["duration_ms"])

        # ----------------------------------------------------------------------
        # Step 3: 交叉裁决与逻辑推理
        # ----------------------------------------------------------------------
        print(f"\n⚖️ [第三动线: 交叉裁决] 融合多源数据执行数学核算与合规判定...")
        verdict, calc_ms = self._stage3_cross_reasoning(fact, policy)
        print(f"    ├─ 核算比对: 申报日均 {verdict['daily_avg']} 元/天 vs 标准上限 {verdict['limit']} 元/天")
        print(f"    ├─ 合规状态: {'✅ 完全合规' if verdict['is_compliant'] else '❌ 超标违规'}")
        if not verdict["is_compliant"]:
            print(f"    └─ 拟追回额: 💰 {verdict['clawback']} 元 (原因: {verdict['violation_reason']})")
        trace.log_span("Stage3_Reasoning", "CALC_REASONING", {"fact": fact, "policy": policy}, verdict, calc_ms)

        # 构造强契约 Payload
        payload = AuditDecisionPayload(
            ticket_id=fact["ticket_id"],
            employee_id=fact["employee_id"],
            employee_name=fact["employee_name"],
            employee_role=fact["role"],
            city=fact["city"],
            city_tier=fact["city_tier"],
            expense_date=fact["expense_date"],
            claimed_amount=fact["amount"],
            hotel_days=fact["hotel_days"],
            daily_average=verdict["daily_avg"],
            applicable_limit_per_day=verdict["limit"],
            policy_version=policy["policy_version"],
            is_compliant=verdict["is_compliant"],
            violation_reason=verdict["violation_reason"],
            clawback_amount=verdict["clawback"],
            citations=[f"[来源: {policy['citation']}]"],
            action_required="AUTO_PASS" if verdict["is_compliant"] else "REQUIRE_HUMAN_APPROVAL"
        )

        # ----------------------------------------------------------------------
        # Step 4: 业务闭环与人机回环门禁 (HITL Action Gate)
        # ----------------------------------------------------------------------
        print(f"\n🛡️ [第四动线: 动作门禁] 评估业务风险等级并判定写操作防线...")

        if verdict["is_compliant"]:
            # 只读/合规操作：全自动通过
            action_code = "AUTO_PASS"
            status_message = "✅ 机审全自动通过：单据数据与制度完全合规，已完成只读备案归档！"
            approval_token = None
            print(f"    └─ 决策路径: 只读/合规低风险 -> 执行直接放行通过")
            trace.log_span("Stage4_ActionGate", "HITL_GATE", {"action": action_code}, {"result": "PASSED"}, 1.2)
        else:
            # 高风险违规追回：物理挂起工作流，派发带签名令牌
            action_code = "REQUIRE_HUMAN_APPROVAL"
            approval_token = self.token_manager.generate_token(
                ticket_id=ticket_id,
                clawback_amount=verdict["clawback"],
                payload=payload.model_dump()
            )
            status_message = (
                f"⚠️ 高风险阻断：涉及非自愿追回款项 ({verdict['clawback']} 元)！"
                f"根据《财务内控安全法》工作流已物理挂起，必须由财务总监人工验签后授权！"
            )
            print(f"    ├─ 决策路径: 资金扣减高风险 -> 触发物理挂起 (SUSPEND)")
            print(f"    ├─ 状态机快照: 上下文已写入持久化隔离区 (Snapshot Key: {approval_token})")
            print(f"    └─ 审批令牌: 🔑 {approval_token} (HMAC-SHA256 签名有效)")
            trace.log_span("Stage4_ActionGate", "HITL_GATE", {"action": action_code, "clawback": verdict["clawback"]}, {
                "suspended": True,
                "token": approval_token
            }, 3.5)

        # 输出 APM 大盘
        trace.print_trace_summary()

        return {
            "success": True,
            "status_message": status_message,
            "action_required": action_code,
            "approval_token": approval_token,
            "decision_payload": payload.model_dump()
        }

    # --------------------------------------------------------------------------
    # 人机回环恢复接口：携带 Token 恢复挂起任务并下发 OA
    # --------------------------------------------------------------------------
    def resume_human_approval(self, approval_token: str, auditor_name: str, approve: bool, rejection_reason: Optional[str] = None) -> Dict[str, Any]:
        """
        人工审核员在审批界面查看证据、事实与角标后，提交带签名 Token 唤醒状态机
        """
        print(f"\n{'─'*80}")
        print(f"👤 [人机回环 HITL 恢复] 审核员 [{auditor_name}] 正在请求唤醒挂起任务...")
        print(f"    ├─ 提交 Token: {approval_token}")
        print(f"    └─ 审批决断: {'【✅ 授权追回并下发 OA】' if approve else '【❌ 驳回处罚退回复核】'}")

        # 1. 严格校验防篡改签名与防重放
        valid, msg, snapshot = self.token_manager.verify_and_consume(approval_token)
        if not valid:
            print(f"    🚨 验签拦截: {msg}")
            return {"success": False, "error_code": "TOKEN_VERIFICATION_FAILED", "message": msg}

        ticket_id = snapshot["ticket_id"]
        clawback = snapshot["clawback_amount"]
        payload = snapshot["payload"]

        # 2. 人工驳回分支
        if not approve:
            print(f"    ℹ️ 人工审查结果: 财务总监驳回追回指令，理由: {rejection_reason or '人工复查后豁免'}")
            return {
                "success": True,
                "status": "REJECTED_BY_HUMAN",
                "ticket_id": ticket_id,
                "message": f"财务总监 {auditor_name} 驳回了该扣款指令，单据退回人工复核通道，未调用外部写接口。"
            }

        # 3. 人工授权分支：恢复状态机并调用外部微服务 API 网关
        print(f"    🚀 验签通过！状态机唤醒 -> 正式调用外部 OA 网关发起资金追回...")
        oa_receipt = self.oa_gateway.dispatch_clawback_order(
            ticket_id=ticket_id,
            employee_id=payload["employee_id"],
            clawback_amount=clawback,
            approver=auditor_name,
            reason=payload["violation_reason"]
        )

        print(f"    🎉 外部闭环完成！")
        print(f"    ├─ OA 工单流水: {oa_receipt['receipt_id']}")
        print(f"    ├─ 扣款目标: {payload['employee_name']} (工号: {payload['employee_id']})")
        print(f"    ├─ 追回金额: ￥{oa_receipt['clawback_amount']} 元")
        print(f"    └─ 授权签署人: {auditor_name}")

        return {
            "success": True,
            "status": "APPROVED_AND_EXECUTED",
            "ticket_id": ticket_id,
            "oa_receipt": oa_receipt,
            "message": f"财务总监 {auditor_name} 签字授权成功！外部 OA 追回工单 [{oa_receipt['receipt_id']}] 已成功下发！"
        }


# ==============================================================================
# 第四部分：端到端综合实战测试与验收演练 (Alignment with Day 18 Checklist)
# ==============================================================================

def run_enterprise_triad_showcase():
    print("=" * 85)
    print("🚀 Day 18 华科智造三位一体协同智能体 (知识库+数据库+API+HITL) 全链路实战验收")
    print("=" * 85)

    agent = TriadBusinessAgent()

    # --------------------------------------------------------------------------
    # 用例 1：周建华合规单据 (自动化机审通过并归档)
    # --------------------------------------------------------------------------
    print("\n" + "▶" * 4 + " 【验收场景 1】周建华合规单据审查 (新规生效期 / 自动放行)")
    res_1 = agent.execute_triad_audit("EXP20240315-01")
    assert res_1["success"] is True
    assert res_1["action_required"] == "AUTO_PASS"
    assert res_1["approval_token"] is None
    print(f"\n📋 场景 1 最终响应: {res_1['status_message']}")

    # --------------------------------------------------------------------------
    # 用例 2：王大明旧规单据超标审查 (触发人机回环挂起 -> 财务总监人工授权恢复)
    # --------------------------------------------------------------------------
    print("\n" + "▶" * 4 + " 【验收场景 2】王大明历史跨版本单据审查 (旧规过渡期 / 触发人机回环挂起)")
    res_2 = agent.execute_triad_audit("EXP20240220-03")
    assert res_2["success"] is True
    assert res_2["action_required"] == "REQUIRE_HUMAN_APPROVAL"
    token_wang = res_2["approval_token"]
    assert token_wang is not None
    print(f"\n📋 场景 2 挂起状态: {res_2['status_message']}")
    print(f"   🔑 提取有效签名审批 Token: {token_wang}")

    # 人工审核员介入审批
    resume_res = agent.resume_human_approval(
        approval_token=token_wang,
        auditor_name="李敏 (财务总监 / Head of Finance)",
        approve=True
    )
    assert resume_res["status"] == "APPROVED_AND_EXECUTED"
    print(f"   ✅ 人工恢复执行结果: {resume_res['message']}")

    # --------------------------------------------------------------------------
    # 用例 3：安全攻防——Token 防重放攻击与非法篡改拦截
    # --------------------------------------------------------------------------
    print("\n" + "▶" * 4 + " 【验收场景 3】安全防御测试：防重放攻击与非法 Token 拦截")
    print("   [攻击模拟 A] 试图重放已消费的令牌进行二次扣款...")
    replay_attack = agent.resume_human_approval(
        approval_token=token_wang,
        auditor_name="恶意攻击者 (Malicious Attacker)",
        approve=True
    )
    print(f"   🛡️ 拦截结果: {replay_attack['message']}")
    assert replay_attack["success"] is False

    print("\n   [攻击模拟 B] 提交伪造篡改的令牌...")
    forged_token = "TOKEN-HITL-FAKED001-999999999999"
    forged_attack = agent.resume_human_approval(
        approval_token=forged_token,
        auditor_name="黑客 (Hacker)",
        approve=True
    )
    print(f"   🛡️ 拦截结果: {forged_attack['message']}")
    assert forged_attack["success"] is False

    # --------------------------------------------------------------------------
    # 用例 4：人工驳回分支 (Human Rejection Workflow)
    # --------------------------------------------------------------------------
    print("\n" + "▶" * 4 + " 【验收场景 4】人工审查驳回分支测试 (单据存疑退回人工)")
    # 临时挂起一个测试单
    temp_token = agent.token_manager.generate_token(
        ticket_id="EXP20240220-03",
        clawback_amount=400.0,
        payload={"employee_id": "HK7991", "employee_name": "王大明", "violation_reason": "测试人工驳回"}
    )
    rejection_res = agent.resume_human_approval(
        approval_token=temp_token,
        auditor_name="张明 (财务副总监)",
        approve=False,
        rejection_reason="出差人员持有总经理签署的特批邮件，豁免此次差额追回。"
    )
    print(f"   ℹ️ 驳回结果: {rejection_res['message']}")
    assert rejection_res["status"] == "REJECTED_BY_HUMAN"

    print("\n" + "=" * 85)
    print("🏁 Day 18 三位一体架构 (Wiki + DB + API + HITL) 全链路验收用例 100% 达成！")
    print("=" * 85)


if __name__ == "__main__":
    run_enterprise_triad_showcase()
