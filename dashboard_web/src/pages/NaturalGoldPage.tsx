import { useEffect, useMemo, useState } from 'react'
import { PdfEvidenceViewer } from '../components/PdfEvidenceViewer'
import { api } from '../lib/api'
import type { NaturalGoldAnnotation, NaturalGoldDisclosure, NaturalGoldRole, NaturalGoldSummary, NaturalGoldTask } from '../types'

const ROLE_LABELS: Record<NaturalGoldRole, string> = {
  annotator_a: '标注员 A',
  annotator_b: '标注员 B',
  adjudicator: '分歧仲裁员',
}
const STATUS_LABELS: Record<string, string> = {
  pending: '待标注', completed: '已完成', waiting: '等待双标', agreed: '双方一致', disagreement: '待仲裁', adjudicated: '已仲裁',
}
const FIELD_LABELS: Record<string, string> = {
  disclosure: '披露状态', subject: '主体', period: '期间', scope: '范围', value: '值', unit: '单位', evidence_pages: '证据页', evidence_text: '证据文本',
}

function blankAnnotation(taskId: string, role: NaturalGoldRole): NaturalGoldAnnotation {
  return {
    task_id: taskId,
    role,
    disclosure: 'found',
    subject: '',
    period: '',
    scope: '',
    value: '',
    unit: '',
    evidence_pages: '',
    evidence_text: '',
    confidence: 'medium',
    note: '',
    reviewer: role === 'annotator_a' ? '标注员A' : role === 'annotator_b' ? '标注员B' : '仲裁员',
  }
}

function AnnotationSnapshot({ title, value }: { title: string; value: Partial<NaturalGoldAnnotation> }) {
  return <article className="gold-snapshot"><header><strong>{title}</strong><span>{value.reviewer || '—'}</span></header>
    <dl><div><dt>判断</dt><dd>{value.disclosure || '—'}</dd></div><div><dt>值 / 单位</dt><dd>{value.value || '—'} {value.unit || ''}</dd></div><div><dt>主体 / 期间</dt><dd>{value.subject || '—'} · {value.period || '—'}</dd></div><div><dt>范围</dt><dd>{value.scope || '—'}</dd></div><div><dt>证据页</dt><dd>{value.evidence_pages || '—'}</dd></div></dl>
    <blockquote>{value.evidence_text || '没有证据文本'}</blockquote>{value.note ? <p>{value.note}</p> : null}</article>
}

