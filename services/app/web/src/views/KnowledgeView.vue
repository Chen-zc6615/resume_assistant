<template>
  <div class="flex h-[calc(100vh-4rem)] -m-6 gap-3">
    <!-- ────────── 左栏：会话（=任务）列表 ────────── -->
    <aside class="w-56 shrink-0 bg-white rounded-xl border border-slate-200 flex flex-col overflow-hidden">
      <div class="flex items-center justify-between px-3 py-2.5 border-b border-slate-100 shrink-0">
        <span class="text-xs font-semibold text-slate-600">对话</span>
        <el-button text size="small" :disabled="sending" @click="newSession">
          <el-icon :size="13"><Plus /></el-icon>&nbsp;新建
        </el-button>
      </div>
      <div class="flex-1 overflow-y-auto chat-scroll p-2 space-y-0.5">
        <div
          v-for="task in tasks" :key="task.task_id"
          class="group flex items-center gap-1 rounded-lg transition-colors"
          :class="task.task_id === taskId ? 'bg-indigo-50' : 'hover:bg-slate-50'"
        >
          <router-link
            :to="`/knowledge/${task.task_id}`"
            class="flex-1 min-w-0 block px-2.5 py-2"
          >
            <div class="text-[13px] text-slate-700 truncate">{{ task.title }}</div>
            <div class="text-[10px] text-slate-400 mt-0.5">{{ formatTime(task.updated_at) }}</div>
          </router-link>
          <el-icon
            class="mr-1.5 text-slate-300 hover:text-red-400 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
            :size="13"
            @click="removeSession(task)"
          ><Delete /></el-icon>
        </div>
        <div v-if="!tasks.length" class="px-3 py-6 text-center text-xs text-slate-400">
          还没有对话，右上有「新建」
        </div>
      </div>
    </aside>

    <!-- ────────── 中栏：消息区 + 输入区 ────────── -->
    <main class="flex-1 min-w-0 flex flex-col min-h-0">
      <section
        ref="scrollRef"
        class="flex-1 overflow-y-auto chat-scroll px-5 py-5 relative"
        @scroll="onScroll"
      >
        <!-- 空态：示例问题按四通道分组（文案与后端意图金标集一致） -->
        <div v-if="!loading && detail && !detail.messages.length" class="max-w-2xl mx-auto pt-6">
          <div class="text-center mb-6">
            <div class="w-12 h-12 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center mx-auto">
              <el-icon :size="24"><ChatDotRound /></el-icon>
            </div>
            <h2 class="mt-3 text-base font-semibold text-slate-800">简历筛选助手</h2>
            <p class="mt-1 text-xs text-slate-400">查询数据、检索人才画像、评估人岗匹配并生成待审批的邀约建议</p>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div v-for="group in sampleGroups" :key="group.title" class="rounded-xl border border-slate-200 bg-white p-3.5">
              <div class="flex items-center gap-2 mb-2">
                <span class="w-7 h-7 rounded-lg flex items-center justify-center text-sm" :class="group.iconBg">{{ group.icon }}</span>
                <span class="text-[13px] font-semibold text-slate-700">{{ group.title }}</span>
              </div>
              <button
                v-for="item in group.items" :key="item" type="button"
                class="block w-full text-left text-xs text-slate-500 hover:text-indigo-600 hover:bg-indigo-50/50 rounded-md px-2 py-1.5 -mx-2 transition-colors"
                :disabled="sending"
                @click="askSample(item)"
              >{{ item }}</button>
            </div>
          </div>
        </div>

        <!-- 消息流 -->
        <TransitionGroup v-if="detail" name="message">
          <div v-for="message in detail.messages" :key="message.message_id" class="mb-4">
            <!-- ▸ 用户问题 -->
            <div v-if="message.role === 'user'" class="flex justify-end">
              <div class="flex flex-col items-end max-w-[80%]">
                <div class="bg-indigo-600 text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                  {{ message.content }}
                </div>
              </div>
            </div>

            <!-- ▸ 助手回答 -->
            <div v-else class="flex justify-start gap-3">
              <span class="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center shrink-0 mt-0.5 text-slate-400">
                <el-icon :size="13"><ChatDotRound /></el-icon>
              </span>
              <div class="flex-1 min-w-0 max-w-[85%]">
                <div
                  class="rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed border"
                  :class="message.intent === 'refuse'
                    ? 'bg-amber-50 border-amber-200 text-amber-800'
                    : 'bg-white border-slate-100 text-slate-700'"
                >
                  <!-- 拒答态 -->
                  <div v-if="message.intent === 'refuse'" class="flex items-center gap-1.5 mb-2">
                    <el-icon :size="13"><WarningFilled /></el-icon>
                    <span class="text-xs font-medium">该问题超出助手能力范围</span>
                  </div>

                  <!-- 意图徽标 + 判定依据 -->
                  <div
                    v-if="intentOf(message) && !isStreaming(message)"
                    class="flex items-center gap-1.5 mb-2 flex-wrap"
                  >
                    <span class="text-[10px] px-1.5 py-0.5 rounded font-medium" :class="intentCls(intentOf(message))">
                      {{ intentLabel(intentOf(message)) }}
                    </span>
                    <span v-if="reasonOf(message)" class="text-[10px] text-slate-400">{{ reasonOf(message) }}</span>
                  </div>

                  <!-- 答案正文 -->
                  <div>
                    <span
                      v-if="isStreaming(message) && !message.content && !liveSteps.length"
                      class="inline-flex items-center gap-1 text-slate-400"
                    >
                      <span class="w-1.5 h-1.5 rounded-full bg-indigo-300 dot-anim" />
                      <span class="w-1.5 h-1.5 rounded-full bg-indigo-300 dot-anim" />
                      <span class="w-1.5 h-1.5 rounded-full bg-indigo-300 dot-anim" />
                      <span class="ml-1 text-xs">识别意图中…</span>
                    </span>
                    <span v-if="isStreaming(message)" class="whitespace-pre-wrap">{{ message.content }}<span
                      class="inline-block w-0.5 h-[1.1em] ml-px align-text-bottom bg-indigo-400 rounded-sm animate-pulse"
                    /></span>
                    <div v-else class="[&_strong]:text-slate-900 [&_div]:my-1" v-html="renderMd(message.content)" />
                  </div>

                  <!-- 执行链路：流式期间实时步骤；完成后渲染落库 tool_traces -->
                  <div v-if="chainOf(message).length" class="mt-3 pt-2.5 border-t border-slate-100">
                    <div class="text-[11px] text-slate-400 mb-1.5">执行链路</div>
                    <div v-for="(step, j) in chainOf(message)" :key="j" class="mb-1.5">
                      <div class="flex items-center gap-1.5 text-[11px] flex-wrap">
                        <span
                          class="w-1.5 h-1.5 rounded-full"
                          :class="step.success === true ? 'bg-emerald-400' : step.success === false ? 'bg-red-400' : 'bg-indigo-300 animate-pulse'"
                        />
                        <code class="bg-slate-50 border border-slate-200 rounded-md px-2 py-0.5 text-slate-600">
                          {{ toolLabel(step.tool) }}
                        </code>
                        <span v-if="step.purpose" class="text-slate-400 truncate max-w-[280px]">{{ step.purpose }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- 数据来源 chips（知识库切片 / 数据库表） -->
                  <div v-if="!isStreaming(message) && sourcesOf(message).length" class="mt-3 pt-2.5 border-t border-slate-100">
                    <div class="text-[11px] text-slate-400 mb-1.5">数据来源（{{ sourcesOf(message).length }}）</div>
                    <div class="flex flex-wrap gap-1.5">
                      <el-tooltip v-for="source in sourcesOf(message)" :key="source" :content="`查看：${source}`" placement="top">
                        <span
                          class="inline-flex items-center gap-1 text-[11px] bg-slate-50 border border-slate-200 rounded-md px-2 py-0.5 text-slate-500 hover:border-indigo-200 hover:text-indigo-600 cursor-pointer transition-colors"
                          @click="openSource(message, source)"
                        >
                          <el-icon :size="11"><Link /></el-icon>
                          {{ source }}
                        </span>
                      </el-tooltip>
                    </div>
                  </div>

                  <!-- 待审批确认卡（按时间归属挂在本条回答下方） -->
                  <div
                    v-for="action in actionsFor(message)" :key="action.action_id"
                    class="mt-3 rounded-xl border p-3"
                    :class="action.status === 'pending' ? 'border-violet-200 bg-violet-50/50' : 'border-slate-200 bg-slate-50/50'"
                  >
                    <div class="flex items-center gap-1.5 text-xs font-medium mb-1.5" :class="action.status === 'pending' ? 'text-violet-700' : 'text-slate-500'">
                      <el-icon :size="14"><Bell /></el-icon>
                      <span>{{ action.status === 'pending' ? '待确认操作（执行后系统将重新核对简历与岗位规则）' : '操作审批记录' }}</span>
                    </div>
                    <p class="text-xs text-slate-700">
                      面试邀约：{{ action.payload.candidate_name || `简历 #${action.payload.resume_id}` }}
                      · {{ action.payload.job_name || `岗位 #${action.payload.job_id}` }}
                    </p>
                    <div class="flex items-center justify-between mt-2">
                      <el-tag :type="actionTag(action.status)" size="small">{{ actionLabel(action.status) }}</el-tag>
                      <div v-if="action.status === 'pending'" class="flex gap-2">
                        <el-button size="small" type="primary" :loading="decidingId === action.action_id" @click="approve(action)">批准邀约</el-button>
                        <el-button size="small" :loading="decidingId === action.action_id" @click="reject(action)">驳回</el-button>
                      </div>
                    </div>
                    <p v-if="action.decision_reason" class="text-[10px] text-slate-400 mt-2">
                      审批说明：{{ action.decision_reason }}
                    </p>
                  </div>

                  <!-- 尾注：工具调用统计 -->
                  <div v-if="!isStreaming(message) && metricCount(message, 'tool_calls')" class="mt-2 text-[10px] text-slate-400">
                    工具调用 {{ metricCount(message, 'tool_calls') }} 次 · 成功 {{ metricCount(message, 'successful_tools') }} 次
                  </div>
                </div>
              </div>
            </div>
          </div>
        </TransitionGroup>

        <!-- 回到底部 -->
        <button
          v-show="showJump" type="button"
          class="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-1.5 rounded-full bg-white border border-slate-200 shadow-md text-xs text-slate-500 hover:text-slate-700 hover:shadow-lg transition-all z-10"
          @click="scrollToBottom(true)"
        >↓ 回到底部</button>
      </section>

      <!-- 输入区 -->
      <section class="mt-3 shrink-0 bg-white rounded-xl border border-slate-200 shadow-sm p-3
                      transition-shadow focus-within:shadow-md focus-within:border-indigo-300">
        <textarea
          v-model="draft" rows="2" maxlength="2000"
          class="w-full text-sm bg-transparent border-0 outline-none resize-none placeholder:text-slate-300 text-slate-700 p-1 leading-relaxed"
          placeholder="输入问题或指令…（Enter 发送，Shift+Enter 换行）"
          :disabled="sending"
          @keydown.enter.exact.prevent="onEnterKey"
        />
        <div class="flex items-center justify-between mt-1">
          <span class="text-[11px] text-slate-400">筛选结论由确定性规则产生，邀约需 HR 确认</span>
          <el-button type="primary" class="!rounded-lg" :loading="sending" size="small" @click="ask">
            <span v-if="!sending" class="flex items-center gap-1.5">
              <el-icon :size="13"><Promotion /></el-icon>发送
            </span>
            <span v-else>生成中…</span>
          </el-button>
        </div>
      </section>
    </main>

    <!-- ────────── 右：检索切片抽屉 ────────── -->
    <el-drawer v-model="drawerOpen" :title="drawerTitle" size="480px" direction="rtl">
      <div class="space-y-3">
        <div
          v-for="(chunk, index) in drawerChunks" :key="index"
          class="rounded-xl border border-slate-200 bg-white p-3 text-[13px] text-slate-700 leading-relaxed whitespace-pre-wrap"
        >{{ chunk }}</div>
        <div v-if="!drawerChunks.length" class="py-8 text-center text-xs text-slate-400">该来源没有可展示的切片内容</div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ChatDotRound, Delete, Link, Plus, Promotion, WarningFilled } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import {
  createTask, decideTaskAction, deleteTask, getTask, listTasks, sendTaskMessageStream,
} from '../api'
import { toast } from '../components/toast'
import { intentCls, intentLabel, toolLabel } from '../utils/agent'
import type { Task, TaskAction, TaskDetail, TaskMessage } from '../types'

