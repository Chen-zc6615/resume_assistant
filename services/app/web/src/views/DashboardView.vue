<template>
  <div class="space-y-6">
    <!-- 欢迎与快捷操作 -->
    <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 class="text-xl font-semibold text-slate-900">{{ greeting }}，{{ hrName }} 👋</h2>
        <p class="text-sm text-slate-500 mt-1">
          今天是 {{ today }}，当前有
          <span class="text-blue-600 font-medium">{{ openRequirements.length }} 个招聘需求</span> 在推进，
          <span class="text-amber-600 font-medium">{{ pendingReviewCount }} 份简历</span> 等待人工复核。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <router-link
          to="/upload"
          class="px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium
                 flex items-center gap-2 shadow-lg shadow-blue-600/20 transition-colors"
        >
          <el-icon :size="18"><Upload /></el-icon>上传简历
        </router-link>
        <router-link
          to="/requirements"
          class="px-4 py-2.5 rounded-lg bg-white border border-slate-200 hover:border-blue-300 hover:text-blue-600
                 text-slate-700 text-sm font-medium flex items-center gap-2 transition-colors"
        >
          <el-icon :size="18"><Briefcase /></el-icon>新增招聘需求
        </router-link>
      </div>
    </section>

    <!-- 关键指标 -->
    <section class="grid grid-cols-2 xl:grid-cols-4 gap-4">
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
            <el-icon :size="20"><Briefcase /></el-icon>
          </div>
          <span class="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">
            开放 {{ openJobCount }} 个岗位
          </span>
        </div>
        <div class="mt-4 text-2xl font-semibold text-slate-900">
          {{ openRequirements.length }} <span class="text-sm font-normal text-slate-400">个</span>
        </div>
        <div class="text-xs text-slate-500 mt-1">进行中的招聘需求</div>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
            <el-icon :size="20"><Loading /></el-icon>
          </div>
          <span class="text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-600">处理中</span>
        </div>
        <div class="mt-4 text-2xl font-semibold text-slate-900">
          {{ processingCount }} <span class="text-sm font-normal text-slate-400">份</span>
        </div>
        <div class="text-xs text-slate-500 mt-1">解析 / 归一化 流水线中</div>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center">
            <el-icon :size="20"><User /></el-icon>
          </div>
          <span class="text-[11px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-600">待处理</span>
        </div>
        <div class="mt-4 text-2xl font-semibold text-slate-900">
          {{ pendingReviewCount }} <span class="text-sm font-normal text-slate-400">份</span>
        </div>
        <div class="text-xs text-slate-500 mt-1">待 HR 人工复核（含 {{ pendingCompleteCount }} 份待补录）</div>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-5">
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
            <el-icon :size="20"><Finished /></el-icon>
          </div>
          <span class="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600">
            待审核 {{ waitingConfirmCount }} 份
          </span>
        </div>
        <div class="mt-4 text-2xl font-semibold text-slate-900">
          {{ doneCount }} <span class="text-sm font-normal text-slate-400">人</span>
        </div>
        <div class="text-xs text-slate-500 mt-1">已完成入库</div>
      </div>
    </section>

    <!-- 待办 -->
    <section class="bg-white rounded-2xl border border-slate-200 p-5">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-slate-900">我的待办</h3>
        <span class="text-[11px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-600">{{ todoItems.length }} 项</span>
      </div>
      <div class="mt-4 space-y-3">
        <router-link
          v-for="(todo, i) in todoItems" :key="i" :to="todo.to"
          class="flex items-start gap-3 p-3 rounded-xl border border-slate-100 hover:border-blue-200
                 hover:bg-blue-50/40 transition-colors"
        >
          <el-icon :size="18" class="mt-0.5" :color="todo.color"><component :is="todo.icon" /></el-icon>
          <span class="flex-1">
            <span class="block text-sm text-slate-800">{{ todo.title }}</span>
            <span class="block text-xs text-slate-400 mt-0.5">{{ todo.desc }}</span>
          </span>
          <el-icon class="text-slate-300"><ArrowRightBold /></el-icon>
        </router-link>
        <div v-if="!todoItems.length" class="py-8 text-center text-sm text-slate-400">暂无待办，一切就绪 🎉</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowRightBold, Bell, Briefcase, Finished, Loading, Upload, User, Warning,
} from '@element-plus/icons-vue'
import { listRequirements, resumeStats } from '../api'
import type { Requirement } from '../types'

const hrName = '李婷'
const requirements = ref<Requirement[]>([])
const stats = ref<{ total?: number; by_status?: Record<string, number> }>({})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '凌晨好'
  if (h < 12) return '上午好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const today = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })

const count = (label: string) => stats.value.by_status?.[label] ?? 0
const openRequirements = computed(() => requirements.value.filter((r) => r.status === 0))
const openJobCount = computed(() => openRequirements.value.reduce((s, r) => s + (r.job_count ?? 0), 0))
const processingCount = computed(() => count('待解析') + count('待归一化'))
const pendingReviewCount = computed(() => count('待人工复核'))
const pendingCompleteCount = computed(() => count('待补录'))
const waitingConfirmCount = computed(() => count('待审核入库'))
const doneCount = computed(() => count('已完成'))

const todoItems = computed(() => {
  const items: { title: string; desc: string; to: string; icon: unknown; color: string }[] = []
  if (pendingReviewCount.value) {
    items.push({
      title: `${pendingReviewCount.value} 份简历等待人工复核`,
      desc: '信息不足的简历需人工判断去向，建议今天内处理',
      to: '/results', icon: User, color: '#d97706',
    })
  }
  if (pendingCompleteCount.value) {
    items.push({
      title: `${pendingCompleteCount.value} 份简历待补录关键字段`,
      desc: '缺少联系电话 / 邮箱，补录后可入库',
      to: '/results', icon: Warning, color: '#e11d48',
    })
  }
  if (waitingConfirmCount.value) {
    items.push({
      title: `${waitingConfirmCount.value} 份简历通过初筛待审核入库`,
      desc: '硬性条件全部满足，确认后进入人才库',
      to: '/results', icon: Bell, color: '#2563eb',
    })
  }
  for (const r of openRequirements.value) {
    if (r.deadline && daysLeft(r.deadline) <= 30) {
      items.push({
        title: `「${r.requirement_name}」将于 ${r.deadline} 截止`,
        desc: `${r.job_count ?? 0} 个岗位，建议关注招聘进度`,
        to: '/requirements', icon: Briefcase, color: '#059669',
      })
    }
  }
  return items
})

function daysLeft(deadline: string): number {
  return Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000)
}

onMounted(async () => {
  const [reqs, s] = await Promise.all([listRequirements(), resumeStats()])
  requirements.value = reqs
  stats.value = s
})
</script>
