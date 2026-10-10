/** 全局 Toast（仿原型右上角提示）：模块级状态 + toast() 函数，组件内直接导入使用。 */
import { reactive } from 'vue'

export interface ToastItem {
  id: number
  message: string
  type: 'success' | 'info' | 'warn' | 'error'
}

const items = reactive<ToastItem[]>([])
let nextId = 1

export function toast(message: string, type: ToastItem['type'] = 'success') {
  const id = nextId++
  items.push({ id, message, type })
  setTimeout(() => {
    const idx = items.findIndex((t) => t.id === id)
    if (idx > -1) items.splice(idx, 1)
  }, 3200)
}

export function useToasts() {
  return items
}
