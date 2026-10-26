<template>
  <div class="space-y-5">
    <!-- 统计（前三卡点击定位到列表，累计简历卡跳简历库） -->
    <section class="grid grid-cols-2 xl:grid-cols-4 gap-4">
      <button
        type="button"
        class="text-left bg-card rounded-xl border border-hairline p-4 flex items-center gap-4 transition-colors hover:border-brand-300 cursor-pointer"
        @click="focusList"
      >
        <div class="w-10 h-10 rounded-xl bg-page text-ink-600 flex items-center justify-center">
          <el-icon :size="20"><Tickets /></el-icon>
        </div>
        <div>
          <div class="text-2xl font-semibold text-ink-900 tracking-tight">{{ requirements.length }}</div>
          <div class="text-xs text-ink-500">招聘需求</div>
        </div>
      </button>
      <button
        type="button"
        class="text-left bg-card rounded-xl border border-hairline p-4 flex items-center gap-4 transition-colors hover:border-brand-300 cursor-pointer"
        @click="focusList"
      >
        <div class="w-10 h-10 rounded-xl bg-page text-ink-600 flex items-center justify-center">
          <el-icon :size="20"><Briefcase /></el-icon>
        </div>
        <div>
          <div class="text-2xl font-semibold text-ink-900 tracking-tight">{{ jobTotal }}</div>
          <div class="text-xs text-ink-500">岗位总数</div>
        </div>
      </button>
      <button
        type="button"
        class="text-left bg-card rounded-xl border border-hairline p-4 flex items-center gap-4 transition-colors hover:border-brand-300 cursor-pointer"
        @click="focusList"
      >
        <div class="w-10 h-10 rounded-xl bg-page text-ink-600 flex items-center justify-center">
          <el-icon :size="20"><VideoPlay /></el-icon>
        </div>
        <div>
          <div class="text-2xl font-semibold text-ink-900 tracking-tight">{{ openJobs.length }}</div>
          <div class="text-xs text-ink-500">招聘中岗位</div>
        </div>
      </button>
      <button
        type="button"
        class="text-left bg-card rounded-xl border border-hairline p-4 flex items-center gap-4 transition-colors hover:border-brand-300 cursor-pointer"
        @click="$router.push('/library')"
      >
        <div class="w-10 h-10 rounded-xl bg-page text-ink-600 flex items-center justify-center">
          <el-icon :size="20"><Files /></el-icon>
        </div>
        <div>
          <div class="text-2xl font-semibold text-ink-900 tracking-tight">{{ resumeTotal }}</div>
          <div class="text-xs text-ink-500">累计收到简历（份）</div>
        </div>
      </button>
    </section>

    <section ref="listSection" class="grid grid-cols-1 xl:grid-cols-4 gap-5 items-start">
      <!-- 需求列表 -->
      <div class="xl:col-span-1 bg-card rounded-xl border border-hairline p-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-ink-900">招聘需求</h3>
          <button
            type="button"
            class="w-7 h-7 rounded-lg bg-brand-50 hover:bg-brand-100 text-brand-600 flex items-center justify-center"
            title="新增招聘需求" @click="openCreate"
          >
            <el-icon :size="14"><Plus /></el-icon>
          </button>
        </div>
        <div class="mt-3 space-y-2">
          <button
            v-for="r in requirements" :key="r.requirement_id" type="button"
            class="w-full text-left rounded-xl border p-3.5 transition-colors"
            :class="r.requirement_id === selected?.requirement_id
              ? 'border-brand-500 bg-brand-50/60'
              : 'border-hairline hover:border-brand-200 hover:bg-page'"
            @click="select(r)"
          >
            <div class="flex items-center justify-between gap-2">
              <span
                class="text-[11px] font-medium"
                :class="r.requirement_id === selected?.requirement_id ? 'text-brand-600' : 'text-ink-400'"
              >RQ-{{ String(r.requirement_id).padStart(4, '0') }}</span>
              <span
                class="text-[11px] px-2 py-0.5 rounded-full"
                :class="r.status === 0 ? 'bg-good-soft text-good' : 'bg-page text-ink-500'"
              >{{ r.status === 0 ? '进行中' : '已关闭' }}</span>
            </div>
            <div class="mt-1.5 text-sm font-medium text-ink-900 leading-snug">{{ r.requirement_name }}</div>
            <div class="mt-1.5 text-[11px] text-ink-400">
              {{ r.job_count ?? 0 }} 个岗位<template v-if="r.deadline"> · 截止 {{ r.deadline }}</template>
            </div>
          </button>
          <div v-if="!requirements.length" class="py-10 text-center text-xs text-ink-400">暂无需求，点击右上角创建</div>
        </div>
      </div>

      <!-- 需求详情与岗位 -->
      <div class="xl:col-span-3 bg-card rounded-xl border border-hairline overflow-hidden">
        <div class="p-5 border-b border-hairline-soft">
          <template v-if="selected">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div class="flex items-center gap-2">
                  <h2 class="text-base font-semibold text-ink-900">{{ selected.requirement_name }}</h2>
                  <span
                    class="text-[11px] px-2 py-0.5 rounded-full"
                    :class="selected.status === 0 ? 'bg-good-soft text-good' : 'bg-page text-ink-500'"
                  >{{ selected.status === 0 ? '进行中' : '已关闭' }}</span>
                </div>
                <p class="text-xs text-ink-400 mt-2">
                  用人部门 {{ selected.dept || '未指定' }} · 负责人 {{ selected.created_by }}
                  <template v-if="selected.deadline"> · 截止 {{ selected.deadline }}</template>
                </p>
                <p v-if="selected.description" class="text-xs text-ink-500 mt-2 leading-relaxed max-w-2xl">
                  {{ selected.description }}
                </p>
              </div>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="px-3 py-2 rounded-lg bg-page hover:bg-hairline-soft text-ink-600 text-xs
                         flex items-center gap-1.5"
                  @click="openPool(selected)"
                >
                  <el-icon :size="14"><FolderOpened /></el-icon>需求池
                </button>
                <button
                  type="button"
                  class="px-3 py-2 rounded-lg bg-page hover:bg-hairline-soft text-ink-600 text-xs
                         flex items-center gap-1.5"
                  @click="openEdit(selected)"
                >
                  <el-icon :size="14"><EditPen /></el-icon>编辑需求
                </button>
                <el-popconfirm
                  title="删除需求将级联删除其岗位与分组、筛选任务，确认？"
                  @confirm="doDelete(selected)"
                >
                  <template #reference>
                    <button
                      type="button"
                      class="px-3 py-2 rounded-lg bg-critical-soft hover:opacity-80 text-critical text-xs
                             flex items-center gap-1.5"
                    >
                      <el-icon :size="14"><Delete /></el-icon>删除需求
                    </button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
          </template>
          <p v-else class="text-sm text-ink-400">暂无招聘需求，请先创建。</p>
        </div>

        <div class="px-5 py-4 flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold text-ink-900">岗位列表</h3>
            <p class="text-xs text-ink-400 mt-1">岗位硬性条件将用于简历筛选中的「岗位硬性条件初筛」环节</p>
          </div>
          <div class="flex items-center gap-2">
            <el-popconfirm title="把需求池内可筛简历重新分配到全部开放岗位并执行初筛？" @confirm="doReassign">
              <template #reference>
                <el-button type="warning" size="small" :loading="reassigning">🔄 重新分配并初筛</el-button>
              </template>
            </el-popconfirm>
            <el-button type="primary" size="small" @click="openJobCreate">➕ 新增岗位</el-button>
          </div>
        </div>

        <div class="overflow-x-auto border-t border-hairline-soft">
          <table class="w-full min-w-[900px] text-sm">
            <thead>
              <tr class="bg-page">
                <th class="text-left font-medium text-[11px] text-ink-400 px-5 py-3">岗位</th>
                <th class="text-left font-medium text-[11px] text-ink-400 px-4 py-3 w-24">招聘人数</th>
                <th class="text-left font-medium text-[11px] text-ink-400 px-4 py-3">硬性条件</th>
                <th class="text-left font-medium text-[11px] text-ink-400 px-4 py-3 w-24">收到简历</th>
                <th class="text-left font-medium text-[11px] text-ink-400 px-4 py-3 w-24">岗位状态</th>
                <th class="text-right font-medium text-[11px] text-ink-400 px-5 py-3 w-56">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-hairline-soft">
              <tr v-for="job in jobs" :key="job.job_id" class="hover:bg-hairline-soft">
                <td class="px-5 py-4">
                  <div class="flex items-center gap-2">
                    <span v-if="job.job_code" class="text-[11px] px-2 py-0.5 rounded-md bg-brand-50 text-brand-600 font-medium">
                      {{ job.job_code }}
                    </span>
                    <span class="text-sm text-ink-900">{{ job.job_name }}</span>
                  </div>
                  <div v-if="job.major" class="text-[11px] text-ink-400 mt-1">{{ job.major }}</div>
                </td>
                <td class="px-4 py-4 text-ink-600">{{ job.headcount ?? '—' }}</td>
                <td class="px-4 py-4">
                  <div class="flex flex-wrap items-center gap-1.5 max-w-md">
                    <span class="text-[11px] px-2 py-0.5 rounded-md bg-page text-ink-600">
                      学历：{{ job.job_min_degree || '不限' }}
                    </span>
                    <span class="text-[11px] px-2 py-0.5 rounded-md bg-page text-ink-600">
                      年限：{{ job.job_min_exp_years != null ? job.job_min_exp_years + ' 年' : '不限' }}
                    </span>
                    <span v-if="job.job_required_skills?.length" class="text-[11px] px-2 py-0.5 rounded-md bg-page text-ink-600">
                      技能：{{ job.job_required_skills.join(' / ') }}
                    </span>
                    <span v-if="job.bonus_items?.length" class="text-[11px] px-2 py-0.5 rounded-md bg-warn-soft text-warn">
                      加分项 {{ job.bonus_items.length }} 项
                    </span>
                    <button type="button" class="text-[11px] text-brand-600 hover:text-brand-700 font-medium" @click="openHardDrawer(job)">
                      查看全部
                    </button>
                  </div>
                </td>
                <td class="px-4 py-4">
                  <span class="text-sm text-ink-600">{{ groupCounts[job.job_id] ?? 0 }}</span>
                  <span class="text-[11px] text-ink-400"> 份</span>
                </td>
                <td class="px-4 py-4">
                  <button
                    type="button"
                    class="text-[11px] px-2.5 py-1 rounded-full hover:opacity-80"
                    :class="job.job_status === 1 ? 'bg-good-soft text-good' : 'bg-page text-ink-500'"
                    @click="toggleJob(job)"
                  >{{ ['草稿', '招聘中', '已关闭'][job.job_status] }}</button>
                </td>
                <td class="px-5 py-4">
                  <div class="flex items-center justify-end gap-1.5">
                    <el-button size="small" @click="openGroup(job)">简历分组</el-button>
                    <el-button size="small" type="primary" plain @click="openJobEdit(job)">编辑</el-button>
                    <el-popconfirm :title="`删除岗位「${job.job_name}」？历史筛选结果保留。`" @confirm="doDeleteJob(job)">
                      <template #reference><el-button size="small" type="danger" plain>删除</el-button></template>
                    </el-popconfirm>
                  </div>
                </td>
              </tr>
              <tr v-if="!jobs.length">
                <td colspan="6" class="px-5 py-14 text-center">
                  <p class="text-sm text-ink-500">该需求下还没有岗位</p>
                  <p class="text-xs text-ink-400 mt-1">点击右上角「新增岗位」为本次招聘添加岗位与硬性条件</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 需求编辑弹窗 -->
    <el-dialog v-model="dialog" :title="editing ? '编辑需求' : '新增招聘需求'" width="560px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="需求名称" required>
          <el-input v-model="form.requirement_name" placeholder="例如：云计算事业部 2026Q4 招聘" />
        </el-form-item>
        <el-form-item label="用人部门">
          <el-input v-model="form.dept" placeholder="例如：云计算事业部" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="需求说明">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="招聘背景、岗位方向等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="submit">{{ editing ? '保存' : '创建需求' }}</el-button>
      </template>
    </el-dialog>

    <!-- 岗位编辑弹窗 -->
    <el-dialog v-model="jobDialog" :title="jobEditing ? '编辑岗位 · ' + (selected?.requirement_name ?? '') : '新增岗位 · ' + (selected?.requirement_name ?? '')" width="680px">
      <el-form :model="jobForm" label-width="110px">
        <div class="grid grid-cols-2 gap-x-4">
          <el-form-item label="岗位编号">
            <el-input v-model="jobForm.job_code" placeholder="例如：A岗位" />
          </el-form-item>
          <el-form-item label="岗位名称" required>
            <el-input v-model="jobForm.job_name" placeholder="例如：后端开发工程师" />
          </el-form-item>
          <el-form-item label="招聘人数">
            <el-input-number v-model="jobForm.headcount" :min="1" style="width: 100%" />
          </el-form-item>
          <el-form-item label="岗位状态">
            <el-select v-model="jobForm.job_status">
              <el-option label="草稿" :value="0" />
              <el-option label="招聘中" :value="1" />
              <el-option label="已关闭" :value="2" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="岗位 JD">
          <el-input v-model="jobForm.job_jd" type="textarea" :rows="3"
            placeholder="粘贴岗位 JD 原文，便于系统理解岗位职责、任职要求与加分方向" />
        </el-form-item>
        <div class="rounded-xl bg-page p-4 space-y-4">
          <div class="text-xs font-medium text-ink-600">岗位硬性条件（初筛判定依据）</div>
          <div class="grid grid-cols-2 gap-x-4">
            <el-form-item label="学历要求">
              <el-select v-model="jobForm.job_min_degree" clearable placeholder="不限">
                <el-option v-for="d in DEGREES" :key="d" :label="d" :value="d" />
              </el-select>
            </el-form-item>
            <el-form-item label="工作年限">
              <el-select v-model="jobForm.job_min_exp_years" clearable placeholder="不限">
                <el-option v-for="y in YEARS" :key="y" :label="y + ' 年'" :value="y" />
              </el-select>
            </el-form-item>
            <el-form-item label="专业方向">
              <el-input v-model="jobForm.major" placeholder="例如：计算机 / 软件工程" />
            </el-form-item>
            <el-form-item label="核心技术">
              <el-select v-model="jobForm.job_required_skills" multiple filterable allow-create
                default-first-option placeholder="输入后回车添加" style="width: 100%" />
            </el-form-item>
          </div>
        </div>
        <div class="rounded-xl bg-page p-4 space-y-4 mt-4">
          <div class="text-xs font-medium text-ink-600">加分项（不参与硬性条件初筛判定）</div>
          <div class="grid grid-cols-2 gap-x-4">
            <el-form-item label="加分技能">
              <el-select v-model="jobForm.job_optional_skills" multiple filterable allow-create
                default-first-option placeholder="如 Redis、Kafka" style="width: 100%" />
            </el-form-item>
            <el-form-item label="行业经验">
              <el-input v-model="bonusIndustry" placeholder="例如：企业服务 SaaS 经验" />
            </el-form-item>
          </div>
          <el-form-item label="语言能力" label-width="110px">
            <el-input v-model="bonusLang" placeholder="例如：英语可读写技术文档" />
          </el-form-item>
        </div>
        <p class="text-xs text-ink-400 mt-3">
          提示：硬性条件由系统在初筛中逐条判定，不满足时自动标记未通过并给出原因；加分项仅作匹配参考，不参与一票否决。
        </p>
      </el-form>
      <template #footer>
        <el-button @click="jobDialog = false">取消</el-button>
        <el-button type="primary" @click="submitJob">{{ jobEditing ? '保存岗位' : '创建并招聘' }}</el-button>
      </template>
    </el-dialog>

    <!-- 硬性条件抽屉 -->
    <el-drawer v-model="hardDrawer" size="460px" :title="`岗位硬性条件 — ${hardViewing?.job_name ?? ''}`">
      <div v-if="hardViewing" class="space-y-3">
        <div class="rounded-xl bg-brand-50/60 border border-brand-100 p-4">
          <p class="text-xs text-brand-700 leading-relaxed">
            以下为岗位硬性条件，全部通过才判定为初筛通过；缺失关键字段时系统将转为待 HR 人工复核。加分项不参与硬性判定，仅作匹配参考。
          </p>
        </div>
        <div class="rounded-xl border border-hairline p-4">
          <div class="flex items-center gap-1.5">
            <el-icon class="text-ink-400" :size="16"><Document /></el-icon>
            <span class="text-sm font-medium text-ink-900">岗位 JD</span>
          </div>
          <p class="text-xs text-ink-500 mt-2 leading-relaxed whitespace-pre-wrap">{{ hardViewing.job_jd || '未填写' }}</p>
        </div>
        <div class="text-xs font-medium text-ink-500 mt-3">硬性条件</div>
        <div v-for="(item, i) in hardItems(hardViewing)" :key="i"
          class="rounded-xl border border-hairline p-4">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-ink-900">{{ item.label }}</span>
            <span class="text-[11px] px-2 py-0.5 rounded-full"
              :class="item.required ? 'bg-critical-soft text-critical' : 'bg-page text-ink-500'">
              {{ item.required ? '硬性' : '参考' }}
            </span>
          </div>
          <p class="text-xs text-ink-500 mt-2 leading-relaxed">{{ item.value }}</p>
        </div>
      </div>
    </el-drawer>

    <!-- 需求池抽屉 -->
    <el-drawer v-model="poolDrawer" size="56%" :title="`需求池 — ${poolRequirement?.requirement_name ?? ''}`">
      <el-alert type="info" :closable="false" class="mb-3"
        title="本需求下上传的全部简历（含未分配、各流转状态）。" />
      <el-table :data="poolResumes" size="small" border max-height="480">
        <el-table-column prop="resume_id" label="ID" width="60" />
        <el-table-column prop="original_file_name" label="简历" min-width="220" />
        <el-table-column prop="status_label" label="当前状态" width="110" />
        <el-table-column prop="failure_reason" label="说明" min-width="180" show-overflow-tooltip />
      </el-table>
    </el-drawer>

    <!-- 简历分组抽屉（分配结果 + 手动调整） -->
    <el-drawer v-model="groupDrawer" size="64%" :title="`简历分组 — ${groupJob?.job_name ?? ''}`">
      <div v-if="groupJob">
        <el-alert type="info" :closable="false" class="mb-3"
          title="需求池简历全量进入每个开放岗位组筛选：任一岗位通过即待审核，全部岗位都不通过才筛出。岗位是否满足由初筛规则判定，命中技能仅作参考；HR 可手动调整后重筛。" />
        <div class="flex items-center gap-2 mb-3">
          <el-button type="primary" size="small" @click="showAddDialog = true">➕ 从简历库添加</el-button>
          <el-button type="success" size="small" :loading="screening" @click="doScreenGroup">
            🎯 执行硬性初筛（组内 {{ groupResumes.length }} 份）
          </el-button>
        </div>
        <el-table :data="groupResumes" size="small" border max-height="420">
          <el-table-column prop="resume_id" label="ID" width="60" />
          <el-table-column prop="original_file_name" label="简历" min-width="200" />
          <el-table-column prop="status_label" label="当前状态" width="110" />
          <el-table-column label="分配来源" width="100">
            <template #default="{ row }">
              <el-tag :type="row.added_by === 'auto:assignment' ? 'success' : 'warning'" size="small">
                {{ row.added_by === 'auto:assignment' ? '自动分配' : '手动添加' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="命中技能" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ hitText(row.match_detail) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-popconfirm title="移出该岗位组？" @confirm="doRemove(row.resume_id)">
                <template #reference><el-button link type="danger">移出</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- 从简历库添加 -->
    <el-dialog v-model="showAddDialog" title="从简历库选择简历加入分组" width="72%" @open="loadLibrary">
      <el-form inline>
        <el-form-item label="状态">
          <el-select v-model="libraryFilter" clearable placeholder="可筛简历" style="width: 160px" @change="loadLibrary">
            <el-option label="待审核入库" :value="10" />
            <el-option label="待初筛" :value="9" />
            <el-option label="待补录" :value="5" />
            <el-option label="待人工复核" :value="6" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-table :data="library" size="small" border max-height="380" @selection-change="(s: ResumeBrief[]) => (picked = s)">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="resume_id" label="ID" width="60" />
        <el-table-column prop="original_file_name" label="简历" min-width="220" />
        <el-table-column prop="status_label" label="状态" width="110" />
      </el-table>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!picked.length" @click="doAddToGroup">加入分组（{{ picked.length }} 份）</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Briefcase, Delete, Document, EditPen, Files, FolderOpened, Plus, Tickets, VideoPlay,
} from '@element-plus/icons-vue'
import {
  addToJobGroup, createJob, createRequirement, deleteJob, deleteRequirement, getUsername, listJobGroup,
  listJobs, listRequirementPool, listRequirements, listResumes, reassignRequirement, removeFromJobGroup,
  screenJobGroup, updateJob, updateRequirement,
} from '../api'
import { toast } from '../components/toast'
import type { BonusItem, GroupResumeBrief, Job, Requirement, ResumeBrief } from '../types'

const DEGREES = ['大专', '本科', '硕士', '博士']
const YEARS = [1, 2, 3, 4, 5, 6, 8, 10]
const router = useRouter()

// ---------------- 需求 ----------------
const requirements = ref<Requirement[]>([])
const selected = ref<Requirement | null>(null)
const dialog = ref(false)
const editing = ref<Requirement | null>(null)
const form = reactive({
  requirement_name: '', dept: '' as string | null, deadline: '' as string | null,
  description: '' as string | null,
})

const jobTotal = computed(() => requirements.value.reduce((s, r) => s + (r.job_count ?? 0), 0))
const resumeTotal = computed(() => requirements.value.reduce((s, r) => s + (r.resume_count ?? 0), 0))
const openJobs = computed(() => jobs.value.filter((j) => j.job_status === 1))

// 统计卡点击定位：滚动到需求列表并轻微高亮
const listSection = ref<HTMLElement | null>(null)
function focusList() {
  listSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function load() {
  try {
    requirements.value = await listRequirements()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '需求列表加载失败'), 'error')
    return
  }
  if (selected.value && !requirements.value.some((r) => r.requirement_id === selected.value!.requirement_id)) {
    selected.value = null
    jobs.value = []
  }
  if (!selected.value && requirements.value.length) await select(requirements.value[0])
}

