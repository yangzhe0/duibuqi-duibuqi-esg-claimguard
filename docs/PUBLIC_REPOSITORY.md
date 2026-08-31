# 仓库发布与数据边界

本项目有两种对外形式，作用不同：

1. **Git 仓库**：保存完整开发历史、当前代码、210 份原始 PDF、正式抽取结果、文档源稿和提交材料；清理前状态由标签 `archive/pre-cleanup-20260831` 与提交 `a274286d` 保留。
2. **轻量公开 ZIP**：由 `scripts/build_public_repository.py` 生成，面向 200 MiB 限制的附件上传；不包含 `.git`、原始 PDF、完整 MinerU 解析目录、模型权重、日志和缓存。

两者不是两套产品。Git 仓库用于追溯和完整交接，轻量 ZIP 用于受文件大小与分发边界限制的评审附件。

## 当前 Git 仓库包含什么

- Dashboard API、React 前端、抽取核心、测试和维护脚本；
- 数据来源索引、下载日志和 210 份公开报告 PDF；
- 200 份正式队列的 manifest、13,000 条抽取结果、验证报告与校验和；
- 项目文档 Markdown、XeLaTeX 源文件、图表与真实产品截图；
- Remotion 视频工程与现有视频材料；
- 比赛四项最终提交件。

完整 MinerU `parsed/` 目录约 9.8 GiB，当前工作区保留但由 `.gitignore` 排除；清理前远端历史中仍可回溯旧解析数据。模型权重、`node_modules`、缓存、日志、环境变量和本地 SQLite 不进入 Git。

## 轻量 ZIP

```bash
cd <project-root>
/opt/miniconda3/bin/conda env list
/opt/miniconda3/bin/conda run -n paperagent python scripts/build_public_repository.py
```

输出位于 `outputs/public_repository/`。构建采用白名单收集，检查路径安全、敏感文件名、本机绝对路径、私钥头和令牌，并生成逐文件大小与 SHA-256 清单。

轻量 ZIP 可以直接复验抽取结果、API、前端构建和文档生成。完整重跑还需要从 Git 仓库或合法来源准备原始 PDF，并配置 MinerU、Qwen3.6 权重与 GPU。

## 版权与敏感信息

公开报告原文版权归发布主体。仓库中的 PDF 用于竞赛研究与复验，对外再分发或商用前需重新核对来源网站条款。推送前必须继续执行敏感路径与内容扫描，不得提交 `.env`、密钥、令牌、个人数据库或模型权重。
