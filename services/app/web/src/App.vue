<template>
  <div class="flex min-h-screen bg-slate-100 text-slate-700">
    <!-- 侧边导航 -->
    <aside class="w-64 shrink-0 bg-slate-900 text-slate-400 sticky top-0 h-screen flex flex-col">
      <div class="h-16 flex items-center gap-3 px-5 border-b border-white/10 shrink-0">
        <div class="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center text-white shrink-0">
          <el-icon :size="20"><Search /></el-icon>
        </div>
        <div class="min-w-0">
          <div class="text-white text-sm font-semibold leading-tight truncate">简历筛选助手</div>
          <div class="text-[11px] text-slate-500 leading-tight truncate">Resume Screening Copilot</div>
        </div>
      </div>
      <nav class="flex-1 overflow-y-auto no-scrollbar px-3 py-4 space-y-1">
        <div class="text-[11px] font-medium text-slate-500 px-3 pb-2">招聘流程</div>
        <router-link
          v-for="item in navItems" :key="item.path" :to="item.path"
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors"
          :class="$route.path === item.path
            ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/30'
            : 'hover:bg-white/5 hover:text-white'"
        >
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>
      </nav>
      <div class="p-3 shrink-0">
        <div class="rounded-xl bg-white/5 p-3">
          <div class="flex items-center gap-2 text-xs text-slate-300">
            <el-icon class="text-emerald-400" :size="15"><Loading /></el-icon>
            <span>处理队列</span>
          </div>
          <div class="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
            <div class="h-full bg-emerald-400 rounded-full transition-all" :style="{ width: queuePercent }" />
          </div>
          <div class="mt-2 text-[11px] text-slate-500 leading-relaxed">
            解析/归一化中 {{ processing }} 份<br />待复核 {{ pendingReview }} 份
          </div>
        </div>
      </div>
    </aside>

    <!-- 主内容 -->
    <div class="flex-1 min-w-0 flex flex-col">
      <header
        class="h-16 bg-white/90 backdrop-blur border-b border-slate-200 sticky top-0 z-30
               flex items-center justify-between px-6 gap-4"
      >
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 text-xs text-slate-400">
            <span>招聘流程</span>
            <el-icon :size="12"><ArrowRight /></el-icon>
            <span class="text-slate-500">{{ $route.meta.title ?? '' }}</span>
          </div>
          <h1 class="text-[15px] font-semibold text-slate-900 leading-tight">{{ $route.meta.title ?? '' }}</h1>
        </div>
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="relative w-9 h-9 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-500"
            @click="notify"
          >
            <el-icon :size="18"><Bell /></el-icon>
            <span v-if="todoCount" class="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500" />
          </button>
          <el-dropdown>
            <button type="button" class="flex items-center gap-2 pl-1 pr-2 py-1 rounded-lg hover:bg-slate-100">
              <span class="w-8 h-8 rounded-full bg-blue-600 text-white text-xs font-semibold flex items-center justify-center">李</span>
              <span class="text-left leading-tight hidden sm:block">
                <span class="block text-xs font-medium text-slate-800">李婷</span>
                <span class="block text-[11px] text-slate-400">招聘 HR</span>
              </span>
              <el-icon class="text-slate-400" :size="14"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="toast('个人资料页建设中', 'info')">个人资料</el-dropdown-item>
                <el-dropdown-item @click="toast('系统设置建设中', 'info')">系统设置</el-dropdown-item>
                <el-dropdown-item divided @click="toast('已退出登录（演示）', 'warn')">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="flex-1 p-6 space-y-6">
        <!-- 上传页保留组件状态：切走再回来，待传清单/批次进度/上传结果不丢失 -->
        <router-view v-slot="{ Component }">
          <keep-alive :include="['UploadView']">
            <component :is="Component" :key="$route.path" />
          </keep-alive>
        </router-view>
      </main>
    </div>

    <AppToast />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowDown, ArrowRight, Bell, Briefcase, DataAnalysis, Files, Loading,
  Monitor, Search, Upload,
} from '@element-plus/icons-vue'
import AppToast from './components/AppToast.vue'
import { toast } from './components/toast'
import { resumeStats } from './api'

const navItems = [
  { path: '/', title: '工作台', icon: Monitor },
  { path: '/requirements', title: '需求岗位管理', icon: Briefcase },
  { path: '/upload', title: '简历上传', icon: Upload },
  { path: '/results', title: '筛选结果查看', icon: Files },
  { path: '/talent', title: '人才库管理', icon: DataAnalysis },
]

const stats = ref<{ total?: number; by_status?: Record<string, number> }>({})

async function loadStats() {
  try {
    stats.value = await resumeStats()
  } catch {
    /* 静默：侧栏统计不阻断页面 */
  }
}
onMounted(loadStats)

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
