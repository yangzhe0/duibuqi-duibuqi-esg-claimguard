# 正式全量运行完成态与复验说明

本文件记录已经结束的正式运行，不是启动新一轮抽取的操作手册。

## 冻结范围

- 报告：200 份；
- 页数：10,528 页；
- 指标：65 项（E/S/G 为 25/20/20）；
- 结果网格：13,000 个唯一 `report_id × indicator_id`；
- 解析：MinerU2.5-Pro-2605-1.2B；
- 抽取：Qwen3.6-27B Q4_K_M；
- 正式输出：`outputs/formal_v3_mineru25_qwen36/`。

## 完成证据

正式运行已结束，MinerU 为 200/200，结果为 found 7,688、missing 5,312、error 0。完成证据为：

- `parse_summary.json`：解析范围与页数；
- `extraction/run_summary.json`：运行级调用、墙钟和恢复说明；
- `extraction/extraction_results.csv`：13,000 条正式结果；
- `extraction/manual_reconciliation.csv`：209 条 Codex Agent 模拟人工工程复核；
- `validation.json`：严格完成门及定量来源计数；
- `CHECKSUMS.sha256`：冻结产物哈希；
- `COMPLETE.json`：工程完成标志。

正式数据已经自包含。产品运行和复验均不需要已删除的历史目录、桥接输入或兼容 fallback。

## 统计口径

`run_summary.json` 中的 10,015 是运行级生成调用数。`extraction_results.csv` 中具有正 `elapsed_seconds` 的行数是结果行级耗时样本，两者不是同一统计对象。任何图表都必须分别命名。

定量结果必须分别统计：

- value origin：直接读取、明确推导；
- unit origin：原文单位、规范化或推断单位。

这些分类数必须在使用时读取 `validation.json`，不得沿用文档中的旧数字。

## 只读复验

运行 Python 前先检查现有 Conda 环境：

```bash
/opt/miniconda3/bin/conda env list
```

随后可执行：

```bash
cd <project-root>
/opt/miniconda3/bin/conda run -n paperagent python scripts/validate_ai_contest_readiness.py
(cd outputs/formal_v3_mineru25_qwen36 && sha256sum -c CHECKSUMS.sha256)
/opt/miniconda3/bin/conda run -n paperagent python -m unittest discover -s tests
(cd dashboard_web && npm run build)
git diff --check
```

不得重跑 MinerU、Qwen、209 条模拟人工工程复核或新的全量抽取。若验证失败，应先定位数据、代码或材料之间的不一致，不得通过重新推理覆盖冻结结果。

## 结论边界

`COMPLETE.json` 与 validation 证明工程链路完整和证据可追溯，不证明语义准确率。本作品不把未经独立人工评测的 Precision、Recall、F1 或准确率领先作为成果声明。
