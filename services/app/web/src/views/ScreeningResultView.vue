<template>
  <div class="space-y-5">
    <!-- 筛选条 -->
    <section class="bg-white rounded-2xl border border-slate-200 p-5">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-3">
          <label class="text-xs text-slate-500">招聘需求</label>
          <el-select v-model="demandId" class="w-72" placeholder="选择需求" @change="onDemandChange">
            <el-option v-for="r in requirements" :key="r.requirement_id" :value="r.requirement_id"
              :label="`RQ-${String(r.requirement_id).padStart(4, '0')} · ${r.requirement_name}`" />
          </el-select>
        </div>
        <div class="flex items-center gap-3">
          <label class="text-xs text-slate-500">目标岗位</label>
          <el-select v-model="jobId" class="w-64" placeholder="全部岗位" @change="loadResults">
            <el-option :value="null" label="全部岗位（并集）" />
            <el-option v-for="j in jobsOfDemand" :key="j.job_id" :value="j.job_id"
              :label="j.job_code ? `${j.job_code} · ${j.job_name}` : j.job_name" />
          </el-select>
        </div>
        <div class="flex items-center gap-2 ml-auto">
          <el-button size="small" @click="load">刷新</el-button>
        </div>
      </div>
      <p class="text-[11px] text-slate-400 mt-3">
        说明：选「全部岗位」展示每个岗位最新判定结果的并集（同一候选人在多岗各有一条判定）；未通过附判定原因，缺失关键字的简历转待人工复核。
      </p>
    </section>

    <!-- 三态汇总 -->
    <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <button
        type="button"
        class="text-left bg-white rounded-2xl border p-5 transition-colors"
        :class="tab === 'pass' ? 'border-emerald-400' : 'border-slate-200 hover:border-emerald-300'"
        @click="tab = 'pass'"
      >
        <div class="flex items-center justify-between">
          <span class="text-xs text-slate-500">初筛通过</span>
          <span class="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
            <el-icon :size="18"><CircleCheck /></el-icon>
          </span>
        </div>
        <div class="mt-3 text-2xl font-semibold text-slate-900">{{ countOf('PASS') }} <span class="text-sm font-normal text-slate-400">份</span></div>
        <div class="text-[11px] text-emerald-600 mt-1">硬性条件全部通过，待 HR 审核入库</div>
      </button>
      <button
        type="button"
        class="text-left bg-white rounded-2xl border p-5 transition-colors"
        :class="tab === 'fail' ? 'border-rose-400' : 'border-slate-200 hover:border-rose-300'"
        @click="tab = 'fail'"
      >
        <div class="flex items-center justify-between">
          <span class="text-xs text-slate-500">初筛未通过</span>
          <span class="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
            <el-icon :size="18"><CircleClose /></el-icon>
          </span>
        </div>
        <div class="mt-3 text-2xl font-semibold text-slate-900">{{ countOf('REJECT') }} <span class="text-sm font-normal text-slate-400">份</span></div>
        <div class="text-[11px] text-rose-500 mt-1">附判定原因（全部岗位均不满足）</div>
      </button>
      <button
        type="button"
        class="text-left bg-white rounded-2xl border p-5 transition-colors"
        :class="tab === 'review' ? 'border-amber-400' : 'border-slate-200 hover:border-amber-300'"
        @click="tab = 'review'"
      >
        <div class="flex items-center justify-between">
          <span class="text-xs text-slate-500">待人工复核</span>
          <span class="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
            <el-icon :size="18"><User /></el-icon>
          </span>
        </div>
        <div class="mt-3 text-2xl font-semibold text-slate-900">{{ countOf('PENDING_REVIEW') }} <span class="text-sm font-normal text-slate-400">份</span></div>
        <div class="text-[11px] text-amber-600 mt-1">信息不足无法判定，需 HR 人工处理</div>
      </button>
    </section>

    <!-- 结果表 -->
    <section class="bg-white rounded-2xl border border-slate-200 overflow-hidden">
      <div class="px-6 py-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100">
        <div class="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100">
          <button
            v-for="t in TABS" :key="t.key" type="button"
            class="px-3.5 py-1.5 rounded-lg text-xs font-medium"
            :class="tab === t.key ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'"
            @click="tab = t.key"
          >{{ t.label }}</button>
        </div>
        <div class="flex items-center gap-2 text-[11px] text-slate-400">
          <span>当前视图：<span class="text-slate-600">{{ viewLabel }}</span></span>
          <span>·</span>
          <span>共 <span class="text-slate-600">{{ filteredRows.length }}</span> 位候选人</span>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[1100px] text-sm">
          <thead>
            <tr class="bg-slate-50 text-xs text-slate-500">
              <th class="text-left font-medium px-6 py-3 w-56">候选人</th>
              <th class="text-left font-medium px-4 py-3 w-44">目标岗位</th>
              <th class="text-left font-medium px-4 py-3 w-36">初筛结果</th>
              <th class="text-left font-medium px-4 py-3">判定原因</th>
              <th class="text-left font-medium px-4 py-3 w-64">缺失字段 / 待复核说明</th>
              <th class="text-right font-medium px-6 py-3 w-64">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in filteredRows" :key="row.result_id" class="hover:bg-slate-50/70">
              <td class="px-6 py-4">
                <div class="flex items-center gap-3">
                  <span class="w-8 h-8 rounded-full bg-blue-50 text-blue-600 text-xs font-semibold flex items-center justify-center shrink-0">
                    {{ (row.name || '候')[0] }}
                  </span>
                  <span class="min-w-0">
                    <span class="block text-sm text-slate-800">{{ row.name || '未归一化' }}</span>
                    <span class="block text-[11px] text-slate-400 mt-0.5 truncate max-w-[180px]">{{ row.original_file_name }} · #{{ row.resume_id }}</span>
                  </span>
                </div>
              </td>
              <td class="px-4 py-4">
                <span class="text-xs text-slate-600">
                  {{ row.result === 'PASS' ? row.passedJobs.join('、') : '全部岗位均不满足' }}
                </span>
              </td>
              <td class="px-4 py-4">
                <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px]" :class="resultCls(row.result)">
                  {{ resultText(row.result) }}
                </span>
              </td>
              <td class="px-4 py-4">
                <span class="text-xs text-slate-500 leading-relaxed">{{ row.firstFail || '硬性条件全部满足' }}</span>
              </td>
              <td class="px-4 py-4">
                <span class="text-xs text-amber-700 leading-relaxed">{{ row.pendingNote || '—' }}</span>
              </td>
              <td class="px-6 py-4">
                <div class="flex items-center justify-end gap-1.5">
                  <button type="button" class="px-2.5 py-1.5 rounded-lg text-xs text-slate-600 bg-slate-100 hover:bg-slate-200"
                    @click="openMatch(row)">岗位匹配</button>
                  <button type="button" class="px-2.5 py-1.5 rounded-lg text-xs text-blue-600 bg-blue-50 hover:bg-blue-100"
                    @click="openReview(row)">HR 复核</button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredRows.length">
              <td colspan="6" class="px-6 py-16 text-center">
                <div class="w-12 h-12 mx-auto rounded-full bg-slate-100 text-slate-400 flex items-center justify-center">
                  <el-icon :size="24"><Filter /></el-icon>
                </div>
                <p class="text-sm text-slate-500 mt-3">暂无筛选结果</p>
                <p class="text-xs text-slate-400 mt-1">选择需求与岗位后查看；或先在简历上传页发起处理</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- HR 复核抽屉：左原始 PDF，右归一化字段（可编辑）+ 入库 / 筛除 -->
    <el-drawer v-model="reviewDrawer" size="70%" :title="`HR 复核 — ${reviewing?.name ?? reviewing?.original_file_name ?? ''}`">
      <div v-if="reviewing" class="h-full flex gap-4">
        <div class="w-1/2 flex flex-col min-h-0">
          <div class="px-3 py-2 bg-slate-50 border border-slate-100 rounded-t-xl flex items-center gap-2 shrink-0">
            <el-icon class="text-rose-500" :size="16"><Document /></el-icon>
            <span class="text-xs font-medium text-slate-700">原始 PDF 简历</span>
            <span class="text-[11px] text-slate-400 ml-auto">未做字段处理</span>
          </div>
          <iframe :src="resumeFileUrl(reviewing.resume_id)" class="flex-1 min-h-0 w-full bg-slate-100 rounded-b-xl" />
        </div>
        <div class="w-1/2 flex flex-col min-h-0">
          <div class="px-3 py-2 bg-slate-50 border border-slate-100 rounded-t-xl flex items-center gap-2 shrink-0">
            <el-icon class="text-blue-600" :size="16"><Checked /></el-icon>
            <span class="text-xs font-medium text-slate-700">归一化后的简历（可编辑修正）</span>
            <el-tag v-if="detail?.status_label" size="small" class="ml-auto">{{ detail?.status_label }}</el-tag>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto p-4">
            <el-alert v-if="detail?.status === 5" type="warning" :closable="false" class="mb-3"
              title="关键字段缺失：请补录电话/邮箱后再入库" />
            <el-form :model="form" label-width="96px" size="small">
              <el-form-item label="姓名" required>
                <el-input v-model="form.name" />
              </el-form-item>
              <el-form-item label="性别">
                <el-select v-model="form.gender" clearable placeholder="未知">
                  <el-option label="男" :value="0" />
                  <el-option label="女" :value="1" />
                </el-select>
              </el-form-item>
              <el-form-item label="电话">
                <el-input v-model="form.phone" :placeholder="form.phone ? '' : '待补录'" />
              </el-form-item>
              <el-form-item label="邮箱">
                <el-input v-model="form.email" :placeholder="form.email ? '' : '待补录'" />
              </el-form-item>
              <el-form-item label="最高学历">
                <el-select v-model="form.highest_education" clearable placeholder="未知">
                  <el-option v-for="d in DEGREES" :key="d" :label="d" :value="d" />
                </el-select>
              </el-form-item>
              <el-form-item label="毕业院校">
                <el-input v-model="form.graduation_institution" />
              </el-form-item>
              <el-form-item label="工作月数">
                <el-input-number v-model="form.total_work_months" :min="0" :max="600" style="width: 100%" />
              </el-form-item>
              <el-form-item label="技能">
                <el-select v-model="form.skills" multiple filterable allow-create default-first-option style="width: 100%" />
              </el-form-item>
            </el-form>
            <p v-if="detail?.failure_reason" class="text-[11px] text-slate-500 leading-relaxed">
              初筛汇总：{{ detail.failure_reason }}
            </p>
          </div>
          <div class="p-3 border-t border-slate-100 flex items-center justify-end gap-2 shrink-0">
            <el-button size="small" :loading="saving" @click="save">保存修改</el-button>
            <el-button size="small" type="warning" plain @click="reparse">重试解析</el-button>
            <el-button size="small" type="danger" plain @click="reject">筛除</el-button>
            <el-button size="small" type="success" :loading="storing" @click="store">💾 入库</el-button>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 岗位匹配情况弹窗（各岗初筛判定；评分功能建设中） -->
    <el-dialog v-model="matchDialog" title="岗位匹配情况" width="640px">
      <p class="text-[11px] text-slate-400 mb-3">
        该候选人在需求下各岗位的初筛判定；匹配度评分功能建设中，当前以硬性条件判定为准。
      </p>
      <div class="space-y-2">
        <div v-for="m in matchRows" :key="m.job_name"
          class="flex items-center gap-3 rounded-xl border border-slate-200 p-3.5">
          <span class="w-10 h-10 rounded-xl bg-slate-100 text-slate-500 flex items-center justify-center text-sm font-semibold shrink-0">—</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm text-slate-800">{{ m.job_name }}</div>
            <div class="text-[11px] text-slate-400 mt-0.5 leading-relaxed">{{ m.reason }}</div>
          </div>
          <span class="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] shrink-0" :class="resultCls(m.result)">
            {{ resultText(m.result) }}
          </span>
        </div>
        <div v-if="!matchRows.length" class="py-8 text-center text-xs text-slate-400">暂无判定记录</div>
      </div>
      <template #footer>
        <el-button @click="matchDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Checked, CircleCheck, CircleClose, Document, Filter, User } from '@element-plus/icons-vue'
