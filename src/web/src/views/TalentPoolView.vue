<template>
  <div class="space-y-5">
    <!-- 统计 -->
    <section class="grid grid-cols-2 xl:grid-cols-4 gap-4">
      <div class="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-4">
        <div class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
          <el-icon :size="20"><FolderChecked /></el-icon>
        </div>
        <div>
          <div class="text-lg font-semibold text-slate-900">{{ poolRows.length }}</div>
          <div class="text-xs text-slate-500">本次岗位通过人才库</div>
        </div>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-4">
        <div class="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
          <el-icon :size="20"><ChatDotRound /></el-icon>
        </div>
        <div>
          <div class="text-lg font-semibold text-slate-900">{{ invitedCount }}</div>
          <div class="text-xs text-slate-500">已进入面试流程</div>
        </div>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-4">
        <div class="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
          <el-icon :size="20"><User /></el-icon>
        </div>
        <div>
          <div class="text-lg font-semibold text-slate-900">{{ todoCount }}</div>
          <div class="text-xs text-slate-500">待复核 / 待补齐 / 待审核</div>
        </div>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-4">
        <div class="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
          <el-icon :size="20"><Collection /></el-icon>
        </div>
        <div>
          <div class="text-lg font-semibold text-slate-900">{{ talentEntries.length }}</div>
          <div class="text-xs text-slate-500">沉淀候选人才库</div>
        </div>
      </div>
    </section>

    <section class="bg-white rounded-2xl border border-slate-200 overflow-hidden">
      <div class="px-6 py-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100">
        <div class="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100">
          <button
            v-for="t in [{ key: 'pool', label: '本次岗位通过人才库' }, { key: 'talent', label: '沉淀候选人才库' }]"
            :key="t.key" type="button"
            class="px-4 py-1.5 rounded-lg text-xs font-medium"
            :class="tab === t.key ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'"
            @click="tab = t.key"
          >{{ t.label }}</button>
        </div>
        <div class="flex items-center gap-2">
          <el-button size="small" @click="load">刷新</el-button>
        </div>
      </div>

      <!-- 本次岗位通过人才库 -->
      <div v-show="tab === 'pool'">
        <div class="px-6 py-3 bg-blue-50/50 border-b border-blue-100 flex items-start gap-2">
          <el-icon class="text-blue-600 mt-0.5" :size="14"><InfoFilled /></el-icon>
          <p class="text-[11px] text-blue-700 leading-relaxed">
            岗位硬性条件通过的简历在 HR 复核后进入此库：可复核候选人信息、标记面试状态、发起面试邀约或沉淀储备。
          </p>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[1100px] text-sm">
            <thead>
              <tr class="bg-slate-50 text-xs text-slate-500">
                <th class="text-left font-medium px-6 py-3 w-56">候选人</th>
                <th class="text-left font-medium px-4 py-3">初筛汇总 / 入库岗位</th>
                <th class="text-left font-medium px-4 py-3 w-40">面试流程</th>
                <th class="text-left font-medium px-4 py-3 w-32">简历状态</th>
                <th class="text-left font-medium px-4 py-3">说明 / 提示</th>
                <th class="text-right font-medium px-6 py-3 w-72">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="row in poolRows" :key="row.resume_id" class="hover:bg-slate-50/70">
                <td class="px-6 py-4">
                  <div class="flex items-center gap-3">
                    <span class="w-8 h-8 rounded-full bg-blue-50 text-blue-600 text-xs font-semibold flex items-center justify-center shrink-0">
                      {{ (row.name || '候')[0] }}
                    </span>
                    <span class="min-w-0">
                      <span class="block text-sm text-slate-800">{{ row.name || '未归一化' }}</span>
                      <span class="block text-[11px] text-slate-400 mt-0.5 truncate max-w-[180px]">#{{ row.resume_id }} · {{ row.original_file_name }}</span>
                    </span>
                  </div>
                </td>
                <td class="px-4 py-4">
                  <span class="text-xs text-slate-500 leading-relaxed">{{ row.failure_reason || '—' }}</span>
                </td>
                <td class="px-4 py-4">
                  <el-tag v-if="row.interview_status != null" :type="interviewTagType(row.interview_status)" size="small">
                    {{ INTERVIEW_LABELS[row.interview_status] }}
                  </el-tag>
                  <span v-else class="text-[11px] text-slate-400">未进入</span>
                </td>
                <td class="px-4 py-4">
                  <el-tag :type="row.status === 4 ? 'success' : 'primary'" size="small">{{ row.status_label }}</el-tag>
                </td>
                <td class="px-4 py-4">
                  <span class="text-xs text-slate-400 leading-relaxed">
                    {{ row.status === 4 ? '已完成入库' : '待 HR 确认入库' }}
                  </span>
                </td>
                <td class="px-6 py-4">
                  <div class="flex items-center justify-end gap-1.5">
                    <el-button size="small" @click="openResume(row)">查看简历</el-button>
                    <el-button size="small" type="primary" plain @click="openStatus(row)">标记状态</el-button>
                    <el-button size="small" type="success" plain @click="openInvite(row)">发起邀约</el-button>
                    <el-button size="small" plain @click="openPoolDialog(row)">沉淀储备</el-button>
                  </div>
                </td>
              </tr>
              <tr v-if="!poolRows.length">
                <td colspan="6" class="px-6 py-14 text-center">
                  <p class="text-sm text-slate-500">暂无通过初筛的候选人</p>
                  <p class="text-xs text-slate-400 mt-1">简历通过岗位硬性条件初筛后将出现在此库</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 沉淀候选人才库 -->
      <div v-show="tab === 'talent'">
        <div class="px-6 py-3 bg-emerald-50/50 border-b border-emerald-100 flex items-start gap-2">
          <el-icon class="text-emerald-600 mt-0.5" :size="14"><MagicStick /></el-icon>
          <p class="text-[11px] text-emerald-700 leading-relaxed">
            沉淀人才库用于长期储备：暂不匹配的人选沉淀于此，后续有新招聘需求时可直接发起人才匹配。
          </p>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[1100px] text-sm">
            <thead>
              <tr class="bg-slate-50 text-xs text-slate-500">
                <th class="text-left font-medium px-6 py-3 w-56">候选人</th>
                <th class="text-left font-medium px-4 py-3">核心技能</th>
                <th class="text-left font-medium px-4 py-3">来源（需求 - 岗位）</th>
                <th class="text-left font-medium px-4 py-3 w-36">简历状态</th>
                <th class="text-left font-medium px-4 py-3">备注</th>
                <th class="text-right font-medium px-6 py-3 w-64">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="e in talentEntries" :key="e.pool_id" class="hover:bg-slate-50/70">
                <td class="px-6 py-4">
                  <div class="flex items-center gap-3">
                    <span class="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 text-xs font-semibold flex items-center justify-center shrink-0">
                      {{ (e.resume?.original_file_name || '候')[0] }}
                    </span>
                    <span class="min-w-0">
                      <span class="block text-sm text-slate-800">#{{ e.resume_id }}</span>
                      <span class="block text-[11px] text-slate-400 mt-0.5 truncate max-w-[180px]">{{ e.resume?.original_file_name }}</span>
                    </span>
                  </div>
                </td>
                <td class="px-4 py-4">
                  <span class="text-xs text-slate-500">{{ e.resume?.status_label ?? '—' }}</span>
                </td>
                <td class="px-4 py-4">
                  <span class="text-xs text-slate-500">{{ e.source_requirement_name ?? '—' }} / {{ e.source_job_name ?? '—' }}</span>
                </td>
                <td class="px-4 py-4">
                  <el-tag size="small" :type="e.resume && e.resume.status === 4 ? 'success' : 'info'">
                    {{ e.resume?.status_label ?? '已删除' }}
                  </el-tag>
                </td>
                <td class="px-4 py-4">
                  <span class="text-xs text-slate-400 leading-relaxed">{{ e.note || '—' }}</span>
                </td>
                <td class="px-6 py-4">
                  <div class="flex items-center justify-end gap-1.5">
                    <el-button v-if="e.resume" size="small" @click="openResume(e.resume)">查看简历</el-button>
                    <el-button size="small" type="primary" plain @click="matchPlaceholder">发起匹配</el-button>
                    <el-popconfirm title="移出沉淀库？（简历记录保留）" @confirm="doRemovePool(e.pool_id)">
                      <template #reference><el-button size="small" type="danger" plain>移出</el-button></template>
                    </el-popconfirm>
                  </div>
                </td>
              </tr>
              <tr v-if="!talentEntries.length">
                <td colspan="6" class="px-6 py-14 text-center">
                  <p class="text-sm text-slate-500">沉淀库还是空的</p>
                  <p class="text-xs text-slate-400 mt-1">在「本次岗位通过人才库」中把暂不跟进的候选人沉淀于此</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 候选人简历抽屉 -->
    <el-drawer v-model="resumeDrawer" size="560px" :title="`候选人简历 — ${drawerResume?.name ?? drawerResume?.original_file_name ?? ''}`">
      <div v-if="drawerDetail" class="space-y-4">
        <div class="rounded-xl border border-slate-200 p-4">
          <div class="grid grid-cols-2 gap-y-2 text-xs">
            <div class="text-slate-400">学历</div>
            <div class="text-slate-700">{{ drawerDetail.profile?.highest_education ?? '未知' }}</div>
            <div class="text-slate-400">工作年限</div>
            <div class="text-slate-700">{{ monthsLabel(drawerDetail.profile?.total_work_months) }}</div>
            <div class="text-slate-400">电话</div>
            <div class="text-slate-700">{{ drawerDetail.profile?.phone ?? '—' }}</div>
            <div class="text-slate-400">邮箱</div>
            <div class="text-slate-700">{{ drawerDetail.profile?.email ?? '—' }}</div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 p-4">
          <div class="text-xs font-medium text-slate-600 mb-2">技能</div>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="s in drawerDetail.profile?.skills ?? []" :key="s"
              class="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-600">{{ s }}</span>
            <span v-if="!drawerDetail.profile?.skills?.length" class="text-xs text-slate-400">未提取到</span>
          </div>
        </div>
        <div v-if="drawerDetail.profile?.work_experiences?.length" class="rounded-xl border border-slate-200 p-4">
          <div class="text-xs font-medium text-slate-600 mb-2">工作经历</div>
          <div v-for="w in drawerDetail.profile.work_experiences" :key="w.work_id" class="text-xs text-slate-600 leading-relaxed mb-2">
            <span class="text-slate-800 font-medium">{{ w.company }}</span> · {{ w.position }}
            <span class="text-slate-400">（{{ w.start_date ?? '?' }} ~ {{ w.is_current ? '至今' : (w.end_date ?? '—') }}）</span>
            <span v-if="w.description" class="block text-slate-400 mt-0.5">{{ w.description }}</span>
          </div>
        </div>
        <p class="text-[11px] text-slate-400 leading-relaxed">{{ drawerDetail.failure_reason }}</p>
      </div>
      <template #footer>
        <el-button class="w-full" @click="resumeFileUrl2">打开 PDF 原文</el-button>
      </template>
    </el-drawer>

    <!-- 标记状态弹窗 -->
    <el-dialog v-model="statusDialog" title="标记候选人状态" width="440px">
      <div class="space-y-4">
        <div>
          <label class="block text-xs text-slate-500 mb-1.5">候选人</label>
          <el-input :model-value="statusTarget?.name ?? statusTarget?.original_file_name" readonly />
        </div>
        <div>
          <label class="block text-xs text-slate-500 mb-1.5">状态</label>
          <el-select v-model="statusValue" style="width: 100%">
            <el-option v-for="(l, i) in INTERVIEW_LABELS" :key="i" :label="l" :value="i" />
          </el-select>
        </div>
        <div>
          <label class="block text-xs text-slate-500 mb-1.5">备注</label>
          <el-input v-model="statusNote" type="textarea" :rows="2" placeholder="记录标记原因，便于团队协同" />
        </div>
      </div>
      <template #footer>
        <el-button @click="statusDialog = false">取消</el-button>
        <el-button type="primary" @click="saveStatus">保存状态</el-button>
      </template>
    </el-dialog>

    <!-- 面试邀约弹窗 -->
    <el-dialog v-model="inviteDialog" title="发起面试邀请" width="520px">
      <div class="rounded-xl bg-slate-50 p-3.5 flex items-center gap-3 mb-4">
        <span class="w-9 h-9 rounded-full bg-blue-600 text-white text-xs font-semibold flex items-center justify-center">
          {{ (inviteTarget?.name || '候')[0] }}
        </span>
        <div>
          <div class="text-sm text-slate-800">{{ inviteTarget?.name ?? inviteTarget?.original_file_name }}</div>
          <div class="text-[11px] text-slate-400">简历 #{{ inviteTarget?.resume_id }}</div>
        </div>
      </div>
      <el-form label-width="88px" size="small">
        <div class="grid grid-cols-2 gap-x-4">
          <el-form-item label="面试时间">
            <el-input v-model="inviteForm.interview_time" placeholder="如 2026-10-12 14:30" />
          </el-form-item>
          <el-form-item label="面试方式">
            <el-select v-model="inviteForm.way" style="width: 100%">
              <el-option v-for="w in WAYS" :key="w" :label="w" :value="w" />
            </el-select>
          </el-form-item>
          <el-form-item label="面试官">
            <el-input v-model="inviteForm.interviewer" placeholder="如 李婷、赵工（用人部门）" />
          </el-form-item>
          <el-form-item label="通知方式">
            <el-select v-model="inviteForm.notify_way" style="width: 100%">
              <el-option v-for="n in ['邮件 + 短信通知', '仅邮件通知', '仅短信通知']" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input v-model="inviteForm.note" type="textarea" :rows="2" placeholder="例如：请候选人准备 15 分钟项目介绍" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inviteDialog = false">取消</el-button>
        <el-button type="primary" @click="sendInvite">发送邀请</el-button>
      </template>
    </el-dialog>

    <!-- 沉淀入库弹窗 -->
    <el-dialog v-model="poolDialog" title="沉淀至候选人才库" width="480px">
      <el-form label-width="88px" size="small">
        <el-form-item label="备注">
          <el-input v-model="poolNote" type="textarea" :rows="3" placeholder="沉淀原因 / 亮点，便于后续匹配（选填）" />
        </el-form-item>
      </el-form>
      <p class="text-[11px] text-slate-400">将 #{{ poolTarget?.resume_id }} 加入沉淀候选人才库（长期储备，可随时移出）。</p>
      <template #footer>
        <el-button @click="poolDialog = false">取消</el-button>
        <el-button type="primary" @click="doPool">确认沉淀</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  ChatDotRound, Collection, FolderChecked, InfoFilled, MagicStick, User,
} from '@element-plus/icons-vue'
import {
  addToTalentPool, createInterview, getResume, listResumes, listTalentPool,
  removeFromTalentPool, resumeFileUrl, setInterviewStatus,
} from '../api'
import { toast } from '../components/toast'
import type { ResumeBrief, ResumeDetail, TalentPoolEntry } from '../types'

