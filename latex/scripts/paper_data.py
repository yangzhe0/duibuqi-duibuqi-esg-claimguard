from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "latex"
RAW_PDFS = ROOT / "data/raw_pdfs"
PARSED = ROOT / "data/parsed_reports_v1"
FORMAL = ROOT / "outputs/formal_v2"
LLM200 = FORMAL / "llm_200"
REVIEW = ROOT / "outputs/review"
SYSTEM_UI = ROOT / "outputs/system_ui"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def as_int(value: object) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0


def as_float(value: object) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return 0.0


def counter_dict(counter: Counter) -> dict[str, int]:
    return {str(k): int(v) for k, v in counter.items()}


def summary(values: list[int | float]) -> dict[str, float]:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "sum": 0}
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(mean(values), 2),
        "median": round(median(values), 2),
        "sum": round(sum(values), 2),
    }


def parse_pdf_name(path: Path) -> dict[str, str]:
    name = path.stem
    parts = name.split("_")
    if len(parts) < 4:
        return {"report_id": name, "stock_code": "", "company": "", "year": "", "report_type": ""}
    code, company, year = parts[0], parts[1], parts[2]
    report_type = "_".join(parts[3:])
    if re.fullmatch(r"0\d{4}", code):
        market = "港股代码"
    elif re.fullmatch(r"[0369]\d{5}", code):
        market = "A股/北交所代码"
    else:
        market = "其他代码"
    return {
        "report_id": name,
        "stock_code": code,
        "company": company,
        "year": year,
        "report_type": report_type,
        "market": market,
    }


def flatten_content(items: object) -> list[dict]:
    out: list[dict] = []
    if isinstance(items, list):
        for item in items:
            out.extend(flatten_content(item))
    elif isinstance(items, dict):
        out.append(items)
        for key in ("children", "blocks", "items"):
            if key in items:
                out.extend(flatten_content(items[key]))
    return out


