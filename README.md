# ESG ClaimGuard

ESG ClaimGuard 是面向上市公司可持续发展报告编制与内部复核人员的披露一致性预审系统。系统对 ESG PDF 报告执行版面解析、ESG-65 指标抽取、逐字证据追溯和一致性检查，最终输出可定位到页码与内容块的结构化结果和问题底稿。

项目不做企业 ESG 评分、排名、投资建议或法定审计结论。`found`、`missing` 和系统风险提示也不等于人工真值；本作品不把未经独立人工评测的 Precision、Recall 或 F1 作为成果声明。

## 当前正式链路

```text
冻结 manifest 选取的 200 份 ESG PDF（10,528 页）
  → MinerU2.5-Pro-2605-1.2B / vlm-engine
  → 带页码、block、表格和版面信息的 canonical parsed 数据
  → Qwen3.6-27B Q4_K_M / 8,192 token context
  → ESG-65 证据约束抽取
  → 确定性数值、单位、引用和 lineage 校验
  → 13,000 条 report × indicator 结果
  → 声明—证据约束图与人工处置工作台
```

两个模型顺序运行，不同时驻留。MinerU 负责文档视觉解析；Qwen 只处理召回后的候选证据，不承担逐页 OCR。证据引用必须能回到同一报告、页码和 block 的原文。

## 当前状态

- MinerU 全量解析完成：200/200，10,528/10,528 页。
- Qwen 全量结果完成：13,000/13,000 个唯一 report × indicator 键。
- 最终分布：found 7,688，missing 5,312，error 0。
- 7,688 条 found 全部通过 canonical block 逐字证据追溯；3,214 条定量 found 全部具有值和来源单位。
- 首次抽取的 209 条证据引用失败已由三个 Codex Agent 模拟人工核验，形成 `manual_reconciliation.csv/json`；193 条为严格可追溯 found，16 条保守判为 missing。
- `validation.json` 全部通过，`CHECKSUMS.sha256` 复核成功，`COMPLETE.json` 已生成。
- 冻结产物仍保留可复验的运行 ID 路径 `outputs/formal_v3_mineru25_qwen36/`；产品与 dashboard 统一使用中性数据集名 `formal_current`。数据已自包含，历史桥接依赖已移至系统回收站。

实时检查必须使用 CSV 解析器，不能用 `wc -l` 统计数据行，因为字段可能包含换行：

```bash
cd <project-root>
tmux list-sessions
pgrep -af 'run_esg_formal_v3.py|llama-server'
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
/opt/miniconda3/bin/conda run -n paperagent python - <<'PY'
import csv
from collections import Counter
from pathlib import Path
p = Path('outputs/formal_v3_mineru25_qwen36/extraction/extraction_results.csv')
rows = list(csv.DictReader(p.open(encoding='utf-8-sig'))) if p.is_file() else []
print('rows=', len(rows), 'reports=', len(rows) / 65 if rows else 0)
print('status=', Counter(row['status'] for row in rows))
PY
```

## 唯一结果口径

项目只交付 MinerU2.5 Pro + Qwen3.6-27B 对 200 份报告运行的这一套全量结果。部分冻结文件名带版本字符，仅用于保持运行证据和校验和，不代表多套产品。运行时不再依赖旧版目录或桥接文件。

## 项目结构

```text
data/raw_pdfs/                         源 PDF 存放目录（正式队列以 input_manifest.csv 的 200 份为准）
outputs/formal_v3_mineru25_qwen36/     自包含、带校验和的冻结正式数据
dashboard_api/                         API、约束图、处置记录和任务编排
dashboard_web/                         React + TypeScript + Vite 工作台
src/esg_demo/                          中性命名的抽取核心
scripts/                               当前运行、验收、展示和提交构建工具
docs/ai_contest/HANDOFF.md             当前唯一项目交接基准
docs/ai_contest/FULL_RUN.md            全量运行与完成门手册
latex/                                 技术论文、正式图表和图表契约
video/claimguard-remotion/              Remotion 无声视频工程
tests/                                 当前保留功能的测试
```

旧困难页 A/B、Pilot-30、旧 dashboard 探针、旧 quality/review 输出、旧提交草案和基于 V2 的 PDF/ZIP/视频已经删除，不能作为当前证据引用。

## 快速审阅

后端 API 使用 Python 3.11+ 标准库。前端依赖由 `dashboard_web/package-lock.json` 固定：

```bash
python -m dashboard_api.server
cd dashboard_web
npm ci
npm run dev
```

默认访问地址为 `http://127.0.0.1:5173`；生产脚本见 `scripts/run_dashboard.sh`。完整 PDF 解析和 Qwen 推理需要额外配置 MinerU、模型权重与 GPU，轻量数据审阅不需要这些大体积资产。

## 本机环境

运行 Python 前先检查 Conda：

```bash
/opt/miniconda3/bin/conda env list
```

- Conda 环境 `paperagent`：项目 Python、测试、API 和编排。
- Conda 环境 `mineru`：MinerU 文档解析。
- Conda 环境 `catalog`：图表与可视化。
- `/opt/miniconda3`：Conda base。

不要重复安装已有依赖，不要假定当前 shell 的 PATH 已激活环境。

## 复验与交付顺序

1. 验证 13,000 个唯一 `report_id × indicator_id`，每份报告恰好 65 条，error 为 0。
2. 只读取已冻结的 209 条 Codex Agent 模拟人工工程复核，不重新执行模型或核验。
3. 运行 `scripts/run_esg_formal_v3.py --stage validate`，检查 `validation.json`、差异报告、校验和和 `COMPLETE.json`。
4. 核验 dashboard 只读取 `formal_current`，历史桥接目录保持不存在。
5. 构建项目文档、300 字简介、技术论文、图表、实机视频和最终 ZIP。
6. 运行完整测试、dashboard smoke、readiness 和 final submission validator。

详细交接信息和强制边界见 [HANDOFF.md](docs/ai_contest/HANDOFF.md)。

公开上传时不要直接包含当前 `.git` 历史、原始报告、解析目录、模型、日志或缓存。使用 `scripts/build_public_repository.py` 生成经过白名单和敏感信息检查的干净快照，边界说明见 [PUBLIC_REPOSITORY.md](docs/PUBLIC_REPOSITORY.md)。

第三方资产与再分发边界见 [NOTICE.md](NOTICE.md)；当前快照用于赛事评审，并未对整个项目授予统一开源许可证。
