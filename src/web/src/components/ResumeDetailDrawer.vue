<template>
  <el-drawer :model-value="visible" size="52%" :title="`简历详情 #${resume?.resume_id ?? ''}`" @close="emit('close')">
    <div v-if="resume">
      <el-tabs v-model="tab" class="detail">
        <el-tab-pane label="📄 原始简历" name="pdf">
          <iframe :src="fileUrl(resume.resume_id)" class="pdf-frame" />
          <div class="pdf-tip">无法显示？<el-link type="primary" :href="fileUrl(resume.resume_id)" target="_blank">新窗口打开原始 PDF</el-link></div>
        </el-tab-pane>        <el-tab-pane label="📋 归一化数据" name="data">
          <el-descriptions :column="2" border size="small" class="page-card">
            <el-descriptions-item label="文件名">{{ resume.original_file_name }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <StatusTag :status="resume.status" :label="resume.status_label" />
            </el-descriptions-item>
            <el-descriptions-item label="上传人">{{ resume.uploaded_by }}</el-descriptions-item>
            <el-descriptions-item label="上传时间">{{ resume.created_at }}</el-descriptions-item>
            <el-descriptions-item label="失败原因" :span="2">
              <span class="fail">{{ resume.failure_reason || '—' }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <template v-if="resume.profile">
            <h4 class="section">基本信息</h4>
            <el-descriptions :column="2" border size="small" class="page-card">
              <el-descriptions-item label="姓名">{{ resume.profile.name }}</el-descriptions-item>
              <el-descriptions-item label="性别">{{ genderLabel }}</el-descriptions-item>
              <el-descriptions-item label="电话">{{ resume.profile.phone || '（缺失，待补录）' }}</el-descriptions-item>
              <el-descriptions-item label="邮箱">{{ resume.profile.email || '（缺失，待补录）' }}</el-descriptions-item>
              <el-descriptions-item label="最高学历">{{ resume.profile.highest_education || '—' }}</el-descriptions-item>
              <el-descriptions-item label="毕业院校">{{ resume.profile.graduation_institution || '—' }}</el-descriptions-item>
              <el-descriptions-item label="工作月数">{{ resume.profile.total_work_months ?? '未知' }}</el-descriptions-item>
              <el-descriptions-item label="技能">
                <el-tag v-for="s in resume.profile.skills" :key="s" size="small" class="skill">{{ s }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>

            <h4 class="section">教育经历</h4>
            <el-table :data="resume.profile.education_experiences" size="small" border class="page-card">
              <el-table-column prop="school" label="学校" />
              <el-table-column prop="major" label="专业" />
              <el-table-column prop="education_level" label="学历" width="70" />
              <el-table-column prop="start_date" label="入学" width="90" />
              <el-table-column prop="end_date" label="毕业" width="90">
                <template #default="{ row }">{{ row.end_date || (row.is_current ? '在读' : '—') }}</template>
              </el-table-column>
            </el-table>

            <h4 class="section">工作经历</h4>
            <el-table :data="resume.profile.work_experiences" size="small" border class="page-card">
              <el-table-column prop="company" label="公司" />
              <el-table-column prop="position" label="职位" />
              <el-table-column prop="start_date" label="开始" width="90" />
              <el-table-column label="结束" width="90">
                <template #default="{ row }">{{ row.end_date || (row.is_current ? '在职' : '—') }}</template>
              </el-table-column>
              <el-table-column prop="description" label="描述" show-overflow-tooltip />
            </el-table>

            <h4 class="section">项目经历</h4>
            <el-table :data="resume.profile.project_experiences" size="small" border class="page-card">
              <el-table-column prop="project_name" label="项目" />
              <el-table-column prop="role" label="角色" width="120" />
              <el-table-column prop="start_date" label="开始" width="90" />
              <el-table-column prop="end_date" label="结束" width="90" />
              <el-table-column prop="description" label="描述" show-overflow-tooltip />
            </el-table>
          </template>
          <el-empty v-else description="尚无归一化数据（解析/归一化未完成）——可切换到「原始简历」标签直接查看 PDF" :image-size="80" />
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ResumeDetail } from '../types'
import { resumeFileUrl } from '../api'
import StatusTag from './StatusTag.vue'

const props = defineProps<{ visible: boolean; resume: ResumeDetail | null }>()
const emit = defineEmits<{ close: [] }>()
const tab = ref('pdf')

const genderLabel = computed(() => {
  const g = props.resume?.profile?.gender
  return g === 0 ? '男' : g === 1 ? '女' : '未知'
})

const fileUrl = resumeFileUrl
</script>

<style scoped>
.section { margin: 14px 0 8px; }
.skill { margin-right: 4px; }
.fail { color: var(--el-color-danger); }
.pdf-frame { width: 100%; height: 82vh; border: 1px solid var(--el-border-color); border-radius: 4px; }
.pdf-tip { margin-top: 6px; font-size: 12px; color: #909399; text-align: center; }
</style>
