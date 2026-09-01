# ESG ClaimGuard 人工智能大赛提交就绪度

> 对照官方初赛提交规范生成。截止时间：**2026 年 9 月 1 日 23:59（北京时间）**。本报告不把系统内部统计解释为模型准确率。

## 结论

- 已具备：10 项
- 待整理：0 项
- 缺失：0 项
- 需要人工：0 项

技术原型和官方四项提交文件均已生成；上传前只需做文件名、可打开性与平台上传终检。 本作品不把未经独立人工评测的准确率作为成果声明，也不把额外人工标注列为本次交付任务。

## 官方要求逐项核验

| 要求 | 状态 | 当前证据 | 下一动作 |
|---|---|---|---|
| 可运行的 AI 原型 | 已具备 | 生产 smoke test 16 个端点通过 | 保持一键验收进入提交包 |
| AI inference 效果与运行指标 | 已具备 | 正式运行：200 份报告、10015 次 Qwen3.6 生成、错误 0；11280 条结果具有正行级耗时 | 在项目文档中与准确率指标分栏呈现 |
| 准确率声明边界 | 已具备 | 本作品仅声明工程完整性和证据可追溯性，不使用工程复核记录计算准确率 | 不声明未经独立人工评测的 Precision、Recall 或 F1 |
| 创新性论证 | 已具备 | 项目文档已用真实来源、数据格式、产品截图、典型正反案例和冻结结果说明四项机制 | 保持工程证据与效果指标边界 |
| 与已有工作对比调研 | 已具备 | 已形成关键词/正则、整份 PDF 单次问答、普通 RAG 三类预注册基线及参考资料 | 保持可审计性对比，不声明未经验证的准确率优势 |
| 数据、行业知识、算法和硬件来源 | 已具备 | 来源与借鉴台账已区分公开数据、标准、模型工具、学术借鉴与项目原创工程 | 部署或再分发前按上游许可证复核 |
| 300 字作品简介 PDF | 已具备 | outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_参赛作品简介.pdf、outputs/ai_contest/submission/supporting/队不起队不起_ESG ClaimGuard_参赛作品简介.pdf | 提交前再次核对文件可打开且正文不超过 300 字 |
| 模板项目文档 PDF | 已具备 | outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_项目文档.pdf、outputs/ai_contest/submission/supporting/队不起队不起_ESG ClaimGuard_项目文档.pdf | 提交前再次核对文件可打开 |
| 5 分钟以内项目视频 | 已具备 | outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_项目视频.mp4、outputs/ai_contest/submission/supporting/队不起队不起_ESG ClaimGuard_无声视频.mp4 | 保持当前成片与源码一致 |
| 200 MB 内其他材料 ZIP | 已具备 | outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_其他.zip | 提交前再次核对 SHA-256 和 200 MB 限制 |

## 已有 Inference 证据

- 数据规模：200 份报告、65 个指标、13000 个 report-indicator 结果
- Qwen3 实际调用：10015 次
- LLM / 结果错误：0 / 0
- 具有正耗时记录的最终结果行：11280 条
- 这些行的中位数 / P95 耗时：2.765 / 3.683 秒
- 最近一次续跑墙钟耗时：27928.801 秒
- 运行硬件：NVIDIA GeForce RTX 5090, 32607 MiB, 580.159.04；AMD Ryzen Threadripper PRO 9955WX 16-Cores；内存 124.8 GiB

10,015 是生成调用总数；行级耗时统计只覆盖仍保留候选计时的最终结果行，二者不是同一统计总体。这些是运行规模、稳定性与时延证据，不是 Precision、Recall 或 F1。

## 我可以继续独立完成

- 提交文件自动复验与口径审计

## 最终仍需要你或团队提供

- 在比赛平台上传四项最终文件并确认在线预览