const route = useRoute()
const router = useRouter()

const tasks = ref<Task[]>([])
const detail = ref<TaskDetail | null>(null)
const loading = ref(false)
const sending = ref(false)
const draft = ref('')
const decidingId = ref<number | null>(null)
const scrollRef = ref<HTMLElement | null>(null)
const atBottom = ref(true)
const showJump = ref(false)

/** 流式期间由 SSE intent/tool 事件驱动的实时态（完成后改读落库消息字段） */
const liveIntent = ref<string | null>(null)
const liveSteps = ref<{ tool: string; success: boolean }[]>([])

const drawerOpen = ref(false)
const drawerTitle = ref('')
const drawerChunks = ref<string[]>([])

const taskId = computed(() => {
  const id = Number(route.params.taskId)
  return Number.isFinite(id) && id > 0 ? id : null
})

// ---- 会话（任务）列表 ----

async function loadTasks() {
  try {
    tasks.value = await listTasks()
  } catch {
    /* 左栏加载失败不阻塞消息区 */
  }
}

async function newSession() {
  try {
    const task = await createTask()
    await loadTasks()
    router.replace(`/knowledge/${task.task_id}`)
  } catch (error: any) {
    toast(error.friendly || '新建对话失败', 'error')
  }
}

async function removeSession(task: Task) {
  await ElMessageBox.confirm(`删除对话「${task.title}」？消息与审批记录将一并删除。`, '删除对话', { type: 'warning' })
  try {
    await deleteTask(task.task_id)
    tasks.value = tasks.value.filter((t) => t.task_id !== task.task_id)
    if (task.task_id === taskId.value) {
      const next = tasks.value[0]
      router.replace(next ? `/knowledge/${next.task_id}` : '/knowledge')
    }
  } catch (error: any) {
    toast(error.friendly || '删除失败', 'error')
  }
}

