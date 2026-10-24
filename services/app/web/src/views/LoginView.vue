<template>
  <div class="min-h-screen bg-page flex items-center justify-center px-4">
    <div class="w-full max-w-sm">
      <!-- 品牌区 -->
      <div class="flex flex-col items-center mb-8">
        <div class="w-14 h-14 rounded-2xl bg-linear-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-xl shadow-blue-900/20">
          <el-icon :size="28"><Search /></el-icon>
        </div>
        <h1 class="mt-4 text-xl font-semibold text-ink-900">简历筛选助手</h1>
        <p class="mt-1.5 text-xs text-ink-400">Resume Screening Copilot · HR 登录</p>
      </div>

      <!-- 登录卡片 -->
      <div class="bg-card rounded-2xl border border-hairline p-7 shadow-sm">
        <el-form @submit.prevent="submit">
          <el-form-item>
            <el-input
              v-model="username"
              size="large"
              placeholder="用户名"
              :disabled="loading"
              autocomplete="username"
            >
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="password"
              size="large"
              type="password"
              placeholder="密码"
              show-password
              :disabled="loading"
              autocomplete="current-password"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <button
            type="submit"
            :disabled="loading || !username.trim() || !password"
            class="mt-1 w-full py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium
                   shadow-lg shadow-brand-600/20 transition-all
                   disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none"
          >
            {{ loading ? '登录中…' : '登 录' }}
          </button>
        </el-form>
        <p class="mt-4 text-center text-[11px] text-ink-400 leading-relaxed">
          初始账号 hr_admin · 详见项目 README
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, Search, User } from '@element-plus/icons-vue'
import { login, setToken } from '../api'
import { toast } from '../components/toast'

defineOptions({ name: 'LoginView' })

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (loading.value || !username.value.trim() || !password.value) return
  loading.value = true
  try {
    const resp = await login({
      username: username.value.trim(),
      password: password.value,
    })
    setToken(resp.session_token)
    toast(`欢迎回来，${resp.user.display_name}`)
    router.replace('/')
  } catch (e) {
    toast(((e as { friendly?: string }).friendly ?? '登录失败，请稍后重试'), 'error')
  } finally {
    loading.value = false
  }
}
</script>
