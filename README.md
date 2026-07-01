# ESG 报告数据智能提取与分析

本项目对应 B 题“ESG 报告数据智能提取与分析：基于大模型的定量与定性指标识别”。项目以 200 份上市公司 ESG 类 PDF 报告为数据基础，构建 ESG-65 指标体系，完成从 PDF 结构化解析、内容块建模、候选证据召回、大语言模型约束抽取、后处理质量诊断到 Streamlit 可视化复核的完整流程。

项目不做 ESG 评分、企业排名或投资建议。系统输出保留 evidence_quote、page_no、block_id 和 risk_tag，便于逐条复核。

## 目录结构

```text
data/                 原始 PDF、解析结果和数据索引
docs/                 赛题、格式要求和项目台账
latex/                最终论文工程与 PDF
outputs/              正式抽取结果、质量复核结果和系统数据
scripts/              数据构建、抽取、质量分析和系统数据脚本
src/esg_demo/         核心抽取模块
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

运行测试：

```bash
python3 -m unittest discover -s tests
```

## 方法概述

1. 将 PDF 解析为 Markdown、图片资源和块级 JSON。
2. 将每份报告表示为带页码、块号、类型和文本的内容块序列。
3. 构建 ESG-65 指标体系，区分 quantitative、qualitative 和 boolean 三类指标。
4. 对每个 report-indicator 任务召回候选证据。
5. 仅在候选证据范围内调用大语言模型，输出固定 JSON schema。
6. 对 value/unit、evidence_quote、page_no、block_id 和 risk_tag 做后处理与质量诊断。
7. 通过 Streamlit 系统进行公司视角、指标视角、证据核验和高风险样本复核。

## 清理状态

当前提交版已移除旧论文、旧实验输出、外部参考工程克隆、临时编译文件、缓存文件和零散说明文档。最终论文工程统一位于 `latex/`，不再保留 `latex_final/`。