def collect_stats() -> dict:
    pdf_meta = [parse_pdf_name(p) for p in sorted(RAW_PDFS.glob("*.pdf"))]
    manifest = read_csv(PARSED / "manifest.csv")
    indicators = read_csv(FORMAL / "indicator_pool_v2.csv")
    results = read_csv(LLM200 / "extraction_results.csv")
    quality = read_json(REVIEW / "quality_metrics.json")
    review_summary = read_json(REVIEW / "review_summary.json")
    risk_cases = read_csv(REVIEW / "risk_cases.csv")
    run_summary = read_json(LLM200 / "run_summary.json")

    pages = [as_int(r.get("pages")) for r in manifest]
    chars = [as_int(r.get("chars")) for r in manifest]
    md_sizes = [as_int(r.get("md_size_bytes")) for r in manifest]
    table_markers = [as_int(r.get("table_markers")) for r in manifest]
    image_refs = [as_int(r.get("image_refs")) for r in manifest]
    headings = [as_int(r.get("headings")) for r in manifest]
    success_count = sum(1 for r in manifest if r.get("status") == "ok")

    content_type_counts: Counter[str] = Counter()
    block_count_by_report: list[int] = []
    image_source_count = 0
    filesystem_images = len(list((PARSED / "reports").glob("**/images/*"))) + len(list((PARSED / "reports").glob("**/*.jpg"))) + len(list((PARSED / "reports").glob("**/*.png")))
    for content_path in sorted((PARSED / "reports").glob("*/*_content_list_v2.json")):
        blocks = flatten_content(read_json(content_path))
        block_count_by_report.append(len(blocks))
        for block in blocks:
            block_type = str(block.get("type") or block.get("category") or block.get("block_type") or "unknown")
            content_type_counts[block_type] += 1
            if block.get("image_source") or block.get("img_path"):
                image_source_count += 1

    by_dim_total: Counter[str] = Counter(r["dimension"] for r in results)
    by_dim_found: Counter[str] = Counter(r["dimension"] for r in results if r["status"] == "found")
    by_type_total: Counter[str] = Counter(r["indicator_type"] for r in results)
    by_type_found: Counter[str] = Counter(r["indicator_type"] for r in results if r["status"] == "found")
    status_counts: Counter[str] = Counter(r["status"] for r in results)
    candidate_empty = sum(1 for r in results if as_int(r.get("source_candidate_count")) == 0)
    candidate_positive = sum(1 for r in results if as_int(r.get("source_candidate_count")) > 0)
    found_rows = [r for r in results if r["status"] == "found"]
    found_page_missing = sum(1 for r in found_rows if not r.get("page_no"))
    found_block_missing = sum(1 for r in found_rows if not r.get("block_id"))
    elapsed_values = [as_float(r.get("elapsed_seconds")) for r in results]

    report_ids = sorted({r["report_id"] for r in results})
    code_to_company: defaultdict[str, set[str]] = defaultdict(set)
    for row in pdf_meta:
        code_to_company[row["stock_code"]].add(row["company"])

    risk_by_issue: Counter[str] = Counter(r.get("suspected_issue_type") or "未标注" for r in risk_cases)
    risk_by_level: Counter[str] = Counter(r.get("risk_level") or "未标注" for r in risk_cases)
    risk_by_dim: Counter[str] = Counter(r.get("dimension") or "未标注" for r in risk_cases)

    typical_cases = []
    for wanted in ("quantitative", "qualitative", "boolean"):
        for row in found_rows:
            if row.get("indicator_type") == wanted and row.get("evidence_quote"):
                typical_cases.append(row)
                break
    for row in risk_cases:
        if row.get("suspected_issue_type") in {"value_unit_missing", "possible_rate_as_count", "possible_money_as_count", "possible_zero_event", "evidence_too_short", "possible_policy_as_boolean"}:
            typical_cases.append(row)
    seen = set()
    unique_cases = []
    for row in typical_cases:
        key = (row.get("report_id"), row.get("indicator_id"), row.get("suspected_issue_type", row.get("indicator_type")))
        if key not in seen:
            seen.add(key)
            unique_cases.append(row)

    stats = {
        "paths": {
            "raw_pdfs": str(RAW_PDFS.relative_to(ROOT)),
            "parsed_manifest": "data/parsed_reports_v1/manifest.csv",
            "indicator_pool": "outputs/formal_v2/indicator_pool_v2.csv",
            "extraction_results": "outputs/formal_v2/llm_200/extraction_results.csv",
            "quality_metrics": "outputs/review/quality_metrics.json",
            "review_summary": "outputs/review/review_summary.json",
            "risk_cases": "outputs/review/risk_cases.csv",
            "streamlit_data": "outputs/system_ui/streamlit_data.json",
        },
        "dataset": {
            "pdf_count": len(pdf_meta),
            "company_count_from_filename": len({r["company"] for r in pdf_meta}),
            "stock_code_count": len({r["stock_code"] for r in pdf_meta}),
            "year_counts": counter_dict(Counter(r["year"] for r in pdf_meta)),
            "report_type_counts": counter_dict(Counter(r["report_type"] for r in pdf_meta)),
            "market_counts": counter_dict(Counter(r["market"] for r in pdf_meta)),
            "industry_note": "现有文件名、manifest 与正式输出未提供可靠行业字段，未纳入行业分布统计。",
        },
        "parsed": {
            "manifest_rows": len(manifest),
            "success_count": success_count,
            "success_ratio": round(success_count / len(manifest), 4) if manifest else 0,
            "pages": summary(pages),
            "chars": summary(chars),
            "md_size_bytes": summary(md_sizes),
            "table_markers": summary(table_markers),
            "image_refs": summary(image_refs),
            "headings": summary(headings),
            "content_blocks": summary(block_count_by_report),
            "block_type_counts": {str(k): int(v) for k, v in content_type_counts.most_common()},
            "image_source_blocks": image_source_count,
            "filesystem_images": filesystem_images,
        },
        "indicators": {
            "count": len(indicators),
            "by_dimension": counter_dict(Counter(r["dimension"] for r in indicators)),
            "by_type": counter_dict(Counter(r["indicator_type"] for r in indicators)),
            "core_count": sum(1 for r in indicators if str(r.get("is_core")).lower() == "true"),
            "examples": indicators[:8],
        },
        "results": {
            "row_count": len(results),
            "report_count": len(report_ids),
            "status_counts": counter_dict(status_counts),
            "by_dimension_total": counter_dict(by_dim_total),
            "by_dimension_found": counter_dict(by_dim_found),
            "by_type_total": counter_dict(by_type_total),
            "by_type_found": counter_dict(by_type_found),
            "candidate_empty": candidate_empty,
            "candidate_positive": candidate_positive,
            "found_page_missing": found_page_missing,
            "found_block_missing": found_block_missing,
            "elapsed_seconds_rows": summary(elapsed_values),
            "run_summary_elapsed_seconds": as_float(run_summary.get("elapsed_seconds")),
        },
        "quality": quality,
        "review_summary": review_summary,
        "risk": {
            "risk_case_count": len(risk_cases),
            "by_issue": counter_dict(risk_by_issue),
            "by_level": counter_dict(risk_by_level),
            "by_dimension": counter_dict(risk_by_dim),
        },
        "typical_cases": unique_cases[:10],
        "streamlit": {
            "tabs": ["系统总览", "公司视角", "指标视角", "证据核验", "高风险样本", "新报告接入"],
            "available_outputs": [p.name for p in sorted(SYSTEM_UI.glob("*"))],
        },
    }
    return stats


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_table(path: Path, header: list[str], rows: list[list[object]]) -> None:
    lines = []
    lines.append("\\begin{tabular}{%s}" % ("l" * len(header)))
    lines.append("\\toprule")
    lines.append(" & ".join(header) + r" \\")
    lines.append("\\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(str(x)) for x in row) + r" \\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def latex_escape(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("$", r"\$")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def write_tables(stats: dict) -> None:
    tables = OUT / "tables"
    write_table(
        tables / "dataset_summary.tex",
        ["项目", "数值"],
        [
            ["原始 PDF", stats["dataset"]["pdf_count"]],
            ["公司数（文件名）", stats["dataset"]["company_count_from_filename"]],
            ["唯一证券代码", stats["dataset"]["stock_code_count"]],
            ["解析成功报告", stats["parsed"]["success_count"]],
            ["解析总页数", stats["parsed"]["pages"]["sum"]],
            ["Markdown 总字符数", stats["parsed"]["chars"]["sum"]],
            ["表格标记总数", stats["parsed"]["table_markers"]["sum"]],
            ["图片引用总数", stats["parsed"]["image_refs"]["sum"]],
        ],
    )
    write_table(
        tables / "indicator_summary.tex",
        ["项目", "E", "S", "G", "合计"],
        [[
            "指标数",
            stats["indicators"]["by_dimension"].get("E", 0),
            stats["indicators"]["by_dimension"].get("S", 0),
            stats["indicators"]["by_dimension"].get("G", 0),
            stats["indicators"]["count"],
        ]],
    )
    write_table(
        tables / "result_summary.tex",
        ["项目", "数值"],
        [
            ["report-indicator 任务", stats["results"]["row_count"]],
            ["found", stats["results"]["status_counts"].get("found", 0)],
            ["missing", stats["results"]["status_counts"].get("missing", 0)],
            ["error", stats["results"]["status_counts"].get("error", 0)],
            ["候选为空直接 missing", stats["results"]["candidate_empty"]],
            ["进入模型判断链路", stats["results"]["candidate_positive"]],
            ["后处理修复", stats["quality"].get("postprocess_repaired_count", 0)],
            ["具体风险样本", stats["risk"]["risk_case_count"]],
        ],
    )
    rows = []
    labels = {
        "quantitative": "定量抽取",
        "qualitative": "定性抽取",
        "boolean": "机制判定",
        "value_unit_missing": "单位缺失风险",
        "possible_rate_as_count": "比例误作数量风险",
        "possible_money_as_count": "金额误作数量风险",
        "possible_zero_event": "零事件复核风险",
        "evidence_too_short": "证据过短风险",
        "possible_policy_as_boolean": "标题式机制风险",
    }
    reason_labels = {
        "quantitative": "表格证据同时给出指标名、数值和单位。",
        "qualitative": "原文片段能够支撑定性描述。",
        "boolean": "证据包含机制、组织或措施，不只是标题。",
        "value_unit_missing": "输出缺少单位或单位语境不完整，需核对表头。",
        "possible_rate_as_count": "证据含比例表达，需确认是否误作数量。",
        "possible_money_as_count": "证据含金额单位，需确认是否误作事件数量。",
        "possible_zero_event": "零事件归一需核对事件边界。",
        "evidence_too_short": "证据片段过短，难以独立支撑判断。",
        "possible_policy_as_boolean": "标题或目录式证据不足以证明机制存在。",
    }
    for row in stats["typical_cases"][:8]:
        issue = row.get("suspected_issue_type") or row.get("indicator_type", "")
        output = row.get("value", "") or row.get("qualitative_text", "")[:28] or row.get("status", "")
        unit = row.get("unit", "")
        if unit and not str(output).endswith(unit):
            output = f"{output} {row.get('unit')}"
        evidence = row.get("evidence_quote", "")
        if len(evidence) > 54:
            evidence = evidence[:54] + "..."
        reason = reason_labels.get(issue) or row.get("llm_reason") or "证据字段与输出字段可互相核验。"
        if len(reason) > 42:
            reason = reason[:42] + "..."
        rows.append([labels.get(issue, issue), row.get("indicator_name", ""), output, evidence, reason])

    lines = [
        r"\setlength{\tabcolsep}{3pt}",
        r"\renewcommand{\arraystretch}{1.18}",
        r"\begin{longtable}{@{}p{2.0cm}p{2.0cm}p{2.3cm}p{4.9cm}p{2.55cm}@{}}",
        r"\caption{典型抽取与风险样本}\label{tab:typical-cases}\\",
        r"\toprule",
        r"案例类型 & 指标 & 抽取输出 & 原文证据摘录 & 复核说明 \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"案例类型 & 指标 & 抽取输出 & 原文证据摘录 & 复核说明 \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in rows:
        lines.append(" & ".join(latex_escape(str(x)) for x in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{longtable}"])
    (tables / "typical_cases.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    stats = collect_stats()
    write_json(OUT / "tables/stats.json", stats)
    write_tables(stats)
    print("wrote latex/tables/stats.json and TeX tables")


if __name__ == "__main__":
    main()
