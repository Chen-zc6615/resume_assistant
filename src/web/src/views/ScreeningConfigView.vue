<template>
  <div>
    <el-card class="page-card">
      <h2 class="page-title">🎯 筛选配置</h2>
      <p class="page-desc">
        从岗位硬性条件派生筛选模板并执行批量初筛。
        需求与岗位的维护在
        <el-link type="primary" @click="router.push('/requirements')">需求管理</el-link>
        页面完成。
      </p>

      <h3>岗位列表</h3>
      <el-table :data="jobs" size="small" border max-height="260">
        <el-table-column prop="job_id" label="ID" width="60" />
        <el-table-column label="需求" min-width="140">
          <template #default="{ row }">{{ requirementName(row.requirement_id) }}</template>
        </el-table-column>
        <el-table-column prop="job_name" label="岗位" min-width="160" />
        <el-table-column label="硬性条件" min-width="260">
          <template #default="{ row }">
            {{ row.job_min_degree ?? '学历不限' }} · {{ row.job_min_exp_years ?? '年限不限' }}年+ ·
            {{ (row.job_required_skills || []).join(' / ') || '无必备技能' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openTemplate(row)">生成筛选模板</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="page-card">
      <h3>筛选模板</h3>
      <el-table :data="templates" size="small" border max-height="280">
        <el-table-column prop="template_id" label="ID" width="60" />
        <el-table-column prop="template_name" label="模板名" min-width="180" />
        <el-table-column prop="job_id" label="岗位" width="70" />
        <el-table-column label="规则" min-width="280">
          <template #default="{ row }">
            {{ row.rules.min_degree ?? '学历不限' }} · {{ row.rules.min_exp_years ?? '年限不限' }}年+ ·
            {{ row.rules.required_skills.join(' / ') || '无' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="run(row.template_id)">▶ 执行筛选</el-button>
            <el-popconfirm title="删除该模板？历史筛选任务与其结果会保留。" @confirm="doDeleteTemplate(row.template_id)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="tplDialog" title="生成筛选模板" width="480px">
      <el-form :model="tplForm" label-width="110px">
        <el-form-item label="模板名称">
          <el-input v-model="tplForm.template_name" />
        </el-form-item>
        <el-form-item label="最低学历">
          <el-select v-model="tplForm.min_degree" clearable placeholder="不限">
            <el-option v-for="d in DEGREES" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="最低年限">
          <el-input-number v-model="tplForm.min_exp_years" :min="0" :max="50" />
        </el-form-item>
        <el-form-item label="必备技能">
          <el-select v-model="tplForm.required_skills" multiple filterable allow-create
            default-first-option style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tplDialog = false">取消</el-button>
        <el-button type="primary" @click="submitTemplate">保存模板</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { createRun, createTemplate, deleteTemplate, listJobs, listRequirements, listTemplates } from '../api'
import type { FilterTemplate, Job, Requirement } from '../types'

const DEGREES = ['大专', '本科', '硕士', '博士']
const router = useRouter()

const jobs = ref<Job[]>([])
const requirements = ref<Requirement[]>([])
const templates = ref<FilterTemplate[]>([])
const tplDialog = ref(false)

function requirementName(requirementId: number): string {
  return requirements.value.find((r) => r.requirement_id === requirementId)?.requirement_name ?? `#${requirementId}`
}

const tplForm = reactive({
  template_name: '',
  job_id: 0,
  min_degree: null as string | null,
  min_exp_years: null as number | null,
  required_skills: [] as string[],
})

async function load() {
  jobs.value = await listJobs()
  requirements.value = await listRequirements()
  templates.value = await listTemplates()
}
onMounted(load)

function openTemplate(job: Job) {
  tplForm.template_name = `${job.job_name} - 硬性条件模板`
  tplForm.job_id = job.job_id
  tplForm.min_degree = job.job_min_degree
  tplForm.min_exp_years = job.job_min_exp_years
  tplForm.required_skills = [...(job.job_required_skills || [])]
  tplDialog.value = true
}

async function submitTemplate() {
  await createTemplate({
    template_name: tplForm.template_name,
    job_id: tplForm.job_id,
    rules: {
      min_degree: tplForm.min_degree,
      min_exp_years: tplForm.min_exp_years,
      required_skills: tplForm.required_skills,
    },
  })
  ElMessage.success('模板已保存')
  tplDialog.value = false
  load()
}

async function doDeleteTemplate(id: number) {
  try {
    await deleteTemplate(id)
    ElMessage.success('模板已删除（历史筛选任务保留）')
    load()
  } catch (e: any) {
    ElMessage.error(e.friendly ?? '删除失败，请稍后重试')
  }
}

async function run(templateId: number) {
  try {
    const r = await createRun({ template_id: templateId })
    if (!r.total) {
      ElMessage.warning('该模板关联的岗位组内没有简历——先在需求管理中把简历分入岗位组')
      return
    }
    ElMessage.success(`筛选完成：${r.passed} 通过 / ${r.rejected} 拒绝 / ${r.pending_review} 待复核`)
    router.push('/results')
  } catch (e: any) {
    ElMessage.error(e.friendly ?? '筛选执行失败')
  }
}
</script>
