#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_review_set import CONCRETE_ISSUE_TYPES, classify_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = PROJECT_ROOT / "outputs/formal_v2/llm_200/extraction_results.csv"
DEFAULT_POOL = PROJECT_ROOT / "outputs/formal_v2/indicator_pool_v2.csv"
DEFAULT_REVIEW_SAMPLE = PROJECT_ROOT / "outputs/review/review_sample.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs/review"

RISK_FIELDS = [
    "report_id",
    "indicator_id",
    "indicator_name",
    "dimension",
    "indicator_type",
    "status",
    "value",
    "unit",
    "evidence_quote",
    "page_no",
    "block_id",
    "block_type",
    "risk_tag",
    "risk_level",
    "caution_tag",
    "suspected_issue_type",
    "risk_reason",
]


def analyze_quality(
    results_path: Path = DEFAULT_RESULTS,
    indicator_pool_path: Path = DEFAULT_POOL,
    review_sample_path: Path = DEFAULT_REVIEW_SAMPLE,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict:
    rows = _read_csv(results_path)
    indicators = _read_csv(indicator_pool_path)
    indicator_by_id = {row.get("indicator_id", ""): row for row in indicators}
    reviewed = _read_csv(review_sample_path) if review_sample_path.exists() else []
    risk_cases = _risk_cases(rows, indicator_by_id)
    classified_rows = [classify_row(row, indicator_by_id.get(row.get("indicator_id", ""), {})) for row in rows]
    metrics = _metrics(rows, indicators, reviewed, risk_cases, classified_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "quality_metrics.json", metrics)
    _write_csv(out_dir / "risk_cases.csv", risk_cases, RISK_FIELDS)
    (out_dir / "quality_report.md").write_text(_quality_report(results_path, indicator_pool_path, metrics, risk_cases), encoding="utf-8")
    return metrics


def _metrics(rows: list[dict], indicators: list[dict], reviewed: list[dict], risk_cases: list[dict], classified_rows: list[dict]) -> dict:
    total = len(rows)
    found = [row for row in rows if row.get("status") == "found"]
    q_found = [row for row in found if row.get("indicator_type") == "quantitative"]
    by_report = Counter(row.get("report_id", "") for row in found)
    per_indicator = _per_indicator_found_rate(rows)
    return {
        "total_results": total,
        "found_count": len(found),
        "missing_count": sum(1 for row in rows if row.get("status") == "missing"),
        "error_count": sum(1 for row in rows if row.get("status") == "error"),
        "found_rate": round(len(found) / total, 6) if total else 0.0,
        "by_dimension": dict(Counter(row.get("dimension", "") for row in rows)),
        "by_indicator_type": dict(Counter(row.get("indicator_type", "") for row in rows)),
        "found_by_dimension": dict(Counter(row.get("dimension", "") for row in found)),
        "found_by_indicator_type": dict(Counter(row.get("indicator_type", "") for row in found)),
        "quantitative_found_count": len(q_found),
        "qualitative_found_count": sum(1 for row in found if row.get("indicator_type") == "qualitative"),
        "boolean_found_count": sum(1 for row in found if row.get("indicator_type") == "boolean"),
        "evidence_empty_count": sum(1 for row in found if not str(row.get("evidence_quote", "")).strip()),
        "evidence_too_short_count": sum(1 for row in found if 0 < len(str(row.get("evidence_quote", "")).strip()) < 8),
        "quantitative_value_missing_count": sum(1 for row in q_found if not str(row.get("value", "")).strip()),
        "quantitative_unit_missing_count": sum(1 for row in q_found if not str(row.get("unit", "")).strip()),
        "quantitative_incomplete_count": sum(1 for row in rows if str(row.get("quantitative_incomplete", "")).lower() == "true"),
        "postprocess_repaired_count": sum(1 for row in rows if str(row.get("postprocess_repaired", "")).lower() == "true"),
        "possible_rate_as_count_count": sum(1 for row in risk_cases if row.get("suspected_issue_type") == "possible_rate_as_count"),
        "possible_money_as_count_count": sum(1 for row in risk_cases if row.get("suspected_issue_type") == "possible_money_as_count"),
        "possible_zero_event_count": sum(1 for row in risk_cases if row.get("suspected_issue_type") == "possible_zero_event"),
        "risk_level_counts": dict(Counter(row.get("risk_level", "") for row in risk_cases if row.get("risk_level", ""))),
        "concrete_risk_cases_count": len(risk_cases),
        "caution_tag_count": sum(1 for row in classified_rows if row.get("caution_tag") == "high_risk_indicator"),
        "per_indicator_found_rate": per_indicator,
        "abnormal_high_found_rate_indicators": [item for item in per_indicator if item["found_rate"] >= 0.95],
        "abnormal_low_found_rate_indicators": [item for item in per_indicator if item["found_rate"] <= 0.05],
        "per_report_found_count_summary": _report_summary(by_report),
        "high_risk_cases_count": len(risk_cases),
        "review_sample_count": len(reviewed),
    }


def _risk_cases(rows: list[dict], indicator_by_id: dict[str, dict]) -> list[dict]:
    cases = []
    for row in rows:
        classified = classify_row(row, indicator_by_id.get(row.get("indicator_id", ""), {}))
        if classified["suspected_issue_type"] not in CONCRETE_ISSUE_TYPES:
            continue
        case = {field: row.get(field, "") for field in RISK_FIELDS}
        case["risk_tag"] = classified["risk_tag"]
        case["risk_level"] = classified["risk_level"]
        case["caution_tag"] = classified["caution_tag"]
        case["suspected_issue_type"] = classified["suspected_issue_type"]
        case["risk_reason"] = classified["review_reason"]
        cases.append(case)
    cases.sort(key=_risk_sort_key)
    return cases


def _per_indicator_found_rate(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("indicator_id", "")].append(row)
    output = []
    for indicator_id, group in sorted(grouped.items()):
        found = sum(1 for row in group if row.get("status") == "found")
        first = group[0]
        output.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": first.get("indicator_name", ""),
                "dimension": first.get("dimension", ""),
                "indicator_type": first.get("indicator_type", ""),
                "total": len(group),
                "found": found,
                "found_rate": round(found / len(group), 6) if group else 0.0,
            }
        )
    return output