import {
  confirmResume, getResume, listJobs, listRequirements, listRuns, reparseResume, rejectResume,
  resumeFileUrl, runResults, updateProfile,
} from '../api'
import { toast } from '../components/toast'
import type { FilterRun, Job, Requirement, ResumeDetail } from '../types'

const DEGREES = ['大专', '本科', '硕士', '博士']
const TABS = [
  { key: 'all', label: '全部' },
  { key: 'pass', label: '初筛通过' },
  { key: 'fail', label: '初筛未通过' },
  { key: 'review', label: '待人工复核' },
]

const requirements = ref<Requirement[]>([])
const allJobs = ref<Job[]>([])
const runs = ref<FilterRun[]>([])
const results = ref<PersonRow[]>([])
const demandId = ref<number | null>(null)
const jobId = ref<number | null>(null)
const tab = ref('all')

const jobsOfDemand = computed(() =>
  demandId.value == null ? allJobs.value : allJobs.value.filter((j) => j.requirement_id === demandId.value),
)

/** 候选人行（一人一行，已按并集归并） */
const filteredRows = computed(() => {
  const key = ({ pass: 'PASS', fail: 'REJECT', review: 'PENDING_REVIEW' } as Record<string, string>)[tab.value]
  return key ? results.value.filter((r) => r.result === key) : results.value
})
const countOf = (result: string) => results.value.filter((r) => r.result === result).length

