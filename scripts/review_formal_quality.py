#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib import error, request


ALLOWED_LABELS = {"correct", "partial", "wrong", "uncertain"}
ALLOWED_ERROR_TYPES = {
    "none",
    "keyword_false_positive",
    "weak_evidence",
    "unit_missing",
    "value_missing",
    "wrong_indicator_mapping",
    "context_insufficient",
    "table_parse_noise",
    "other",
}
ALLOWED_DECISIONS = {"keep", "revise_keywords", "merge_or_redefine", "drop", "need_more_review"}
DEFAULT_OUT_DIR = Path("outputs/formal_v1")
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "qwen3:30b"


def run_review(
    project_root: Path,
    out_dir: Path | None = None,
    use_llm: bool = True,
    max_llm_reviews: int = 80,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
) -> dict:
    base = project_root / (out_dir or DEFAULT_OUT_DIR)
    review_rows = _read_csv(base / "quality_review_sample.csv")
    coverage_rows = _read_csv(base / "candidate_coverage.csv")
    indicator_rows = _read_csv(base / "indicator_pool.csv")
    extraction_rows = _read_csv(base / "extraction_results.csv")
    summary = _read_json(base / "run_summary.json")

    indicators = {row["indicator_id"]: row for row in indicator_rows}
    labeled_rows = []
    high_risk_indexes = []
    for row in review_rows:
        labeled = dict(row)
        heuristic = _heuristic_label(row, indicators.get(row.get("indicator_id", ""), {}))
        labeled.update(heuristic)
        labeled["review_method"] = "heuristic"
        if labeled["ai_label"] in {"partial", "wrong", "uncertain"}:
            high_risk_indexes.append(len(labeled_rows))
        labeled_rows.append(labeled)

    llm_reviewed = 0
    if use_llm and max_llm_reviews > 0 and _ollama_available(ollama_url):
        for index in high_risk_indexes[:max_llm_reviews]:
            llm_result = _llm_review(labeled_rows[index], ollama_url, model)
            if llm_result:
                labeled_rows[index].update(llm_result)
                labeled_rows[index]["review_method"] = "heuristic+qwen3"
                llm_reviewed += 1

    metrics_rows = _metrics_rows(labeled_rows, indicator_rows)
    pruning_rows = _pruning_rows(indicator_rows, coverage_rows, metrics_rows)

    _write_csv(base / "quality_review_ai_labeled.csv", labeled_rows)
    _write_csv(base / "quality_review_metrics.csv", metrics_rows)
    _write_csv(base / "indicator_pruning_suggestions.csv", pruning_rows)
    _write_markdown_report(
        base / "formal_v1_quality_review.md",
        summary=summary,
        labeled_rows=labeled_rows,
        metrics_rows=metrics_rows,
        pruning_rows=pruning_rows,
        coverage_rows=coverage_rows,
        extraction_rows=extraction_rows,
        llm_reviewed=llm_reviewed,
    )
    return {
        "reviewed_rows": len(labeled_rows),
        "metrics_rows": len(metrics_rows),
        "pruning_rows": len(pruning_rows),
        "llm_reviewed": llm_reviewed,
        "label_counts": dict(Counter(row["ai_label"] for row in labeled_rows)),
        "decision_counts": dict(Counter(row["decision"] for row in pruning_rows)),
    }


