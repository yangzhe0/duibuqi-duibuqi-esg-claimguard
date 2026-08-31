#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V3_ROOT = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36"
DEFAULT_RESULTS = V3_ROOT / "extraction/extraction_results.csv"
DEFAULT_POOL = V3_ROOT / "indicator_pool.csv"
DEFAULT_OUT_DIR = V3_ROOT / "review"
DEFAULT_SAMPLE_SIZE = 300

REVIEW_FIELDS = [
    "review_id",
    "report_id",
    "indicator_id",
    "indicator_name",
    "dimension",
    "indicator_type",
    "status",
    "value",
    "unit",
    "qualitative_text",
    "evidence_quote",
    "page_no",
    "block_id",
    "block_type",
    "source_candidate_count",
    "llm_confidence",
    "llm_reason",
    "postprocess_repaired",
    "quantitative_incomplete",
    "repair_method",
    "repair_reason",
    "risk_tag",
    "risk_level",
    "caution_tag",
    "review_reason",
    "needs_manual_check",
    "suspected_issue_type",
]

HIGH_RISK_KEYWORDS = (
    "客户投诉",
    "投诉数量",
    "投诉次数",
    "工伤",
    "安全事故",
    "处罚",
    "罚款",
    "反腐败",
    "董事会多元化",
    "女性董事",
    "员工性别",
    "专利",
    "温室气体",
    "碳排放",
    "能源消耗",
    "用水",
    "废弃物",
    "污染物",
    "VOC",
    "VOCs",
)

COUNT_HINTS = (
    "投诉",
    "工伤",
    "事故",
    "次数",
    "数量",
    "人数",
    "员工",
    "专利",
    "董事",
    "供应商数量",
    "会议",
    "培训",
)
MONEY_UNITS = ("元", "万元", "亿元", "人民币")
RATE_UNITS = ("%", "％", "百分比", "率")
ZERO_TERMS = ("未发生", "没有发生", "未收到", "无", "零", "0")
CONCRETE_ISSUE_TYPES = {
    "evidence_empty",
    "evidence_too_short",
    "value_unit_missing",
    "value_unit_suspicious",
    "possible_rate_as_count",
    "possible_money_as_count",
    "possible_zero_event",
    "possible_table_header_loss",
    "possible_policy_as_boolean",
}
RISK_LEVEL_BY_ISSUE = {
    "evidence_empty": "high",
    "value_unit_missing": "high",
    "possible_rate_as_count": "high",
    "possible_money_as_count": "high",
    "evidence_too_short": "medium",
    "possible_table_header_loss": "medium",
    "possible_policy_as_boolean": "medium",
    "possible_zero_event": "low",
    "value_unit_suspicious": "low",
}
STRICT_COUNT_IDS = {
    "s_customer_complaints",
    "s_work_injury",
    "g_board_size",
    "g_board_meetings",
    "g_shareholder_meetings",
    "s_patents",
    "s_supplier_count",
    "s_volunteer_hours",
}


