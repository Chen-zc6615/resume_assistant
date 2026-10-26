/**
 * Agent 展示层共享模块：意图徽标、工具中文名、审批状态标签。
 * /knowledge 聊天页与 TaskConversation(/tasks)共用，保证两处口径一致。
 * 意图值与后端 AgentIntent 枚举一一对应（kb/sql/action/refuse）。
 */

export const INTENT_META: Record<string, { label: string; cls: string }> = {
  kb: { label: '知识库问答', cls: 'bg-emerald-50 text-emerald-600' },
  sql: { label: '数据查询', cls: 'bg-blue-50 text-blue-600' },
  action: { label: '业务操作', cls: 'bg-violet-50 text-violet-600' },
  refuse: { label: '超出范围', cls: 'bg-slate-100 text-slate-500' },
}

export const intentLabel = (intent?: string | null): string =>
  INTENT_META[intent ?? '']?.label ?? intent ?? ''

export const intentCls = (intent?: string | null): string =>
  INTENT_META[intent ?? '']?.cls ?? 'bg-slate-100 text-slate-500'

/** 后端真实工具集（agent_service.AGENT_TOOLS），旧页遗留死映射已清理 */
export const TOOL_LABELS: Record<string, string> = {
  query_recruitment_database: '招聘数据库查询',
  search_talent_knowledge: '人才知识库检索',
  evaluate_candidate_for_job: '人岗匹配评估',
}

export const toolLabel = (tool: string): string => TOOL_LABELS[tool] ?? tool

/** AgentAction 审批五态（与后端状态机一致） */
export const ACTION_STATUS_META: Record<string, { label: string; tag: 'warning' | 'info' | 'danger' | 'success' }> = {
  pending: { label: '待审批', tag: 'warning' },
  approved: { label: '已批准', tag: 'info' },
  rejected: { label: '已驳回', tag: 'danger' },
  executed: { label: '已执行', tag: 'success' },
  failed: { label: '执行失败', tag: 'danger' },
}

export const actionStatusLabel = (status: string): string =>
  ACTION_STATUS_META[status]?.label ?? status