async function load() {
  const [reqs, jobs, runList] = await Promise.all([listRequirements(), listJobs(), listRuns(100)])
  requirements.value = reqs
  allJobs.value = jobs
  runs.value = runList
  // 默认选最近一次结果对应的需求
  if (!demandId.value && runList.length) {
    demandId.value = runList[0].requirement_id ?? null
  }
  await loadResults()
}

/** 归并后的候选人行：一人一行，任一岗通过即通过（与状态机口径一致） */
interface PersonRow {
  result_id: number
  resume_id: number
  name: string | null
  original_file_name: string | null
  result: 'PASS' | 'REJECT' | 'PENDING_REVIEW'
  passedJobs: string[]
  firstFail: string
  pendingNote: string
}

/**
 * 聚合结果：岗位=全部 -> 需求下每个岗位**最新一次任务**的判定按候选人归并
 * （一人一行：任一岗通过即通过，目标岗位=其通过的岗位；与多岗状态机口径一致）；
 * 岗位=单岗 -> 该岗最新一次任务，同样按人归并。
 */
async function loadResults() {
  const jobs = demandId.value == null
    ? allJobs.value
    : allJobs.value.filter((j) => j.requirement_id === demandId.value)
  const scopeJobs = jobId.value == null ? jobs : jobs.filter((j) => j.job_id === jobId.value)

  // 每个岗位取最新一条任务（runs 已按 run_id 倒序）
  const latestRuns = scopeJobs
    .map((j) => runs.value.find((r) => r.job_id === j.job_id))
    .filter((r): r is FilterRun => !!r)

  if (!latestRuns.length) {
    results.value = []
    return
  }
  const merged = await Promise.all(
    latestRuns.map(async (run) => {
      const list = await runResults(run.run_id)
      return list.map((r) => ({ ...r, job_name: run.job_name ?? `岗位${run.job_id}` }))
    }),
  )
  const allRows = merged.flat()

  // 按候选人聚合：任一岗 PASS -> 通过（通过岗位=目标岗位）；
  // 无 PASS 有 PENDING -> 待复核；全 REJECT -> 不通过（原因取首个失败明细）
  const byResume = new Map<number, PersonRow>()
  for (const row of allRows) {
    const cur = byResume.get(row.resume_id)
    if (!cur) {
      byResume.set(row.resume_id, {
        result_id: row.result_id,
        resume_id: row.resume_id,
        name: row.name,
        original_file_name: row.original_file_name,
        result: row.result,
        passedJobs: row.result === 'PASS' ? [row.job_name] : [],
        firstFail: row.reasons.find((x) => x.passed === false)?.detail ?? '',
        pendingNote: row.reasons.find((x) => x.passed == null)?.detail ?? '',
      })
      continue
    }
    if (row.result === 'PASS') cur.passedJobs.push(row.job_name)
    // 最优结果升级：REJECT -> PENDING -> PASS
    const rank = { REJECT: 0, PENDING_REVIEW: 1, PASS: 2 } as Record<string, number>
    if (rank[row.result] > rank[cur.result]) cur.result = row.result
    if (!cur.firstFail) cur.firstFail = row.reasons.find((x) => x.passed === false)?.detail ?? ''
    if (!cur.pendingNote) cur.pendingNote = row.reasons.find((x) => x.passed == null)?.detail ?? ''
  }
  results.value = [...byResume.values()]
}

