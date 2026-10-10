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
  UploadResponse,
} from '../types'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const detail = err.response?.data?.detail
    if (detail) err.friendly = typeof detail === 'string' ? detail : JSON.stringify(detail)
    return Promise.reject(err)
  },
)

// ---- 简历 ----
export const uploadResumes = (files: File[], hrId: string, requirementId: number) => {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  form.append('hr_id', hrId)
  form.append('requirement_id', String(requirementId))
  return http.post<UploadResponse>('/resumes/upload', form).then((r) => r.data)
}

export const listResumes = (status?: number) =>
  http.get<ResumeBrief[]>('/resumes', { params: status != null ? { status } : {} }).then((r) => r.data)

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

export default http
