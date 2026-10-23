<template>
  <div class="space-y-6">
    <!-- 三步指引 -->
    <section class="bg-card rounded-xl border border-hairline px-6 py-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-3">
          <span class="w-7 h-7 rounded-full bg-brand-500 text-white text-xs font-semibold flex items-center justify-center">1</span>
          <span class="text-sm font-medium text-ink-900">选择所属招聘需求</span>
        </div>
        <el-icon class="text-ink-300"><ArrowRight /></el-icon>
        <div class="flex items-center gap-3">
          <span class="w-7 h-7 rounded-full bg-brand-500 text-white text-xs font-semibold flex items-center justify-center">2</span>
          <span class="text-sm font-medium text-ink-900">批量上传 PDF 简历</span>
        </div>
        <el-icon class="text-ink-300"><ArrowRight /></el-icon>
        <div class="flex items-center gap-3">
          <span class="w-7 h-7 rounded-full bg-good text-white text-xs font-semibold flex items-center justify-center">3</span>
          <span class="text-sm font-medium text-ink-900">自动解析 · 归一化 · 分配岗位 · 硬性初筛</span>
        </div>
        <span class="ml-auto text-[11px] px-2.5 py-1 rounded-full bg-page text-ink-500">下方实时展示处理状态</span>
      </div>
    </section>

    <section class="grid grid-cols-1 xl:grid-cols-3 gap-5 items-start">
      <!-- 上传表单 -->
      <div class="xl:col-span-2 bg-card rounded-xl border border-hairline p-6 space-y-5">
        <div>
          <h3 class="text-sm font-semibold text-ink-900">上传设置</h3>
          <p class="text-xs text-ink-400 mt-1">
            上传的简历将进入所选需求池并自动分配到该需求下的全部开放岗位；任一岗位通过初筛即待审核入库
          </p>
        </div>
        <div>
          <label class="block text-xs text-ink-500 mb-1.5">所属招聘需求 <span class="text-critical">*</span></label>
          <el-select v-model="requirementId" placeholder="选择招聘需求" style="width: 100%" size="large">
            <el-option
              v-for="r in requirements" :key="r.requirement_id" :value="r.requirement_id"
              :label="`RQ-${String(r.requirement_id).padStart(4, '0')} · ${r.requirement_name}（${r.job_count ?? 0} 岗位 / ${r.resume_count ?? 0} 简历）`"
            />
          </el-select>
        </div>
        <div>
          <label class="block text-xs text-ink-500 mb-2">将自动分配至以下开放岗位</label>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="job in requirementJobs" :key="job.job_id"
              class="px-3.5 py-2 rounded-xl text-xs font-medium border border-brand-200 bg-brand-50 text-brand-600"
            >
              {{ job.job_code || job.job_name }}
            </span>
          </div>
          <p class="text-[11px] text-ink-400 mt-2">
            {{ requirementJobs.length ? `共 ${requirementJobs.length} 个开放岗位全部参与筛选（全量分配，不设技能门槛）` : '该需求下暂无开放岗位——请先在需求岗位管理中添加' }}
          </p>
        </div>

        <div>
          <label class="block text-xs text-ink-500 mb-2">简历文件</label>
          <div
            class="rounded-xl border-2 border-dashed border-hairline bg-page px-6 py-8 text-center
                   transition-colors cursor-pointer hover:border-brand-300"
            @click="pickFiles()"
            @dragover.prevent
            @drop.prevent="onDrop"
          >
            <div class="w-12 h-12 mx-auto rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center">
              <el-icon :size="26"><UploadFilled /></el-icon>
            </div>
            <p class="text-sm text-ink-600 mt-3">
              将 PDF 简历拖拽到此处，或 <span class="text-brand-600 font-medium">点击选择文件</span>
            </p>
            <p class="text-[11px] text-ink-400 mt-1">仅支持 .pdf，单份不超过 5M，可多选批量上传</p>
            <input ref="fileInputEl" class="hidden" type="file" multiple accept=".pdf" @change="onPickFiles" />
          </div>
          <div v-if="pendingFiles.length" class="mt-3 space-y-2">
            <div
              v-for="(f, i) in pendingFiles" :key="f.name"
              class="flex items-center gap-3 px-3.5 py-2.5 rounded-xl border border-hairline bg-card"
            >
              <el-icon class="text-lg text-ink-500"><Document /></el-icon>
              <span class="text-xs text-ink-600 flex-1 truncate">{{ f.name }}</span>
              <span class="text-[11px] text-ink-400">{{ (f.size / 1024 / 1024).toFixed(1) }} MB</span>
              <button
                type="button"
                class="w-6 h-6 rounded-md hover:bg-hairline-soft text-ink-400 flex items-center justify-center"
                @click="pendingFiles.splice(i, 1)"
              >
                <el-icon :size="14"><Close /></el-icon>
              </button>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between gap-3 pt-1">
          <p class="text-[11px] text-ink-400">
            提交后系统按「解析 → 归一化 → 岗位分配 → 各岗硬性初筛」顺序处理，全部岗位都不满足才筛出
          </p>
          <div class="flex items-center gap-3">
            <button
              type="button"
              class="px-4 py-2.5 rounded-lg text-sm text-ink-600 bg-page hover:bg-hairline-soft"
              @click="pendingFiles = []"
            >清空列表</button>
            <button
              type="button"
              :disabled="uploading"
              class="px-4 py-2.5 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium
                     flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
              @click="startUpload"
            >
              <el-icon :size="18"><VideoPlay /></el-icon>{{ uploading ? '上传处理中…' : '开始上传并解析' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 流程说明 -->
      <div class="bg-card rounded-xl border border-hairline p-6">
        <h3 class="text-sm font-semibold text-ink-900">处理阶段说明</h3>
        <ol class="mt-4 space-y-3">
          <li v-for="(s, i) in STAGES" :key="i" class="flex gap-3">
            <span
              class="w-6 h-6 rounded-full text-[11px] font-semibold flex items-center justify-center shrink-0"
              :class="i === STAGES.length - 1 ? 'bg-good-soft text-good' : 'bg-brand-50 text-brand-600'"
            >{{ i + 1 }}</span>
            <span>
              <span class="block text-xs font-medium text-ink-900">{{ s.name }}</span>
              <span class="block text-[11px] text-ink-400 mt-0.5 leading-relaxed">{{ s.desc }}</span>
            </span>
          </li>
        </ol>
        <div class="mt-5 rounded-xl bg-warn-soft border border-warn/40 p-4">
          <div class="flex items-start gap-2">
            <el-icon class="text-lg text-warn mt-0.5"><Warning /></el-icon>
            <p class="text-xs text-warn leading-relaxed">
              简历面对需求下所有开放岗位筛选：任一岗位通过即待审核入库，全部岗位都不满足才被筛出；信息不足的简历转待人工复核，不会被直接淘汰。
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- 上传结果 -->
    <section v-if="uploadResult" class="bg-card rounded-xl border border-hairline overflow-hidden">
      <div class="px-6 py-4 border-b border-hairline-soft">
        <h3 class="text-sm font-semibold text-ink-900">上传结果</h3>
      </div>
      <div class="grid grid-cols-3 gap-4 p-6">
        <div class="text-center">
          <div class="text-2xl font-semibold text-ink-900">{{ successCount }}</div>
          <div class="text-xs text-ink-500 mt-1">上传成功</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-semibold text-warn">{{ dupCount }}</div>
          <div class="text-xs text-ink-500 mt-1">重复文件（已去重）</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-semibold text-critical">{{ rejectCount }}</div>
          <div class="text-xs text-ink-500 mt-1">校验失败</div>
        </div>
      </div>
      <el-tabs v-model="activeTab" class="px-4 pb-4">
        <el-tab-pane :label="`✅ 成功列表（${okItems.length}）`" name="ok">
          <el-table :data="okItems" size="small" border max-height="260">
            <el-table-column prop="original_file_name" label="文件名" min-width="240" />
            <el-table-column label="结果" width="180">
              <template #default="{ row }">
                <el-tag v-if="row.accepted" type="success" size="small">已接收（#{{ row.resume_id }}）</el-tag>
                <el-tag v-if="row.duplicated" type="warning" size="small" class="ml-1">重复，复用 #{{ row.resume_id }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane :label="`❌ 失败列表（${failItems.length}）`" name="fail">
          <el-table :data="failItems" size="small" border max-height="260">
            <el-table-column prop="original_file_name" label="文件名" min-width="240" />
            <el-table-column prop="reason" label="失败原因">
              <template #default="{ row }"><span class="text-critical">{{ row.reason }}</span></template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </section>

    <!-- 处理状态 -->
    <section v-if="batch" class="bg-card rounded-xl border border-hairline overflow-hidden">
      <div class="px-6 py-5 flex flex-wrap items-center justify-between gap-4 border-b border-hairline-soft">
        <div>
          <h3 class="text-sm font-semibold text-ink-900">简历处理状态</h3>
          <p class="text-xs text-ink-400 mt-1">状态随处理进度自动流转，无需刷新页面</p>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-[11px]">
          <span class="px-2.5 py-1 rounded-full bg-brand-50 text-brand-600">处理中 {{ runningCount }} 份</span>
          <span class="px-2.5 py-1 rounded-full bg-good-soft text-good">初筛完成 {{ doneCount }} 份</span>
          <span class="px-2.5 py-1 rounded-full bg-critical-soft text-critical">处理失败 {{ batch.failed }} 份</span>
          <button
            type="button"
            class="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-xs font-medium
                   flex items-center gap-1.5"
            @click="goResults"
          >
            查看已筛选完成的简历结果
          </button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[980px] text-sm">
          <thead>
            <tr class="bg-page text-[11px] text-ink-400">
              <th class="text-left font-medium px-6 py-3">简历 / 候选人</th>
              <th class="text-left font-medium px-4 py-3 w-56">挂载需求</th>
              <th class="text-left font-medium px-4 py-3 w-[280px]">处理进度</th>
              <th class="text-left font-medium px-4 py-3 w-44">当前状态</th>
              <th class="text-left font-medium px-4 py-3">说明</th>
              <th class="text-right font-medium px-6 py-3 w-28">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-hairline-soft">
            <tr v-for="row in batch.per_resume" :key="row.resume_id" class="hover:bg-hairline-soft">
              <td class="px-6 py-4">
                <div class="flex items-center gap-3">
                  <span class="w-8 h-8 rounded-lg bg-page text-ink-500 flex items-center justify-center shrink-0">
                    <el-icon :size="16"><Document /></el-icon>
                  </span>
                  <span class="min-w-0">
                    <span class="block text-sm text-ink-900 truncate max-w-[240px]">{{ row.original_file_name }}</span>
                    <span class="block text-[11px] text-ink-400 mt-0.5">#{{ row.resume_id }} · {{ row.uploaded_by }}</span>
                  </span>
                </div>
              </td>
              <td class="px-4 py-4">
                <span class="text-xs text-ink-600">{{ selectedRequirement?.requirement_name ?? '—' }}</span>
              </td>
              <td class="px-4 py-4">
                <div class="flex items-center gap-1">
                  <div
                    v-for="(s, i) in STAGES" :key="s.key"
                    class="flex-1 h-1.5 rounded-full overflow-hidden"
                    :class="stageBg(row, i)"
                  >
                    <div
                      v-if="isCurrent(row, i)"
                      class="h-full bg-brand-500 rounded-full"
                      :style="{ width: Math.min(rowPercent(row), 100) + '%' }"
                    />
                  </div>
                </div>
                <div class="flex items-center justify-between mt-2">
                  <span class="text-[11px] text-ink-400">{{ stageLabel(row) }}</span>
                  <span class="text-[11px] text-ink-500">{{ rowPercent(row) }}%</span>
                </div>
              </td>
              <td class="px-4 py-4">
                <span
                  v-if="row.stage && row.stage !== 'done'"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] bg-brand-50 text-brand-600"
                >{{ stageName(row) }}</span>
                <span v-else-if="row.status === 10"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] bg-good-soft text-good"
                >✓ 待审核入库</span>
                <span v-else-if="row.status === 3"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] bg-critical-soft text-critical"
                >初筛不通过</span>
                <span v-else-if="row.status === 6"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] bg-warn-soft text-warn"
                >待人工复核</span>
                <span v-else-if="row.status === 5"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] bg-warn-soft text-warn"
                >待补录</span>
                <span v-else
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] bg-page text-ink-500"
                >{{ row.status_label }}</span>
              </td>
              <td class="px-4 py-4">
                <span class="text-xs text-ink-500 leading-relaxed">{{ row.failure_reason || '—' }}</span>
              </td>
              <td class="px-6 py-4 text-right">
                <a
                  v-if="row.stage === 'done' || row.status === 10"
                  class="px-2.5 py-1.5 rounded-lg text-xs text-brand-600 bg-brand-50 hover:bg-brand-100 cursor-pointer"
                  @click="goResults"
                >查看结果</a>
                <span v-else class="px-2.5 py-1.5 rounded-lg text-xs text-ink-400 bg-page">处理中</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onActivated, onUnmounted, ref } from 'vue'
