<template>
  <div>
    <el-card class="page-card">
      <h2 class="page-title">📚 简历库</h2>
      <p class="page-desc">全部简历文件与处理状态；点击查看归一化详情。</p>

      <el-form inline>
        <el-form-item label="状态">
          <el-select v-model="statusFilter" clearable placeholder="全部状态" style="width: 180px"
            @change="load">
            <el-option v-for="(label, code) in STATUS" :key="code" :label="label" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="load">刷新</el-button>
        </el-form-item>
      </el-form>

      <el-row :gutter="12" class="stats">
        <el-col :span="8"><el-statistic title="简历总数" :value="stats.total ?? 0" /></el-col>
        <el-col :span="16">
          <div class="stat-chips">
            <el-tag v-for="(count, label) in stats.by_status" :key="label" size="large" class="chip">
              {{ label }}：{{ count }}
            </el-tag>
          </div>
        </el-col>
      </el-row>

      <el-table :data="rows" size="small" border max-height="520">
        <el-table-column prop="resume_id" label="ID" width="60" />
        <el-table-column prop="original_file_name" label="文件名" min-width="220" />
        <el-table-column prop="status_label" label="状态" width="110">
          <template #default="{ row }">
            <StatusTag :status="row.status" :label="row.status_label" />
          </template>
        </el-table-column>
        <el-table-column prop="failure_reason" label="原因" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><span class="fail">{{ row.failure_reason }}</span></template>
        </el-table-column>
        <el-table-column prop="uploaded_by" label="上传人" width="90" />
        <el-table-column prop="created_at" label="上传时间" width="170" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.resume_id)">详情</el-button>
            <el-button v-if="row.status <= 2" link type="warning" @click="reparse(row.resume_id)">重试解析</el-button>
            <el-popconfirm v-if="row.status === 3"
              title="恢复为待初筛？规则修正后可重新分组筛选。" @confirm="restore(row.resume_id)">
              <template #reference><el-button link type="success">恢复待筛</el-button></template>
            </el-popconfirm>
            <el-popconfirm title="确认删除该简历及全部归一化数据？" @confirm="remove(row.resume_id)">
              <template #reference><el-button link type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <ResumeDetailDrawer :visible="!!detail" :resume="detail" @close="detail = null" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { deleteResume, getResume, listResumes, reparseResume, restoreResume, resumeStats } from '../api'
import type { ResumeBrief, ResumeDetail } from '../types'
import ResumeDetailDrawer from '../components/ResumeDetailDrawer.vue'
import StatusTag from '../components/StatusTag.vue'

// 与后端 STATUS_LABELS 对应
const STATUS: Record<number, string> = {
  0: '上传失败', 1: '解析失败', 2: '归一化失败', 3: '初筛不通过',
  4: '已完成', 5: '待补录', 6: '待人工复核', 7: '待解析', 8: '待归一化',
  9: '待初筛', 10: '待审核入库',
}

const rows = ref<ResumeBrief[]>([])
const stats = ref<{ total?: number; by_status?: Record<string, number> }>({})
// 支持 ?status=4 直达（工作台"已入库"卡片深链）
const route = useRoute()
const statusQuery = Number(route.query.status)
const statusFilter = ref<number | null>(
  Number.isInteger(statusQuery) && statusQuery >= 0 && statusQuery <= 10 ? statusQuery : null,
)
const detail = ref<ResumeDetail | null>(null)

async function load() {
  rows.value = await listResumes(statusFilter.value ?? undefined)
  stats.value = await resumeStats()
}

onMounted(load)

async function openDetail(id: number) {
  try {
    detail.value = await getResume(id)
  } catch (e: any) {
    ElMessage.error(e.friendly ?? '加载详情失败')
  }
}

async function reparse(id: number) {
  await reparseResume(id)
  ElMessage.success('已触发重新解析，稍后刷新查看')
  setTimeout(load, 3000)
}

async function remove(id: number) {
  try {
    await deleteResume(id)
    ElMessage.success('已删除')
    load()
  } catch (e: any) {
    ElMessage.error(e.friendly ?? '删除失败，请稍后重试')
  }
}

async function restore(id: number) {
  try {
    await restoreResume(id)
    ElMessage.success('已恢复为待初筛，可在需求管理中重新分组筛选')
    load()
  } catch (e: any) {
    ElMessage.error(e.friendly ?? '恢复失败，请稍后重试')
  }
}
</script>

<style scoped>
.fail { color: var(--el-color-danger); }
.stats { margin-bottom: 16px; }
.stat-chips { display: flex; flex-wrap: wrap; gap: 6px; padding-top: 18px; }
.chip { font-weight: 500; }
</style>
