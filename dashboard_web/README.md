# ESG ClaimGuard Dashboard

这是比赛项目的独立前端实现，不依赖公司内部代码、服务或资源。前端使用 React、TypeScript、Vite 和 PDF.js；后端 API 仅使用 Python 标准库。

## 开发运行

终端一：

```bash
/home/sues01/.conda/envs/paperagent/bin/python -m dashboard_api.server
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
- 数据覆盖、工作流记录与 Natural-Gold 评测协议展示（正式准确率待冻结金标准后计算）；
- 当前报告结果 CSV 导出；
- 新 PDF 上传、后台任务进度和失败原因展示；
- 上传后自动完成 PDF 校验登记、MinerU 解析、ESG-65 召回、Qwen3 抽取和结果入库。
- 声明、证据、数值约束和披露条款组成的可查询约束图；
- 阻断、重要、提示三级问题清单，不使用未经校准的伪精确分数；
- 声明—证据失配与总量—分项口径差异候选；
- issue-level 确认、修正、待补材料、接受风险和排除记录；
- 预审工作底稿 CSV 导出。
- Natural-Gold v1 的 300 条固定分层样本、双人盲标和第三人分歧仲裁；
- 金标准完成前锁住模型 Precision、Recall 和 F1，防止把工作流标签冒充测试集；

## 产品定位

系统不是 ESG 评分、企业排名或法定审计工具。它帮助报告编制复核人员发现披露内部的证据失配、口径差异和条款覆盖提示，并形成可追溯工作底稿。新模型合同见 `docs/ai_contest/题目分析.md`。

## 上传流水线

服务默认复用本机 `/home/sues01/.conda/envs/mineru/bin/mineru` 和 Ollama 的 `qwen3:30b`，不依赖公司项目。可通过 `ESG_MINERU_BIN`、`ESG_MODEL`、`ESG_OLLAMA_URL` 覆盖。

新 PDF 通过 SHA-256 去重后登记到 `data/raw_pdfs`、`data/report_index.csv` 和 `data/download_log.csv`；MinerU 结构化结果进入 `data/parsed_reports_v1/reports`；每项任务的抽取产物和日志保存在 `outputs/dashboard/tasks/<task_id>`。任务结果自动合并到仪表盘查询，不修改已有 200 份正式基线结果。