import {
  ArrowRight, Close, Document, UploadFilled, VideoPlay, Warning,
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { batchStatus, listJobs, listRequirements, uploadResumes } from '../api'
import { toast } from '../components/toast'
import type { BatchStatus, Job, Requirement, UploadItem, UploadResponse } from '../types'

// keep-alive include 匹配名：切走保留上传/批次状态（App.vue）
defineOptions({ name: 'UploadView' })

// 处理阶段（对齐后端 pipeline：parsing/normalizing/screening/done）
const STAGES = [
  { key: 'parsing', name: '简历解析', desc: '提取 PDF 文本与版式，扫描件自动 OCR 兜底' },
  { key: 'normalizing', name: '归一化', desc: '统一学历 / 年限 / 技能 / 时间口径，未提及字段一律留空' },
  { key: 'screening', name: '岗位分配与初筛', desc: '全量进入需求下各开放岗位，逐条判定硬性条件（三态）' },
  { key: 'done', name: '完成', desc: '结果按岗位归档，可在筛选结果页查看与复核' },
]
const STAGE_WEIGHT: Record<string, number> = { parsing: 0.2, normalizing: 0.6, screening: 0.9, done: 1 }

const router = useRouter()
const requirements = ref<Requirement[]>([])
const allJobs = ref<Job[]>([])
const requirementId = ref<number | null>(null)
const uploadResult = ref<UploadResponse | null>(null)
const batch = ref<BatchStatus | null>(null)
const activeTab = ref('ok')
const pendingFiles = ref<File[]>([])
const uploading = ref(false)
const fileInputEl = ref<HTMLInputElement | null>(null)
let timer: number | undefined

const selectedRequirement = computed(
  () => requirements.value.find((r) => r.requirement_id === requirementId.value) ?? null,
)
const requirementJobs = computed(
  () => allJobs.value.filter((j) => j.requirement_id === requirementId.value && j.job_status === 1),
)

const okItems = computed(() => (uploadResult.value?.items ?? []).filter((i) => i.accepted))
const failItems = computed(() => (uploadResult.value?.items ?? []).filter((i) => !i.accepted))
const dupCount = computed(() => okItems.value.filter((i) => i.duplicated).length)
const rejectCount = computed(() => failItems.value.length)
const successCount = computed(() => okItems.value.length - dupCount.value)
const doneCount = computed(() => batch.value?.per_resume.filter((r) => (r.stage ?? 'done') === 'done').length ?? 0)
const runningCount = computed(() => (batch.value?.total ?? 0) - doneCount.value)

async function refreshOptions() {
  requirements.value = await listRequirements()
  allJobs.value = await listJobs()
}
refreshOptions()
onActivated(refreshOptions)

function pickFiles() {
  fileInputEl.value?.click()
}

function onPickFiles(e: Event) {
  const input = e.target as HTMLInputElement
  addFiles(Array.from(input.files ?? []))
  input.value = ''
}

function onDrop(e: DragEvent) {
  addFiles(Array.from(e.dataTransfer?.files ?? []))
}

function addFiles(files: File[]) {
  // 上传进行中不接受新文件：否则会在上传结束时随 pendingFiles 一起被清空，造成静默丢失
  if (uploading.value) return toast('上传处理中，请稍后再添加文件', 'warn')
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      toast(`「${f.name}」上传简历格式应为 .pdf`, 'error')
      continue
    }
    if (f.size > 5 * 1024 * 1024) {
      toast(`「${f.name}」单个文件不能大于 5M，请重新上传`, 'error')
      continue
    }
    if (!pendingFiles.value.some((p) => p.name === f.name && p.size === f.size)) {
      pendingFiles.value.push(f)
    }
  }
}

