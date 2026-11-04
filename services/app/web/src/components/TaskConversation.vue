<template>
  <div>
    <div v-if="loading" class="py-12 flex justify-center">
      <el-icon class="is-loading text-ink-400" :size="22"><Loading /></el-icon>
    </div>
    <template v-else-if="detail">
      <div ref="messageArea" class="max-h-[480px] overflow-y-auto px-5 py-4">
        <div v-for="message in detail.messages" :key="message.message_id" class="mb-5">
          <div class="flex gap-3" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
            <div
              class="max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-6 whitespace-pre-wrap"
              :class="message.role === 'user'
                ? 'bg-brand-500 text-white rounded-br-md'
                : 'bg-hairline-soft text-ink-700 rounded-bl-md'"
            >{{ message.content }}</div>
          </div>
          <details v-if="message.role === 'assistant' && message.tool_traces.length" class="mt-2 ml-1">
            <summary class="cursor-pointer text-xs text-ink-400 hover:text-ink-600">
              查看 {{ message.tool_traces.length }} 次工具调用
            </summary>
            <div class="mt-2 space-y-2">
              <div
                v-for="(trace, index) in message.tool_traces"
                :key="`${message.message_id}-${index}`"
                class="text-xs border border-hairline rounded-lg px-3 py-2 bg-card"
              >
                <span :class="trace.success ? 'text-good' : 'text-critical'">
                  {{ trace.success ? '成功' : '失败' }}
                </span>
                <span class="ml-2 font-medium text-ink-700">{{ toolLabel(trace.tool) }}</span>
              </div>
            </div>
          </details>
        </div>

        <div v-for="action in detail.actions" :key="action.action_id" class="mb-4">
          <div
            class="border rounded-xl p-4"
            :class="action.status === 'pending' ? 'border-warn/40 bg-warn-soft' : 'border-hairline bg-page'"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-ink-900">面试邀约待确认</div>
                <div class="text-xs text-ink-600 mt-1">
                  {{ action.payload.candidate_name || `简历 #${action.payload.resume_id}` }}
                  · {{ action.payload.job_name || `岗位 #${action.payload.job_id}` }}
                </div>
              </div>
              <el-tag :type="actionTag(action.status)" size="small">{{ actionLabel(action.status) }}</el-tag>
            </div>
            <div v-if="action.status === 'pending'" class="mt-3 flex gap-2">
              <el-button
                size="small" type="primary"
                :loading="decidingId === action.action_id"
                @click="approve(action)"
              >批准邀约</el-button>
              <el-button
                size="small"
                :loading="decidingId === action.action_id"
                @click="reject(action)"
              >驳回</el-button>
            </div>
            <div v-if="action.decision_reason" class="mt-2 text-xs text-ink-500">
              说明：{{ action.decision_reason }}
            </div>
          </div>
        </div>

        <div v-if="!detail.messages.length" class="py-8 text-center text-sm text-ink-400">
          还没有对话，在下方输入任务内容
        </div>
      </div>

      <div class="border-t border-hairline p-4 bg-card">
        <el-input
          v-model="draft"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          resize="none"
          maxlength="2000"
          show-word-limit
          placeholder="输入任务内容，Enter 发送，Shift + Enter 换行"
          @keydown="onKeydown"
        />
        <div class="mt-2 flex items-center justify-between">
          <span class="text-[11px] text-ink-400">筛选结论由确定性规则产生，邀约需 HR 确认</span>
          <el-button
            type="primary" :icon="Promotion"
            :loading="sending" :disabled="!draft.trim()"
            @click="send"
          >发送</el-button>
        </div>
      </div>
    </template>
    <div v-else class="py-12 text-center text-sm text-ink-400">任务不存在或已删除</div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { Loading, Promotion } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import {
  decideTaskAction, getTask, sendTaskMessageStream,
} from '../api'
import { toast } from './toast'
import { toolLabel } from '../utils/agent'
import type { TaskAction, TaskDetail, TaskMessage } from '../types'

const props = defineProps<{ taskId: number }>()
const emit = defineEmits<{
  /** 详情就绪 / 变化（标题、待审批数）时通知父级同步展示 */
  (e: 'sync', payload: { title: string; pendingCount: number }): void
}>()

const detail = ref<TaskDetail | null>(null)
const loading = ref(false)
const draft = ref('')
const sending = ref(false)
const decidingId = ref<number | null>(null)
const messageArea = ref<HTMLElement | null>(null)

async function load() {
  loading.value = true
  try {
    detail.value = await getTask(props.taskId)
    emitSync()
  } catch (error: any) {
    detail.value = null
    toast(error.friendly || '任务详情加载失败', 'error')
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

function emitSync() {
  if (!detail.value) return
  emit('sync', {
    title: detail.value.title,
    pendingCount: detail.value.actions.filter((a) => a.status === 'pending').length,
  })
}

async function send() {
  const current = detail.value
  if (!current || !draft.value.trim() || sending.value) return
  const message = draft.value.trim()
  draft.value = ''
  sending.value = true

  const taskId = current.task_id
  const optimisticUser: TaskMessage = {
    message_id: -Date.now(), task_id: taskId, role: 'user',
    content: message, tool_traces: [], created_at: new Date().toISOString(),
  }
  const optimisticAssistant: TaskMessage = {
    message_id: -Date.now() - 1, task_id: taskId, role: 'assistant',
    content: '', tool_traces: [], created_at: new Date().toISOString(),
  }
  current.messages.push(optimisticUser, optimisticAssistant)
  await scrollBottom()

  try {
    const response = await sendTaskMessageStream(taskId, message, (event) => {
      if (event.type === 'delta' && event.text) {
        optimisticAssistant.content += event.text
        void scrollBottom()
      }
    })
    const start = current.messages.indexOf(optimisticUser)
    if (start >= 0) current.messages.splice(start, 2, response.user_message, response.assistant_message)
    current.actions.push(...response.new_actions)
    if (current.title === '新任务') current.title = message.slice(0, 120)
    emitSync()
    await scrollBottom()
  } catch (error: any) {
    const start = current.messages.indexOf(optimisticUser)
    if (start >= 0) current.messages.splice(start, 2)
    draft.value = message
    toast(error.friendly || '任务执行失败，请稍后重试', 'error')
  } finally {
    sending.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

async function approve(action: TaskAction) {
  const current = detail.value
  if (!current) return
  await ElMessageBox.confirm('确认创建这条面试邀约？系统会在提交前重新核对简历和岗位规则。', '批准邀约', { type: 'warning' })
  decidingId.value = action.action_id
  try {
    const updated = await decideTaskAction(current.task_id, action.action_id, true)
    replaceAction(updated)
    toast('面试邀约已创建', 'success')
    emitSync()
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
    emitSync()
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

async function scrollBottom() {
  await nextTick()
  if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight
}

onMounted(load)
watch(() => props.taskId, load)
</script>