function onDemandChange() {
  jobId.value = null
  loadResults()
}

const viewLabel = computed(() => {
  const req = requirements.value.find((r) => r.requirement_id === demandId.value)
  const job = allJobs.value.find((j) => j.job_id === jobId.value)
  return [req?.requirement_name ?? '全部需求', job ? (job.job_code || job.job_name) : '全部岗位（并集）'].join(' / ')
})

function resultCls(r: string) {
  return { PASS: 'bg-emerald-50 text-emerald-600', REJECT: 'bg-rose-50 text-rose-600', PENDING_REVIEW: 'bg-amber-50 text-amber-600' }[r] ?? 'bg-slate-100 text-slate-500'
}
function resultText(r: string) {
  return ({ PASS: '初筛通过', REJECT: '初筛未通过', PENDING_REVIEW: '待人工复核' } as Record<string, string>)[r] ?? r
}

// ---------------- HR 复核 ----------------
const reviewDrawer = ref(false)
const reviewing = ref<PersonRow | null>(null)
const detail = ref<ResumeDetail | null>(null)
const saving = ref(false)
const storing = ref(false)
const form = reactive({
  name: '', gender: null as number | null, phone: null as string | null,
  email: null as string | null, highest_education: null as string | null,
  graduation_institution: null as string | null, total_work_months: null as number | null,
  skills: [] as string[],
})