const INTERVIEW_LABELS = ['待面试', '已邀请面试', '面试中', '已入职', '暂不跟进']
const WAYS = ['线上一面（腾讯会议）', '线上二面（技术面）', '现场面试', '电话初筛沟通']

const tab = ref('pool')
const allResumes = ref<ResumeBrief[]>([])
const talentEntries = ref<TalentPoolEntry[]>([])

/** 本次岗位通过人才库：初筛通过待审核(10) + 已完成(4) */
const poolRows = computed(() =>
  allResumes.value
    .filter((r) => r.status === 10 || r.status === 4)
    .map((r) => r),
)
const invitedCount = computed(
  () => poolRows.value.filter((r) => r.interview_status != null && r.interview_status <= 2).length,
)
const todoCount = computed(
  () => allResumes.value.filter((r) => [5, 6].includes(r.status)).length,
)

// ---------------- 数据加载 ----------------
async function load() {
  const [resumes, pool] = await Promise.all([listResumes(), listTalentPool()])
  allResumes.value = resumes
  talentEntries.value = pool
}

function interviewTagType(s: number) {
  return (['primary', 'success', 'warning', 'success', 'info'] as const)[s] ?? 'info'
}

// ---------------- 简历抽屉 ----------------
const resumeDrawer = ref(false)
const drawerDetail = ref<ResumeDetail | null>(null)
const drawerResume = ref<ResumeBrief | null>(null)

