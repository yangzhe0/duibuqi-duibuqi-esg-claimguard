# formal_v2 Indicator Selection Report

本报告基于 formal_v1 `AI-assisted quality review` 和 `辅助质检预标注` 结果生成，不是人工 gold 标注。

## Inputs

- `outputs/formal_v1/indicator_pruning_suggestions.csv`
- `outputs/formal_v1/indicator_pool.csv`
- `outputs/formal_v1/quality_review_metrics.csv`
- `outputs/formal_v1/candidate_coverage.csv`

## Selection Summary

- formal_v1 决策分布：{'keep': 60, 'revise_keywords': 9, 'need_more_review': 21, 'drop': 1}
- formal_v1 候选覆盖分布：{'candidate': 5842, 'missing': 3258}
- formal_v2 指标数量：65
- 来源决策分布：{'keep': 60, 'revise_keywords': 5}
- E/S/G 分布：{'E': 25, 'S': 20, 'G': 20}
- indicator_type 分布：{'quantitative': 35, 'boolean': 15, 'qualitative': 15}
- 关键词修订记录数：24

## Selection Policy

- 默认保留 `decision=keep` 的指标。
- 仅纳入少量 `revise_keywords` 且可通过关键词收窄修复的指标。
- `need_more_review` 不进入 formal_v2；`drop` 不进入 formal_v2。
- 部分机制、制度、管理类定性指标在 formal_v2 中转为 `boolean`，用于验证报告是否披露该机制或措施。

## Next Step

使用 `scripts/run_esg_formal_v2.py` 对 10-20 份报告运行 qwen3 小规模正式抽取，并根据 found 结果进行下一轮复核。
