import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '工作台' } },
    { path: '/requirements', name: 'requirements', component: () => import('../views/RequirementManagementView.vue'), meta: { title: '需求岗位管理' } },
    { path: '/upload', name: 'upload', component: () => import('../views/UploadView.vue'), meta: { title: '简历上传' } },
    { path: '/results', name: 'results', component: () => import('../views/ScreeningResultView.vue'), meta: { title: '筛选结果查看' } },
    { path: '/talent', name: 'talent', component: () => import('../views/TalentPoolView.vue'), meta: { title: '人才库管理' } },
    // 功能保留页（不在主导航，URL 直达）
    { path: '/library', name: 'library', component: () => import('../views/LibraryView.vue'), meta: { title: '简历库' } },
    { path: '/screening', name: 'screening', component: () => import('../views/ScreeningConfigView.vue'), meta: { title: '筛选配置' } },
  ],
})

export default router
