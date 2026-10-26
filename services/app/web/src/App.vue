<template>
  <div class="flex min-h-screen bg-page text-ink-600">
    <!-- 侧边导航（登录页隐藏；浅色设计语言与登录页统一） -->
    <aside v-if="!isPublic" class="w-64 shrink-0 text-ink-500 sticky top-0 h-screen flex flex-col bg-card border-r border-hairline">
      <div class="h-16 flex items-center gap-3 px-5 border-b border-hairline shrink-0">
        <div class="w-9 h-9 rounded-xl bg-linear-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-blue-600/25 shrink-0">
          <el-icon :size="20"><Search /></el-icon>
        </div>
        <div class="min-w-0">
          <div class="text-ink-900 text-sm font-semibold leading-tight truncate">简历筛选助手</div>
          <div class="text-[11px] text-ink-400 leading-tight truncate">Resume Screening Copilot</div>
        </div>
      </div>
      <nav class="flex-1 overflow-y-auto no-scrollbar px-3 py-4 space-y-1">
        <div class="text-[11px] font-medium text-ink-400 px-3 pb-2">招聘流程</div>
        <router-link
          v-for="item in navItems" :key="item.path" :to="item.path"
          class="relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors"
          :class="isActive(item.path)
            ? 'bg-brand-500/10 text-ink-900 font-medium'
            : 'text-ink-600 hover:bg-page hover:text-ink-900'"
        >
          <span
            v-if="isActive(item.path)"
            class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-brand-500"
          />
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>
        <!-- 任务组：父项就地展开子列表，子项进入对应任务对话 -->
        <div>
          <button
            type="button"
            class="relative w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors"
            :class="onTasksRoute
              ? 'bg-brand-500/10 text-ink-900 font-medium'
              : 'text-ink-600 hover:bg-page hover:text-ink-900'"
            @click="taskNavOpen = !taskNavOpen"
          >
            <span
              v-if="onTasksRoute"
              class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-brand-500"
            />
            <el-icon :size="18"><ChatLineRound /></el-icon>
            <span class="flex-1 text-left">任务</span>
            <el-icon
              class="text-ink-400 transition-transform"
              :class="taskNavOpen ? 'rotate-90' : ''"
              :size="14"
            ><ArrowRight /></el-icon>
          </button>
          <div v-show="taskNavOpen" class="mt-1 ml-[26px] border-l border-hairline pl-2 space-y-0.5">
            <router-link
              v-for="t in navTasks"
              :key="t.task_id"
              :to="`/tasks/${t.task_id}`"
              class="block px-2.5 py-1.5 rounded-lg text-[13px] truncate transition-colors"
              :class="route.path === `/tasks/${t.task_id}`
                ? 'bg-page text-ink-900 font-medium'
                : 'text-ink-500 hover:text-ink-900 hover:bg-page/60'"
            >{{ t.title }}</router-link>
            <button
              type="button"
              class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[13px] text-brand-600 hover:text-brand-500 transition-colors"
              @click="newTaskFromNav"
            >
              <el-icon :size="12"><Plus /></el-icon> 新建任务
            </button>
            <div v-if="!navTasks.length" class="px-2.5 py-1 text-[11px] text-ink-400">还没有任务</div>
          </div>
        </div>
      </nav>
      <div class="p-3 shrink-0">
        <div class="rounded-xl bg-page border border-hairline p-3">
          <div class="flex items-center gap-2 text-xs text-ink-500">
            <el-icon class="text-good" :size="15"><Loading /></el-icon>
            <span>处理队列</span>
          </div>
          <div class="mt-2 h-1.5 rounded-full bg-hairline overflow-hidden">
            <div class="h-full bg-good rounded-full transition-all" :style="{ width: queuePercent }" />
          </div>
          <div class="mt-2 text-[11px] text-ink-400 leading-relaxed">
            解析/归一化中 {{ processing }} 份<br />待复核 {{ pendingReview }} 份
          </div>
        </div>
      </div>
    </aside>

    <!-- 主内容 -->
    <div class="flex-1 min-w-0 flex flex-col">
      <!-- 顶栏（登录页隐藏） -->
      <header
        v-if="!isPublic"
        class="h-16 bg-page border-b border-hairline sticky top-0 z-30
               flex items-center justify-between px-6 gap-4"
      >
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 text-xs text-ink-400">
            <span>招聘流程</span>
            <el-icon :size="12"><ArrowRight /></el-icon>
            <span class="text-ink-600">{{ $route.meta.title ?? '' }}</span>
          </div>
          <h1 class="text-[15px] font-semibold text-ink-900 leading-tight">{{ $route.meta.title ?? '' }}</h1>
        </div>
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="relative w-9 h-9 rounded-lg bg-hairline-soft hover:bg-hairline flex items-center justify-center text-ink-500 transition-colors"
            @click="notify"
          >
            <el-icon :size="18"><Bell /></el-icon>
            <span v-if="todoCount" class="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-critical" />
          </button>
          <el-dropdown>
            <button type="button" class="flex items-center gap-2 pl-1 pr-2 py-1 rounded-lg hover:bg-hairline-soft transition-colors">
              <span class="w-8 h-8 rounded-full bg-brand-500 text-white text-xs font-semibold flex items-center justify-center">
                {{ (authUser?.display_name || '李')[0] }}
              </span>
              <span class="text-left leading-tight hidden sm:block">
                <span class="block text-xs font-medium text-ink-700">{{ authUser?.display_name ?? '招聘 HR' }}</span>
                <span class="block text-[11px] text-ink-400">{{ authUser?.username ?? '' }}</span>
              </span>
              <el-icon class="text-ink-400" :size="14"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="toast('个人资料页建设中', 'info')">个人资料</el-dropdown-item>
                <el-dropdown-item @click="toast('系统设置建设中', 'info')">系统设置</el-dropdown-item>
                <el-dropdown-item divided @click="doLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="flex-1" :class="isPublic ? '' : 'p-6 space-y-6'">
        <!-- 上传页保留组件状态：切走再回来，待传清单/批次进度/上传结果不丢失 -->
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <keep-alive :include="['UploadView']">
              <component :is="Component" :key="$route.path" />
            </keep-alive>
          </Transition>
        </router-view>
      </main>
    </div>

    <AppToast />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown, ArrowRight, Bell, Briefcase, ChatDotRound, ChatLineRound, DataAnalysis, Files, Loading,
  Monitor, Plus, Search, Upload,
} from '@element-plus/icons-vue'
import AppToast from './components/AppToast.vue'
import { toast } from './components/toast'
import { authMe, createTask, listTasks, logout, resumeStats, setToken } from './api'
import type { Task } from './types'

