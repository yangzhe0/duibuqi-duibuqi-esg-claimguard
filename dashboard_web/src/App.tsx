import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from './lib/api'
import { OverviewPage } from './pages/OverviewPage'
import { AuditPage } from './pages/AuditPage'
import { QualityPage } from './pages/QualityPage'
import { UploadPage } from './pages/UploadPage'
import type { EvidenceTarget, ReviewMetrics, Summary, SystemHealth } from './types'

const WorkbenchPage = lazy(() => import('./pages/WorkbenchPage').then((module) => ({ default: module.WorkbenchPage })))
const NaturalGoldPage = lazy(() => import('./pages/NaturalGoldPage').then((module) => ({ default: module.NaturalGoldPage })))

type Page = 'overview' | 'audit' | 'workbench' | 'quality' | 'naturalgold' | 'upload'

const emptyMetrics: ReviewMetrics = { reviewed_count: 0, label_counts: {}, precision: null, recall: null, f1: null, note: '' }

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [metrics, setMetrics] = useState<ReviewMetrics>(emptyMetrics)
  const [error, setError] = useState('')
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null)
  const [auditReportId, setAuditReportId] = useState('')
  const [health, setHealth] = useState<SystemHealth | null>(null)

  const refreshMetrics = () => api.reviewMetrics().then(setMetrics)
  const openEvidence = (target: EvidenceTarget) => { setEvidenceTarget(target); setPage('workbench') }
  const openAudit = (reportId = '') => { setAuditReportId(reportId); setPage('audit') }
  useEffect(() => {
    Promise.all([api.summary(), api.reviewMetrics(), api.health()])
      .then(([summaryPayload, metricsPayload, healthPayload]) => { setSummary(summaryPayload); setMetrics(metricsPayload); setHealth(healthPayload) })
      .catch((reason: Error) => setError(reason.message))
  }, [])

  return <div className="app-shell">
    <header className="topbar">
      <button className="brand" onClick={() => setPage('overview')}><span className="brand-mark"><i /><i /><i /></span><span><strong>ESG ClaimGuard</strong><small>可持续披露一致性预审</small></span></button>
      <nav>
        <button className={page === 'overview' ? 'active' : ''} onClick={() => setPage('overview')}><span>◫</span>系统总览</button>
        <button className={page === 'audit' ? 'active' : ''} onClick={() => openAudit()}><span>◇</span>披露预审</button>
        <button className={page === 'workbench' ? 'active' : ''} onClick={() => { setEvidenceTarget(null); setPage('workbench') }}><span>▤</span>证据复核</button>
        <button className={page === 'quality' ? 'active' : ''} onClick={() => setPage('quality')}><span>⌁</span>质量评测</button>
        <button className={page === 'naturalgold' ? 'active' : ''} onClick={() => setPage('naturalgold')}><span>◎</span>金标准</button>
        <button className={page === 'upload' ? 'active' : ''} onClick={() => setPage('upload')}><span>↥</span>接入报告</button>
      </nav>
      <div className={`topbar-meta ${health && !health.pipeline_ready ? 'warning' : ''}`} title={health?.pipeline_ready ? `MinerU + ${health.model.requested} 已就绪` : '解析或模型服务未就绪'}><span className="system-dot" />{health?.pipeline_ready ? '离线流水线就绪' : '流水线未就绪'} <b>V3.1</b></div>
    </header>
    {error ? <div className="global-error">无法连接数据服务：{error}</div> : null}
    {!summary ? <div className="app-loading"><span /><strong>正在载入 ESG 证据空间</strong></div> : <>
      {page === 'overview' && <OverviewPage summary={summary} onStartAudit={() => openAudit()} onUpload={() => setPage('upload')} />}
      {page === 'audit' && <AuditPage initialReportId={auditReportId} onOpenEvidence={openEvidence} />}
      {page === 'workbench' && <Suspense fallback={<div className="app-loading"><span /><strong>正在载入证据工作台</strong></div>}><WorkbenchPage onReviewSaved={refreshMetrics} target={evidenceTarget} /></Suspense>}
      {page === 'quality' && <QualityPage metrics={metrics} summary={summary} />}
      {page === 'naturalgold' && <Suspense fallback={<div className="app-loading"><span /><strong>正在载入金标准工作台</strong></div>}><NaturalGoldPage /></Suspense>}
      {page === 'upload' && <UploadPage onOpenAudit={openAudit} pipelineReady={health?.pipeline_ready ?? false} />}
    </>}
  </div>
}
