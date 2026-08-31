# ESG ClaimGuard 公开仓库说明

## 上传边界

公开仓库应使用构建脚本生成的干净快照，不应直接上传当前工作目录，也不应携带原 `.git` 历史。当前工程的完整运行资产包含公开报告 PDF、MinerU 解析产物、模型运行日志和本地模型文件，体积大且可能受上游再分发条款约束，因此不属于公开代码快照。

公开快照包含：

- Dashboard API、React 前端、抽取核心、测试与当前维护脚本；
- 项目文档源稿、XeLaTeX 源文件、图表和依赖许可清单；
- 冻结正式运行的轻量 manifest、汇总、验证报告、抽取结果和校验和；
- Remotion 视频工程源文件及演示所需的项目自有素材；
- 逐文件大小与 SHA-256 清单。

公开快照不包含：

- 原始 ESG 报告 PDF 和 MinerU `parsed/` 目录；
- Qwen、MinerU 或其他模型权重；
- `node_modules`、构建缓存、日志、临时文件和本机软链接；
- `.git` 历史、密钥、令牌、环境变量文件和个人绝对路径；
- 比赛最终视频、独立配音等大体积上传件，它们仍在比赛正式提交目录单独管理。

## 构建与验证

```bash
cd <project-root>
/opt/miniconda3/bin/conda env list
/opt/miniconda3/bin/conda run -n base python scripts/build_public_repository.py
```

输出位于 `outputs/public_repository/`。构建过程采用白名单收集文件，检查路径安全、敏感文件名、本机绝对路径、私钥头和 Bearer Token，并生成 `PUBLIC_REPOSITORY_MANIFEST.json`。

如需上传到 Git 托管网站，建议解压公开快照后在新目录执行 `git init`，不要复用当前项目的历史 `.git` 目录。

## 复现层级

公开快照可以直接复验轻量数据、API、前端构建和文档生成。重新执行 200 份报告的完整解析与推理，还需要自行准备有权使用的报告文件、MinerU 运行环境、Qwen3.6 模型权重及相应 GPU 资源。