def _heuristic_label(row: dict, indicator: dict) -> dict:
    evidence = _clean(row.get("evidence_quote", ""))
    indicator_name = _clean(row.get("indicator_name", ""))
    indicator_type = row.get("indicator_type", "")
    keywords = _split_pipe(indicator.get("keywords", ""))
    units = _split_pipe(indicator.get("common_units", ""))
    keyword_hits = _keyword_hits(evidence, indicator_name, keywords)
    has_number = bool(re.search(r"\d+(?:,\d{3})*(?:\.\d+)?", evidence))
    has_unit = bool(_keyword_hits(evidence, "", units)) or _has_generic_unit(evidence)
    evidence_len = len(evidence)
    table_noise = "\x00" in row.get("evidence_quote", "") or evidence.strip() in {"", "0", "1", "2"}

    if table_noise:
        return _label("uncertain", 0.25, "证据疑似解析噪声或过短，无法判断指标支持关系。", "table_parse_noise", "人工抽查或回看原 block")
    if not keyword_hits:
        return _label("wrong", 0.78, "证据未命中指标名称或配置关键词，疑似关键词误召回。", "keyword_false_positive", "修订关键词或删除该候选")
    if evidence_len < 12:
        return _label("uncertain", 0.3, "证据文本过短，上下文不足。", "context_insufficient", "补充相邻 block 或降低候选置信度")

    if indicator_type == "quantitative":
        if has_number and has_unit:
            return _label("correct", 0.86, f"证据包含指标相关词、数值和单位；命中词：{';'.join(keyword_hits[:4])}。", "none", "保留")
        if has_number:
            return _label("partial", 0.68, f"证据相关且包含数值，但单位不清晰；命中词：{';'.join(keyword_hits[:4])}。", "unit_missing", "补充单位词或改进表格解析")
        return _label("partial", 0.56, f"证据相关但未见明确数值；命中词：{';'.join(keyword_hits[:4])}。", "value_missing", "要求后续 LLM 抽取时核验数值")

    if evidence_len >= 30:
        return _label("correct", 0.82, f"证据包含指标相关词且有完整定性表述；命中词：{';'.join(keyword_hits[:4])}。", "none", "保留")
    return _label("partial", 0.58, f"证据相关但定性语义边界较短；命中词：{';'.join(keyword_hits[:4])}。", "weak_evidence", "补充相邻 block")