async function startUpload() {
  if (uploading.value) return // 函数级防重入（按钮 disabled 之外的双保险）
  if (requirementId.value == null) return toast('请先选择挂载需求', 'error')
  if (!pendingFiles.value.length) return toast('请先选择简历文件', 'error')
  if (!requirementJobs.value.length) {
    return toast('该需求下没有开放岗位，简历将停留待人工分岗——建议先去需求岗位管理添加', 'warn')
  }
  uploading.value = true
  await doUpload(pendingFiles.value)
  uploading.value = false
  pendingFiles.value = []
}

async function doUpload(files: File[]) {
  try {
    const resp = await uploadResumes(files, 'hr_admin', requirementId.value as number)
    uploadResult.value = resp
    const hasNew = resp.items.some((i: UploadItem) => i.accepted && !i.duplicated)
    if (hasNew) startPolling(resp.batch_id)
    else {
      batch.value = {
        batch_id: resp.batch_id, total: 0, finished: 0, failed: 0,
        parse_success: 0, normalize_success: 0,
        parsing: 0, normalizing: 0, screening: 0, per_resume: [],
      }
    }
    if (rejectCount.value) toast(`${rejectCount.value} 个文件校验失败，请重新上传`, 'error')
    if (dupCount.value) toast(`${dupCount.value} 个重复文件已按哈希去重`, 'info')
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '上传失败'), 'error')
  }
}