async function loadDetail() {
  if (!taskId.value) {
    detail.value = null
    return
  }
  loading.value = true
  try {
    detail.value = await getTask(taskId.value)
  } catch (error: any) {
    detail.value = null
    toast(error.friendly || '对话加载失败', 'error')
  } finally {
    loading.value = false
    scrollToBottom(true)
  }
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  const today = new Date()
  return d.toDateString() === today.toDateString()
    ? d.toTimeString().slice(0, 5)
    : `${d.getMonth() + 1}/${d.getDate()}`
}

// ---- 消息渲染辅助 ----

function isStreaming(message: TaskMessage): boolean {
  return sending.value && message.message_id < 0
}

function intentOf(message: TaskMessage): string | null {
  if (isStreaming(message)) return liveIntent.value
  return message.intent ?? null
}

function reasonOf(message: TaskMessage): string {
  if (isStreaming(message)) return ''
  return String(message.metrics?.intent_reason ?? '')
}

function metricCount(message: TaskMessage, key: string): number {
  return Number(message.metrics?.[key] ?? 0)
}

interface ChainStep {
  tool: string
  success: boolean | null  // null = 执行中（仅流式期间出现）
  purpose?: string
}

/** 执行链路：流式期间用实时事件（tool 事件），完成后用落库 tool_traces */
function chainOf(message: TaskMessage): ChainStep[] {
  if (isStreaming(message)) return liveSteps.value
  return (message.tool_traces ?? []).map((trace) => ({
    tool: trace.tool,
    success: trace.success,
    purpose: String(trace.arguments?.purpose ?? trace.arguments?.query ?? ''),
  }))
}

