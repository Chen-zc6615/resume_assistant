<template>
  <div class="max-w-4xl mx-auto">
    <!-- 任务头部：标题 + 重命名 / 删除 -->
    <div class="bg-card border border-hairline rounded-2xl px-5 py-4 flex items-center gap-3">
      <div class="min-w-0 flex-1">
        <div class="text-sm font-semibold text-ink-900 truncate">{{ title }}</div>
        <div class="mt-1 flex items-center gap-2 text-[11px] text-ink-400">
          <span>任务 #{{ taskId }}</span>
          <span v-if="pendingCount" class="px-1.5 py-0.5 rounded-full bg-warn-soft text-warn font-medium">
            {{ pendingCount }} 个待审批
          </span>
        </div>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <el-button link :icon="EditPen" @click="rename">重命名</el-button>
        <el-button link type="danger" :icon="Delete" @click="remove">删除</el-button>
      </div>
    </div>

    <!-- 对话与输入 -->
    <div class="mt-3 bg-card border border-hairline rounded-2xl overflow-hidden">
      <TaskConversation :task-id="taskId" @sync="onSync" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Delete, EditPen } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import TaskConversation from '../components/TaskConversation.vue'
import { deleteTask, getTask, renameTask } from '../api'
import { toast } from '../components/toast'

defineOptions({ name: 'TaskDetailView' })

const route = useRoute()
const router = useRouter()
const taskId = computed(() => Number(route.params.taskId))

const title = ref(`任务 #${taskId.value}`)
const pendingCount = ref(0)

function onSync(payload: { title: string; pendingCount: number }) {
  title.value = payload.title
  pendingCount.value = payload.pendingCount
}

onMounted(async () => {
  try {
    const detail = await getTask(taskId.value)
    title.value = detail.title
    pendingCount.value = detail.actions.filter((a) => a.status === 'pending').length
  } catch {
    /* TaskConversation 内部会提示加载失败 */
  }
})

async function rename() {
  const { value } = await ElMessageBox.prompt('输入新的任务名称', '重命名任务', {
    inputValue: title.value,
    inputValidator: (text) => Boolean(text?.trim()) || '任务名称不能为空',
  })
  await renameTask(taskId.value, value.trim())
  title.value = value.trim()
  toast('任务已重命名')
}

async function remove() {
  await ElMessageBox.confirm(`删除任务“${title.value}”？消息和待审批动作也会删除。`, '删除任务', { type: 'warning' })
  await deleteTask(taskId.value)
  toast('任务已删除', 'info')
  router.replace('/tasks')
}
</script>