def _llm_review(row: dict, ollama_url: str, model: str) -> dict | None:
    payload = {
        "indicator_id": row.get("indicator_id", ""),
        "indicator_name": row.get("indicator_name", ""),
        "dimension": row.get("dimension", ""),
        "indicator_type": row.get("indicator_type", ""),
        "value": row.get("value", ""),
        "unit": row.get("unit", ""),
        "qualitative_text": row.get("qualitative_text", ""),
        "evidence_quote": row.get("evidence_quote", "")[:900],
        "page_no": row.get("page_no", ""),
        "block_type": row.get("block_type", ""),
    }
    prompt = (
        "/no_think\n"
        "你是 ESG 指标抽取质量复核器。只能根据给定字段判断 evidence_quote 是否支持 indicator_id，禁止根据常识补答案。\n"
        "如果证据不足，必须判 wrong 或 uncertain。输出 JSON 对象，字段固定为 ai_label,ai_confidence,ai_reason,error_type,suggested_action。\n"
        "ai_label 只能是 correct, partial, wrong, uncertain。error_type 只能是 none, keyword_false_positive, weak_evidence, unit_missing, value_missing, wrong_indicator_mapping, context_insufficient, table_parse_noise, other。\n"
        f"样本：{json.dumps(payload, ensure_ascii=False)}"
    )
    req_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 512},
    }
    try:
        opener = request.build_opener(request.ProxyHandler({}))
        req = request.Request(
            ollama_url,
            data=json.dumps(req_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = json.loads(result.get("response", "{}"))
    except (OSError, error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    label = content.get("ai_label", row.get("ai_label"))
    error_type = content.get("error_type", row.get("error_type"))
    if label not in ALLOWED_LABELS or error_type not in ALLOWED_ERROR_TYPES:
        return None
    try:
        confidence = float(content.get("ai_confidence", row.get("ai_confidence", 0.5)))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "ai_label": label,
        "ai_confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "ai_reason": _clean(str(content.get("ai_reason", row.get("ai_reason", ""))))[:240],
        "error_type": error_type,
        "suggested_action": _clean(str(content.get("suggested_action", row.get("suggested_action", ""))))[:160],
    }


def _metrics_rows(labeled_rows: list[dict], indicator_rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in labeled_rows:
        grouped[row["indicator_id"]].append(row)
    output = []
    for indicator in indicator_rows:
        rows = grouped.get(indicator["indicator_id"], [])
        counts = Counter(row["ai_label"] for row in rows)
        reviewed = len(rows)
        error_counts = Counter(row["error_type"] for row in rows if row.get("error_type") != "none")
        output.append(
            {
                "indicator_id": indicator["indicator_id"],
                "indicator_name": indicator["indicator_name"],
                "dimension": indicator["dimension"],
                "indicator_type": indicator["indicator_type"],
                "reviewed_count": reviewed,
                "correct_count": counts["correct"],
                "partial_count": counts["partial"],
                "wrong_count": counts["wrong"],
                "uncertain_count": counts["uncertain"],
                "correct_rate": _rate(counts["correct"], reviewed),
                "usable_rate": _rate(counts["correct"] + counts["partial"], reviewed),
                "dominant_error_type": error_counts.most_common(1)[0][0] if error_counts else "none",
            }
        )
    return output


def _pruning_rows(indicator_rows: list[dict], coverage_rows: list[dict], metrics_rows: list[dict]) -> list[dict]:
    coverage = defaultdict(Counter)
    for row in coverage_rows:
        coverage[row["indicator_id"]][row["status"]] += 1
    metrics = {row["indicator_id"]: row for row in metrics_rows}
    output = []
    for indicator in indicator_rows:
        iid = indicator["indicator_id"]
        cov = coverage[iid]
        candidate = cov["candidate"]
        missing = cov["missing"]
        total = candidate + missing
        metric = metrics[iid]
        reviewed = int(metric["reviewed_count"])
        correct_rate = float(metric["correct_rate"])
        usable_rate = float(metric["usable_rate"])
        coverage_rate = candidate / total if total else 0.0
        decision, reason, hint = _decision(coverage_rate, reviewed, correct_rate, usable_rate, metric["dominant_error_type"])
        output.append(
            {
                "indicator_id": iid,
                "indicator_name": indicator["indicator_name"],
                "dimension": indicator["dimension"],
                "indicator_type": indicator["indicator_type"],
                "candidate_count": candidate,
                "missing_count": missing,
                "coverage_rate": f"{coverage_rate:.4f}",
                "reviewed_count": reviewed,
                "correct_rate": f"{correct_rate:.4f}",
                "usable_rate": f"{usable_rate:.4f}",
                "dominant_error_type": metric["dominant_error_type"],
                "decision": decision,
                "reason": reason,
                "revision_hint": hint,
            }
        )
    return output


def _decision(coverage_rate: float, reviewed: int, correct_rate: float, usable_rate: float, error_type: str) -> tuple[str, str, str]:
    if reviewed < 2:
        return ("need_more_review", "辅助质检样本不足，不能稳定判断。", "下一轮抽样优先补足该指标样本。")
    if usable_rate >= 0.85 and correct_rate >= 0.75:
        return ("keep", "证据可用率高；即使覆盖率较高，辅助质检未显示明显误命中。", "进入 formal_v2 候选保留清单。")
    if usable_rate >= 0.75 and 0.15 <= coverage_rate <= 0.95:
        return ("keep", "证据可用率较高且覆盖率处于合理区间。", "进入 formal_v2 候选保留清单。")
    if coverage_rate > 0.9 and (correct_rate < 0.5 or error_type in {"keyword_false_positive", "wrong_indicator_mapping"}):
        return ("revise_keywords", "覆盖率过高且误命中风险较高。", "收紧泛化关键词，增加指标限定词。")
    if usable_rate < 0.35 and reviewed >= 3:
        return ("drop", "辅助质检显示长期弱证据或误命中。", "除非论文必须覆盖，否则 formal_v2 暂不保留。")
    if error_type in {"wrong_indicator_mapping", "weak_evidence"}:
        return ("merge_or_redefine", "指标边界或证据粒度不清，容易与其他指标混淆。", "合并相近指标或重写指标定义。")
    return ("revise_keywords", "质量表现中等，需要通过关键词和证据窗口改进。", "补充同义词、单位词或相邻 block 召回。")


def _write_markdown_report(
    path: Path,
    summary: dict,
    labeled_rows: list[dict],
    metrics_rows: list[dict],
    pruning_rows: list[dict],
    coverage_rows: list[dict],
    extraction_rows: list[dict],
    llm_reviewed: int,
) -> None:
    label_counts = Counter(row["ai_label"] for row in labeled_rows)
    dimension_counts = _group_label_rates(labeled_rows, "dimension")
    type_counts = _group_label_rates(labeled_rows, "indicator_type")
    error_counts = Counter(row["error_type"] for row in labeled_rows)
    decision_counts = Counter(row["decision"] for row in pruning_rows)
    suggested_size = max(50, min(65, decision_counts["keep"] + round(decision_counts["revise_keywords"] * 0.5)))
    lines = [
        "# formal_v1 AI-assisted quality review",
        "",
        "本报告是 `辅助质检预标注`，不是严格人工 gold 标注。",
        "",
        "## Inputs",
        "",
        "- `outputs/formal_v1/quality_review_sample.csv`",
        "- `outputs/formal_v1/candidate_coverage.csv`",
        "- `outputs/formal_v1/indicator_pool.csv`",
        "- `outputs/formal_v1/extraction_results.csv`",
        "- `outputs/formal_v1/run_summary.json`",
        "",
        "## Summary",
        "",
        f"- 样本数量：{len(labeled_rows)}",
        f"- 指标池规模：{summary.get('indicators', len(metrics_rows))}",
        f"- 覆盖扫描报告数：{summary.get('reports', '')}",
        f"- 候选覆盖行数：{len(coverage_rows)}",
        f"- extraction_results 行数：{len(extraction_rows)}",
        f"- qwen3 高风险复核样本数：{llm_reviewed}",
        f"- 各 label 数量：{dict(label_counts)}",
        f"- 最常见错误类型：{error_counts.most_common(5)}",
        "",
        "## E/S/G Quality Difference",
        "",
        _markdown_table(["dimension", "reviewed", "correct", "partial", "wrong", "uncertain", "usable_rate"], dimension_counts),
        "",
        "## Quantitative vs Qualitative",
        "",
        _markdown_table(["indicator_type", "reviewed", "correct", "partial", "wrong", "uncertain", "usable_rate"], type_counts),
        "",
        "## Pruning Decisions",
        "",
        f"- 建议保留 keep：{decision_counts['keep']}",
        f"- 建议修改 revise_keywords：{decision_counts['revise_keywords']}",
        f"- 建议合并或重定义 merge_or_redefine：{decision_counts['merge_or_redefine']}",
        f"- 建议删除 drop：{decision_counts['drop']}",
        f"- 需要更多复核 need_more_review：{decision_counts['need_more_review']}",
        f"- formal_v2 指标池建议规模：约 {suggested_size} 个稳定指标，控制在 50-65 个区间。",
        "",
        "## Next Step",
        "",
        _next_step(decision_counts),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _next_step(decision_counts: Counter) -> str:
    if decision_counts["keep"] >= 35 and decision_counts["drop"] <= 20:
        return "建议进入小规模 LLM 正式抽取：先选择 keep 与高优先级 revise_keywords 指标，跑 10-20 份报告并复核 found 结果。"
    return "暂不建议直接进入较大规模 LLM 抽取；应先修订高误命中指标关键词，并补充 need_more_review 指标样本。"


def _group_label_rates(rows: list[dict], key: str) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get(key, "")].append(row)
    output = []
    for value, items in sorted(grouped.items()):
        counts = Counter(row["ai_label"] for row in items)
        output.append(
            {
                key: value,
                "reviewed": len(items),
                "correct": counts["correct"],
                "partial": counts["partial"],
                "wrong": counts["wrong"],
                "uncertain": counts["uncertain"],
                "usable_rate": f"{((counts['correct'] + counts['partial']) / len(items)):.4f}",
            }
        )
    return output


def _markdown_table(headers: list[str], rows: list[dict]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def _ollama_available(url: str) -> bool:
    try:
        opener = request.build_opener(request.ProxyHandler({}))
        req = request.Request(url.replace("/api/generate", "/api/tags"), method="GET")
        with opener.open(req, timeout=3) as resp:
            return resp.status == 200
    except (OSError, error.URLError, TimeoutError):
        return False


def _label(ai_label: str, confidence: float, reason: str, error_type: str, action: str) -> dict:
    return {
        "ai_label": ai_label,
        "ai_confidence": round(confidence, 2),
        "ai_reason": reason,
        "error_type": error_type,
        "suggested_action": action,
    }


def _keyword_hits(text: str, indicator_name: str, keywords: list[str]) -> list[str]:
    hits = []
    candidates = [indicator_name] if indicator_name else []
    candidates.extend(keywords)
    for keyword in candidates:
        keyword = keyword.strip()
        if keyword and keyword in text and keyword not in hits:
            hits.append(keyword)
    return hits


def _has_generic_unit(text: str) -> bool:
    return bool(re.search(r"(吨|千克|公斤|克|立方米|万立方米|千瓦时|兆瓦时|MWh|kWh|小时|人次|万元|元|%|％|次|件|项|家|人)", text))


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def _rate(value: int, total: int) -> str:
    return f"{(value / total):.4f}" if total else "0.0000"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\x00", "")).strip()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AI-assisted quality review for formal_v1 ESG extraction outputs.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--no-llm", action="store_true", help="Disable qwen3 high-risk adjudication.")
    parser.add_argument("--max-llm-reviews", type=int, default=80)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    summary = run_review(
        project_root=Path("."),
        out_dir=Path(args.out_dir),
        use_llm=not args.no_llm,
        max_llm_reviews=args.max_llm_reviews,
        ollama_url=args.ollama_url,
        model=args.model,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
