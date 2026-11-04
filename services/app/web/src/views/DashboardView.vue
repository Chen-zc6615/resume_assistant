<template>
  <div class="space-y-6">
    <!-- 欢迎与快捷操作 -->
    <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 class="text-xl font-semibold text-ink-900">{{ greeting }}，{{ hrName }} 👋</h2>
        <p class="text-sm text-ink-500 mt-1">
          今天是 {{ today }}，当前有
          <span class="text-brand-600 font-medium">{{ openRequirements.length }} 个招聘需求</span> 在推进，
          <span class="text-warn font-medium">{{ pendingReviewCount }} 份简历</span> 等待人工复核。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <router-link
          to="/upload"
          class="px-4 py-2.5 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium
                 flex items-center gap-2 transition-colors"
        >
          <el-icon :size="18"><Upload /></el-icon>上传简历
        </router-link>
        <router-link
          to="/requirements"
          class="px-4 py-2.5 rounded-lg bg-card border border-hairline hover:border-brand-300 hover:text-brand-600
                 text-ink-700 text-sm font-medium flex items-center gap-2 transition-colors"
        >
          <el-icon :size="18"><Briefcase /></el-icon>新增招聘需求
        </router-link>
      </div>
    </section>

    <!-- 关键指标（紧凑单行，点击跳转对应页面） -->
    <section class="flex flex-wrap items-stretch gap-3">
      <button
        type="button" class="text-left bg-card rounded-xl border border-hairline px-4 py-2.5 flex items-center gap-2.5
               hover:border-brand-300 transition-colors cursor-pointer" @click="$router.push('/requirements')"
      >
        <span class="w-7 h-7 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center">
          <el-icon :size="15"><Briefcase /></el-icon>
        </span>
        <div class="leading-tight">
          <div class="text-base font-semibold text-ink-900">
            {{ openRequirements.length }} <span class="text-xs font-normal text-ink-400">个需求</span>
          </div>
          <div class="text-[11px] text-ink-500">进行中 · 开放 {{ openJobCount }} 岗</div>
        </div>
      </button>
      <button
        type="button" class="text-left bg-card rounded-xl border border-hairline px-4 py-2.5 flex items-center gap-2.5
               hover:border-warn transition-colors cursor-pointer" @click="$router.push('/library')"
      >
        <span class="w-7 h-7 rounded-lg bg-warn-soft text-warn flex items-center justify-center">
          <el-icon :size="15"><Loading /></el-icon>
        </span>
        <div class="leading-tight">
          <div class="text-base font-semibold text-ink-900">
            {{ processingCount }} <span class="text-xs font-normal text-ink-400">份</span>
          </div>
          <div class="text-[11px] text-ink-500">解析 / 归一化中 · 点击查看</div>
        </div>
      </button>
      <button
        type="button" class="text-left bg-card rounded-xl border border-hairline px-4 py-2.5 flex items-center gap-2.5
               hover:border-critical transition-colors cursor-pointer" @click="$router.push('/results?tab=review')"
      >
        <span class="w-7 h-7 rounded-lg bg-critical-soft text-critical flex items-center justify-center">
          <el-icon :size="15"><User /></el-icon>
        </span>
        <div class="leading-tight">
          <div class="text-base font-semibold text-ink-900">
            {{ pendingReviewCount }} <span class="text-xs font-normal text-ink-400">份</span>
          </div>
          <div class="text-[11px] text-ink-500">待复核（含待补录 {{ pendingCompleteCount }}）</div>
        </div>
      </button>
      <button
        type="button" class="text-left bg-card rounded-xl border border-hairline px-4 py-2.5 flex items-center gap-2.5
               hover:border-good transition-colors cursor-pointer" @click="$router.push('/library?status=4')"
      >
        <span class="w-7 h-7 rounded-lg bg-good-soft text-good flex items-center justify-center">
          <el-icon :size="15"><Finished /></el-icon>
        </span>
        <div class="leading-tight">
          <div class="text-base font-semibold text-ink-900">
            {{ doneCount }} <span class="text-xs font-normal text-ink-400">人</span>
          </div>
          <div class="text-[11px] text-ink-500">已入库 · 待审核 {{ waitingConfirmCount }} 份</div>
        </div>
      </button>
    </section>

    <!-- 待办 -->
    <section class="bg-card rounded-xl border border-hairline p-5">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-ink-900">我的待办</h3>
        <span class="text-[11px] px-2 py-0.5 rounded-full bg-critical-soft text-critical">{{ todoItems.length }} 项</span>
      </div>
      <div class="mt-4 space-y-3">
        <router-link
          v-for="(todo, i) in todoItems" :key="i" :to="todo.to"
          class="flex items-start gap-3 p-3 rounded-xl border border-hairline-soft hover:border-brand-200
                 hover:bg-brand-50/50 transition-colors"
        >
          <el-icon :size="18" class="mt-0.5" :color="todo.color"><component :is="todo.icon" /></el-icon>
          <span class="flex-1">
            <span class="block text-sm text-ink-700">{{ todo.title }}</span>
            <span class="block text-xs text-ink-400 mt-0.5">{{ todo.desc }}</span>
          </span>
          <el-icon class="text-ink-300"><ArrowRightBold /></el-icon>
        </router-link>
        <div v-if="!todoItems.length" class="py-8 text-center text-sm text-ink-400">暂无待办，一切就绪 🎉</div>
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
      to: '/results?tab=review', icon: User, color: '#b97900',
    })
  }
  if (pendingCompleteCount.value) {
    items.push({
      title: `${pendingCompleteCount.value} 份简历待补录关键字段`,
      desc: '缺少联系电话 / 邮箱，补录后可入库',
      to: '/results?tab=pass', icon: Warning, color: '#ec835a',
    })
  }
  if (waitingConfirmCount.value) {
    items.push({
      title: `${waitingConfirmCount.value} 份简历通过初筛待审核入库`,
      desc: '硬性条件全部满足，确认后进入人才库',
      to: '/results?tab=pass', icon: Bell, color: '#2a78d6',
    })
  }
  for (const r of openRequirements.value) {
    if (r.deadline && daysLeft(r.deadline) <= 30) {
      items.push({
        title: `「${r.requirement_name}」将于 ${r.deadline} 截止`,
        desc: `${r.job_count ?? 0} 个岗位，建议关注招聘进度`,
        to: '/requirements', icon: Briefcase, color: '#0ca30c',
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