function openCreate() {
  editing.value = null
  Object.assign(form, { requirement_name: '', dept: '', deadline: '', description: '' })
  dialog.value = true
}

function openEdit(r: Requirement) {
  editing.value = r
  Object.assign(form, {
    requirement_name: r.requirement_name, dept: r.dept, deadline: r.deadline, description: r.description,
  })
  dialog.value = true
}

async function submit() {
  if (!form.requirement_name.trim()) return toast('请填写需求名称', 'error')
  try {
    if (editing.value) {
      await updateRequirement(editing.value.requirement_id, {
        requirement_name: form.requirement_name, dept: form.dept || null,
        deadline: form.deadline || null, description: form.description,
        status: editing.value.status, created_by: editing.value.created_by,
      })
      toast('需求已保存')
    } else {
      const created = await createRequirement({
        requirement_name: form.requirement_name, dept: form.dept || null,
        deadline: form.deadline || null, description: form.description,
      })
      toast('需求已创建，请继续添加岗位与硬性条件')
      selected.value = created
    }
    dialog.value = false
    await load()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '保存失败'), 'error')
  }
}

async function doDelete(r: Requirement) {
  try {
    await deleteRequirement(r.requirement_id)
    toast('需求已删除', 'warn')
    await load()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '删除失败'), 'error')
  }
}