async function openReview(row: PersonRow) {
  reviewing.value = row
  detail.value = await getResume(row.resume_id)
  const p = detail.value.profile
  Object.assign(form, {
    name: p?.name ?? '', gender: p?.gender ?? null, phone: p?.phone ?? null,
    email: p?.email ?? null, highest_education: p?.highest_education ?? null,
    graduation_institution: p?.graduation_institution ?? null,
    total_work_months: p?.total_work_months ?? null, skills: p?.skills ?? [],
  })
  reviewDrawer.value = true
}

async function save() {
  if (!reviewing.value) return
  saving.value = true
  try {
    await updateProfile(reviewing.value.resume_id, { ...form })
    toast('归一化字段已保存')
    detail.value = await getResume(reviewing.value.resume_id)
    loadResults()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '保存失败'), 'error')
  } finally {
    saving.value = false
  }
}

async function store() {
  if (!reviewing.value) return
  storing.value = true
  try {
    await confirmResume(reviewing.value.resume_id)
    toast('已入库（状态：已完成）')
    reviewDrawer.value = false
    loadResults()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '入库失败'), 'error')
  } finally {
    storing.value = false
  }
}

async function reject() {
  if (!reviewing.value) return
  const { value } = await ElMessageBox.prompt('请填写筛除原因（留痕，区别于规则淘汰）', '人工筛除', {
    confirmButtonText: '确认筛除',
    cancelButtonText: '取消',
    inputPattern: /\S+/, inputErrorMessage: '原因必填',
  })
  await rejectResume(reviewing.value.resume_id, value)
  toast('已人工筛除', 'warn')
  reviewDrawer.value = false
  loadResults()
}

async function reparse() {
  if (!reviewing.value) return
  await reparseResume(reviewing.value.resume_id)
  toast('已触发重新解析，稍后刷新查看', 'info')
  reviewDrawer.value = false
}

// ---------------- 岗位匹配情况 ----------------
const matchDialog = ref(false)
const matchRows = ref<{ job_name: string; result: string; reason: string }[]>([])

async function openMatch(row: PersonRow) {
  // 从全部任务中找该简历各岗最新判定（前端聚合，最近任务在前）
  const seen = new Set<string>()
  const rows: typeof matchRows.value = []
  for (const run of runs.value) {
    const list = await runResults(run.run_id)
    const hit = list.find((r) => r.resume_id === row.resume_id)
    if (hit && !seen.has(run.job_name ?? '')) {
      seen.add(run.job_name ?? '')
      rows.push({
        job_name: run.job_name ?? `岗位${run.job_id}`,
        result: hit.result,
        reason: hit.reasons.find((x) => x.passed === false)?.detail
          ?? hit.reasons.find((x) => x.passed == null)?.detail
          ?? '硬性条件全部满足',
      })
    }
  }
  matchRows.value = rows
  matchDialog.value = true
}

onMounted(load)
</script>
