# Project Status

## 当前项目状态

本项目当前处于数据候选库构建完成后的整理阶段。已经完成 CNINFO ESG 相关 PDF 的下载、主索引生成、文件级一致性校验和 LaTeX 模板编译打通。

200 份 PDF 是原始候选报告库，不是训练集、测试集或最终实验集。当前只完成文件级干净校验。内容级可用性还需要通过 MinerU 解析抽检确认。

## 已完成事项

- 从 CNINFO 下载 200 份 ESG 相关 PDF。
- `data/raw_pdfs/` 下保留 200 个 PDF。
- `data/report_index.csv` 正好 200 行。
- 主索引不混入 skipped / failed 记录。
- 每一行 `local_path` 都真实存在。
- `error_nonempty = 0`。
- 文件名格式为 `股票代码_公司简称_年份_报告类型.pdf`。
- LaTeX 已经能编译通过，输出 `latex/MathModel.pdf`，共 9 页。
- 建立项目归档文档和目录结构。

## 已确认事实

- `company_unique = 198`。
- `stock_unique = 200`。
- `year_dist = {'2025': 196, '2026': 4}`。
- `year` 字段可能是公告发布年份，不一定是报告所属年份。
- `report_type_dist = {'ESG报告': 171, '可持续发展报告': 18, 'ESG暨社会责任报告': 11}`。
- `source_dist = {'cninfo': 200}`。
- LiSu/CJK 字体警告已处理；当前仅剩普通字形替代警告，不影响 PDF 生成。

## 当前不能声称的内容

- 不能声称已经构建训练集。
- 不能声称已经构建测试集。
- 不能声称 200 份 PDF 是最终实验数据集。
- 不能声称已经完成标注数据集。
- 不能暗示 200 份 PDF 会全部进入后续实验评估。
- 不能声称已经完成 MinerU 内容解析质量评估。
- 不能声称模型训练、指标抽取或实验效果已经完成。

## 关键路径

1. 原始候选 PDF 报告库完成。
2. 抽样 20 份 PDF 做内容级解析质量检查。
3. 生成 `parse_quality_sample_20.csv`。
4. 基于解析质量确定有效样本筛选规则。
5. 批量解析有效样本。
6. 设计 ESG 指标 schema。
7. 完成结构化抽取与人工核查。
8. 基于有效样本确定开发集、测试集或人工标注子集。
9. 写作方法、实验与结果部分。

## 关键命令

校验候选 PDF 报告库：

```bash
python3 scripts/validate_clean_dataset.py
```

编译 LaTeX：

```bash
cd latex
latexmk -xelatex -interaction=nonstopmode -halt-on-error MathModel.tex
```

## 当前风险

- 文件级干净不代表内容级可用。
- 部分 PDF 可能是扫描件、复杂表格或版面质量较差。
- 部分标题相关文件可能正文信息不足。
- 可能存在重复或近重复披露。
- `year` 字段可能被误用为报告所属年份。
- 尚未完成人工标注，不能开展正式监督评测。

## 下一步任务

下一步建议抽样 20 份 PDF 做内容级解析质量检查，重点检查 MinerU 或其他 PDF 解析工具对文本、表格、跨页结构和版面顺序的处理效果，并生成 `parse_quality_sample_20.csv`。