async function select(r: Requirement) {
  selected.value = r
  try {
    jobs.value = (await listJobs()).filter((j) => j.requirement_id === r.requirement_id)
    await reloadGroupCounts()
  } catch (e) {
    jobs.value = []
    toast(((e as { friendly?: string }).friendly ?? '岗位加载失败'), 'error')
  }
}

// ---------------- 需求池 ----------------
const poolDrawer = ref(false)
const poolRequirement = ref<Requirement | null>(null)
const poolResumes = ref<ResumeBrief[]>([])

async function openPool(r: Requirement) {
  poolRequirement.value = r
  poolDrawer.value = true
  poolResumes.value = await listRequirementPool(r.requirement_id)
}

// ---------------- 岗位 ----------------
const jobs = ref<Job[]>([])
const jobDialog = ref(false)
const jobEditing = ref<Job | null>(null)
const hardDrawer = ref(false)
const hardViewing = ref<Job | null>(null)
const reassigning = ref(false)
const bonusIndustry = ref('')
const bonusLang = ref('')
const jobForm = reactive({
  job_code: '' as string | null, job_name: '', headcount: 1 as number | null,
  job_jd: '', job_status: 1,
  job_min_degree: null as string | null, job_min_exp_years: null as number | null,
  major: '' as string | null,
  job_required_skills: [] as string[], job_optional_skills: [] as string[],
})

