/** Axios 封装与全部后端接口 */

import axios from 'axios'
import type {
  BatchStatus,
  FilterResult,
  FilterRun,
  FilterTemplate,
  GroupResumeBrief,
  Interview,
  Job,
  Requirement,
  ResumeBrief,
  ResumeDetail,
  ResumeProfileData,
  TalentPoolEntry,
  Task,
  TaskAction,
  TaskDetail,
  TaskMessageResponse,
  UploadResponse,
} from '../types'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

// ---- 登录会话令牌（Bearer，存 localStorage；非 Cookie 模式无 CSRF 面）----
const TOKEN_KEY = 'sr_session_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string | null) => {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

// ---- 登录用户名（上传/筛选等 hr_id 字段用；未登录兜底默认管理员）----
const USERNAME_KEY = 'sr_username'
export const getUsername = () => localStorage.getItem(USERNAME_KEY) || 'hr_admin'
export const setUsername = (name: string | null) => {
  if (name) localStorage.setItem(USERNAME_KEY, name)
  else localStorage.removeItem(USERNAME_KEY)
}

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const detail = err.response?.data?.detail
    if (detail) err.friendly = typeof detail === 'string' ? detail : JSON.stringify(detail)
    // 会话过期/未登录：清除本地态并回登录页（登录接口自身的 401 是凭据错误，不跳转）
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      setToken(null)
      setUsername(null)
      if (location.pathname !== '/login') location.assign('/login')
    }
    return Promise.reject(err)
  },
)

// ---- 认证 ----
export interface LoginResponse {
  user: { user_id: number; username: string; display_name: string }
  session_token: string
  expires_at: string
}

export const login = (payload: { username: string; password: string }) =>
  http.post<LoginResponse>('/auth/login', payload).then((r) => r.data)

export const logout = () => http.post('/auth/logout').then((r) => r.data)

export const authMe = () =>
  http.get<LoginResponse['user']>('/auth/me').then((r) => r.data)

// ---- 简历 ----
export const uploadResumes = (files: File[], hrId: string, requirementId: number) => {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  form.append('hr_id', hrId)
  form.append('requirement_id', String(requirementId))
  return http.post<UploadResponse>('/resumes/upload', form).then((r) => r.data)
}

export const listResumes = (status?: number, limit = 200) =>
  http.get<ResumeBrief[]>('/resumes', {
    params: { ...(status != null ? { status } : {}), limit },
  }).then((r) => r.data)

export const resumeStats = () => http.get('/resumes/stats').then((r) => r.data)

export const getResume = (id: number) => http.get<ResumeDetail>(`/resumes/${id}`).then((r) => r.data)

export const deleteResume = (id: number) => http.delete(`/resumes/${id}`).then((r) => r.data)

export const reparseResume = (id: number) => http.post(`/resumes/${id}/reparse`).then((r) => r.data)

// PDF 访问 URL：带缓存版本参数。
// 服务端已设 no-store，但浏览器磁盘里可能仍残留旧版 attachment 响应；
// 附加 v 参数使 URL 唯一化，强制绕开磁盘缓存。
let fileUrlVersion = Date.now()
export const bumpFileUrlVersion = () => { fileUrlVersion = Date.now() }

export const resumeFileUrl = (id: number) => `/api/resumes/${id}/file?v=${fileUrlVersion}`

export const updateProfile = (id: number, payload: Partial<ResumeProfileData>) =>
  http.patch<ResumeProfileData>(`/resumes/${id}/profile`, payload).then((r) => r.data)

export const confirmResume = (id: number) => http.post(`/resumes/${id}/confirm`).then((r) => r.data)

export const rejectResume = (id: number, reason: string) =>
  http.post(`/resumes/${id}/reject`, { reason }).then((r) => r.data)

export const restoreResume = (id: number) =>
  http.post(`/resumes/${id}/restore`).then((r) => r.data)

export const setInterviewStatus = (id: number, status: number) =>
  http.post(`/resumes/${id}/interview-status`, { status }).then((r) => r.data)

// ---- 人才域（面试邀约 / 沉淀库）----
export const createInterview = (payload: Partial<Interview>) =>
  http.post<Interview>('/talent/interviews', payload).then((r) => r.data)

export const listInterviews = (resumeId?: number) =>
  http.get<Interview[]>('/talent/interviews', { params: resumeId ? { resume_id: resumeId } : {} })
    .then((r) => r.data)

export const addToTalentPool = (resumeId: number, payload: object) =>
  http.post<TalentPoolEntry>(`/talent/pool?resume_id=${resumeId}`, payload).then((r) => r.data)

export const listTalentPool = () =>
  http.get<TalentPoolEntry[]>('/talent/pool').then((r) => r.data)

export const removeFromTalentPool = (poolId: number) =>
  http.delete(`/talent/pool/${poolId}`).then((r) => r.data)

export const syncTalentKnowledge = (poolId: number) =>
  http.post<{ ok: boolean; talent_card_id: string; chunk_count: number }>(
    `/talent/pool/${poolId}/sync-knowledge`,
  ).then((r) => r.data)

export const batchStatus = (batchId: string) =>
  http.get<BatchStatus>(`/parse/${batchId}/status`).then((r) => r.data)

// ---- 需求 ----
export const listRequirements = () =>
  http.get<Requirement[]>('/requirements').then((r) => r.data)
export const createRequirement = (payload: Partial<Requirement>) =>
  http.post<Requirement>('/requirements', payload).then((r) => r.data)
export const updateRequirement = (id: number, payload: Partial<Requirement>) =>
  http.put<Requirement>(`/requirements/${id}`, payload).then((r) => r.data)
