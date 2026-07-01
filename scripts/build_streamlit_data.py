#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_review_set import HIGH_RISK_KEYWORDS, classify_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = PROJECT_ROOT / "outputs/formal_v2/llm_200/extraction_results.csv"
DEFAULT_POOL = PROJECT_ROOT / "outputs/formal_v2/indicator_pool_v2.csv"
DEFAULT_METRICS = PROJECT_ROOT / "outputs/review/quality_metrics.json"
DEFAULT_RISK_CASES = PROJECT_ROOT / "outputs/review/risk_cases.csv"
DEFAULT_REVIEW_SAMPLE = PROJECT_ROOT / "outputs/review/review_sample.csv"
DEFAULT_OUT = PROJECT_ROOT / "outputs/system_ui/streamlit_data.json"


def build_streamlit_data(
    results_path: Path = DEFAULT_RESULTS,
    indicator_pool_path: Path = DEFAULT_POOL,
    metrics_path: Path = DEFAULT_METRICS,
    risk_cases_path: Path = DEFAULT_RISK_CASES,
    review_sample_path: Path = DEFAULT_REVIEW_SAMPLE,
    out_path: Path = DEFAULT_OUT,
) -> dict:
    results = _read_csv(results_path)
    indicator_pool = _read_csv(indicator_pool_path)
    quality_metrics = _read_json(metrics_path)
    risk_cases = _read_csv(risk_cases_path)
    review_samples = _read_csv(review_sample_path)

    indicator_by_id = {row.get("indicator_id", ""): row for row in indicator_pool}
    risk_lookup = {(row.get("report_id"), row.get("indicator_id")): row for row in risk_cases}
    enriched_results = [
        _enrich_result(row, risk_lookup.get((row.get("report_id"), row.get("indicator_id"))), indicator_by_id.get(row.get("indicator_id", ""), {}))
        for row in results
    ]
    data = {
        "metadata": {
            "results_path": _display_path(results_path),
            "indicator_pool_path": _display_path(indicator_pool_path),
            "quality_metrics_path": _display_path(metrics_path),
            "risk_cases_path": _display_path(risk_cases_path),
            "review_sample_path": _display_path(review_sample_path),
            "note": "自动质量诊断和抽样复核辅助，不等同于人工标注评价结论。",
        },
        "summary": _summary(enriched_results, indicator_pool, quality_metrics, risk_cases),
        "quality_metrics": quality_metrics,
        "indicator_pool": indicator_pool,
        "results": enriched_results,
        "reports": _reports(enriched_results),
        "indicators": _indicators(enriched_results),
        "risk_cases": risk_cases,
        "review_samples": review_samples,
        "new_report_command": "python3 scripts/esg_system.py --input-json /path/to/new_report_mineru.json --out-dir outputs/system_ui/new_report",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _summary(results: list[dict], indicator_pool: list[dict], metrics: dict, risk_cases: list[dict]) -> dict:
    report_ids = {row.get("report_id", "") for row in results if row.get("report_id", "")}
    indicator_ids = {row.get("indicator_id", "") for row in results if row.get("indicator_id", "")}
    found = [row for row in results if row.get("status") == "found"]
    quantitative_found = [row for row in found if row.get("indicator_type") == "quantitative"]
    return {
        "report_count": len(report_ids),
        "indicator_count": len(indicator_ids) or len(indicator_pool),
        "total_results": len(results),
        "found_count": metrics.get("found_count", sum(1 for row in results if row.get("status") == "found")),
        "missing_count": metrics.get("missing_count", sum(1 for row in results if row.get("status") == "missing")),
        "error_count": metrics.get("error_count", sum(1 for row in results if row.get("status") == "error")),
        "quantitative_found_count": metrics.get("quantitative_found_count", len(quantitative_found)),
        "quantitative_value_missing_count": metrics.get("quantitative_value_missing_count", sum(1 for row in quantitative_found if not row.get("value", "").strip())),
        "quantitative_unit_missing_count": metrics.get("quantitative_unit_missing_count", sum(1 for row in quantitative_found if not row.get("unit", "").strip())),
        "evidence_empty_count": metrics.get("evidence_empty_count", sum(1 for row in found if not row.get("evidence_quote", "").strip())),
        "high_risk_cases_count": metrics.get("high_risk_cases_count", len(risk_cases)),
        "concrete_risk_cases_count": metrics.get("concrete_risk_cases_count", len(risk_cases)),
        "caution_tag_count": metrics.get("caution_tag_count", sum(1 for row in results if _is_caution(row))),
        "risk_level_counts": metrics.get("risk_level_counts", dict(Counter(row.get("risk_level", "") for row in risk_cases if row.get("risk_level", "")))),
        "postprocess_repaired_count": metrics.get("postprocess_repaired_count", sum(1 for row in results if str(row.get("postprocess_repaired", "")).lower() == "true")),
        "by_dimension": dict(Counter(row.get("dimension", "") for row in results)),
        "by_indicator_type": dict(Counter(row.get("indicator_type", "") for row in results)),
        "found_by_dimension": dict(Counter(row.get("dimension", "") for row in found)),
        "found_by_indicator_type": dict(Counter(row.get("indicator_type", "") for row in found)),
    }


def _reports(results: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in results:
        grouped[row.get("report_id", "")].append(row)
    output = []
    for report_id, rows in sorted(grouped.items()):
        output.append(
            {
                "report_id": report_id,
                "found_count": sum(1 for row in rows if row.get("status") == "found"),
                "missing_count": sum(1 for row in rows if row.get("status") == "missing"),
                "error_count": sum(1 for row in rows if row.get("status") == "error"),
                "risk_count": sum(1 for row in rows if row.get("risk_tag") and row.get("risk_tag") != "normal"),
                "caution_count": sum(1 for row in rows if row.get("caution_tag") == "high_risk_indicator"),
            }
        )
    return output


def _indicators(results: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in results:
        grouped[row.get("indicator_id", "")].append(row)
    output = []
    for indicator_id, rows in sorted(grouped.items()):
        first = rows[0]
        status_counts = Counter(row.get("status", "") for row in rows)
        found = [row for row in rows if row.get("status") == "found"]
        output.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": first.get("indicator_name", ""),
                "dimension": first.get("dimension", ""),
                "indicator_type": first.get("indicator_type", ""),
                "found_count": status_counts.get("found", 0),
                "missing_count": status_counts.get("missing", 0),
                "error_count": status_counts.get("error", 0),
                "found_rate": round(status_counts.get("found", 0) / len(rows), 6) if rows else 0.0,
                "risk_count": sum(1 for row in rows if row.get("risk_tag") and row.get("risk_tag") != "normal"),
                "caution_count": sum(1 for row in rows if row.get("caution_tag") == "high_risk_indicator"),
                "value_unit_samples": [
                    {
                        "report_id": row.get("report_id", ""),
                        "value": row.get("value", ""),
                        "unit": row.get("unit", ""),
                        "evidence_quote": row.get("evidence_quote", ""),
                        "page_no": row.get("page_no", ""),
                        "block_id": row.get("block_id", ""),
                    }
                    for row in found[:30]
                ],
            }
        )
    return output


def _enrich_result(row: dict, risk: dict | None, indicator: dict | None = None) -> dict:
    enriched = dict(row)
    classified = classify_row(row, indicator or {})
    enriched["risk_tag"] = (risk or {}).get("risk_tag", "normal")
    enriched["risk_level"] = (risk or {}).get("risk_level", "")
    enriched["caution_tag"] = classified.get("caution_tag", "")
    enriched["suspected_issue_type"] = (risk or {}).get("suspected_issue_type", "normal_sample")
    enriched["risk_reason"] = (risk or {}).get("risk_reason", "")
    return enriched


def _is_caution(row: dict) -> bool:
    text = f"{row.get('indicator_id','')} {row.get('indicator_name','')} {row.get('evidence_quote','')}".lower()
    return any(token.lower() in text for token in HIGH_RISK_KEYWORDS)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _read_json(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Streamlit UI data from existing ESG extraction and review outputs.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--indicator-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--quality-metrics", default=str(DEFAULT_METRICS))
    parser.add_argument("--risk-cases", default=str(DEFAULT_RISK_CASES))
    parser.add_argument("--review-sample", default=str(DEFAULT_REVIEW_SAMPLE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    data = build_streamlit_data(
        Path(args.results),
        Path(args.indicator_pool),
        Path(args.quality_metrics),
        Path(args.risk_cases),
        Path(args.review_sample),
        Path(args.out),
    )
    print(json.dumps({"output": args.out, "summary": data["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