def build_review_set(
    results_path: Path = DEFAULT_RESULTS,
    indicator_pool_path: Path = DEFAULT_POOL,
    out_dir: Path = DEFAULT_OUT_DIR,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> dict:
    rows = _read_csv(results_path)
    indicators = {row.get("indicator_id", ""): row for row in _read_csv(indicator_pool_path)}
    annotated = [_annotate_row(row, indicators.get(row.get("indicator_id", ""), {})) for row in rows]
    sampled = _sample_rows(annotated, sample_size)
    for index, row in enumerate(sampled, start=1):
        row["review_id"] = f"RS-{index:04d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "review_sample.csv", sampled, REVIEW_FIELDS)
    _write_json(out_dir / "review_sample.json", sampled)
    summary = _summary(sampled)
    _write_json(out_dir / "review_summary.json", summary)
    return summary


def classify_row(row: dict, indicator: dict | None = None) -> dict:
    indicator = indicator or {}
    issue = "normal_sample"
    reasons = []
    evidence = str(row.get("evidence_quote", "") or "").strip()
    value = str(row.get("value", "") or "").strip()
    unit = str(row.get("unit", "") or "").strip()
    name = str(row.get("indicator_name", "") or indicator.get("indicator_name", ""))
    indicator_id = str(row.get("indicator_id", "") or indicator.get("indicator_id", ""))
    indicator_type = str(row.get("indicator_type", "") or indicator.get("indicator_type", ""))
    status = str(row.get("status", ""))
    block_type = str(row.get("block_type", ""))
    high_risk = _is_high_risk(indicator_id, name, evidence)

    if status == "found" and not evidence:
        issue = "evidence_empty"
        reasons.append("found result has empty evidence_quote")
    elif evidence and _visible_len(evidence) < 8:
        issue = "evidence_too_short"
        reasons.append("evidence_quote is too short for reliable verification")
    elif status == "found" and indicator_type == "quantitative" and (not value or not unit):
        issue = "value_unit_missing"
        reasons.append("quantitative found result lacks value or unit")
    elif _is_strict_count_like(name, indicator_id) and _contains_rate(value, unit, evidence):
        issue = "possible_rate_as_count"
        reasons.append("count-like indicator contains percent/rate expression")
    elif _is_strict_count_like(name, indicator_id) and any(token in unit for token in MONEY_UNITS):
        issue = "possible_money_as_count"
        reasons.append("count-like indicator uses money unit")
    elif indicator_type == "boolean" and status == "found" and _looks_title_like(evidence):
        issue = "possible_policy_as_boolean"
        reasons.append("boolean evidence is only a short title-like phrase")
    elif _is_zero_event(row, evidence, value):
        issue = "possible_zero_event"
        reasons.append("zero-event normalization needs source evidence review")
    elif _possible_table_header_loss(row, evidence, value, unit):
        issue = "possible_table_header_loss"
        reasons.append("short table evidence may have lost row/column context")

    if high_risk and issue == "normal_sample":
        issue = "high_risk_indicator"
        reasons.append("indicator belongs to high-risk review category")

    is_concrete = issue in CONCRETE_ISSUE_TYPES
    risk_tag = issue if is_concrete else "normal"
    risk_level = RISK_LEVEL_BY_ISSUE.get(issue, "")
    caution_tag = "high_risk_indicator" if high_risk else ""
    return {
        "risk_tag": risk_tag,
        "risk_level": risk_level,
        "caution_tag": caution_tag,
        "review_reason": "; ".join(reasons) if reasons else "stratified normal sample",
        "needs_manual_check": "true" if issue != "normal_sample" or high_risk else "false",
        "suspected_issue_type": issue,
    }


def _annotate_row(row: dict, indicator: dict) -> dict:
    classified = classify_row(row, indicator)
    output = {field: "" for field in REVIEW_FIELDS}
    for field in REVIEW_FIELDS:
        if field in row:
            output[field] = row.get(field, "")
    output.update(classified)
    return output


def _sample_rows(rows: list[dict], sample_size: int) -> list[dict]:
    if len(rows) <= sample_size:
        return list(rows)
    selected: list[dict] = []
    selected_keys = set()

    def add(row: dict) -> None:
        key = (row.get("report_id"), row.get("indicator_id"))
        if key not in selected_keys and len(selected) < sample_size:
            selected.append(row)
            selected_keys.add(key)

    for key_name in ("dimension", "indicator_type", "status", "suspected_issue_type"):
        groups = defaultdict(list)
        for row in rows:
            groups[row.get(key_name, "")].append(row)
        for group in groups.values():
            add(sorted(group, key=_priority_key)[0])

    strata = defaultdict(list)
    for row in rows:
        strata[(row.get("dimension", ""), row.get("indicator_type", ""), row.get("status", ""))].append(row)
    quota = max(1, sample_size // max(len(strata), 1))
    for group in strata.values():
        for row in sorted(group, key=_priority_key)[:quota]:
            add(row)

    for row in sorted(rows, key=_priority_key):
        add(row)
        if len(selected) >= sample_size:
            break
    return selected


def _priority_key(row: dict) -> tuple:
    issue = row.get("suspected_issue_type", "normal_sample")
    score = 0
    if issue != "normal_sample":
        score += 100
    if row.get("caution_tag") == "high_risk_indicator":
        score += 50
    if row.get("indicator_type") == "quantitative" and row.get("status") == "found":
        score += 30
    if row.get("status") == "missing":
        score += 12
    if str(row.get("postprocess_repaired", "")).lower() == "true":
        score += 10
    if str(row.get("quantitative_incomplete", "")).lower() == "true":
        score += 15
    stable = int(hashlib.md5(f"{row.get('report_id')}|{row.get('indicator_id')}".encode("utf-8")).hexdigest()[:8], 16)
    return (-score, stable)


def _summary(rows: list[dict]) -> dict:
    return {
        "total_review_samples": len(rows),
        "by_dimension": dict(Counter(row.get("dimension", "") for row in rows)),
        "by_indicator_type": dict(Counter(row.get("indicator_type", "") for row in rows)),
        "by_status": dict(Counter(row.get("status", "") for row in rows)),
        "by_suspected_issue_type": dict(Counter(row.get("suspected_issue_type", "") for row in rows)),
        "concrete_risk_count": sum(1 for row in rows if row.get("suspected_issue_type") in CONCRETE_ISSUE_TYPES),
        "caution_tag_count": sum(1 for row in rows if row.get("caution_tag") == "high_risk_indicator"),
        "by_risk_level": dict(Counter(row.get("risk_level", "") for row in rows if row.get("risk_level", ""))),
        "needs_manual_check_count": sum(1 for row in rows if row.get("needs_manual_check") == "true"),
    }


def _is_high_risk(indicator_id: str, name: str, evidence: str) -> bool:
    text = f"{indicator_id} {name} {evidence}".lower()
    return any(keyword.lower() in text for keyword in HIGH_RISK_KEYWORDS)


def _is_count_like(name: str, indicator_id: str) -> bool:
    text = f"{indicator_id} {name}"
    return any(token in text for token in COUNT_HINTS)


def _is_strict_count_like(name: str, indicator_id: str) -> bool:
    if indicator_id in STRICT_COUNT_IDS:
        return True
    text = f"{indicator_id} {name}"
    return any(token in text for token in ("次数", "数量", "事故", "投诉"))


def _contains_rate(value: str, unit: str, evidence: str) -> bool:
    value_unit = f"{value} {unit}"
    if any(token in value_unit for token in RATE_UNITS):
        return True
    compact = re.sub(r"\s+", "", evidence or "")
    return bool(re.search(r"(投诉率|投诉处理率|投诉解决率|事故率|发生率|占比|比例)[^，。；;]{0,12}\d+(?:\.\d+)?\s*(%|％)", compact))


def _looks_title_like(evidence: str) -> bool:
    compact = re.sub(r"\s+", "", evidence or "")
    return _visible_len(compact) < 12 and not re.search(r"[，。；;,.、]", compact)


def _possible_table_header_loss(row: dict, evidence: str, value: str, unit: str) -> bool:
    if row.get("block_type") != "table" or not evidence or _visible_len(evidence) >= 12:
        return False
    indicator_type = row.get("indicator_type", "")
    incomplete = (
        str(row.get("quantitative_incomplete", "")).lower() == "true"
        or (indicator_type == "quantitative" and (not value or not unit))
    )
    delimiter_loss = "|" not in evidence and not re.search(r"\s{2,}|[｜:：]", evidence)
    weak_quant_context = indicator_type == "quantitative" and (
        not re.search(r"\d", evidence)
        or (value and value not in evidence)
        or (unit and unit not in evidence)
    )
    return incomplete or (delimiter_loss and weak_quant_context)


def _is_zero_event(row: dict, evidence: str, value: str) -> bool:
    if str(value).replace(",", "").strip() not in {"0", "0.0", "0.00"}:
        return False
    compact = re.sub(r"\s+", "", evidence or "")
    return any(term in compact for term in ZERO_TERMS)


def _indicator_supported(name: str, evidence: str) -> bool:
    if not name or not evidence:
        return False
    tokens = [token for token in re.split(r"[与和及或、\s]+", name) if len(token) >= 2]
    return any(token in evidence for token in tokens[:4])


def _visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _read_csv(path: Path) -> list[dict]:
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
    parser = argparse.ArgumentParser(description="Build a stratified ESG extraction review sample without manual truth labels.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--indicator-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    args = parser.parse_args()
    summary = build_review_set(Path(args.results), Path(args.indicator_pool), Path(args.out_dir), args.sample_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
