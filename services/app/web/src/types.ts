/** TypeScript 类型：与后端 src/models/schemas.py 一一对应 */

export interface UploadItem {
  resume_id: number
  original_file_name: string
  duplicated: boolean
  accepted: boolean
  reason: string | null
}

export interface UploadResponse {
  batch_id: string
  items: UploadItem[]
}

export interface ResumeBrief {
  resume_id: number
  original_file_name: string
  name?: string | null
  status: number
  status_label: string
  failure_reason: string | null
  interview_status?: number | null // 0待面试/1已邀请/2面试中/3已入职/4暂不跟进/null未进入
  uploaded_by: string
  created_at: string | null
  stage?: string | null // parsing / normalizing / screening / done
}

export interface EducationExperience {
  education_id?: number
  school: string
  major: string | null
  education_level: string | null
  start_date: string | null
  end_date: string | null
  is_current: boolean | null
}

export interface WorkExperience {
  work_id?: number
  company: string
  position: string
  start_date: string | null
  end_date: string | null
  is_current: boolean | null
  description: string | null
}

export interface ProjectExperience {
  project_id?: number
  project_name: string
  role: string | null
  start_date: string | null
  end_date: string | null
  description: string | null
}

export interface ResumeProfileData {
  profile_id: number | null
  resume_id: number
  name: string
  gender: number | null
  phone: string | null
  email: string | null
  highest_education: string | null
  graduation_institution: string | null
  total_work_months: number | null
  skills: string[]
  education_experiences: EducationExperience[]
  work_experiences: WorkExperience[]
  project_experiences: ProjectExperience[]
}

export interface ResumeDetail extends ResumeBrief {
  profile: ResumeProfileData | null
}

export interface BatchStatus {
  batch_id: string
  total: number
  finished: number
  failed: number
  parse_success: number
  normalize_success: number
  parsing: number
  normalizing: number
  screening: number
  per_resume: ResumeBrief[]
}

export interface Requirement {
  requirement_id: number
  requirement_name: string
  dept: string | null
  deadline: string | null
  description: string | null
  status: number // 0-进行中 1-已关闭
  created_by: string
  job_count?: number
  resume_count?: number
}

/** 非技能加分项（行业经验/语言能力等） */
export interface BonusItem {
  label: string
  value: string
}

export interface Job {
  requirement_id: number
  job_id: number
  job_code: string | null
  job_name: string
  headcount: number | null
  major: string | null
  job_jd: string
  job_min_degree: string | null
  job_min_exp_years: number | null
  job_required_skills: string[]
  job_optional_skills: string[]
  bonus_items: BonusItem[]
  job_status: number
  job_created_by: string
}

export interface FilterRule {
  min_degree: string | null
  min_exp_years: number | null
  required_skills: string[]
}

export interface FilterTemplate {
  template_id: number
  template_name: string
  job_id: number
  rules: FilterRule
  created_by: string
}

export interface FilterRun {
  run_id: number
  template_id: number | null
  job_id: number
  status: number
  total: number
  passed: number
  rejected: number
  pending_review: number
  job_name?: string | null
  requirement_id?: number | null
  requirement_name?: string | null
}

/** 岗位组内简历（含分配依据：自动命中的技能 / 手动添加标记） */
export interface GroupResumeBrief extends ResumeBrief {
  added_by: string
  match_detail: { required_hits?: string[]; optional_hits?: string[]; note?: string } | null
}

export interface ReasonItem {
  rule: string
  passed: boolean | null
  detail: string
}

export interface FilterResult {
  result_id: number
  run_id: number
  resume_id: number
  profile_id: number | null
  result: 'PASS' | 'REJECT' | 'PENDING_REVIEW'
  reasons: ReasonItem[]
  name: string | null
  original_file_name: string | null
}

/** 面试邀约 */
export interface Interview {
  interview_id: number
  resume_id: number
  job_id: number | null
  job_name: string | null
  interview_time: string | null
  way: string | null
  interviewer: string | null
  note: string | null
  notify_way: string | null
  created_by: string
}

/** 沉淀候选人才库条目 */
export interface TalentPoolEntry {
  pool_id: number
  resume_id: number
  resume: ResumeBrief | null
  source_requirement_id: number | null
  source_requirement_name: string | null
  source_job_id: number | null
  source_job_name: string | null
  note: string | null
  created_by: string
  created_at: string | null
  knowledge_sync_status: 'pending' | 'syncing' | 'success' | 'failed'
  knowledge_document_id: string | null
  knowledge_chunk_count: number | null
  knowledge_sync_error: string | null
  knowledge_synced_at: string | null
}