async function openResume(row: ResumeBrief) {
  drawerResume.value = row
  drawerDetail.value = await getResume(row.resume_id)
  resumeDrawer.value = true
}

function resumeFileUrl2() {
  if (drawerResume.value) window.open(resumeFileUrl(drawerResume.value.resume_id), '_blank')
}

function monthsLabel(months?: number | null): string {
  if (months == null) return '年限未知'
  return months % 12 ? `${Math.floor(months / 12)} 年 ${months % 12} 个月` : `${months / 12} 年`
}

// ---------------- 标记状态 ----------------
const statusDialog = ref(false)
const statusTarget = ref<ResumeBrief | null>(null)
const statusValue = ref(0)
const statusNote = ref('')

function openStatus(row: ResumeBrief) {
  statusTarget.value = row
  statusValue.value = row.interview_status ?? 0
  statusNote.value = ''
  statusDialog.value = true
}

async function saveStatus() {
  if (!statusTarget.value) return
  await setInterviewStatus(statusTarget.value.resume_id, statusValue.value)
  toast(`已标记为「${INTERVIEW_LABELS[statusValue.value]}」`)
  statusDialog.value = false
  load()
}

// ---------------- 面试邀约 ----------------
const inviteDialog = ref(false)
const inviteTarget = ref<ResumeBrief | null>(null)
const inviteForm = reactive({
  interview_time: '', way: WAYS[0], interviewer: '', note: '', notify_way: '邮件 + 短信通知',
})

