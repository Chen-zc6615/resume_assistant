<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: number; label: string }>()

const tagType = computed(() => {
  // 成功类绿色、失败类红色、中间态橙色/灰色
  if (props.status === 4 || props.status === 9 || props.status === 10) return 'success'
  if (props.status === 0 || props.status === 1 || props.status === 2 || props.status === 3) return 'danger'
  if (props.status === 5 || props.status === 6) return 'warning'
  return 'info'
})
</script>
