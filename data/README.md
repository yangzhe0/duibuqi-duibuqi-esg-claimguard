# Data Directory

本目录保存当前阶段的原始候选 PDF 报告库及其索引。

## 目录说明

- `raw_pdfs/`：200 份 CNINFO ESG 相关原始候选 PDF 报告。
- `mineru_outputs/`：预留给后续 MinerU 或其他 PDF 解析工具输出。
- `report_index.csv`：主索引，仅包含成功下载且本地路径有效的 PDF 记录。
- `download_log.csv`：下载与跳过日志。

## 当前状态

- PDF 数量：200。
- 主索引记录数：200。
- 每一行 `local_path` 均真实存在。
- 主索引 `error` 非空数量为 0。
- 当前 200 份 PDF 是原始候选报告库，不是训练集、测试集或最终实验集。

## 后续使用原则

后续应先进行内容级解析质量检查，再确定有效样本、人工标注子集和实验划分。