function openInvite(row: ResumeBrief) {
  inviteTarget.value = row
  Object.assign(inviteForm, { interview_time: '', way: WAYS[0], interviewer: '', note: '', notify_way: '邮件 + 短信通知' })
  inviteDialog.value = true
}

async function sendInvite() {
  if (!inviteTarget.value) return
  await createInterview({
    resume_id: inviteTarget.value.resume_id,
    interview_time: inviteForm.interview_time || null,
    way: inviteForm.way,
    interviewer: inviteForm.interviewer || null,
    note: inviteForm.note || null,
    notify_way: inviteForm.notify_way,
  })
  toast('面试邀请已发送（简历标记为已邀请面试）')
  inviteDialog.value = false
  load()
}

// ---------------- 沉淀 ----------------
const poolDialog = ref(false)
const poolTarget = ref<ResumeBrief | null>(null)
const poolNote = ref('')

function openPoolDialog(row: ResumeBrief) {
  poolTarget.value = row
  poolNote.value = ''
  poolDialog.value = true
}

async function doPool() {
  if (!poolTarget.value) return
  try {
    await addToTalentPool(poolTarget.value.resume_id, { note: poolNote.value || null })
    toast('已沉淀至候选人才库')
    poolDialog.value = false
    load()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '沉淀失败'), 'error')
  }
}

async function doRemovePool(poolId: number) {
  await removeFromTalentPool(poolId)
  toast('已移出沉淀库', 'info')
  load()
}

function matchPlaceholder() {
  toast('人才匹配功能建设中（将对接知识库语义检索）', 'info')
}

onMounted(load)
</script>
