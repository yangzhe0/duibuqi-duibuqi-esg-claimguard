import { useEffect, useMemo, useState } from 'react'
import { PdfEvidenceViewer } from '../components/PdfEvidenceViewer'
import { ReviewPanel } from '../components/ReviewPanel'
import { api } from '../lib/api'
import type { Evidence, EvidenceTarget, ExtractionResult, ReportItem } from '../types'

function StatusBadge({ status }: { status: string }) {
  const label = status === 'found' ? '已发现' : status === 'missing' ? '未披露' : '异常'
  return <span className={`status-badge status-${status}`}>{label}</span>
}

export function WorkbenchPage({ onReviewSaved, target }: { onReviewSaved: () => void; target: EvidenceTarget | null }) {
  const [reports, setReports] = useState<ReportItem[]>([])
  const [reportSearch, setReportSearch] = useState('')
  const [selectedReport, setSelectedReport] = useState('')
  const [results, setResults] = useState<ExtractionResult[]>([])
  const [selected, setSelected] = useState<ExtractionResult | null>(null)
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [dimension, setDimension] = useState('')
  const [resultSearch, setResultSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.reports().then(({ items }) => {
      setReports(items)
      const first = target?.reportId || items.find((item) => item.has_pdf)?.report_id || items[0]?.report_id || ''
      setSelectedReport(first)
    })
  }, [])

  useEffect(() => {
    if (!selectedReport) return
    setLoading(true)
    api.results({ report_id: selectedReport, limit: 100 }).then(({ items }) => {
      setResults(items)
      setSelected(items.find((item) => item.indicator_id === target?.indicatorId) || items.find((item) => item.status === 'found') || items[0] || null)
      setLoading(false)
    })
  }, [selectedReport, target?.nonce])

  useEffect(() => {
    if (!target || target.reportId !== selectedReport) return
    const match = results.find((item) => item.indicator_id === target.indicatorId)
    if (match) setSelected(match)
  }, [target?.nonce, results, selectedReport])

  useEffect(() => {
    if (!selected?.block_id) return setEvidence(null)
    api.evidence(selected.report_id, selected.block_id).then(setEvidence).catch(() => setEvidence(null))
  }, [selected])

  const visibleReports = useMemo(
    () => reports.filter((item) => item.report_id.toLowerCase().includes(reportSearch.toLowerCase())),
    [reports, reportSearch],
  )
  const visibleResults = useMemo(() => results.filter((item) => {
    if (dimension && item.dimension !== dimension) return false
    const text = `${item.indicator_name} ${item.indicator_id}`.toLowerCase()
    return text.includes(resultSearch.toLowerCase())
  }), [results, dimension, resultSearch])

  return (
    <main className="workbench-page">
      <aside className="report-rail">
        <div className="rail-heading"><span className="kicker">REPORTS</span><h2>报告库</h2><span>{reports.length} 份</span></div>
        <div className="search-box"><span>⌕</span><input placeholder="搜索公司或代码" value={reportSearch} onChange={(event) => setReportSearch(event.target.value)} /></div>
        <div className="report-list">
          {visibleReports.map((item) => <button key={item.report_id} className={selectedReport === item.report_id ? 'active' : ''} onClick={() => setSelectedReport(item.report_id)}>
            <span className="report-avatar">{item.report_id.slice(0, 2)}</span>
            <span><strong>{item.report_id.replace(/_20\d\d_.*/, '').replace(/^\d+_/, '')}</strong><small>{item.report_id.split('_')[0]} · {item.found_count} 项披露</small></span>
            {item.risk_count ? <i>{item.risk_count}</i> : null}
          </button>)}
        </div>
      </aside>
      <section className="document-column">
        <header className="workbench-header">
          <div><span className="kicker">EVIDENCE WORKSPACE</span><h2>{selectedReport.replace(/_20\d\d_.*/, '').replace(/^\d+_/, '') || '报告证据工作台'}</h2></div>
          <div className="header-actions"><span className="model-pill">Qwen3 · Evidence constrained</span><a href={selectedReport ? api.exportUrl(selectedReport) : '#'}>CSV ↓</a><a href={selectedReport ? api.exportJsonUrl(selectedReport) : '#'}>JSON ↓</a><a href={selectedReport ? api.pdfUrl(selectedReport) : '#'} target="_blank">原文 ↗</a></div>
        </header>
        {selectedReport ? <PdfEvidenceViewer url={api.pdfUrl(selectedReport)} evidence={evidence} requestedPage={Number(selected?.page_no || 1)} /> : null}
      </section>
      <aside className="result-column">
        <div className="result-browser">
          <div className="section-heading compact"><div><span className="kicker">INDICATORS</span><h2>抽取结果</h2></div><span>{visibleResults.length}</span></div>
          <div className="result-filters">
            <div className="segment-control">{['', 'E', 'S', 'G'].map((key) => <button className={dimension === key ? 'active' : ''} key={key || 'all'} onClick={() => setDimension(key)}>{key || '全部'}</button>)}</div>
            <input placeholder="搜索指标" value={resultSearch} onChange={(event) => setResultSearch(event.target.value)} />
          </div>
          <div className="indicator-list">
            {loading ? <div className="empty-state">正在载入抽取结果…</div> : visibleResults.map((item) => <button key={item.indicator_id} className={selected?.indicator_id === item.indicator_id ? 'active' : ''} onClick={() => setSelected(item)}>
              <span className={`dimension-dot dim-${item.dimension}`}>{item.dimension}</span>
              <span><strong>{item.indicator_name}</strong><small>{item.value ? `${item.value} ${item.unit}` : item.qualitative_text || '当前证据不足'}</small></span>
              <StatusBadge status={item.status} />
            </button>)}
          </div>
        </div>
        {selected ? <div className="result-detail">
          <div className="detail-title"><div><span className={`dimension-dot dim-${selected.dimension}`}>{selected.dimension}</span><h3>{selected.indicator_name}</h3></div><StatusBadge status={selected.status} /></div>
          <div className="value-display"><span>结构化结果</span><strong>{selected.value || selected.qualitative_text || '—'}</strong><small>{selected.unit}</small></div>
          <dl>
            <div><dt>模型置信度</dt><dd>{selected.llm_confidence ? `${(Number(selected.llm_confidence) * 100).toFixed(0)}%` : '—'}</dd></div>
            <div><dt>证据位置</dt><dd>第 {selected.page_no || '—'} 页 · {selected.block_type || '—'}</dd></div>
            <div><dt>推理耗时</dt><dd>{selected.elapsed_seconds ? `${selected.elapsed_seconds}s` : '—'}</dd></div>
          </dl>
          <div className="quote-block"><span>原文证据</span><blockquote>{selected.evidence_quote || '当前结果没有可展示的证据片段。'}</blockquote></div>
          {selected.risk_level ? <div className={`risk-callout risk-${selected.risk_level}`}><strong>{selected.risk_level.toUpperCase()} RISK</strong><p>{selected.risk_reason || selected.risk_tag}</p></div> : null}
          <ReviewPanel result={selected} onSaved={onReviewSaved} />
        </div> : null}
      </aside>
    </main>
  )
}
