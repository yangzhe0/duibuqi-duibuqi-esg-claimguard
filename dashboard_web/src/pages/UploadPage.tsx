import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PipelineTask } from '../types'

const steps = [
  ['PDF 安全检查与登记', 'registered'],
  ['MinerU 版面解析', 'mineru'],
  ['ESG-65 候选证据召回', 'extracting'],
  ['Qwen3 约束式结构化抽取', 'extracting'],
  ['结果入库与人工复核', 'completed'],
] as const

const stageOrder: Record<string, number> = { queued: 0, registered: 1, mineru: 1, extracting: 3, completed: 5, failed: -1 }

export function UploadPage({ onOpenAudit, pipelineReady }: { onOpenAudit: (reportId: string) => void; pipelineReady: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [task, setTask] = useState<PipelineTask | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
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
    setBusy(true); setError(''); setTask(null)
    try {
      setTask(await api.upload(file))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '上传失败')
    } finally { setBusy(false) }
  }

  return <main className="page upload-page"><section className="page-title"><div><span className="kicker">NEW REPORT INTAKE</span><h1>接入新报告</h1><p>上传公开 ESG、可持续发展或社会责任报告，进入统一解析与证据抽取流程。</p></div></section>
    <section className="upload-layout">
      <article className={`upload-zone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFile(event.dataTransfer.files[0] || null) }}>
        <div className="upload-icon">↥</div><h2>{file ? file.name : '拖放 PDF 报告到这里'}</h2><p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '单个文件不超过 200 MB，提交后自动完成解析和指标抽取'}</p>
        <label className="secondary-button">选择文件<input type="file" accept="application/pdf" hidden onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
        <button className="primary-button" disabled={!file || busy || running || !pipelineReady} onClick={upload}>{busy ? '正在上传' : running ? '任务处理中' : !pipelineReady ? '离线流水线未就绪' : '上传并创建任务'}</button>
        {!pipelineReady ? <div className="upload-readiness-warning">请先确认 MinerU、Ollama 和 qwen3:30b 均已启动。</div> : null}
        {task ? <div className={`upload-status ${task.status}`}><strong>{task.message}</strong><span>{task.progress}% · {task.report_id}</span><progress max="100" value={task.progress} />{task.error ? <small>{task.error}</small> : null}{task.status === 'completed' ? <button className="primary-button" onClick={() => onOpenAudit(task.report_id)}>进入披露预审 →</button> : null}</div> : null}
        {error ? <div className="upload-status failed">{error}</div> : null}
      </article>
      <article className="panel intake-steps"><div className="section-heading"><div><span className="kicker">PROCESS</span><h2>处理流程</h2></div></div>
        {steps.map(([label], index) => { const active = task ? stageOrder[task.stage] > index : false; return <div className={`intake-step ${active ? 'done' : ''}`} key={label}><span>{active ? '✓' : index + 1}</span><div><strong>{label}</strong><small>{active ? '已完成' : task && stageOrder[task.stage] === index ? '正在执行' : '等待任务执行'}</small></div></div> })}
      </article>
    </section>
  </main>
}
