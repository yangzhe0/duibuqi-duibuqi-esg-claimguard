# ESG ClaimGuard 当前交接基准

> 更新时间：2026-08-25 UTC  
> 项目根目录：`<project-root>`

## 1. 当前完成态

ESG ClaimGuard 的冻结正式链路已经完成，不存在仍在运行的 MinerU 或 Qwen 全量任务：

- 200 份报告，共 10,528 页；
- ESG-65 指标池，形成 13,000 个唯一 `report_id × indicator_id` 结果；
- found 7,688、missing 5,312、error 0；
- 209 条证据字段异常记录已完成内部工程纠错，其中 193 条重新截取为严格可追溯 found，16 条保守改为 missing；该过程不是独立人工测试；
- `validation.json`、`CHECKSUMS.sha256` 与 `COMPLETE.json` 已生成；
- 正式数据根已自包含，dashboard 只使用当前正式数据，不依赖已删除的历史目录或静默 fallback。

上述完成态证明网格、字段、证据追溯和运行合同完整，不证明抽取语义准确率。本作品不把未经独立人工评测的 Precision、Recall、F1 或准确率领先作为成果声明。

## 2. 唯一正式数据与模型

```text
outputs/final_results/
├── input_manifest.csv
├── indicator_pool.csv
├── parsed/
├── extraction/extraction_results.csv
├── extraction/manual_reconciliation.csv
├── extraction/run_summary.json
├── validation.json
├── CHECKSUMS.sha256
└── COMPLETE.json
```

- 解析模型：MinerU2.5-Pro-2605-1.2B，`vlm-engine`；
- 抽取模型：Qwen3.6-27B Q4_K_M，context 8,192，temperature 0；
- dashboard 数据集标识：`formal_current`；

冻结输出根名称中的 `v3` 是复现实验 ID 的一部分，不表示产品仍维护多套正式版本。当前运行时不需要历史桥接文件。

## 3. 产品边界

系统服务于 ESG 报告编制复核和内部审阅，提供带页码、block、逐字证据、问题依据和处置记录的预审线索。系统不提供企业 ESG 评分、投资建议、法定审计或违规认定。

`found` 表示形成了满足工程证据合同的候选，`missing` 表示当前解析与召回范围内证据不足；二者都不是人工真值。所有材料必须将覆盖率、工程完整性与独立准确率分开描述。

## 4. 正式运行事实

- Qwen 运行级生成调用：10,015 次；
- 总墙钟：27,928.801 秒；
- 调用错误与最终结果 error：0；
- `elapsed_seconds` 只存在于部分结果行，图表必须把“有耗时记录的结果行”与“运行级生成调用”分开；
- 定量 value origin 与 unit origin 的最新计数以 `validation.json` 为唯一来源，文档和图表不得硬编码历史分类数。

209 条内部工程纠错源于熔断后保留记录的保守处置。它用于修复正式数据的证据字段，不得改称专家盲审、独立人工测试或准确率评测。

## 5. 复验入口

禁止重跑 MinerU、Qwen、209 条内部纠错或新的全量抽取。只执行只读/验证命令：

```bash
cd <project-root>
/opt/miniconda3/bin/conda env list
/opt/miniconda3/bin/conda run -n paperagent python -m unittest discover -s tests
/opt/miniconda3/bin/conda run -n paperagent python scripts/validate_contest_readiness.py
(cd outputs/final_results && sha256sum -c CHECKSUMS.sha256)
(cd dashboard_web && npm run build)
git diff --check
```

最终验收还必须实测两份 PDF、MP4、ZIP、四个正式文件的名称/大小/SHA-256，以及 dashboard API smoke。测试通过只证明对应检查范围，不得外推为准确率。

## 6. 提交材料

正式目录 `outputs/contest_materials/submission/final/` 最终只允许保留：

1. `队不起队不起_ESG ClaimGuard_参赛作品简介.pdf`
2. `队不起队不起_ESG ClaimGuard_项目文档.pdf`
3. `队不起队不起_ESG ClaimGuard_项目视频.mp4`
4. `队不起队不起_ESG ClaimGuard_其他.zip`

材料就绪不等于已上传。比赛平台上传需要用户账号，交接文档不得写成“已经上传”。
