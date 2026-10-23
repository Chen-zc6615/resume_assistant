<template>
  <div class="max-w-4xl mx-auto space-y-3">
    <!-- 顶部操作条 -->
    <div class="flex items-center justify-between">
      <p class="text-sm text-ink-500">共 {{ tasks.length }} 个任务，点击展开对话</p>
      <el-button type="primary" :icon="Plus" @click="newTask">新建任务</el-button>
    </div>

    <!-- 任务列表（手风琴：点击展开对话） -->
    <div
      v-for="task in tasks"
      :key="task.task_id"
      class="bg-card border rounded-2xl overflow-hidden transition-shadow"
      :class="expandedId === task.task_id ? 'border-brand-300 shadow-sm' : 'border-hairline hover:border-ink-300'"
    >
      <!-- 列表行（收起态摘要 / 展开态表头） -->
      <button
        type="button"
        class="group w-full px-5 py-4 flex items-center gap-3 text-left"
        @click="toggle(task)"
      >
        <el-icon
          class="text-ink-400 transition-transform shrink-0"
          :class="expandedId === task.task_id ? 'rotate-90' : ''"
        ><ArrowRight /></el-icon>
        <div class="min-w-0 flex-1">
          <div class="text-sm font-medium text-ink-900 truncate">{{ task.title }}</div>
          <div class="mt-1 flex items-center gap-2 text-[11px] text-ink-400">
            <span>{{ formatTime(task.updated_at) }}</span>
            <span
              v-if="pendingCount(task)"
              class="px-1.5 py-0.5 rounded-full bg-warn-soft text-warn font-medium"
            >{{ pendingCount(task) }} 个待审批</span>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0">
          <el-button
            class="opacity-0 group-hover:opacity-100"
            link :icon="EditPen" @click.stop="renameTaskRow(task)"
          />
          <el-button
            class="opacity-0 group-hover:opacity-100"
            link type="danger" :icon="Delete" @click.stop="removeTask(task)"
          />
        </div>
      </button>

      <!-- 展开区：对话与输入（共用 TaskConversation 组件，详情页同款） -->
      <div v-if="expandedId === task.task_id" class="border-t border-hairline">
        <TaskConversation :task-id="task.task_id" @sync="onSync(task, $event)" />
      </div>
    </div>

    <el-empty v-if="!tasks.length" description="还没有任务" :image-size="88" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import TaskConversation from '../components/TaskConversation.vue'
import { createTask, deleteTask, getTask, listTasks, renameTask } from '../api'
import { toast } from '../components/toast'
import type { Task } from '../types'

defineOptions({ name: 'TaskView' })

const router = useRouter()
const tasks = ref<Task[]>([])
const expandedId = ref<number | null>(null)

/** 展开任务待审批数缓存（TaskConversation sync 事件回填，供收起态摘要显示） */
const pendingCounts = ref<Record<number, number>>({})

function pendingCount(task: Task): number {
  return pendingCounts.value[task.task_id] ?? 0
}

function onSync(task: Task, payload: { title: string; pendingCount: number }) {
  pendingCounts.value[task.task_id] = payload.pendingCount
  if (task.title !== payload.title) {
    task.title = payload.title
  }
}

async function loadTasks() {
  tasks.value = await listTasks()
}

async function toggle(task: Task) {
  expandedId.value = expandedId.value === task.task_id ? null : task.task_id
}

async function newTask() {
  const task = await createTask()
  await loadTasks()
  // 新任务直接进入详情页，与侧边栏「任务 → 新建」行为一致
  router.push(`/tasks/${task.task_id}`)
}

async function removeTask(task: Task) {
  await ElMessageBox.confirm(`删除任务“${task.title}”？消息和待审批动作也会删除。`, '删除任务', { type: 'warning' })
  await deleteTask(task.task_id)
  if (expandedId.value === task.task_id) expandedId.value = null
  await loadTasks()
  toast('任务已删除', 'info')
}

async function renameTaskRow(task: Task) {
  const { value } = await ElMessageBox.prompt('输入新的任务名称', '重命名任务', {
    inputValue: task.title,
    inputValidator: (text) => Boolean(text?.trim()) || '任务名称不能为空',
  })
  await renameTask(task.task_id, value.trim())
  task.title = value.trim()
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  try {
    await loadTasks()
    // 回填各任务待审批数（收起态摘要用）
    await Promise.all(tasks.value.map(async (task) => {
      try {
        const detail = await getTask(task.task_id)
        pendingCounts.value[task.task_id] = detail.actions.filter((a) => a.status === 'pending').length
      } catch { /* 单个任务摘要缺失不阻塞列表 */ }
    }))
  } catch {
    toast('任务列表加载失败', 'error')
  }
})
</script>
