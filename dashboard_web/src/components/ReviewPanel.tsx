import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { ExtractionResult } from '../types'

const LABELS = [
  ['correct', '正确'],
  ['partial', '部分正确'],
  ['incorrect', '错误抽取'],
  ['missed', '模型遗漏'],
  ['confirmed_missing', '确认未披露'],
] as const

export function ReviewPanel({ result, onSaved }: { result: ExtractionResult; onSaved: () => void }) {
  const [label, setLabel] = useState('correct')
  const [value, setValue] = useState(result.value || '')
  const [unit, setUnit] = useState(result.unit || '')
  const [evidence, setEvidence] = useState(result.evidence_quote || '')
  const [note, setNote] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLabel(result.status === 'missing' ? 'confirmed_missing' : 'correct')
    setValue(result.value || '')
    setUnit(result.unit || '')
    setEvidence(result.evidence_quote || '')
    setNote('')
    setMessage('')
    api.reviews(result.report_id, result.indicator_id).then(({ items }) => {
      const saved = items[0]
      if (!saved) return
      setLabel(saved.label)
      setValue(saved.corrected_value)
      setUnit(saved.corrected_unit)
      setEvidence(saved.corrected_evidence)
      setNote(saved.note)
    })
  }, [result])

  const save = async () => {
    setSaving(true); setMessage('')
    try {
      await api.saveReview({
        report_id: result.report_id,
        indicator_id: result.indicator_id,
        label,
        corrected_value: value,
        corrected_unit: unit,
        corrected_evidence: evidence,
        note,
        reviewer: '比赛复核员',
      })
      setMessage('复核记录已保存，诊断队列将自动更新')
      onSaved()
    } catch (reason) {
      setMessage(reason instanceof Error ? `保存失败：${reason.message}` : '保存失败')
    } finally { setSaving(false) }
  }

  return (
    <div className="review-panel">
      <div className="section-heading compact">
        <div><span className="kicker">HUMAN IN THE LOOP</span><h3>人工复核</h3></div>
        {message ? <span className={message.startsWith('保存失败') ? 'error-text' : 'success-text'}>{message}</span> : null}
      </div>
      <div className="review-labels">
        {LABELS.map(([key, text]) => (
          <button key={key} className={label === key ? 'active' : ''} onClick={() => setLabel(key)}>{text}</button>
        ))}
      </div>
      <div className="form-grid">
        <label>修正值<input value={value} onChange={(event) => setValue(event.target.value)} /></label>
        <label>修正单位<input value={unit} onChange={(event) => setUnit(event.target.value)} /></label>
      </div>
      <label>证据文本<textarea rows={3} value={evidence} onChange={(event) => setEvidence(event.target.value)} /></label>
      <label>复核备注<textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录判断依据或待确认问题" /></label>
      <button className="primary-button" disabled={saving} onClick={save}>{saving ? '正在保存…' : '保存复核结果'}</button>
    </div>
  )
}