const groupCounts = ref<Record<number, number>>({})

async function reloadGroupCounts() {
  const counts: Record<number, number> = {}
  try {
    await Promise.all(jobs.value.map(async (j) => {
      counts[j.job_id] = (await listJobGroup(j.job_id)).length
    }))
    groupCounts.value = counts
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '分组数量加载失败'), 'error')
  }
}

async function doReassign() {
  if (!selected.value) return
  reassigning.value = true
  try {
    const res = await reassignRequirement(selected.value.requirement_id)
    toast(`已重新分配 ${res.total_resumes} 份简历到 ${res.assigned_jobs} 个岗位并完成初筛`)
    await select(selected.value)
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '重新分配失败'), 'error')
  } finally {
    reassigning.value = false
  }
}

function openJobCreate() {
  if (!selected.value) return
  jobEditing.value = null
  Object.assign(jobForm, {
    job_code: '', job_name: '', headcount: 1, job_jd: '', job_status: 1,
    job_min_degree: null, job_min_exp_years: null, major: '',
    job_required_skills: [], job_optional_skills: [],
  })
  bonusIndustry.value = ''
  bonusLang.value = ''
  jobDialog.value = true
}

function openJobEdit(job: Job) {
  jobEditing.value = job
  Object.assign(jobForm, {
    job_code: job.job_code, job_name: job.job_name, headcount: job.headcount ?? 1,
    job_jd: job.job_jd, job_status: job.job_status,
    job_min_degree: job.job_min_degree, job_min_exp_years: job.job_min_exp_years,
    major: job.major,
    job_required_skills: [...(job.job_required_skills || [])],
    job_optional_skills: [...(job.job_optional_skills || [])],
  })
  const industry = job.bonus_items?.find((b) => b.label === '行业经验')
  const lang = job.bonus_items?.find((b) => b.label === '语言能力')
  bonusIndustry.value = industry?.value ?? ''
  bonusLang.value = lang?.value ?? ''
  jobDialog.value = true
}

