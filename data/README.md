# 数据包说明

本目录保存 ESG ClaimGuard 的公开报告来源记录与原始 PDF。正式结果不按“目录里有什么就跑什么”，而由 `outputs/formal_v3_mineru25_qwen36/input_manifest.csv` 固定 200 份报告。

## 数据来源与获取方式

数据来自巨潮资讯网公开公告全文检索。`scripts/download_cninfo_esg.py` 使用关键词“ESG报告”分页读取公告元数据，保留 PDF 附件，排除摘要、提示性公告、发布通知、英文重复件和明显无关条目。下载过程会：

1. 记录公告 ID、证券代码、公司、标题和公告时间；
2. 保存公告详情页 URL 与 PDF 静态附件 URL；
3. 先写入 `.part`，检查 PDF 文件头后再原子改名；
4. 计算 SHA-256 与文件大小；
5. 把下载、跳过、重复或失败原因写入日志。

当前 `download_log.csv` 有 518 条处置记录，`report_index.csv` 登记 210 份已保留报告。正式 manifest 从中冻结 200 份，其余文件不进入 13,000 条结果统计。

## 文件说明

### `download_log.csv`

检索与下载处置日志。字段：

- `id`：巨潮公告 ID；
- `stock_code`、`company`、`title`：公告身份；
- `status`：`downloaded`、`skipped_english`、`skipped_summary`、重复或其他处置；
- `error`：失败原因。

### `report_index.csv`

原始报告索引。除公告身份外，还保存：

- `source_url`：公告详情页；
- `pdf_url`：公开 PDF 附件；
- `original_pdf_filename`、`normalized_filename`；
- `local_path`；
- `file_sha256`、`file_size_bytes`。

### `raw_pdfs/`

公开报告 PDF。文件名使用“证券代码_公司_报告年度_报告类型.pdf”。正式队列以 manifest 为准，不应仅按目录文件数推断运行范围。

## 正式数据如何连接

```text
report_index.csv.source_url / pdf_url
  ↕ announcement ID + normalized filename
data/raw_pdfs/*.pdf
  ↕ report_id + pdf_sha256
outputs/formal_v3_mineru25_qwen36/input_manifest.csv
  ↕ report_id + parsed_sha256
outputs/formal_v3_mineru25_qwen36/parsed/*/*_content_list_v2.json
  ↕ report_id + page_no + block_id
outputs/formal_v3_mineru25_qwen36/extraction/extraction_results.csv
```

解析 JSON 按页保存区块列表，区块含 `type`、`content` 和 `bbox`；表格同时保留 HTML。抽取结果的主要字段为 `status`、`value`、`unit`、`evidence_quote`、`page_no`、`block_id`、`value_origin`、`unit_origin` 和各级哈希。

## 完整性检查

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/validate_clean_dataset.py
(cd outputs/formal_v3_mineru25_qwen36 && sha256sum -c CHECKSUMS.sha256)
```

CSV 字段可能包含换行，统计行数时必须使用 CSV 解析器，不要使用 `wc -l`。

## 使用边界

报告来自公开披露，但原文版权仍归发布主体。本仓库中的报告仅用于本次竞赛研究与结果复验；对外再分发或商用前，应重新核对来源网站和报告发布主体的条款。系统结果是证据候选，不是企业评分、违规认定或人工金标准。
