import { MetricCard } from '../components/MetricCard'
import type { Summary } from '../types'

function HorizontalBars({ values }: { values: Record<string, number> }) {
  const max = Math.max(...Object.values(values), 1)
  return <div className="bar-list">{Object.entries(values).map(([key, value]) => (
    <div className="bar-row" key={key}>
      <span>{key}</span><div><i style={{ width: `${value / max * 100}%` }} /></div><strong>{value.toLocaleString()}</strong>
    </div>
  ))}</div>
}

export function OverviewPage({ summary, onStartAudit, onUpload }: { summary: Summary; onStartAudit: () => void; onUpload: () => void }) {
  return (
    <main className="page overview-page">
      <section className="hero-panel">
        <div>
          <span className="kicker">SUSTAINABILITY DISCLOSURE PRE-REVIEW</span>
          <h1>在报告发布前，找出<br />互相打架的 ESG 声明</h1>
          <p>把段落、表格和披露条款连接成声明—证据约束图。系统给出冲突双方、计算过程和处置记录，最终导出可交付的预审工作底稿。</p>
          <div className="hero-actions"><button onClick={onStartAudit}>开始披露预审 <span>→</span></button><button onClick={onUpload}>接入新报告</button></div>
        </div>
        <div className="hero-orbit" aria-hidden="true"><span>E</span><span>S</span><span>G</span><b>65</b></div>
      </section>
      <section className="metric-grid">
        <MetricCard eyebrow="报告语料" value={summary.report_count.toString()} detail="份上市公司 ESG 报告" />
        <MetricCard eyebrow="结构化任务" value={summary.total_results.toLocaleString()} detail={`${summary.indicator_count} 个领域指标`} accent="green" />
        <MetricCard eyebrow="证据命中" value={`${(summary.found_rate * 100).toFixed(1)}%`} detail={`${summary.found_count.toLocaleString()} 条可追溯结果`} accent="gold" />
        <MetricCard eyebrow="运行错误" value={summary.error_count.toString()} detail="结构化任务 error 状态" accent="red" />
      </section>
      <section className="overview-grid">
        <article className="panel innovation-panel">
          <div className="section-heading"><div><span className="kicker">FROM CLAIM TO WORKPAPER</span><h2>一次预审，完成发现、判断、处置与交付</h2></div></div>
          <div className="innovation-steps">
            <div><span>01</span><strong>建图</strong><p>连接声明、原文证据、数值约束和适用条款。</p></div>
            <i>→</i><div><span>02</span><strong>核验</strong><p>识别数值失配、总分差异和证据不足。</p></div>
            <i>→</i><div><span>03</span><strong>处置</strong><p>确认、修正、待补材料、接受风险或排除。</p></div>
            <i>→</i><div><span>04</span><strong>交付</strong><p>导出含证据、依据、责任人和状态的工作底稿。</p></div>
          </div>
        </article>
        <article className="panel chart-panel">
          <div className="section-heading"><div><span className="kicker">DISCLOSURE MAP</span><h2>E / S / G 证据分布</h2></div><span className="data-note">自动抽取状态</span></div>
          <HorizontalBars values={summary.dimension_found} />
        </article>
        <article className="panel chart-panel">
          <div className="section-heading"><div><span className="kicker">CONTENT TYPE</span><h2>指标类型命中</h2></div><span className="data-note">found 结果</span></div>
          <HorizontalBars values={summary.type_found} />
        </article>
        <article className="panel pipeline-panel">
          <div className="section-heading"><div><span className="kicker">TRACEABLE PIPELINE</span><h2>证据约束抽取链路</h2></div></div>
          <div className="pipeline">
            {['PDF 解析', '原子声明', '证据关联', '约束核验', '问题处置', '底稿导出'].map((step, index) => (
              <div key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong>{index < 5 ? <i>→</i> : null}</div>
            ))}
          </div>
        </article>
      </section>
    </main>
  )
}
