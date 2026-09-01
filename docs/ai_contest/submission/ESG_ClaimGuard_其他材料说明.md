# ESG ClaimGuard 其他辅助材料（轻量审阅包）

本 ZIP 用于比赛评审和代码审阅，包含前后端源码、正式 13,000 行结果、必要 manifest、验证报告、技术论文、图表及逐文件 SHA-256 清单。它不是完整离线模型镜像。

## 包内可验证范围

- `formal_current` 的 200 份报告、65 项指标、13,000 行结果可由 API 读取和汇总；
- `validation.json`、`COMPLETE.json` 和工程证据可供独立检查；
- `SUBMISSION_MANIFEST.json` 记录每个包内文件的来源路径、大小和 SHA-256；
- `latex/submission/` 保存项目文档、300 字简介和技术论文的 XeLaTeX 源文件，`outputs/ai_contest/submission/latex_build_report.json` 记录构建结果与 PDF 哈希；
- React 前端可用 Node.js 20+ 在 `dashboard_web/` 目录执行 `npm ci && npm run build`；
- Python API 仅依赖 Python 3.11+ 标准库，可在解压根目录执行 `python -m dashboard_api.server`。

## 有意不包含的资产

根据提交包白名单和 200 MiB 限制，本包不包含 200 份源 PDF、10,528 页 canonical parsed、MinerU/Qwen 模型、`node_modules`、运行日志或缓存。因此：

- 总览、结果查询和工程统计可以离线审阅；
- PDF 回原文、bbox 证据定位和新报告上传推理需要在完整部署中恢复 `data/raw_pdfs/`、`outputs/final_results/parsed/` 及模型运行时；
- 包内 `CHECKSUMS.sha256` 是完整冻结数据集的 provenance 清单，部分被体积规则排除的文件不会在本轻量包中重复提供；包内完整性应以 `SUBMISSION_MANIFEST.json` 为准。

完整工程数据在原项目中是自包含的；本 ZIP 只声明自身为轻量审阅包，不把未打包资产描述为可用。

## 指标边界

13,000 行网格、逐字引文门和 SHA-256 证明工程完整性与可追溯性；本作品不把未经独立人工评测的 Precision、Recall、F1 或抽取准确率作为成果声明。
