<template>
  <el-table :data="rows" size="small" border max-height="480">
    <el-table-column prop="resume_id" label="ID" width="60" />
    <el-table-column prop="name" label="姓名" width="90" />
    <el-table-column prop="original_file_name" label="文件名" min-width="200" show-overflow-tooltip />
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="reasons">
          <div v-for="(r, i) in row.reasons" :key="i" class="reason">
            <el-tag size="small" :type="r.passed === true ? 'success' : r.passed === false ? 'danger' : 'warning'">
              {{ r.passed === true ? '通过' : r.passed === false ? '未通过' : '信息不足' }}
            </el-tag>
            <b>{{ r.rule }}</b>：{{ r.detail }}
          </div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="判定明细" min-width="280">
      <template #default="{ row }">
        <span class="summary">{{ row.reasons.map((r: any) => r.rule).join(' · ') }}</span>
      </template>
    </el-table-column>
    <el-table-column label="简历" width="100" fixed="right">
      <template #default="{ row }">
        <el-link type="primary" :href="resumeFileUrl(row.resume_id)" target="_blank">查看</el-link>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { FilterResult } from '../types'
import { resumeFileUrl } from '../api'

defineProps<{ rows: FilterResult[] }>()
</script>

<style scoped>
.reasons { padding: 8px 20px; }
.reason { margin: 4px 0; display: flex; align-items: center; gap: 8px; }
.summary { color: #909399; font-size: 12px; }
</style>