const route = useRoute()
const router = useRouter()
// 登录页等公开路由：隐藏侧栏与顶栏，全屏渲染
const isPublic = computed(() => route.meta.public === true)

const navItems = [
  { path: '/', title: '工作台', icon: Monitor },
  { path: '/requirements', title: '需求岗位管理', icon: Briefcase },
  { path: '/upload', title: '简历上传', icon: Upload },
  { path: '/results', title: '筛选结果查看', icon: Files },
  { path: '/talent', title: '人才库管理', icon: DataAnalysis },
  { path: '/knowledge', title: '简历筛选助手', icon: ChatDotRound },
]

// 激活态前缀匹配：/knowledge/12 也高亮 /knowledge（首页必须全等，避免所有路由命中 /）
function isActive(path: string): boolean {
  return path === '/' ? route.path === '/' : route.path === path || route.path.startsWith(path + '/')
}

// ---- 任务组：侧栏内就地展开任务子列表，点子项进入对话 ----
const navTasks = ref<Task[]>([])
const taskNavOpen = ref(false)
const onTasksRoute = computed(() => route.path === '/tasks' || route.path.startsWith('/tasks/'))

async function loadNavTasks() {
  try {
    navTasks.value = await listTasks()
  } catch {
    /* 侧栏任务列表加载失败不阻塞整体 */
  }
}

async function newTaskFromNav() {
  const task = await createTask()
  await loadNavTasks()
  taskNavOpen.value = true
  router.push(`/tasks/${task.task_id}`)
}

const authUser = ref<{ user_id: number; username: string; display_name: string } | null>(null)
const stats = ref<{ total?: number; by_status?: Record<string, number> }>({})

async function loadStats() {
  try {
    stats.value = await resumeStats()
  } catch {
    /* 静默：侧栏统计不阻断页面 */
  }
}

onMounted(async () => {
  if (isPublic.value) return
  loadStats()
  loadNavTasks()
  try {
    authUser.value = await authMe() // token 失效时 401 拦截器会自动跳登录
  } catch {
    /* 已由拦截器处理 */
  }
})

// 进入任务相关路由时自动展开侧栏任务组并刷新子列表
watch(
  () => route.path,
  () => {
    if (onTasksRoute.value) {
      taskNavOpen.value = true
      loadNavTasks()
    }
  },
  { immediate: true },
)

async function doLogout() {
  try {
    await logout()
  } catch {
    /* 会话已失效时同样继续本地退出 */
  }
  setToken(null)
  toast('已退出登录', 'info')
  router.replace('/login')
}

const count = (label: string) => stats.value.by_status?.[label] ?? 0
const processing = computed(() => count('待解析') + count('待归一化'))
const pendingReview = computed(
  () => count('待人工复核') + count('待补录') + count('待审核入库'),
)
const todoCount = computed(() => pendingReview.value)
const queuePercent = computed(() => {
  const total = stats.value.total ?? 0
  return total ? `${Math.round(((total - processing.value) / total) * 100)}%` : '0%'
})

function notify() {
  const parts: string[] = []
  if (count('待人工复核')) parts.push(`${count('待人工复核')} 份待人工复核`)
  if (count('待补录')) parts.push(`${count('待补录')} 份待补录`)
  if (count('待审核入库')) parts.push(`${count('待审核入库')} 份待审核入库`)
  toast(parts.length ? `您有 ${todoCount.value} 条待处理：${parts.join('、')}` : '暂无待处理事项', 'info')
}
</script>

<style scoped>
.no-scrollbar { scrollbar-width: none; -ms-overflow-style: none; }
.no-scrollbar::-webkit-scrollbar { display: none; }
</style>

<style>
/* 聊天页全局样式（/knowledge）：细滚动条 */
.chat-scroll { scrollbar-width: thin; scrollbar-color: rgba(148,163,184,0.45) transparent; }
.chat-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
.chat-scroll::-webkit-scrollbar-track { background: transparent; }
.chat-scroll::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.45); border-radius: 3px; }
.chat-scroll::-webkit-scrollbar-thumb:hover { background: rgba(100,116,139,0.65); }
</style>
