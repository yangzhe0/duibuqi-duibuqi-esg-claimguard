# Natural-Gold v1 数据建设协议

## 目的与边界

Natural-Gold 用于评价系统在真实 ESG 报告上的声明发现、字段抽取和证据定位能力。它不使用自动风险规则充当答案，也不与故障注入数据 ESG-Inject 混算。形成完整金标准前，只允许报告样本覆盖、标注进度和标注一致性，不允许报告模型 Precision、Recall 或 F1。

## 样本冻结

- 版本：`natural-gold-v1`
- 规模：300 个 `report × indicator` 任务
- 维度：E/S/G 各 100 条
- 指标：覆盖 ESG-65 全部 65 个指标；E 指标各抽 4 份报告，S/G 指标各抽 5 份报告
- 报告：在每个指标内使用固定种子对可用 PDF 做 SHA-256 排序后取样
- 防泄漏：样本清单不包含模型 status、value、evidence、confidence 或风险标签
- 完整性：`dataset.json` 保存固定种子和 `manifest.csv` 的 SHA-256；开始标注后不得覆盖 v1，如需改变规则必须新建 v2

## 三人角色

1. `annotator_a` 与 `annotator_b` 分别阅读原始 PDF，独立填写，不查看模型结果和对方标签。
2. 两人必须是不同人员。系统以 `task_id + role` 保存记录并保留更新时间。
3. 两人对 disclosure、主体、期间、范围、值、单位、最小证据页和最小证据文本的严格归一化结果完全一致时，自动形成共识金标准。
4. 任一字段不一致即进入仲裁队列。只有 A/B 均完成后，第三名 `adjudicator` 才能读取双方记录；仲裁员不得与 A/B 同名。

## 标注字段

| 字段 | 取值或要求 |
|---|---|
| `disclosure` | `found` / `missing` / `uncertain` |
| `subject` | 声明主体；无法判断可留空 |
| `period` | 报告期间或声明期间 |
| `scope` | 组织、地理、业务或排放范围 |
| `value` | 定量指标在 `found` 时必填 |
| `unit` | 原文单位，不擅自换算 |
| `evidence_pages` | `found` 时必填；多页使用逗号分隔 |
| `evidence_text` | 能独立支持判断的最小连续原文；`found` 时必填 |
| `confidence` | `high` / `medium` / `low` |
| `note` | `uncertain` 时必须说明不确定原因 |

`missing` 表示通读与合理检索后没有找到该指标披露；`uncertain` 只用于报告内容、表格结构或指标定义确实无法可靠判断的情况，不能用来替代尚未完成。

## 评价开关

只有 300 条任务全部形成共识或完成仲裁时，`ready_to_evaluate` 才会变为 `true`。此后评测脚本才输出：

- 披露发现 Precision、Recall、F1 与混淆计数；
- 定量值和单位严格匹配率；
- 证据页严格匹配率；
- 中文字符 bigram 证据文本 F1。

当前生产结果尚未结构化输出 subject、period、scope，评测结果必须把这些字段标记为 unavailable，不能用空值伪装成高分。

## 执行命令

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/build_natural_gold.py
/opt/miniconda3/bin/conda run -n paperagent python scripts/evaluate_natural_gold.py
```

标注工作台通过 `bash scripts/run_dashboard.sh` 启动，在“金标准”页面选择 A、B 或仲裁员角色。离线清单也可从 `/api/natural-gold/manifest.csv` 导出。
