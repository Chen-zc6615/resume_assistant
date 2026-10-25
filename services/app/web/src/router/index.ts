import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录', public: true } },
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '工作台' } },
    { path: '/requirements', name: 'requirements', component: () => import('../views/RequirementManagementView.vue'), meta: { title: '需求岗位管理' } },
    { path: '/upload', name: 'upload', component: () => import('../views/UploadView.vue'), meta: { title: '简历上传' } },
    { path: '/results', name: 'results', component: () => import('../views/ScreeningResultView.vue'), meta: { title: '筛选结果查看' } },
    { path: '/talent', name: 'talent', component: () => import('../views/TalentPoolView.vue'), meta: { title: '人才库管理' } },
    { path: '/tasks', name: 'tasks', component: () => import('../views/TaskView.vue'), meta: { title: '任务' } },
    { path: '/tasks/:taskId', name: 'task-detail', component: () => import('../views/TaskDetailView.vue'), meta: { title: '任务对话' } },
    // 功能保留页（不在主导航，URL 直达）
    { path: '/library', name: 'library', component: () => import('../views/LibraryView.vue'), meta: { title: '简历库' } },
    { path: '/screening', name: 'screening', component: () => import('../views/ScreeningConfigView.vue'), meta: { title: '筛选配置' } },
  ],
})

// 登录守卫：未持令牌一律先登录；已登录访问 /login 时回工作台
router.beforeEach((to) => {
  const loggedIn = !!getToken()
  if (!to.meta.public && !loggedIn) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && loggedIn) return { name: 'dashboard' }
  return true
})

export default router
