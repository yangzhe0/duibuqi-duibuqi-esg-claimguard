import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import type { ClaimGraph, EvidenceTarget, PreauditIssue, PreauditSummary, ReportItem } from '../types'

const filterLabels: Record<string, string> = {
  open: '全部待处理', blocking: '阻断', important: '重要', attention: '提示', closed: '已关闭',
}

const actionLabels: Record<string, string> = {
  confirmed: '确认问题', resolved: '已修正', pending_material: '待补材料', accepted: '接受风险', not_issue: '判定非问题', open: '重新打开',
}

function companyName(reportId: string) {
  return reportId.replace(/_20\d\d_.*/, '').replace(/^\d+_/, '')
}

function IssueBadge({ issue }: { issue: PreauditIssue }) {
  return <span className={`issue-badge severity-${issue.severity}`}>{issue.severity_label}</span>
}

export function AuditPage({ initialReportId = '', onOpenEvidence }: { initialReportId?: string; onOpenEvidence: (target: EvidenceTarget) => void }) {
  const [reports, setReports] = useState<ReportItem[]>([])
  const [reportId, setReportId] = useState(initialReportId)
  const [summary, setSummary] = useState<PreauditSummary | null>(null)
  const [graph, setGraph] = useState<ClaimGraph | null>(null)
  const [issues, setIssues] = useState<PreauditIssue[]>([])
  const [selected, setSelected] = useState<PreauditIssue | null>(null)
  const [filter, setFilter] = useState('open')
  const [action, setAction] = useState('confirmed')
  const [note, setNote] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.reports(), api.preauditSummary()])
      .then(([reportPayload, globalSummary]) => {
        setReports(reportPayload.items.filter((item) => item.has_pdf))
        if (!reportId) setReportId(globalSummary.suggested_report_id || reportPayload.items[0]?.report_id || '')
      })
      .catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => { if (initialReportId) setReportId(initialReportId) }, [initialReportId])

  const load = () => {
    if (!reportId) return
    setLoading(true); setError('')
    Promise.all([api.preauditSummary(reportId), api.preauditIssues(reportId, true), api.claimGraph(reportId)])
      .then(([summaryPayload, issuePayload, graphPayload]) => {
        setSummary(summaryPayload); setIssues(issuePayload.items); setGraph(graphPayload)
        setSelected((current) => issuePayload.items.find((item) => item.issue_id === current?.issue_id) || issuePayload.items.find((item) => !item.closed) || issuePayload.items[0] || null)
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [reportId])

  useEffect(() => {
    setAction(selected?.action === 'open' ? 'confirmed' : selected?.action || 'confirmed')
    setNote(selected?.action_note || '')
    setReviewer(selected?.reviewer || '')
  }, [selected?.issue_id])

  const visible = useMemo(() => issues.filter((item) => {
    if (filter === 'closed') return item.closed
    if (filter === 'open') return !item.closed
    return !item.closed && item.severity === filter
  }), [issues, filter])

  const counts = useMemo(() => ({
    open: issues.filter((item) => !item.closed).length,
    blocking: issues.filter((item) => !item.closed && item.severity === 'blocking').length,
    important: issues.filter((item) => !item.closed && item.severity === 'important').length,
    attention: issues.filter((item) => !item.closed && item.severity === 'attention').length,
    closed: issues.filter((item) => item.closed).length,
  }), [issues])

  const saveAction = async () => {
    if (!selected) return
    setSaving(true); setError('')
    try {
      await api.saveIssueAction({ issue_id: selected.issue_id, report_id: selected.report_id, action, note, reviewer })
      const [nextSummary, nextIssues] = await Promise.all([api.preauditSummary(reportId), api.preauditIssues(reportId, true)])
      setSummary(nextSummary); setIssues(nextIssues.items)
      const saved = nextIssues.items.find((item) => item.issue_id === selected.issue_id)
      setSelected(saved?.closed && filter !== 'closed' ? nextIssues.items.find((item) => !item.closed) || saved : saved || nextIssues.items.find((item) => !item.closed) || null)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const openEvidence = (item: PreauditIssue, indicatorId: string) => {
    onOpenEvidence({ reportId: item.report_id, indicatorId, nonce: Date.now() })
  }

  return <main className="page preaudit-page">
    <section className="page-title preaudit-title">
      <div><span className="kicker">CLAIM–EVIDENCE CONSTRAINT GRAPH</span><h1>可持续披露一致性预审</h1><p>发现声明与证据失配、跨页数值口径差异和需要确认的条款缺口，并形成可交付底稿。</p></div>
      <div className="preaudit-toolbar">
        <label>当前报告</label>
        <select value={reportId} onChange={(event) => setReportId(event.target.value)}>{reports.map((item) => <option key={item.report_id} value={item.report_id}>{companyName(item.report_id)} · {item.report_id.split('_')[0]}</option>)}</select>
        <button onClick={load}>重新核验</button>
        <a href={api.workpaperUrl(reportId)} download>导出工作底稿 ↓</a>
      </div>
    </section>

    {error ? <div className="global-error">预审失败：{error}</div> : null}

    <section className="preaudit-kpis">
      <article className="blocking"><span>阻断问题</span><strong>{summary?.blocking_count ?? '—'}</strong><small>发布前必须确认</small></article>
      <article className="important"><span>重要问题</span><strong>{summary?.important_count ?? '—'}</strong><small>结构或语义风险</small></article>
      <article className="attention"><span>待确认提示</span><strong>{summary?.attention_count ?? '—'}</strong><small>含条款适用性入口</small></article>
      <article className="closed"><span>已关闭</span><strong>{summary?.closed_count ?? '—'}</strong><small>已修正、接受或排除</small></article>
      <article className="coverage"><span>证据可回溯率</span><strong>{summary?.evidence_coverage == null ? '—' : `${(summary.evidence_coverage * 100).toFixed(0)}%`}</strong><small>found 声明含 quote + block</small></article>
    </section>

    <section className="graph-strip">
      <div><span>声明节点</span><strong>{graph?.stats.claim_count ?? '—'}</strong></div><i>supports</i>
      <div><span>证据节点</span><strong>{graph?.stats.evidence_count ?? '—'}</strong></div><i>constrained_by</i>
      <div><span>可计算约束</span><strong>{graph?.stats.constraint_count ?? '—'}</strong></div><i>governed_by</i>
      <div><span>标准节点</span><strong>{graph?.stats.standard_count ?? '—'}</strong></div>
      <p>{graph ? `${graph.stats.node_count} 个节点 · ${graph.stats.edge_count} 条可查询关系` : '正在构建约束图'}</p>
    </section>

    <section className="preaudit-workspace">
      <article className="panel issue-queue-panel">
        <div className="section-heading"><div><span className="kicker">ISSUE REGISTER</span><h2>问题清单</h2></div><span className="no-score-pill">三级严重度 · 无伪精确评分</span></div>
        <div className="issue-tabs">{Object.keys(filterLabels).map((key) => <button key={key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key)}>{filterLabels[key]}<i>{counts[key as keyof typeof counts]}</i></button>)}</div>
        <div className="issue-queue">
          {loading ? <div className="empty-state">正在构建声明—证据约束图…</div> : visible.map((item) => <button key={item.issue_id} className={selected?.issue_id === item.issue_id ? 'active' : ''} onClick={() => setSelected(item)}>
            <IssueBadge issue={item} />
            <span><strong>{item.title}</strong><small>{item.indicator_names.join(' · ') || item.requirement.topic}</small><p>{item.finding}</p></span>
            <b className={item.closed ? 'closed' : ''}>{item.closed ? '已关闭' : item.action === 'confirmed' ? '已确认' : item.action === 'pending_material' ? '待材料' : '待处理'}</b>
          </button>)}
          {!loading && !visible.length ? <div className="empty-state">该分组当前没有问题。</div> : null}
        </div>
      </article>

      <article className="panel issue-detail-panel">
        {selected ? <>
          <header><div><IssueBadge issue={selected} /><span className="issue-id">{selected.issue_id}</span><h2>{selected.title}</h2><p>{selected.finding}</p></div><div className="trace-state"><span>{selected.closed ? 'CLOSED' : 'OPEN'}</span><strong>{selected.closed ? actionLabels[selected.action] : '需要人工判断'}</strong></div></header>

          {selected.calculation.display ? <section className="calculation-card"><span>可复算约束</span><strong>{selected.calculation.formula}</strong><code>{selected.calculation.display}</code><p>容差 {(Number(selected.calculation.tolerance) * 100).toFixed(0)}%；超出容差只触发口径核验，不自动认定报告错误。</p></section> : null}

          <section className={`evidence-comparison ${selected.evidence.length > 2 ? 'multiple' : ''}`}>
            {selected.evidence.length ? selected.evidence.map((evidence, index) => <article key={`${evidence.block_id}-${index}`}>
              <div><span>{evidence.label}</span><b>第 {evidence.page_no || '—'} 页</b></div>
              <h3>{evidence.indicator_name}</h3>
              <strong>{evidence.value ? `${evidence.value} ${evidence.unit}` : '无结构化数值'}</strong>
              <blockquote>{evidence.quote || '当前没有可回溯证据，这本身就是问题。'}</blockquote>
              {evidence.block_id ? <button onClick={() => openEvidence(selected, evidence.indicator_id)}>打开 PDF 原文与坐标框 →</button> : null}
            </article>) : <article className="no-evidence-card"><span>条款覆盖核验</span><h3>当前候选范围未找到披露或省略说明</h3><p>请先判断条款对本公司是否适用，再决定补充披露、说明不适用或排除该提示。</p></article>}
          </section>

          {selected.requirement.standard ? <section className="requirement-card"><div><span>规则依据</span><strong>{selected.requirement.standard}</strong><p>{selected.requirement.clause} · {selected.requirement.topic}</p></div><a href={selected.requirement.source_url} target="_blank" rel="noreferrer">查看官方原文 ↗</a></section> : null}

          <section className="graph-path"><span>可追溯路径</span><div><b>报告</b><i>contains</i><b>{selected.indicator_names.length > 1 ? `${selected.indicator_names.length} 条声明` : selected.indicator_names[0] || '条款议题'}</b><i>{selected.calculation.display ? 'constrained_by' : selected.requirement.standard ? 'governed_by' : 'supports'}</i><b>{selected.calculation.display ? '数值约束' : selected.requirement.standard ? '披露条款' : '原文证据'}</b></div></section>
        </> : <div className="empty-state">选择一项问题查看证据与处置动作。</div>}
      </article>

      <aside className="panel issue-action-panel">
        <span className="kicker">DISPOSITION</span><h2>处置并关闭问题</h2><p>处置记录会写入工作底稿；“待补材料”和“确认问题”仍保留在开放队列。</p>
        <div className="action-options">{[...(selected?.closed ? ['open'] : []), 'confirmed', 'resolved', 'pending_material', 'accepted', 'not_issue'].map((key) => <button key={key} className={action === key ? 'active' : ''} onClick={() => setAction(key)}><i />{actionLabels[key]}</button>)}</div>
        <label>处理说明<textarea rows={5} value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录口径差异、修正位置或排除依据…" /></label>
        <label>复核人<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="姓名或角色（可选）" /></label>
        <button className="save-disposition" disabled={!selected || saving} onClick={saveAction}>{saving ? '正在保存…' : '保存处置记录'}</button>
        {selected?.updated_at ? <small>最近更新：{new Date(selected.updated_at).toLocaleString()}</small> : null}
        <div className="product-boundary"><strong>能力边界</strong><p>本系统核验报告内部披露一致性，不评价企业真实 ESG 表现，不替代审计或鉴证。</p></div>
      </aside>
    </section>
  </main>
}