function bonusItemsOf(): BonusItem[] {
  const items: BonusItem[] = []
  if (bonusIndustry.value.trim()) items.push({ label: '行业经验', value: bonusIndustry.value.trim() })
  if (bonusLang.value.trim()) items.push({ label: '语言能力', value: bonusLang.value.trim() })
  return items
}

async function submitJob() {
  if (!selected.value) return
  if (!jobForm.job_name.trim()) return toast('请填写岗位名称', 'error')
  const base = {
    ...jobForm,
    requirement_id: selected.value.requirement_id,
    bonus_items: bonusItemsOf(),
    job_created_by: jobEditing.value?.job_created_by ?? getUsername(),
  }
  try {
    if (jobEditing.value) {
      await updateJob(jobEditing.value.job_id, base as Partial<Job>)
      toast('岗位已更新')
    } else {
      await createJob({ ...base, job_status: 1 } as Partial<Job>)
      toast('岗位已创建并开始招聘，硬性条件已同步至初筛规则')
    }
    jobDialog.value = false
    await select(selected.value)
    load()
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '保存失败'), 'error')
  }
}

async function toggleJob(job: Job) {
  const next = job.job_status === 1 ? 2 : job.job_status === 2 ? 1 : 1
  try {
    await updateJob(job.job_id, {
      requirement_id: job.requirement_id, job_code: job.job_code, job_name: job.job_name,
      headcount: job.headcount, major: job.major, job_jd: job.job_jd,
      job_min_degree: job.job_min_degree, job_min_exp_years: job.job_min_exp_years,
      job_required_skills: job.job_required_skills, job_optional_skills: job.job_optional_skills,
      bonus_items: job.bonus_items, job_status: next, job_created_by: job.job_created_by,
    })
    toast(next === 1 ? '岗位已恢复招聘' : '岗位已暂停招聘', next === 1 ? 'success' : 'warn')
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '岗位状态更新失败'), 'error')
  }
  if (selected.value) await select(selected.value)
}

