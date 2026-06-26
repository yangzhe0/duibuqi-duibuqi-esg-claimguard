# ESG-Agent

面向上市公司 ESG 报告的智能解析与指标抽取系统。

## 项目背景

上市公司 ESG 报告通常以 PDF 形式披露，内容包含环境、社会与治理相关的定量指标和定性描述。报告篇幅较长、版式差异明显，且经常包含复杂表格、跨页段落和非结构化文本。人工阅读和录入效率较低，因此本项目拟探索基于 PDF 解析、大模型与结构化抽取方法的 ESG 指标识别流程。

## 当前任务目标

当前阶段聚焦于原始候选 PDF 报告库的构建与文件级校验，为后续内容解析、样本筛选、指标体系设计和模型实验提供可追溯的原始材料。

需要强调的是，当前 200 份 PDF 仅为原始候选 PDF 报告库，不是训练集、测试集、最终实验数据集或标注数据集。

## 当前完成情况

- 已从 CNINFO 采集 200 份 ESG 相关 PDF。
- `data/raw_pdfs/` 下有 200 个 PDF 文件。
- `data/report_index.csv` 正好 200 行。
- 主索引不混入 skipped / failed 记录。
- 每一行 `local_path` 均真实存在。
- `error` 非空数量为 0。
- 文件名格式为 `股票代码_公司简称_年份_报告类型.pdf`。
- LaTeX 主文件已能编译通过，输出 `latex/MathModel.pdf`，共 9 页。

## 数据来源概述

数据来源为巨潮资讯网（CNINFO）。采集时围绕 ESG 报告、可持续发展报告、社会责任报告、环境、社会及治理报告等相关主题进行检索和筛选。当前数据仅完成文件级一致性校验，尚未完成内容级解析质量评估、人工标注或训练集/测试集划分。

## 技术路线规划

1. 构建原始候选 PDF 报告库并完成文件级校验。
2. 抽样使用 MinerU 或其他 PDF 解析工具检查文本、表格和版面解析质量。
3. 基于内容级检查结果制定有效样本筛选规则。
4. 构建 ESG 指标 schema，覆盖环境、社会、治理三个维度。
5. 对有效样本进行结构化抽取、人工核查和结果统计。
6. 在完成有效样本确认后，再设计开发集、测试集或人工标注子集。

## 当前目录结构

```text
contest_xiaoshumo/
├── README.md
├── docs/
│   ├── PROJECT_STATUS.md
│   ├── DATA_CARD.md
│   ├── TASK_PLAN.md
│   └── LATEX_NOTES.md
├── data/
│   ├── raw_pdfs/
│   ├── mineru_outputs/
│   ├── report_index.csv
│   ├── download_log.csv
│   └── README.md
├── scripts/
├── src/
├── latex/
└── outputs/
    ├── figures/
    ├── tables/
    └── results/
```

## 快速开始

校验当前候选 PDF 报告库：

```bash
python3 scripts/validate_clean_dataset.py
```

编译 LaTeX 论文模板：

```bash
cd latex
latexmk -xelatex -interaction=nonstopmode -halt-on-error MathModel.tex
```

后续 MinerU 解析、结构化抽取和模型实验命令尚未确定，待内容级质量检查完成后补充。

## 后续计划

下一步建议从 200 份候选报告中抽样 20 份 PDF，运行 MinerU 或其他解析工具，生成 `parse_quality_sample_20.csv`，用于判断文本、表格和版面解析质量，并据此确定有效样本筛选规则。
