# ESG ClaimGuard 生产链路 Smoke Test

> 状态：**通过**。该检查启动真实生产后端，验证前端入口、核心 API、PDF 证据与工作底稿导出；不会写入复核或金标准数据。

## 验收摘要

- 检查时间：2026-08-31T06:25:34+00:00
- 检查端点：18
- Python：`conda:paperagent`
- 启动命令：`bash scripts/run_dashboard.sh --host 127.0.0.1 --port 48037`
- 状态隔离：临时任务目录与临时 SQLite（检查后已删除）
- 临时服务：`http://127.0.0.1:48037`（检查后已关闭）

## 数据合同

- 通过：`report_count_at_least_200`
- 通过：`indicator_count_is_65`
- 通过：`result_count_matches_reports_times_indicators`
- 通过：`natural_gold_metrics_remain_locked`

## 响应最慢的 5 个端点

| 路径 | HTTP | 类型 | 字节 | 毫秒 |
|---|---:|---|---:|---:|
| `/api/preaudit/summary` | 200 | application/json | 334 | 196.68 |
| `/api/audit/summary` | 200 | application/json | 743 | 165.80 |
| `/api/summary` | 200 | application/json | 528 | 83.66 |
| `/api/pdf/000016_%E6%B7%B1%E5%BA%B7%E4%BD%B3%EF%BC%A1_2025_ESG%E6%8A%A5%E5%91%8A` | 200 | application/pdf | 18571555 | 10.43 |
| `/api/evidence/000016_%E6%B7%B1%E5%BA%B7%E4%BD%B3%EF%BC%A1_2025_ESG%E6%8A%A5%E5%91%8A?block_id=000016_%E6%B7%B1%E5%BA%B7%E4%BD%B3%EF%BC%A1_2025_ESG%E6%8A%A5%E5%91%8A%3Ap43%3Ab0` | 200 | application/json | 1303 | 5.58 |

这份结果只证明系统可启动、路由可访问和关键数据合同成立，不代表抽取准确率。
