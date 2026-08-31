# formal_v3 与历史 formal_v2 工程差异

> 本报告只比较两条工程链路的输出变化，不代表准确率；未使用 Natural-Gold。

- 对齐键：13000
- 有变化：7149
- 无变化：5851

## 状态迁移

| 迁移 | 条数 |
|---|---:|
| `found->found` | 7255 |
| `found->missing` | 522 |
| `missing->found` | 433 |
| `missing->missing` | 4790 |

## 字段变化

| 字段 | 条数 |
|---|---:|
| `status` | 955 |
| `value` | 2075 |
| `unit` | 758 |
| `qualitative_text` | 5129 |
| `evidence_quote` | 5770 |
| `page_no` | 2009 |
| `block_id` | 2412 |
| `block_type` | 1526 |
