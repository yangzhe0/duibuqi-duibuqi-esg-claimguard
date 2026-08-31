import { MetricCard } from '../components/MetricCard'
import type { ReviewMetrics, Summary } from '../types'

const LABELS: Record<string, string> = {
  correct: '正确', partial: '部分正确', incorrect: '错误抽取', missed: '模型遗漏', confirmed_missing: '确认未披露',
}

export function QualityPage({ metrics, summary }: { metrics: ReviewMetrics; summary: Summary }) {
  const max = Math.max(...Object.values(metrics.label_counts || {}), 1)
  return <main className="page quality-page">
    <section className="page-title"><div><span className="kicker">VALIDATION & GOVERNANCE</span><h1>验证与数据治理</h1><p>展示数据覆盖、工程完成门和人工复核工作流，不把自动运行状态解释为准确率。</p></div><span className="review-count">工作流记录 <strong>{metrics.reviewed_count}</strong> 条</span></section>
    <section className="metric-grid quality-metrics">
      <MetricCard eyebrow="人工工作流记录" value={metrics.reviewed_count.toLocaleString()} detail="用于产品闭环，不冒充金标准" />
      <MetricCard eyebrow="结构化 FOUND" value={summary.found_count.toLocaleString()} detail="自动运行状态，不等同正确" accent="green" />
      <MetricCard eyebrow="结构化 MISSING" value={summary.missing_count.toLocaleString()} detail="待复核状态，不等同遗漏" accent="gold" />
      <MetricCard eyebrow="平均推理耗时" value={`${summary.avg_inference_seconds.toFixed(3)}s`} detail={`${summary.model_call_count.toLocaleString()} 次候选证据判断`} accent="red" />
    </section>
    <section className="quality-grid">
      <article className="panel review-distribution"><div className="section-heading"><div><span className="kicker">REVIEW LABELS</span><h2>人工复核分布</h2></div></div>
        {Object.entries(metrics.label_counts || {}).map(([key, value]) => <div className="review-bar" key={key}><span>{LABELS[key] || key}</span><div><i style={{ width: `${value / max * 100}%` }} /></div><strong>{value}</strong></div>)}
        {!metrics.reviewed_count ? <div className="empty-hint">从“证据工作台”或“披露预审”开始记录人工判断。</div> : null}
      </article>
      <article className="panel methodology-card"><div className="section-heading"><div><span className="kicker">ACCEPTANCE BOUNDARY</span><h2>本次作品验收口径</h2></div></div>
        <ul><li><b>冻结</b><span>200 份报告与 65 项指标形成唯一结果网格</span></li><li><b>追溯</b><span>found 结果绑定页码、区块和原文引文</span></li><li><b>完整</b><span>运行清单、验证报告与 SHA-256 支持复验</span></li><li><b>边界</b><span>不声明未经独立人工评测的准确率</span></li></ul>
        <p>当前复核标签用于产品工作流和问题处置，不作为 Precision、Recall 或 F1 的计算依据。</p>
      </article>
      <article className="panel quality-warning"><span>!</span><div><strong>避免误读自动结果</strong><p>当前 {summary.found_count.toLocaleString()} 条 found 与 {summary.missing_count.toLocaleString()} 条 missing 是运行状态，不等同于准确率结论。只有经过人工复核的样本进入评测指标。</p></div></article>
    </section>
  </main>
}
