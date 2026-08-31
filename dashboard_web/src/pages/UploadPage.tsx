import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { ExtractionResult, PipelineTask, TaskPreaudit, TaskSummary } from '../types'

const steps = [
  ['PDF 安全检查与登记', 'registered'],
  ['MinerU 版面解析', 'mineru'],
  ['ESG-65 候选证据召回', 'extracting'],
  ['Qwen3 约束式结构化抽取', 'extracting'],
  ['结果入库与人工复核', 'completed'],
] as const

const stageOrder: Record<string, number> = { queued: 0, registered: 1, mineru: 1, extracting: 3, completed: 5, failed: -1 }

export function UploadPage({ pipelineReady }: { onOpenAudit: (reportId: string) => void; pipelineReady: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [task, setTask] = useState<PipelineTask | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [taskSummary, setTaskSummary] = useState<TaskSummary | null>(null)
  const [taskResults, setTaskResults] = useState<ExtractionResult[]>([])
  const [taskPreaudit, setTaskPreaudit] = useState<TaskPreaudit | null>(null)
  const running = task?.status === 'queued' || task?.status === 'running'

  useEffect(() => {
    if (!task || task.status === 'completed' || task.status === 'failed') return
    const timer = window.setInterval(async () => {
      try { setTask(await api.task(task.task_id)) }
      catch (reason) { setError(reason instanceof Error ? reason.message : '任务状态查询失败') }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [task?.task_id, task?.status])

  const upload = async () => {
    if (!file) return
    setBusy(true); setError(''); setTask(null); setTaskSummary(null); setTaskResults([]); setTaskPreaudit(null)
    try {
      setTask(await api.upload(file))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '上传失败')
    } finally { setBusy(false) }
  }

  const openTaskResults = async () => {
    if (!task) return
    setBusy(true); setError('')
    try {
      const [summary, results, preaudit] = await Promise.all([api.taskSummary(task.task_id), api.taskResults(task.task_id), api.taskPreaudit(task.task_id)])
      setTaskSummary(summary); setTaskResults(results.items); setTaskPreaudit(preaudit)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '任务结果查询失败')
    } finally { setBusy(false) }
  }

  return <main className="page upload-page"><section className="page-title"><div><span className="kicker">NEW REPORT INTAKE</span><h1>接入新报告</h1><p>上传公开 ESG、可持续发展或社会责任报告，进入统一解析与证据抽取流程。</p></div></section>
    <section className="upload-layout">
      <article className={`upload-zone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFile(event.dataTransfer.files[0] || null) }}>
        <div className="upload-icon">↥</div><h2>{file ? file.name : '拖放 PDF 报告到这里'}</h2><p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '单个文件不超过 200 MB，提交后自动完成解析和指标抽取'}</p>
        <label className="secondary-button">选择文件<input type="file" accept="application/pdf" hidden onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
        <button className="primary-button" disabled={!file || busy || running || !pipelineReady} onClick={upload}>{busy ? '正在上传' : running ? '任务处理中' : !pipelineReady ? '离线流水线未就绪' : '上传并创建任务'}</button>
        {!pipelineReady ? <div className="upload-readiness-warning">请先确认 MinerU2.5 解析服务与 Qwen3.6-27B 抽取运行时均已就绪。</div> : null}
        {task ? <div className={`upload-status ${task.status}`}><strong>{task.message}</strong><span>{task.progress}% · {task.report_id}</span><progress max="100" value={task.progress} />{task.error ? <small>{task.error}</small> : null}{task.status === 'completed' ? <button className="primary-button" disabled={busy} onClick={openTaskResults}>查看本次任务结果 →</button> : null}</div> : null}
        {error ? <div className="upload-status failed">{error}</div> : null}
      </article>
      <article className="panel intake-steps"><div className="section-heading"><div><span className="kicker">PROCESS</span><h2>处理流程</h2></div></div>
        {steps.map(([label], index) => { const active = task ? stageOrder[task.stage] > index : false; return <div className={`intake-step ${active ? 'done' : ''}`} key={label}><span>{active ? '✓' : index + 1}</span><div><strong>{label}</strong><small>{active ? '已完成' : task && stageOrder[task.stage] === index ? '正在执行' : '等待任务执行'}</small></div></div> })}
      </article>
    </section>
    {taskSummary ? <section className="panel task-results"><div className="section-heading"><div><span className="kicker">TASK-SCOPED RESULT</span><h2>{taskSummary.report_id}</h2><small>{taskSummary.dataset_id} · 与 formal_current 完全隔离</small></div><a href={api.taskPdfUrl(taskSummary.task_id)} target="_blank">查看本次上传 PDF ↗</a></div>
      <div className="task-result-metrics"><span>指标 <b>{taskSummary.total_results}</b></span><span>有证据 <b>{taskSummary.found_count}</b></span><span>证据不足 <b>{taskSummary.missing_count}</b></span><span>错误 <b>{taskSummary.error_count}</b></span><span>预审线索 <b>{taskPreaudit?.total ?? 0}</b></span></div>
      <div className="task-result-table"><table><thead><tr><th>指标</th><th>状态</th><th>结果</th><th>证据</th></tr></thead><tbody>{taskResults.map((row) => <tr key={row.indicator_id}><td>{row.indicator_name}</td><td>{row.status}</td><td>{[row.value, row.unit].filter(Boolean).join(' ') || row.qualitative_text || '—'}</td><td>{row.evidence_quote || '当前候选证据不足'}</td></tr>)}</tbody></table></div>
    </section> : null}
  </main>
}