async function doDeleteJob(job: Job) {
  try {
    await deleteJob(job.job_id)
    toast('岗位已删除（历史筛选结果保留）', 'warn')
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '岗位删除失败'), 'error')
  }
  if (selected.value) await select(selected.value)
}

function hardItems(job: Job): { label: string; value: string; required: boolean }[] {
  const items = [
    { label: '学历', value: job.job_min_degree || '不限', required: true },
    { label: '工作年限', value: job.job_min_exp_years != null ? `${job.job_min_exp_years} 年` : '不限', required: true },
    { label: '专业方向', value: job.major || '不限', required: false },
    { label: '核心技术', value: job.job_required_skills?.join(' / ') || '无', required: true },
  ]
  return items.concat((job.bonus_items || []).map((b) => ({ label: b.label, value: b.value, required: false })))
}

function openHardDrawer(job: Job) {
  hardViewing.value = job
  hardDrawer.value = true
}

// ---------------- 简历分组 ----------------
const groupDrawer = ref(false)
const groupJob = ref<Job | null>(null)
const groupResumes = ref<GroupResumeBrief[]>([])
const showAddDialog = ref(false)
const library = ref<ResumeBrief[]>([])
const libraryFilter = ref<number | null>(null)
const picked = ref<ResumeBrief[]>([])
const screening = ref(false)

