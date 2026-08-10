# ESG 报告数据智能提取与分析

本项目对应 B 题“ESG 报告数据智能提取与分析：基于大模型的定量与定性指标识别”，并扩展为面向人工智能创新大赛的 **ESG ClaimGuard｜可持续披露一致性预审系统**。项目以 200 份上市公司 ESG 类 PDF 报告为数据基础，将结构化声明、原文证据、数值约束和官方披露条款组织为可查询的声明—证据约束图，帮助报告编制复核人员在发布前发现证据失配和口径差异，并导出预审工作底稿。

项目不做 ESG 评分、企业排名或投资建议。系统输出保留 evidence_quote、page_no、block_id 和 risk_tag，便于逐条复核。

## 目录结构

```text
data/                 原始 PDF、解析结果和数据索引
docs/                 赛题、格式要求和项目台账
latex/                最终论文工程与 PDF
outputs/              正式抽取结果、质量复核结果和系统数据
scripts/              数据构建、抽取、质量分析和系统数据脚本
src/esg_demo/         核心抽取模块
dashboard_api/        声明—证据约束图、问题台账和预审 API
dashboard_web/        React 比赛展示与人工处置工作台
tests/                单元测试
streamlit_app.py      Streamlit 复核系统
```

## 关键产物

- 最终论文：`latex/MathModel.pdf`
- 论文源码：`latex/MathModel.tex`
- 图表契约：`latex/figure_contracts.md`
- 图表面板：`latex/figure_gallery.html`
- 自查记录：`latex/SELF_CHECK.md`
- 项目台账：`docs/台账.md`
- 正式结果：`outputs/formal_v2/llm_200/extraction_results.csv`
- 指标池：`outputs/formal_v2/indicator_pool_v2.csv`
- 质量诊断：`outputs/review/quality_metrics.json`
- 风险样本：`outputs/review/risk_cases.csv`
- 重构模型合同：`docs/ai_contest/题目分析.md`
- MVP 合同与覆盖验证：`outputs/ai_contest/preaudit_mvp_validation.md`
- Natural-Gold 协议：`docs/ai_contest/NATURAL_GOLD_PROTOCOL.md`
- Natural-Gold 冻结清单：`data/evaluation/natural_gold/v1/manifest.csv`
- Pilot-30 双路 Silver 汇总：`outputs/ai_contest/natural_gold_pilot30/summary.md`
- Pilot-30 人工核查队列：`outputs/ai_contest/natural_gold_pilot30/human_review_queue.csv`
- Pilot-30 图表预览：`outputs/ai_contest/natural_gold_pilot30/figures/index.html`

## 数据规模

| 项目 | 数值 |
|---|---:|
| 原始 ESG 类 PDF | 200 |
| 公司数（文件名口径） | 198 |
| ESG 指标 | 65 |
| E/S/G 指标 | 25 / 20 / 20 |
| 定量/定性/机制性指标 | 35 / 15 / 15 |
| report-indicator 任务 | 13000 |
| found / missing / error | 7777 / 5223 / 0 |
| 具体风险样本 | 164 |

found/missing/error 是结构化抽取运行结果分布，不是人工标注评价结论。

## 运行方式

重新生成论文图表并编译 PDF：

```bash
bash latex/build.sh
```

运行 Streamlit 复核系统：

```bash
streamlit run streamlit_app.py
```

运行独立的比赛展示前端：

```bash
bash scripts/run_dashboard.sh
```

浏览器访问 `http://127.0.0.1:8765`。该版本提供声明—证据约束图、问题台账、PDF 证据高亮、人工处置和工作底稿导出；网页上传会自动调用本机 MinerU Conda 环境和 Ollama `qwen3:30b`，完成解析、ESG-65 抽取及结果入库。详细说明见 `dashboard_web/README.md`。

建议演示路径：

1. 在“披露预审”选择系统推荐报告；
2. 打开“结构化数值无法在证据中定位”，对照声明值与表格原文；
3. 打开总量—分项口径差异候选，查看三段证据和可复算公式；
4. 跳转 PDF 页码与 bbox，选择确认、修正、待补材料、接受风险或排除；
5. 关闭问题后导出 CSV 工作底稿，检查问题 ID、证据、依据、责任人和状态；
6. 在“接入报告”上传新 PDF，等待 MinerU 与 Qwen3 完成后进入该报告预审。

Natural-Gold 数据建设路径：

1. 进入“金标准”，选择标注员 A，独立完成报告—指标任务；
2. 切换标注员 B，在看不到 A 与模型答案的条件下独立标注；
3. 切换分歧仲裁员，只处理 A/B 不一致的任务；
4. 300 条全部形成共识或完成仲裁后，系统才开放正式准确率计算。

为了先估计人工工作量，可运行冻结的 Pilot-30。Silver-A 使用严格块级检索，Silver-B 使用较宽的同页上下文检索；二者均由本机模型生成，只负责产生人工候选，不会写入 Natural-Gold。当前结果为 30/30 成对完成、11 条存在字段分歧、其中 3 条存在披露状态分歧，建议先人工核查这 11 条并抽查 4 条一致样本。

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/run_natural_gold_pilot.py --stage all
/opt/miniconda3/bin/conda run -n catalog python scripts/plot_natural_gold_pilot.py
```

重新生成 MVP 合同与覆盖验证：

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/validate_preaudit_mvp.py
```

重新生成同一规则的 Natural-Gold 清单并检查当前评测开关：

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/build_natural_gold.py
/opt/miniconda3/bin/conda run -n paperagent python scripts/evaluate_natural_gold.py
```

运行测试：

```bash
/opt/miniconda3/bin/conda run -n paperagent python -m unittest discover -s tests
```

## 方法概述

1. 将 PDF 解析为 Markdown、图片资源和块级 JSON。
2. 将每份报告表示为带页码、块号、类型和文本的内容块序列。
3. 构建 ESG-65 指标体系，区分 quantitative、qualitative 和 boolean 三类指标。
4. 对每个 report-indicator 任务召回候选证据。
5. 仅在候选证据范围内调用大语言模型，输出固定 JSON schema。
6. 对 value/unit、evidence_quote、page_no、block_id 和 risk_tag 做后处理与质量诊断。
7. 将声明、原文证据、计算约束和披露条款组织为可查询约束图，生成可复核问题而非企业评分。
8. 在问题级工作台完成人工确认、修正、待补材料、接受风险或排除，并导出可追溯底稿。

## 清理状态

当前提交版已移除旧论文、旧实验输出、外部参考工程克隆、临时编译文件、缓存文件和零散说明文档。最终论文工程统一位于 `latex/`，不再保留 `latex_final/`。
