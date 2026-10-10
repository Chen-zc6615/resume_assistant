<template>
  <div class="fixed top-20 right-6 z-[300] flex flex-col gap-3 items-end pointer-events-none">
    <div
      v-for="t in items"
      :key="t.id"
      class="toast-in pointer-events-auto bg-white border shadow-lg shadow-slate-900/5 rounded-xl px-4 py-3 flex items-start gap-3 max-w-sm"
      :class="ringOf(t.type)"
    >
      <el-icon :size="18" :color="colorOf(t.type)" style="margin-top: 2px">
        <component :is="iconOf(t.type)" />
      </el-icon>
      <div class="text-sm text-slate-700 leading-snug">{{ t.message }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CircleCheckFilled, InfoFilled, WarningFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { useToasts, type ToastItem } from './toast'

const items = useToasts()

const iconOf = (t: ToastItem['type']) =>
  ({ success: CircleCheckFilled, info: InfoFilled, warn: WarningFilled, error: CircleCloseFilled })[t]
const colorOf = (t: ToastItem['type']) =>
  ({ success: '#059669', info: '#2563eb', warn: '#d97706', error: '#e11d48' })[t]
const ringOf = (t: ToastItem['type']) =>
  ({ success: 'border-emerald-100', info: 'border-blue-100', warn: 'border-amber-100', error: 'border-rose-100' })[t]
</script>

<style scoped>
.toast-in { animation: toastIn 0.25s ease both; }
@keyframes toastIn {
  from { opacity: 0; transform: translateX(18px); }
  to { opacity: 1; transform: translateX(0); }
}
</style>
