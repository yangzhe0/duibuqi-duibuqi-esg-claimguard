# formal_v2 LLM Sample Error Analysis

本报告分析 formal_v2 小样本 LLM 抽取中的 JSON/error 与定量字段缺失问题，不是人工 gold 标注。

- 问题记录数：3
- error_category 分布：{'quantitative_unit_missing': 3}

## Problem Rows

- `g_independent_director_ratio` / `600278_东方创业_2025_ESG报告` / quantitative_unit_missing：定量结果缺少单位，且 evidence_quote 无法可靠补齐。 修复策略：保持 found 并标记 quantitative_incomplete；后续补充单位词召回或人工复核。
- `g_board_diversity` / `600278_东方创业_2025_ESG报告` / quantitative_unit_missing：定量结果缺少单位，且 evidence_quote 无法可靠补齐。 修复策略：保持 found 并标记 quantitative_incomplete；后续补充单位词召回或人工复核。
- `g_independent_director_ratio` / `600783_鲁信创投_2025_ESG报告` / quantitative_unit_missing：定量结果缺少单位，且 evidence_quote 无法可靠补齐。 修复策略：保持 found 并标记 quantitative_incomplete；后续补充单位词召回或人工复核。
