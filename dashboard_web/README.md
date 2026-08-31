# ESG ClaimGuard Dashboard

这是比赛项目的独立前端实现，不依赖公司内部代码、服务或资源。前端使用 React、TypeScript、Vite 和 PDF.js；后端 API 仅使用 Python 标准库。

## 开发运行

终端一：

```bash
/opt/miniconda3/bin/conda run -n paperagent python -m dashboard_api.server
```

终端二：

```bash
cd dashboard_web
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。

## 生产运行

```bash
bash scripts/run_dashboard.sh
```

访问 `http://127.0.0.1:8765`。脚本在缺少 `dist/` 时自动安装前端依赖并构建。

## 功能

- 系统规模、E/S/G 分布和指标类型看板；
- 报告与指标筛选；
- PDF 原文渲染和 bbox 证据高亮；
- 结构化结果、置信度、耗时和风险信息；
- 人工复核与 SQLite 本地持久化；
- 数据覆盖、工程完成门与人工复核工作流展示；
- 当前报告结果 CSV 导出；
- 新 PDF 上传、后台任务进度和失败原因展示；
- 上传后自动完成 PDF 校验登记、MinerU 解析、ESG-65 召回、Qwen3 抽取和结果入库。
- 声明、证据、数值约束和披露条款组成的可查询约束图；
- 阻断、重要、提示三级问题清单，不使用未经校准的伪精确分数；
- 声明—证据失配与总量—分项口径差异候选；
- issue-level 确认、修正、待补材料、接受风险和排除记录；
- 预审工作底稿 CSV 导出。
- 明确区分自动运行状态与人工真值，不把工作流标签冒充准确率评测；

## 产品定位

系统不是 ESG 评分、企业排名或法定审计工具。它帮助报告编制复核人员发现披露内部的证据失配、口径差异和条款覆盖提示，并形成可追溯工作底稿。新模型合同见 `docs/ai_contest/题目分析.md`。

## 上传流水线

默认 `claimguard` 配置顺序执行两个本地进程：MinerU 3.4 的 `vlm-engine` 使用 MinerU2.5-Pro-2605-1.2B 完成版面与 OCR，进程退出并释放显存后，再临时启动 `llama-server` 运行 Qwen3.6-27B Q4_K_M。文本抽取不加载视觉投影；视觉投影仅为后续困难页面复核保留。每项任务结束都会关闭 27B 服务，因此两个模型不会同时驻留。

运行参数可通过 `ESG_MINERU_BACKEND`、`ESG_LLM_API`、`ESG_MODEL`、`ESG_LLAMA_SERVER_BIN`、`ESG_QWEN_MODEL_PATH`、`ESG_QWEN_MMPROJ_PATH` 和 `ESG_GGML_CUDA_BACKEND` 显式配置；测试或多实例运行可通过 `ESG_TASK_ROOT` 和 `ESG_REVIEW_DB` 隔离任务状态与复核数据库。模型权重位于系统模型目录，不属于项目或提交包。正式环境不启用 V1/V2 静默回退。

新 PDF 计算 SHA-256 并登记到隔离任务目录，随后进入与正式 V3 相同的 canonical 解析、ESG-65 抽取和证据门禁。上传任务不覆盖冻结 manifest 中的 200 份正式结果；全量 V3 完成门通过后，网站只以 `formal_current` 为默认正式数据集。

## 生产验收

以下命令会使用临时任务目录和临时 SQLite 启动完整生产服务，检查前端入口、核心 API、PDF 证据与工作底稿后自动关闭，不会改动正式复核或金标准数据：

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/smoke_dashboard.py
```