/** 数据来源 chips：从工具结果里的 sources 数组去重 */
function sourcesOf(message: TaskMessage): string[] {
  const set = new Set<string>()
  for (const trace of message.tool_traces ?? []) {
    const sources = (trace.result as any)?.sources
    if (Array.isArray(sources)) sources.forEach((s: unknown) => set.add(String(s)))
  }
  return [...set]
}

/** 打开切片抽屉：定位该来源对应的工具结果，展示检索切片内容（零新端点） */
function openSource(message: TaskMessage, source: string) {
  const chunks: string[] = []
  for (const trace of message.tool_traces ?? []) {
    const result = trace.result as any
    const sources: unknown[] = Array.isArray(result?.sources) ? result.sources : []
    const rows: any[] = Array.isArray(result?.results) ? result.results : []
    if (sources.includes(source)) {
      rows.forEach((row) => {
        const text = row?.content ?? row?.text
        if (text) chunks.push(String(text))
      })
    }
  }
  drawerTitle.value = source
  drawerChunks.value = chunks
  drawerOpen.value = true
}

/** 审批卡归属：挂在「触发它的那条回答」下方——created_at 落在本条回答与其后第一条消息之间 */
function actionsFor(message: TaskMessage): TaskAction[] {
  const current = detail.value
  if (!current || message.role !== 'assistant' || isStreaming(message)) return []
  const messages = current.messages
  const index = messages.indexOf(message)
  const nextBound = messages[index + 1]?.created_at ?? '￿'
  return current.actions.filter(
    (a) => a.created_at >= message.created_at && a.created_at < nextBound,
  )
}