function startPolling(batchId: string) {
  stopPolling()
  timer = window.setInterval(async () => {
    try {
      batch.value = await batchStatus(batchId)
      if (batch.value && batch.value.finished >= batch.value.total) stopPolling()
    } catch {
      stopPolling()
    }
  }, 400)
}

function stopPolling() {
  if (timer) window.clearInterval(timer)
  timer = undefined
}
onUnmounted(stopPolling)

function stageIndex(row: BatchStatus['per_resume'][number]): number {
  const stage = row.stage ?? 'done'
  return Math.max(0, STAGES.findIndex((s) => s.key === stage))
}
function isCurrent(row: BatchStatus['per_resume'][number], i: number): boolean {
  const stage = row.stage ?? 'done'
  return stage !== 'done' && STAGES[i].key === stage
}
function stageBg(row: BatchStatus['per_resume'][number], i: number): string {
  const stage = row.stage ?? 'done'
  if (stage === 'done') return i <= 3 ? 'bg-good' : 'bg-hairline'
  if (i < stageIndex(row)) return 'bg-brand-500'
  if (isCurrent(row, i)) return 'bg-hairline'
  return 'bg-hairline'
}
function stageName(row: BatchStatus['per_resume'][number]): string {
  return STAGES[stageIndex(row)]?.name ?? '处理中'
}
function stageLabel(row: BatchStatus['per_resume'][number]): string {
  return `第 ${Math.min(stageIndex(row) + 1, STAGES.length)}/${STAGES.length} 步 · ${stageName(row)}`
}
function rowPercent(row: BatchStatus['per_resume'][number]): number {
  const total = batch.value?.total ?? 0
  if (!total) return 0
  const failed = !!row.failure_reason && row.status <= 2
  const units = failed ? 1 : STAGE_WEIGHT[row.stage ?? 'done'] ?? 1
  return Math.min(100, Math.round(units * 100))
}

function goResults() {
  router.push('/results')
}
</script>
