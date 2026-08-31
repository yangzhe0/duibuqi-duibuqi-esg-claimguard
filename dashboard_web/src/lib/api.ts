import type { AuditItem, AuditSummary, ClaimGraph, Evidence, ExtractionResult, NaturalGoldAnnotation, NaturalGoldRole, NaturalGoldSummary, NaturalGoldTask, PipelineTask, PreauditIssue, PreauditSummary, ReportItem, ReviewMetrics, Summary, SystemHealth, TaskPreaudit, TaskSummary } from '../types'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: response.statusText }))
    throw new Error(payload.error || `请求失败：${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<SystemHealth>('/api/health'),
  summary: () => request<Summary>('/api/summary'),
  reports: (search = '') =>
    request<{ items: ReportItem[]; total: number }>(`/api/reports?search=${encodeURIComponent(search)}`),
  results: (params: Record<string, string | number>) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== '') query.set(key, String(value))
    })
    return request<{ items: ExtractionResult[]; total: number }>(`/api/results?${query}`)
  },
  evidence: (reportId: string, blockId: string) =>
    request<Evidence>(`/api/evidence/${encodeURIComponent(reportId)}?block_id=${encodeURIComponent(blockId)}`),
  reviewMetrics: () => request<ReviewMetrics>('/api/review-metrics'),
  auditSummary: (reportId = '') =>
    request<AuditSummary>(`/api/audit/summary${reportId ? `?report_id=${encodeURIComponent(reportId)}` : ''}`),
  auditQueue: (reportId: string, limit = 65, includeReviewed = false) =>
    request<{ items: AuditItem[]; total: number; report_id: string }>(
      `/api/audit/queue?report_id=${encodeURIComponent(reportId)}&limit=${limit}&include_reviewed=${includeReviewed}`,
    ),
  preauditSummary: (reportId = '') =>
    request<PreauditSummary>(`/api/preaudit/summary${reportId ? `?report_id=${encodeURIComponent(reportId)}` : ''}`),
  preauditIssues: (reportId: string, includeClosed = true) =>
    request<{ items: PreauditIssue[]; total: number; report_id: string }>(
      `/api/preaudit/issues?report_id=${encodeURIComponent(reportId)}&include_closed=${includeClosed}`,
    ),
  claimGraph: (reportId: string) =>
    request<ClaimGraph>(`/api/preaudit/graph?report_id=${encodeURIComponent(reportId)}`),
  saveIssueAction: (payload: { issue_id: string; report_id: string; action: string; note: string; reviewer: string }) =>
    request<Record<string, string>>('/api/preaudit/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  naturalGoldSummary: () => request<NaturalGoldSummary>('/api/natural-gold/summary'),
  naturalGoldTasks: (role: NaturalGoldRole, status = 'all') =>
    request<{ items: NaturalGoldTask[]; total: number; role: NaturalGoldRole; status: string }>(
      `/api/natural-gold/tasks?role=${encodeURIComponent(role)}&status=${encodeURIComponent(status)}`,
    ),
  saveNaturalGoldAnnotation: (payload: NaturalGoldAnnotation) =>
    request<NaturalGoldAnnotation>('/api/natural-gold/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  naturalGoldManifestUrl: () => '/api/natural-gold/manifest.csv',
  reviews: (reportId = '', indicatorId = '') =>
    request<{ items: Record<string, string>[]; metrics: ReviewMetrics }>(
      `/api/reviews?report_id=${encodeURIComponent(reportId)}&indicator_id=${encodeURIComponent(indicatorId)}`,
    ),
  saveReview: (payload: Record<string, string>) =>
    request<Record<string, string>>('/api/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  upload: async (file: File) => {
    const response = await fetch('/api/uploads', {
      method: 'POST',
      headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/pdf' },
      body: file,
    })
    if (!response.ok) throw new Error((await response.json()).error || '上传失败')
    return response.json() as Promise<PipelineTask>
  },
  task: (taskId: string) => request<PipelineTask>(`/api/tasks/${encodeURIComponent(taskId)}`),
  tasks: () => request<{ items: PipelineTask[]; total: number }>('/api/tasks'),
  taskSummary: (taskId: string) => request<TaskSummary>(`/api/tasks/${encodeURIComponent(taskId)}/summary`),
  taskResults: (taskId: string) => request<{ items: ExtractionResult[]; total: number; dataset_id: string; scope: 'single_upload' }>(`/api/tasks/${encodeURIComponent(taskId)}/results`),
  taskPreaudit: (taskId: string) => request<TaskPreaudit>(`/api/tasks/${encodeURIComponent(taskId)}/preaudit`),
  taskPdfUrl: (taskId: string) => `/api/tasks/${encodeURIComponent(taskId)}/pdf`,
  taskEvidenceUrl: (taskId: string, blockId: string) => `/api/tasks/${encodeURIComponent(taskId)}/evidence?block_id=${encodeURIComponent(blockId)}`,
  pdfUrl: (reportId: string) => `/api/pdf/${encodeURIComponent(reportId)}`,
  exportUrl: (reportId: string) => `/api/export/results.csv?report_id=${encodeURIComponent(reportId)}`,
  exportJsonUrl: (reportId: string) => `/api/export/results.json?report_id=${encodeURIComponent(reportId)}`,
  workpaperUrl: (reportId: string) => `/api/preaudit/workpaper.csv?report_id=${encodeURIComponent(reportId)}`,
}