def _report_summary(found_counts: Counter) -> dict:
    values = sorted(found_counts.values())
    if not values:
        return {"min": 0, "max": 0, "mean": 0.0, "median": 0, "p25": 0, "p75": 0}
    return {
        "min": values[0],
        "max": values[-1],
        "mean": round(sum(values) / len(values), 4),
        "median": _percentile(values, 0.5),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
        "lowest_reports": [{"report_id": key, "found_count": value} for key, value in found_counts.most_common()[:-11:-1]],
        "highest_reports": [{"report_id": key, "found_count": value} for key, value in found_counts.most_common(10)],
    }


def _quality_report(results_path: Path, pool_path: Path, metrics: dict, risk_cases: list[dict]) -> str:
    top_risks = risk_cases[:30]
    lines = [
        "# ESG 抽取结果质量诊断报告",
        "",
        "本报告为自动质量诊断和抽样复核辅助，不等同于人工标注评价结论。",
        "",
        "## 1. 数据来源",
        "",
        f"- 抽取结果：`{_display_path(results_path)}`",
        f"- 指标池：`{_display_path(pool_path)}`",
        f"- 结果总数：{metrics['total_results']}",
        "",
        "## 2. 总体运行统计",
        "",
        f"- found：{metrics['found_count']}",
        f"- missing：{metrics['missing_count']}",
        f"- error：{metrics['error_count']}",
        f"- found 占比：{metrics['found_rate']:.4f}（结构化抽取结果分布）",
        f"- E/S/G found 分布：{metrics['found_by_dimension']}",
        f"- 指标类型 found 分布：{metrics['found_by_indicator_type']}",
        "",
        "## 3. 定量字段完整性",
        "",
        f"- quantitative found：{metrics['quantitative_found_count']}",
        f"- value 缺失：{metrics['quantitative_value_missing_count']}",
        f"- unit 缺失：{metrics['quantitative_unit_missing_count']}",
        f"- quantitative_incomplete：{metrics['quantitative_incomplete_count']}",
        f"- postprocess_repaired：{metrics['postprocess_repaired_count']}",
        f"- 疑似比例误作次数：{metrics['possible_rate_as_count_count']}",
        f"- 疑似金额误作数量/次数：{metrics['possible_money_as_count_count']}",
        f"- 零事件归一需复核：{metrics['possible_zero_event_count']}",
        f"- 具体风险样本数：{metrics['concrete_risk_cases_count']}",
        f"- caution_tag 样本数：{metrics['caution_tag_count']}",
        f"- risk_level 分布：{metrics['risk_level_counts']}",
        "",
        "## 4. 证据可追溯性",
        "",
        f"- evidence_quote 空缺：{metrics['evidence_empty_count']}",
        f"- evidence_quote 过短：{metrics['evidence_too_short_count']}",
        "- page_no、block_id、block_type 已保留在结果和风险样本中，用于回看 MinerU block。",
        "",
        "## 5. 指标层面异常",
        "",
        f"- found 率过高指标数：{len(metrics['abnormal_high_found_rate_indicators'])}",
        f"- found 率过低指标数：{len(metrics['abnormal_low_found_rate_indicators'])}",
        "- found 率过高可能意味着指标边界过宽或关键词过泛；found 率过低可能意味着披露确实少、关键词召回不足或指标定义过窄。",
        "",
        "## 6. 报告层面异常",
        "",
        f"- 每份报告 found 指标数摘要：{metrics['per_report_found_count_summary']}",
        "",
        "## 7. 高风险样本",
        "",
    ]
    if not top_risks:
        lines.append("无自动识别风险样本。")
    else:
        for row in top_risks:
            evidence = str(row.get("evidence_quote", "")).replace("\n", " ")[:120]
            lines.append(
                f"- `{row['report_id']}` / `{row['indicator_name']}` / {row['suspected_issue_type']}："
                f"{row['risk_reason']}；value={row.get('value','')} unit={row.get('unit','')}；证据：{evidence}"
            )
    lines.extend(
        [
            "",
            "## 8. 结论",
            "",
            "这些指标用于质量控制、风险定位和抽样复核入口。没有人工真值集时，不能将 found/missing/error 或本报告中的风险统计解释为人工标注评价结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _risk_sort_key(row: dict) -> tuple:
    issue_order = {
        "evidence_empty": 0,
        "value_unit_missing": 1,
        "possible_rate_as_count": 2,
        "possible_money_as_count": 3,
        "possible_zero_event": 4,
        "evidence_too_short": 5,
        "possible_table_header_loss": 6,
        "possible_policy_as_boolean": 7,
        "value_unit_suspicious": 8,
    }
    level_order = {"high": 0, "medium": 1, "low": 2}
    return (level_order.get(row.get("risk_level"), 9), issue_order.get(row.get("suspected_issue_type"), 99), row.get("report_id", ""), row.get("indicator_id", ""))


def _percentile(values: list[int], q: float) -> int:
    index = int((len(values) - 1) * q)
    return values[index]


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fieldnames} for row in rows])


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze ESG extraction quality signals without claiming manual accuracy.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--indicator-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--review-sample", default=str(DEFAULT_REVIEW_SAMPLE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()
    metrics = analyze_quality(Path(args.results), Path(args.indicator_pool), Path(args.review_sample), Path(args.out_dir))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