function hitText(detail: GroupResumeBrief['match_detail']): string {
  if (!detail) return '—'
  const parts = [...(detail.required_hits || []), ...(detail.optional_hits || [])]
  if (detail.note) return detail.note
  return parts.length ? parts.join('、') : '—'
}

async function openGroup(job: Job) {
  groupJob.value = job
  groupDrawer.value = true
  await reloadGroup()
}

async function reloadGroup() {
  if (!groupJob.value) return
  groupResumes.value = await listJobGroup(groupJob.value.job_id)
  reloadGroupCounts()
}

async function loadLibrary() {
  try {
    const all = await listResumes(libraryFilter.value ?? undefined)
    // 待筛选池：排除失败（0/1/2）、已判定（3/4）与处理中（7/8），只留待推进的简历
    library.value = libraryFilter.value == null
      ? all.filter((r) => ![0, 1, 2, 3, 4, 7, 8].includes(r.status))
      : all
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '简历库加载失败'), 'error')
  }
}

async function doAddToGroup() {
  if (!groupJob.value || !picked.value.length) return
  const res = await addToJobGroup(groupJob.value.job_id, picked.value.map((p) => p.resume_id))
  toast(`已加入 ${res.added} 份${res.skipped_duplicated ? `（${res.skipped_duplicated} 份已在组中跳过）` : ''}`)
  showAddDialog.value = false
  picked.value = []
  reloadGroup()
}

async function doRemove(resumeId: number) {
  if (!groupJob.value) return
  await removeFromJobGroup(groupJob.value.job_id, resumeId)
  reloadGroup()
}

async function doScreenGroup() {
  if (!groupJob.value) return
  screening.value = true
  try {
    const run = await screenJobGroup(groupJob.value.job_id)
    toast(`初筛完成：${run.passed} 通过 / ${run.rejected} 拒绝 / ${run.pending_review} 待复核`)
    reloadGroup()
    router.push('/results')
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '初筛执行失败'), 'error')
  } finally {
    screening.value = false
  }
}

onMounted(load)
</script>