export function NaturalGoldPage() {
  const [role, setRole] = useState<NaturalGoldRole>('annotator_a')
  const [status, setStatus] = useState('all')
  const [summary, setSummary] = useState<NaturalGoldSummary | null>(null)
  const [tasks, setTasks] = useState<NaturalGoldTask[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [form, setForm] = useState<NaturalGoldAnnotation>(blankAnnotation('', role))
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const selected = useMemo(() => tasks.find((task) => task.task_id === selectedId) || tasks[0] || null, [tasks, selectedId])
  const reload = async (nextRole = role, nextStatus = status) => {
    const [summaryPayload, taskPayload] = await Promise.all([api.naturalGoldSummary(), api.naturalGoldTasks(nextRole, nextStatus)])
    setSummary(summaryPayload)
    setTasks(taskPayload.items)
    setSelectedId((current) => taskPayload.items.some((task) => task.task_id === current) ? current : taskPayload.items[0]?.task_id || '')
  }

  useEffect(() => { reload().catch((reason: Error) => setMessage(`加载失败：${reason.message}`)) }, [])
  useEffect(() => {
    setStatus(role === 'adjudicator' ? 'disagreement' : 'all')
    const nextStatus = role === 'adjudicator' ? 'disagreement' : 'all'
    reload(role, nextStatus).catch((reason: Error) => setMessage(`加载失败：${reason.message}`))
  }, [role])
  useEffect(() => {
    if (!selected) return
    const saved = selected.annotation
    setForm({ ...blankAnnotation(selected.task_id, role), ...saved, task_id: selected.task_id, role } as NaturalGoldAnnotation)
    setMessage('')
  }, [selected?.task_id, role])

  const changeStatus = (next: string) => {
    setStatus(next)
    reload(role, next).catch((reason: Error) => setMessage(`加载失败：${reason.message}`))
  }
  const update = (field: keyof NaturalGoldAnnotation, value: string) => setForm((current) => ({ ...current, [field]: value }))
  const save = async () => {
    if (!selected) return
    setSaving(true); setMessage('')
    try {
      await api.saveNaturalGoldAnnotation({ ...form, task_id: selected.task_id, role })
      setMessage('已保存并写入独立标注记录')
      const currentIndex = tasks.findIndex((task) => task.task_id === selected.task_id)
      await reload(role, status)
      const next = tasks.slice(currentIndex + 1).find((task) => role === 'adjudicator' ? task.status === 'disagreement' : task.status === 'pending')
      if (next) setSelectedId(next.task_id)
    } catch (reason) {
      setMessage(reason instanceof Error ? `保存失败：${reason.message}` : '保存失败')
    } finally { setSaving(false) }
  }

  const requestedPage = Number(form.evidence_pages.split(',')[0]) || 1
  const canAdjudicate = role !== 'adjudicator' || selected?.status === 'disagreement' || selected?.status === 'adjudicated'
  const filters = role === 'adjudicator' ? ['all', 'disagreement', 'adjudicated', 'waiting', 'agreed'] : ['all', 'pending', 'completed']

  return <main className="natural-gold-page">
    <header className="gold-header">
      <div><span className="kicker">NATURAL-GOLD V1</span><h1>双人盲标与分歧仲裁</h1><p>固定 300 条自然样本；金标准完成前不生成模型准确率。</p></div>
      <div className="gold-role-picker"><label>当前角色</label>{(Object.keys(ROLE_LABELS) as NaturalGoldRole[]).map((key) => <button key={key} className={role === key ? 'active' : ''} onClick={() => setRole(key)}>{ROLE_LABELS[key]}</button>)}<a href={api.naturalGoldManifestUrl()}>导出冻结清单 ↓</a></div>
    </header>
    <section className="gold-kpis">
      <article><span>金标准进度</span><strong>{summary?.gold_count || 0}<small> / {summary?.total_tasks || 300}</small></strong><i style={{ width: `${(summary?.gold_progress || 0) * 100}%` }} /></article>
      <article><span>标注员 A</span><strong>{summary?.role_completed.annotator_a || 0}</strong><small>独立记录</small></article>
      <article><span>标注员 B</span><strong>{summary?.role_completed.annotator_b || 0}</strong><small>独立记录</small></article>
      <article><span>待仲裁</span><strong>{summary?.pending_adjudication || 0}</strong><small>{summary?.both_complete || 0} 条完成双标</small></article>
      <article><span>Disclosure κ</span><strong>{summary?.disclosure_kappa == null ? '—' : summary.disclosure_kappa.toFixed(3)}</strong><small>仅基于已完成双标</small></article>
    </section>
    <section className="gold-boundary"><strong>{summary?.manifest_state === 'frozen' ? '清单已冻结' : '清单状态异常'}</strong><span>E/S/G 各 100 · {summary?.sampling.unique_reports || 0} 份报告 · 65 个指标</span><code>{summary?.manifest_sha256.slice(0, 16) || '—'}…</code><p>{role === 'adjudicator' ? '仲裁视图显示 A/B 的独立答案，但仍不显示模型输出。' : '盲标视图不会返回模型结果或另一位标注员的答案。'}</p></section>
    <section className="gold-workspace">
      <aside className="gold-task-panel panel">
        <div className="section-heading compact"><div><span className="kicker">SAMPLE QUEUE</span><h2>{ROLE_LABELS[role]}任务</h2></div><span className="no-score-pill">{tasks.length} 条</span></div>
        <div className="gold-filters">{filters.map((key) => <button key={key} className={status === key ? 'active' : ''} onClick={() => changeStatus(key)}>{key === 'all' ? '全部' : STATUS_LABELS[key]}</button>)}</div>
        <div className="gold-task-list">{tasks.map((task) => <button key={task.task_id} className={selected?.task_id === task.task_id ? 'active' : ''} onClick={() => setSelectedId(task.task_id)}><span className={`dimension-dot dim-${task.dimension}`}>{task.dimension}</span><span><strong>{task.indicator_name}</strong><small>{task.report_id.replace(/_20\d\d_.*/, '').replace(/^\d+_/, '')}</small><i>#{task.sample_order} · {task.indicator_type}</i></span><b className={`gold-status ${task.status}`}>{STATUS_LABELS[task.status]}</b></button>)}</div>
      </aside>
      <section className="gold-document-column">
        <header><div><span className="kicker">SOURCE DOCUMENT</span><h2>{selected?.report_id || '选择任务'}</h2></div>{selected ? <a href={api.pdfUrl(selected.report_id)} target="_blank">新窗口打开 ↗</a> : null}</header>
        {selected ? <PdfEvidenceViewer url={api.pdfUrl(selected.report_id)} evidence={null} requestedPage={requestedPage} /> : <div className="empty-state">当前筛选没有任务</div>}
      </section>
      <aside className="gold-form-panel panel">
        {selected ? <><div className="gold-task-title"><span className={`dimension-dot dim-${selected.dimension}`}>{selected.dimension}</span><div><small>{selected.indicator_id}</small><h2>{selected.indicator_name}</h2><p>{selected.indicator_type === 'quantitative' ? '找到披露时，必须填写原文值、证据页和最小证据。' : '判断是否存在具有实质内容的披露，并记录最小证据。'}</p></div></div>
          {role === 'adjudicator' && selected.annotations ? <div className="gold-comparison"><div className="gold-differences">分歧字段：{selected.disagreement_fields?.map((field) => FIELD_LABELS[field] || field).join('、') || '无'}</div><AnnotationSnapshot title="标注员 A" value={selected.annotations.annotator_a} /><AnnotationSnapshot title="标注员 B" value={selected.annotations.annotator_b} /></div> : null}
          <div className="gold-disclosure"><span>披露判断</span>{(['found', 'missing', 'uncertain'] as NaturalGoldDisclosure[]).map((key) => <button key={key} className={form.disclosure === key ? 'active' : ''} onClick={() => update('disclosure', key)}>{key === 'found' ? '已披露' : key === 'missing' ? '未找到' : '无法判断'}</button>)}</div>
          <div className="gold-form-grid"><label>声明主体<input value={form.subject} onChange={(event) => update('subject', event.target.value)} placeholder="如：公司及境内子公司" /></label><label>报告期间<input value={form.period} onChange={(event) => update('period', event.target.value)} placeholder="如：2025 年度" /></label><label className="wide">统计范围 / scope<input value={form.scope} onChange={(event) => update('scope', event.target.value)} placeholder="组织、地理、业务或排放范围" /></label><label>原文值<input value={form.value} onChange={(event) => update('value', event.target.value)} /></label><label>原文单位<input value={form.unit} onChange={(event) => update('unit', event.target.value)} /></label><label className="wide">证据页码<input value={form.evidence_pages} onChange={(event) => update('evidence_pages', event.target.value)} placeholder="多页使用逗号，例如 12,13" /></label><label className="wide">最小证据文本<textarea rows={4} value={form.evidence_text} onChange={(event) => update('evidence_text', event.target.value)} placeholder="粘贴能独立支持判断的最小连续原文" /></label><label>信心<select value={form.confidence} onChange={(event) => update('confidence', event.target.value)}><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label><label>标注人<input value={form.reviewer} onChange={(event) => update('reviewer', event.target.value)} /></label><label className="wide">备注<textarea rows={2} value={form.note} onChange={(event) => update('note', event.target.value)} placeholder="无法判断时必须写明原因" /></label></div>
          <button className="save-gold" disabled={saving || !canAdjudicate} onClick={save}>{saving ? '正在保存…' : role === 'adjudicator' ? '保存仲裁结论' : '保存独立标注'}</button>
          {!canAdjudicate ? <small className="gold-form-note">只有 A/B 已完成且存在分歧的任务需要仲裁。</small> : null}{message ? <p className={message.startsWith('保存失败') || message.startsWith('加载失败') ? 'error-text' : 'success-text'}>{message}</p> : null}
        </> : <div className="empty-state">当前筛选没有任务</div>}
      </aside>
    </section>
  </main>
}