// ---- 发送流 ----

/** 示例问题按四通道分组（文案与 services/app/evals/agent_intents/golden.jsonl 判例一致） */
const sampleGroups = [
  { title: '候选人画像', icon: '💬', iconBg: 'bg-emerald-100 text-emerald-600',
    items: ['张三做过哪些项目？', '哪几位候选人有 B 端产品经验？'] },
  { title: '数据查询', icon: '🗄', iconBg: 'bg-blue-100 text-blue-600',
    items: ['现在有多少份待审核简历？', '各初筛状态的简历分别有多少份？'] },
  { title: '业务操作', icon: '⚡', iconBg: 'bg-violet-100 text-violet-600',
    items: ['如果匹配就帮李雷发面试邀约', '李雷和高级后端工程师岗位匹配吗？'] },
  { title: '能力边界', icon: '🚧', iconBg: 'bg-slate-100 text-slate-500',
    items: ['你能做什么？', '今天天气怎么样？'] },
]

function askSample(item: string) {
  draft.value = item
  void ask()
}

async function ask() {
  const q = draft.value.trim()
  if (!q || sending.value) return
  let current = detail.value

  // 无任务时空态首问：先建任务再发（不预建空任务）
  if (!current) {
    try {
      const task = await createTask()
      await loadTasks()
      current = { ...task, messages: [], actions: [] }
      detail.value = current
    } catch (error: any) {
      toast(error.friendly || '创建对话失败', 'error')
      return
    }
  }

  sending.value = true
  draft.value = ''
  liveIntent.value = null
  liveSteps.value = []

  const optimisticUser: TaskMessage = {
    message_id: -Date.now(), task_id: current.task_id, role: 'user',
    content: q, tool_traces: [], created_at: new Date().toISOString(),
  }
  const optimisticAssistant: TaskMessage = {
    message_id: -Date.now() - 1, task_id: current.task_id, role: 'assistant',
    content: '', tool_traces: [], created_at: new Date().toISOString(),
  }
  current.messages.push(optimisticUser, optimisticAssistant)
  scrollToBottom()

  try {
    const response = await sendTaskMessageStream(current.task_id, q, (event) => {
      if (event.type === 'intent' && event.intent) {
        liveIntent.value = event.intent
      } else if (event.type === 'tool' && event.name) {
        liveSteps.value.push({ tool: event.name, success: event.success ?? true })
        scrollToBottom()
      } else if (event.type === 'delta' && event.text) {
        optimisticAssistant.content += event.text
        scrollToBottom()
      }
    })
    const start = current.messages.indexOf(optimisticUser)
    if (start >= 0) current.messages.splice(start, 2, response.user_message, response.assistant_message)
    current.actions.push(...response.new_actions)
    if (current.title === '新任务') {
      current.title = q.slice(0, 120)
      void loadTasks()
    }
    // 无参路由首问后落地址，刷新可直达恢复
    if (!taskId.value) router.replace(`/knowledge/${current.task_id}`)
  } catch (error: any) {
    const start = current.messages.indexOf(optimisticUser)
    if (start >= 0) current.messages.splice(start, 2)
    draft.value = q
    toast(error.friendly || '任务执行失败，请稍后重试', 'error')
  } finally {
    sending.value = false
    liveIntent.value = null
    liveSteps.value = []
  }
}

