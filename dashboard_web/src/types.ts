export type Summary = {
  report_count: number
  indicator_count: number
  total_results: number
  found_count: number
  missing_count: number
  error_count: number
  found_rate: number
  risk_count: number
  dimension_found: Record<string, number>
  type_found: Record<string, number>
  model_call_count: number
  avg_inference_seconds: number
}

export type ReportItem = {
  report_id: string
  found_count: number
  missing_count: number
  risk_count: number
  has_pdf: boolean
}

export type ExtractionResult = {
  report_id: string
  indicator_id: string
  indicator_name: string
  dimension: 'E' | 'S' | 'G'
  indicator_type: string
  status: 'found' | 'missing' | 'error'
  value: string
  unit: string
  qualitative_text: string
  evidence_quote: string
  page_no: string
  block_id: string
  block_type: string
  llm_confidence: string
  llm_reason: string
  elapsed_seconds: string
  risk_tag: string
  risk_level: string
  risk_reason: string
  suspected_issue_type: string
}

export type Evidence = {
  report_id: string
  block_id: string
  page_no: number
  block_index: number
  block_type: string
  bbox: number[]
  coordinate_space: number[]
  text: string
}

export type ReviewMetrics = {
  reviewed_count: number
  label_counts: Record<string, number>
  precision: null
  recall: null
  f1: null
  metrics_status?: string
  note: string
}

export type PipelineTask = {
  task_id: string
  report_id: string
  filename: string
  size: number
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  progress: number
  message: string
  error: string
  created_at: string
  updated_at: string
}

export type TaskSummary = {
  task_id: string
  dataset_id: string
  scope: 'single_upload'
  report_id: string
  total_results: number
  found_count: number
  missing_count: number
  error_count: number
  completed_at: string
}

export type TaskPreaudit = {
  task_id: string
  dataset_id: string
  scope: 'single_upload'
  report_id: string
  total: number
  items: Array<{
    issue_id: string
    indicator_id: string
    indicator_name: string
    issue_type: string
    severity: 'blocking' | 'important' | 'attention'
    finding: string
  }>
}

export type AuditSignals = {
  rule_risk: number
  uncertainty: number
  peer_gap: number
  feedback: number
}

export type PeerEvidence = {
  report_id: string
  value: string
  unit: string
  evidence_quote: string
  page_no: string
  block_id: string
}

export type AuditItem = ExtractionResult & {
  priority_score: number
  priority_band: 'high' | 'medium' | 'low'
  category: 'risk' | 'gap' | 'uncertainty' | 'routine'
  category_label: string
  signals: AuditSignals
  priority_reasons: string[]
  peer_found_rate: number
  peer_found_count: number
  peer_total: number
  review_count_for_indicator: number
  feedback_error_probability: number
  reviewed: boolean
  review_label: string
  peer_examples: PeerEvidence[]
}

export type AuditSummary = {
  scope: string
  report_id: string
  suggested_report_id: string
  total_items: number
  unreviewed_count: number
  reviewed_count: number
  known_risk_count: number
  actionable_gap_count: number
  uncertain_count: number
  high_priority_count: number
  risk_recall_at_20: number | null
  found_by_dimension: Record<string, number>
  method: {
    formula: string
    weights: AuditSignals
    gap_threshold: number
    note: string
  }
}

export type EvidenceTarget = { reportId: string; indicatorId: string; nonce: number }

export type SystemHealth = {
  status: 'ready' | 'degraded'
  pipeline_ready: boolean
  profile: 'claimguard' | 'legacy'
  mineru: { ready: boolean; executable: string; backend: string }
  ollama: { ready: boolean; url: string }
  model: { ready: boolean; requested: string; available_count: number; api: 'openai' | 'ollama' }
  runtime_assets: Record<string, { ready: boolean; path: string }>
  error: string
}

export type PreauditEvidence = {
  label: string
  indicator_id: string
  indicator_name: string
  value: string
  unit: string
  quote: string
  page_no: string
  block_id: string
  block_type: string
}

export type PreauditRequirement = {
  standard?: string
  clause?: string
  topic?: string
  source_url?: string
}

export type PreauditCalculation = {
  formula?: string
  display?: string
  relative_gap?: number
  tolerance?: number
  verdict?: string
}

export type PreauditIssue = {
  issue_id: string
  report_id: string
  issue_type: string
  severity: 'blocking' | 'important' | 'attention'
  severity_label: string
  title: string
  finding: string
  indicator_ids: string[]
  indicator_names: string[]
  evidence: PreauditEvidence[]
  calculation: PreauditCalculation
  requirement: PreauditRequirement
  action: 'open' | 'confirmed' | 'resolved' | 'accepted' | 'pending_material' | 'not_issue'
  action_note: string
  reviewer: string
  updated_at: string
  closed: boolean
}

export type PreauditSummary = {
  scope: string
  report_id: string
  suggested_report_id: string
  report_count?: number
  total_issues?: number
  open_issues?: number
  blocking_count?: number
  important_count?: number
  attention_count?: number
  closed_count?: number
  evidence_coverage?: number
  claim_count?: number
  evidence_count?: number
  constraint_count?: number
  standard_count?: number
  method_note: string
}

export type ClaimGraph = {
  report_id: string
  nodes: Record<string, unknown>[]
  edges: { source: string; target: string; type: string }[]
  stats: {
    claim_count: number
    evidence_count: number
    constraint_count: number
    standard_count: number
    node_count: number
    edge_count: number
  }
  note: string
}

export type NaturalGoldRole = 'annotator_a' | 'annotator_b' | 'adjudicator'
export type NaturalGoldDisclosure = 'found' | 'missing' | 'uncertain'

export type NaturalGoldAnnotation = {
  task_id: string
  role: NaturalGoldRole
  disclosure: NaturalGoldDisclosure
  subject: string
  period: string
  scope: string
  value: string
  unit: string
  evidence_pages: string
  evidence_text: string
  confidence: 'high' | 'medium' | 'low'
  note: string
  reviewer: string
  updated_at?: string
}

export type NaturalGoldTask = {
  sample_order: string
  task_id: string
  dataset_version: string
  report_id: string
  indicator_id: string
  indicator_name: string
  dimension: 'E' | 'S' | 'G'
  indicator_type: string
  stratum: string
  pdf_path: string
  status: 'pending' | 'completed' | 'waiting' | 'agreed' | 'disagreement' | 'adjudicated'
  annotation: Partial<NaturalGoldAnnotation>
  blinded: boolean
  model_output_visible: false
  annotations?: {
    annotator_a: Partial<NaturalGoldAnnotation>
    annotator_b: Partial<NaturalGoldAnnotation>
    adjudicator: Partial<NaturalGoldAnnotation>
  }
  disagreement_fields?: string[]
}

export type NaturalGoldSummary = {
  dataset_version: string
  manifest_state: string
  manifest_sha256: string
  total_tasks: number
  role_completed: Record<NaturalGoldRole, number>
  both_complete: number
  exact_agreements: number
  disagreements: number
  pending_adjudication: number
  adjudicated: number
  gold_count: number
  gold_progress: number
  disclosure_kappa: number | null
  ready_to_evaluate: boolean
  metrics_status: string
  sampling: {
    dimensions: Record<string, number>
    indicator_types: Record<string, number>
    unique_reports: number
    unique_indicators: number
    model_output_blinded: boolean
  }
  note: string
}