export const deleteRequirement = (id: number) =>
  http.delete(`/requirements/${id}`).then((r) => r.data)
export const listRequirementPool = (id: number) =>
  http.get<ResumeBrief[]>(`/requirements/${id}/resumes`).then((r) => r.data)
export const reassignRequirement = (id: number) =>
  http.post(`/requirements/${id}/reassign`).then((r) => r.data)

// ---- 岗位 ----
export const listJobs = () => http.get<Job[]>('/jobs').then((r) => r.data)
export const createJob = (job: Partial<Job>) => http.post<Job>('/jobs', job).then((r) => r.data)
export const updateJob = (id: number, job: Partial<Job>) =>
  http.put<Job>(`/jobs/${id}`, job).then((r) => r.data)
export const deleteJob = (id: number) => http.delete(`/jobs/${id}`).then((r) => r.data)

// ---- 岗位简历分组 ----
export const listJobGroup = (jobId: number) =>
  http.get<GroupResumeBrief[]>(`/jobs/${jobId}/resumes`).then((r) => r.data)

export const addToJobGroup = (jobId: number, resumeIds: number[]) =>
  http.post(`/jobs/${jobId}/resumes`, { resume_ids: resumeIds }).then((r) => r.data)

export const removeFromJobGroup = (jobId: number, resumeId: number) =>
  http.delete(`/jobs/${jobId}/resumes/${resumeId}`).then((r) => r.data)

export const screenJobGroup = (jobId: number) =>
  http.post<FilterRun>(`/jobs/${jobId}/screen`).then((r) => r.data)

// ---- 筛选 ----
export const listTemplates = () =>
  http.get<FilterTemplate[]>('/screening/templates').then((r) => r.data)

export const createTemplate = (payload: { template_name: string; job_id: number; rules: object }) =>
  http.post<FilterTemplate>('/screening/templates', payload).then((r) => r.data)

export const deleteTemplate = (id: number) =>
  http.delete(`/screening/templates/${id}`).then((r) => r.data)

export const listRuns = (limit = 10) =>
  http.get<FilterRun[]>('/screening/runs', { params: { limit } }).then((r) => r.data)

export const createRun = (payload: { template_id: number; resume_ids?: number[] }) =>
  http.post<FilterRun>('/screening/runs', payload).then((r) => r.data)

export const runResults = (runId: number) =>
  http.get<FilterResult[]>(`/screening/runs/${runId}/results`).then((r) => r.data)

export const runExportUrl = (runId: number) => `/api/screening/runs/${runId}/export.csv`

// ---- 任务 ----
export const listTasks = () => http.get<Task[]>('/tasks').then((r) => r.data)

export const createTask = (title?: string) =>
  http.post<Task>('/tasks', { title: title || null }).then((r) => r.data)

export const getTask = (taskId: number) =>
  http.get<TaskDetail>(`/tasks/${taskId}`).then((r) => r.data)

export const renameTask = (taskId: number, title: string) =>
  http.patch<Task>(`/tasks/${taskId}`, { title }).then((r) => r.data)

export const deleteTask = (taskId: number) => http.delete(`/tasks/${taskId}`)

export const sendTaskMessage = (taskId: number, message: string) =>
  http.post<TaskMessageResponse>(`/tasks/${taskId}/messages`, { message }).then((r) => r.data)

export interface TaskStreamEvent {
  type: 'delta' | 'tool' | 'intent' | 'done' | 'error'
  text?: string
  name?: string
  success?: boolean
  /** intent 事件携带的意图值（kb/sql/action/refuse） */
  intent?: string
  payload?: TaskMessageResponse
  detail?: string
  status?: number
}

/**
 * 流式发消息（SSE 打字机）。逐事件回调 onEvent，done 时 resolve 完整落库结果。
 * 404/422 等未打开流就失败的错误走 reject（与 axios 同样挂 friendly）。
 */
export async function sendTaskMessageStream(
  taskId: number,
  message: string,
  onEvent: (event: TaskStreamEvent) => void,
): Promise<TaskMessageResponse> {
  // 原生 fetch 不走 axios 拦截器：手动带 Bearer，并补齐 401 清态跳登录语义
  const token = getToken()
  const resp = await fetch(`/api/tasks/${taskId}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message }),
  })
  if (!resp.ok) {
    if (resp.status === 401) {
      setToken(null)
      setUsername(null)
      if (location.pathname !== '/login') location.assign('/login')
    }
    const detail = await resp.json().catch(() => null)
    const error: any = new Error('任务执行失败')
    error.friendly = detail?.detail || `请求失败（${resp.status}）`
    throw error
  }
  if (!resp.body) throw new Error('当前浏览器不支持流式响应')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let final: TaskMessageResponse | null = null
  let streamError: string | null = null

  for (; ;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      const event: TaskStreamEvent = JSON.parse(line.slice(6))
      if (event.type === 'done') {
        final = event.payload as TaskMessageResponse
      } else if (event.type === 'error') {
        streamError = event.detail || '任务执行失败'
      } else {
        onEvent(event)
      }
    }
  }

  if (streamError) {
    const error: any = new Error(streamError)
    error.friendly = streamError
    throw error
  }
  if (!final) {
    const error: any = new Error('流式响应意外中断')
    error.friendly = '流式响应意外中断，请重试'
    throw error
  }
  return final
}

export const decideTaskAction = (
  taskId: number,
  actionId: number,
  approved: boolean,
  reason?: string,
) => http.post<TaskAction>(`/tasks/${taskId}/actions/${actionId}/decision`, {
  approved,
  reason: reason || null,
}).then((r) => r.data)

export default http
