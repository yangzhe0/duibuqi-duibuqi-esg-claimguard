# 术语表

> **状态：已废止（2026-08-09）。** 新术语统一见 [术语表格.md](./术语表格.md)。

| 中文术语 | 英文术语 | 缩写/符号 | 定义 |
|---|---|---|---|
| 可信披露诊断台 | Trustworthy Disclosure Diagnostic Workbench | TDDW | 基于原文证据组织 ESG 抽取、诊断和人工复核的产品 |
| 证据风险图 | Evidence Risk Graph | ERG | 报告、指标、证据块、同行参照和反馈关系组成的可解释结构 |
| 复核优先级 | Review Priority | `Priority(r,i)` | 表示 report-indicator 任务值得优先人工检查的 0—100 数值 |
| 规则风险 | Rule Risk | `R(r,i)` | 已知结构错误模式带来的风险分量 |
| 证据不确定性 | Evidence Uncertainty | `U(r,i)` | 候选竞争、字段完整性、后处理和置信信息共同产生的不确定性 |
| 同行披露缺口 | Corpus Disclosure Gap | `G(r,i)` | 本报告 missing、但该指标在语料中普遍 found 的提示 |
| 人工反馈风险 | Human Feedback Risk | `F(i)` | 基于指标历史复核结果和平滑先验计算的反馈分量 |
| 可行动缺口 | Actionable Gap | — | 语料 found 率不低于阈值且当前报告 missing 的指标 |
| 证据块 | Evidence Block | block | MinerU 解析得到、带页码和坐标框的最小可追溯内容单元 |
| 风险覆盖率 | Risk Recall@K | — | 前 K 个队列任务覆盖已知规则风险样本的比例 |
| 工作量削减 | Workload Reduction | — | 达到目标覆盖率时相对全量检查减少的任务比例 |