function onEnterKey(event: KeyboardEvent) {
  // 中文输入法选词回车（isComposing）不触发发送
  if (event.isComposing) return
  void ask()
}

// ---- 审批 ----

async function approve(action: TaskAction) {
  const current = detail.value
  if (!current) return
  await ElMessageBox.confirm('确认创建这条面试邀约？系统会在提交前重新核对简历和岗位规则。', '批准邀约', { type: 'warning' })
  decidingId.value = action.action_id
  try {
    const updated = await decideTaskAction(current.task_id, action.action_id, true)
    replaceAction(updated)
    toast('面试邀约已创建', 'success')
  } catch (error: any) {
    toast(error.friendly || '审批失败', 'error')
  } finally {
    decidingId.value = null
  }
}

async function reject(action: TaskAction) {
  const current = detail.value
  if (!current) return
  const { value } = await ElMessageBox.prompt('请填写驳回原因', '驳回邀约', {
    inputValidator: (text) => Boolean(text?.trim()) || '驳回原因不能为空',
  })
  decidingId.value = action.action_id
  try {
    const updated = await decideTaskAction(current.task_id, action.action_id, false, value.trim())
    replaceAction(updated)
    toast('已驳回邀约', 'info')
  } catch (error: any) {
    toast(error.friendly || '驳回失败', 'error')
  } finally {
    decidingId.value = null
  }
}

function replaceAction(updated: TaskAction) {
  if (!detail.value) return
  const index = detail.value.actions.findIndex((item) => item.action_id === updated.action_id)
  if (index >= 0) detail.value.actions[index] = updated
}

function actionLabel(status: TaskAction['status']) {
  return ({ pending: '待审批', approved: '已批准', rejected: '已驳回', executed: '已执行', failed: '执行失败' })[status]
}

function actionTag(status: TaskAction['status']) {
  if (status === 'executed') return 'success'
  if (status === 'rejected' || status === 'failed') return 'danger'
  if (status === 'pending') return 'warning'
  return 'info'
}

// ---- 滚动 ----

function scrollToBottom(force = false) {
  nextTick(() => {
    const el = scrollRef.value
    if (el && (force || atBottom.value)) el.scrollTop = el.scrollHeight
  })
}

function onScroll() {
  const el = scrollRef.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  showJump.value = el.scrollHeight - el.scrollTop - el.clientHeight > 200
}

// ---- 轻量 markdown 渲染（先转义防 XSS）：**加粗** / # 标题 / - 列表 / 换行 ----

function renderMd(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc
    .replace(/^### (.+)$/gm, '<div class="font-semibold text-slate-800 mt-2">$1</div>')
    .replace(/^## (.+)$/gm, '<div class="font-semibold text-slate-900 mt-2">$1</div>')
    .replace(/^# (.+)$/gm, '<div class="font-semibold text-slate-900 mt-2">$1</div>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<div class="pl-4">• $1</div>')
    .replace(/\n/g, '<br>')
}

// ---- 生命周期 ----

onMounted(async () => {
  await loadTasks()
  if (!taskId.value && tasks.value.length) {
    router.replace(`/knowledge/${tasks.value[0].task_id}`)
    return
  }
  void loadDetail()
})

watch(taskId, () => void loadDetail())
</script>

<style scoped>
/* 消息入场（keyframes 放非 scoped 块避免作用域改名） */
.message-enter-active {
  animation: msg-in 0.28s ease-out both;
}
</style>

<style>
@keyframes msg-in {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 打字指示器 */
@keyframes dot-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
  30% { transform: translateY(-4px); opacity: 1; }
}
.dot-anim { animation: dot-bounce 1.6s ease-in-out infinite; }
.dot-anim:nth-child(2) { animation-delay: 0.2s; }
.dot-anim:nth-child(3) { animation-delay: 0.4s; }
</style>
