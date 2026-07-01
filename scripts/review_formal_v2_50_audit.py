#!/usr/bin/env python3
import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_esg_formal_v2 import (
    HIGH_RISK_REVIEW_INDICATORS,
    _parse_llm_json,
    _sample_review_rows,
    _safe_float,
    _write_csv,
)
from src.esg_demo.ollama import OllamaClient
from src.esg_demo.runner import DEFAULT_MODEL, DEFAULT_OLLAMA_URL, _validate_model


DEFAULT_DIR = Path("outputs/formal_v2/llm_50")
ALLOWED_LABELS = {"correct", "partial", "wrong", "uncertain"}
ALLOWED_ERROR_TYPES = {
    "none",
    "wrong_indicator_mapping",
    "weak_evidence",
    "value_error",
    "unit_error",
    "missing_value_unit",
    "boolean_misread",
    "qualitative_boundary_issue",
    "zero_event_ambiguity",
    "table_parse_noise",
    "context_insufficient",
    "other",
}


def run_audit(
    base_dir: Path = DEFAULT_DIR,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    max_rows: int = 200,
    client=None,
) -> dict:
    _validate_model(model)
    started = time.time()
    base_dir.mkdir(parents=True, exist_ok=True)
    extraction_rows = _read_csv(base_dir / "extraction_results.csv")
    sample_rows = _read_csv(base_dir / "sample_review.csv")
    review_rows = _prepare_review_rows(sample_rows, extraction_rows, max_rows)
    judge = client or OllamaClient(model=model, url=ollama_url)

    audited = []
    for row in review_rows:
        row_started = time.time()
        prompt = _build_audit_prompt(row)
        raw = ""
        try:
            raw = judge.generate(prompt)
            payload = _parse_llm_json(raw)
            audit = _normalize_audit_payload(payload)
        except Exception as exc:
            audit = {
                "audit_label": "uncertain",
                "audit_confidence": "0.0000",
                "audit_error_type": "context_insufficient",
                "audit_reason": f"judge_parse_or_call_error: {exc}",
                "fix_priority": "medium",
                "fix_suggestion": "保留样本进入人工或后续 AI-assisted review，不据此改写指标。",
            }
        merged = dict(row)
        merged.update(audit)
        merged["audit_elapsed_seconds"] = f"{time.time() - row_started:.3f}"
        merged["judge_model"] = model
        merged["judge_raw_response"] = raw
        audited.append(merged)

    _write_csv(base_dir / "sample_review_ai_audited.csv", audited)
    by_indicator = _metrics_by(audited, ["indicator_id", "indicator_name", "dimension", "indicator_type"])
    by_dimension = _metrics_by(audited, ["dimension"])
    by_type = _metrics_by(audited, ["indicator_type"])
    _write_csv(base_dir / "audit_metrics_by_indicator.csv", by_indicator)
    _write_csv(base_dir / "audit_metrics_by_dimension.csv", by_dimension)
    _write_csv(base_dir / "audit_metrics_by_type.csv", by_type)
    suggestions = _fix_suggestions(by_indicator, audited)
    _write_csv(base_dir / "pre_100_fix_suggestions.csv", suggestions)

    summary = _audit_summary(audited, by_indicator, suggestions, round(time.time() - started, 3))
    _write_audit_report(base_dir / "ai_audit_report.md", summary, by_dimension, by_type, suggestions)
    return summary


def _prepare_review_rows(sample_rows: list[dict], extraction_rows: list[dict], max_rows: int) -> list[dict]:
    selected = []
    seen = set()
    for row in sample_rows:
        key = (row.get("report_id"), row.get("indicator_id"))
        if key in seen:
            continue
        selected.append(row)
        seen.add(key)
        if len(selected) >= max_rows:
            return selected[:max_rows]
    for row in _sample_review_rows(extraction_rows, max_rows=max_rows * 2):
        key = (row.get("report_id"), row.get("indicator_id"))
        if key in seen:
            continue
        selected.append(row)
        seen.add(key)
        if len(selected) >= max_rows:
            break
    return selected


def _build_audit_prompt(row: dict) -> str:
    allowed_view = {
        "report_id": row.get("report_id", ""),
        "indicator_id": row.get("indicator_id", ""),
        "indicator_name": row.get("indicator_name", ""),
        "dimension": row.get("dimension", ""),
        "indicator_type": row.get("indicator_type", ""),
        "status": row.get("status", ""),
        "value": row.get("value", ""),
        "unit": row.get("unit", ""),
        "qualitative_text": row.get("qualitative_text", ""),
        "evidence_quote": row.get("evidence_quote", ""),
        "page_no": row.get("page_no", ""),
        "block_type": row.get("block_type", ""),
        "llm_confidence": row.get("llm_confidence", ""),
        "postprocess_repaired": row.get("postprocess_repaired", ""),
        "quantitative_incomplete": row.get("quantitative_incomplete", ""),
        "repair_method": row.get("repair_method", ""),
        "repair_reason": row.get("repair_reason", ""),
    }
    return (
        "/no_think\n"
        "你是 ESG 抽取结果的 AI-assisted quality audit judge。只能基于给定 evidence_quote 判断，不能凭常识、报告背景或外部知识补答案。\n"
        "判断 extraction 是否被 evidence_quote 支持。不要把本任务写成人工标注。\n"
        "label 规则：correct=证据明确支持指标和值/单位/文本；partial=方向相关但值、单位、边界或证据不完整；wrong=证据不能支持该指标或明显误映射；uncertain=证据或上下文不足。\n"
        "audit_error_type 只能取：none,wrong_indicator_mapping,weak_evidence,value_error,unit_error,missing_value_unit,boolean_misread,qualitative_boundary_issue,zero_event_ambiguity,table_parse_noise,context_insufficient,other。\n"
        "定量 quantitative：value 必须是证据中的数值或零事件归一；unit 必须能由证据或明确零事件计数语义支持。缺 value/unit 时通常 partial 或 wrong，并标记 missing_value_unit/unit_error/value_error。\n"
        "布尔 boolean：证据必须支持机制/政策/措施存在，不能只因关键词出现就 correct。\n"
        "定性 qualitative：qualitative_text 应与 evidence_quote 边界一致，不能过度概括。\n"
        "只返回 JSON 对象，字段：audit_label,audit_confidence,audit_error_type,audit_reason,fix_priority,fix_suggestion。\n"
        f"待审结果：{json.dumps(allowed_view, ensure_ascii=False)}"
    )


def _normalize_audit_payload(payload: dict) -> dict:
    label = str(payload.get("audit_label", "") or "").strip().lower()
    if label not in ALLOWED_LABELS:
        label = "uncertain"
    error_type = str(payload.get("audit_error_type", "") or "").strip()
    if error_type not in ALLOWED_ERROR_TYPES:
        error_type = "other" if label in {"partial", "wrong"} else "context_insufficient"
    if label == "correct" and error_type != "none":
        error_type = "none"
    confidence = _safe_float(payload.get("audit_confidence"), 0.0)
    confidence = max(0.0, min(1.0, confidence))
    priority = str(payload.get("fix_priority", "") or "").strip().lower()
    if priority not in {"none", "low", "medium", "high"}:
        priority = "none" if label == "correct" else "medium"
    return {
        "audit_label": label,
        "audit_confidence": f"{confidence:.4f}",
        "audit_error_type": error_type,
        "audit_reason": str(payload.get("audit_reason", "") or "")[:300],
        "fix_priority": priority,
        "fix_suggestion": str(payload.get("fix_suggestion", "") or "")[:300],
    }


def _metrics_by(rows: list[dict], keys: list[str]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key, "") for key in keys)].append(row)
    metrics = []
    for key_values, group in sorted(groups.items()):
        counts = Counter(row["audit_label"] for row in group)
        errors = Counter(row["audit_error_type"] for row in group if row["audit_error_type"] != "none")
        reviewed = len(group)
        item = {key: value for key, value in zip(keys, key_values)}
        item.update(
            {
                "reviewed_count": reviewed,
                "correct_count": counts["correct"],
                "partial_count": counts["partial"],
                "wrong_count": counts["wrong"],
                "uncertain_count": counts["uncertain"],
                "correct_rate": f"{(counts['correct'] / reviewed if reviewed else 0):.4f}",
                "usable_rate": f"{((counts['correct'] + counts['partial']) / reviewed if reviewed else 0):.4f}",
                "dominant_error_type": errors.most_common(1)[0][0] if errors else "none",
            }
        )
        metrics.append(item)
    return metrics


def _fix_suggestions(metrics: list[dict], audited: list[dict]) -> list[dict]:
    rows_by_indicator = defaultdict(list)
    for row in audited:
        rows_by_indicator[row["indicator_id"]].append(row)
    suggestions = []
    for item in metrics:
        indicator_id = item["indicator_id"]
        reviewed = int(item["reviewed_count"])
        correct_rate = float(item["correct_rate"])
        usable_rate = float(item["usable_rate"])
        dominant = item["dominant_error_type"]
        wrong_count = int(item["wrong_count"])
        sample_reasons = [
            row["audit_reason"]
            for row in rows_by_indicator[indicator_id]
            if row["audit_label"] in {"partial", "wrong", "uncertain"}
        ][:3]
        high_risk = indicator_id in HIGH_RISK_REVIEW_INDICATORS
        if reviewed < 2:
            action = "monitor_only"
            enter_100 = "yes"
            priority = "low"
            reason = "抽检样本少，未发现集中爆发问题。"
        elif usable_rate >= 0.75 and correct_rate >= 0.45:
            action = "keep"
            enter_100 = "yes"
            priority = "low"
            reason = "AI-assisted audit 可用率较高。"
        elif dominant in {"missing_value_unit", "unit_error", "value_error", "zero_event_ambiguity", "table_parse_noise"}:
            action = "strengthen_postprocess"
            enter_100 = "yes"
            priority = "high" if high_risk or usable_rate < 0.5 else "medium"
            reason = "问题集中在定量字段或表格解析，可通过保守后处理和 prompt 约束控制。"
        elif dominant in {"wrong_indicator_mapping", "weak_evidence"}:
            action = "revise_keywords_or_hold"
            enter_100 = "no" if usable_rate < 0.5 else "yes"
            priority = "high" if usable_rate < 0.5 else "medium"
            reason = "存在误映射或弱证据风险，需要收紧关键词或暂缓。"
        else:
            action = "need_more_review"
            enter_100 = "yes" if wrong_count == 0 else ("yes" if usable_rate >= 0.5 else "no")
            priority = "medium"
            reason = "质量信号不充分，需在 100 份阶段继续监控。"
        suggestions.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": item["indicator_name"],
                "dimension": item["dimension"],
                "indicator_type": item["indicator_type"],
                "reviewed_count": reviewed,
                "correct_rate": item["correct_rate"],
                "usable_rate": item["usable_rate"],
                "dominant_error_type": dominant,
                "recommended_action": action,
                "enter_100": enter_100,
                "priority": priority,
                "reason": reason,
                "revision_hint": "；".join(sample_reasons)[:500] if sample_reasons else "无明显修复项。",
            }
        )
    return suggestions


def _audit_summary(audited: list[dict], by_indicator: list[dict], suggestions: list[dict], elapsed: float) -> dict:
    label_counts = Counter(row["audit_label"] for row in audited)
    error_counts = Counter(row["audit_error_type"] for row in audited)
    reviewed = len(audited)
    usable = label_counts["correct"] + label_counts["partial"]
    wrong_indicators = [row for row in by_indicator if int(row["wrong_count"]) >= 2 or float(row["usable_rate"]) < 0.5]
    high_priority = [row for row in suggestions if row["priority"] == "high"]
    can_enter_100 = (
        reviewed >= 150
        and (usable / reviewed if reviewed else 0) >= 0.65
        and len(high_priority) <= 8
        and len(wrong_indicators) <= 8
    )
    return {
        "reviewed_count": reviewed,
        "label_counts": dict(label_counts),
        "error_counts": dict(error_counts),
        "overall_correct_rate": round(label_counts["correct"] / reviewed if reviewed else 0, 4),
        "overall_usable_rate": round(usable / reviewed if reviewed else 0, 4),
        "indicator_count_reviewed": len(by_indicator),
        "high_priority_fix_count": len(high_priority),
        "problem_indicator_count": len(wrong_indicators),
        "can_enter_100": can_enter_100,
        "elapsed_seconds": elapsed,
    }


def _write_audit_report(path: Path, summary: dict, by_dimension: list[dict], by_type: list[dict], suggestions: list[dict]) -> None:
    label_counts = summary["label_counts"]
    error_counts = summary["error_counts"]
    action_counts = Counter(row["recommended_action"] for row in suggestions)
    hold = [row for row in suggestions if row["enter_100"] == "no"]
    high = [row for row in suggestions if row["priority"] == "high"]
    lines = [
        "# formal_v2 50-report AI-assisted Quality Audit",
        "",
        "本报告是 AI-assisted quality audit / 辅助质检评估，不是人工 gold annotation，也不声明人工标注评价结论。",
        "",
        "## Inputs",
        "",
        "- `outputs/formal_v2/llm_50/extraction_results.csv`",
        "- `outputs/formal_v2/llm_50/extraction_results.json`",
        "- `outputs/formal_v2/llm_50/sample_review.csv`",
        "- `outputs/formal_v2/llm_50/error_analysis.csv`",
        "- `outputs/formal_v2/llm_50/llm_50_diagnostics.md`",
        "- `outputs/formal_v2/llm_50/run_summary.json`",
        "",
        "## Summary",
        "",
        f"- 审核样本数：{summary['reviewed_count']}",
        f"- label 分布：{label_counts}",
        f"- error_type 分布：{error_counts}",
        f"- overall correct_rate：{summary['overall_correct_rate']:.4f}",
        f"- overall usable_rate：{summary['overall_usable_rate']:.4f}",
        f"- 覆盖指标数：{summary['indicator_count_reviewed']}",
        f"- high priority fix 数：{summary['high_priority_fix_count']}",
        f"- 建议动作分布：{dict(action_counts)}",
        f"- 是否满足进入 100 份前置条件：{'是' if summary['can_enter_100'] else '否'}",
        f"- audit 耗时：{summary['elapsed_seconds']} 秒",
        "",
        "## Metrics By Dimension",
        "",
    ]
    for row in by_dimension:
        lines.append(
            f"- {row['dimension']}：reviewed={row['reviewed_count']}，correct_rate={row['correct_rate']}，usable_rate={row['usable_rate']}，dominant_error={row['dominant_error_type']}"
        )
    lines.extend(["", "## Metrics By Type", ""])
    for row in by_type:
        lines.append(
            f"- {row['indicator_type']}：reviewed={row['reviewed_count']}，correct_rate={row['correct_rate']}，usable_rate={row['usable_rate']}，dominant_error={row['dominant_error_type']}"
        )
    lines.extend(["", "## High Priority Fixes", ""])
    if high:
        for row in high[:20]:
            lines.append(
                f"- `{row['indicator_id']}`：{row['recommended_action']}，usable_rate={row['usable_rate']}，原因：{row['reason']}，提示：{row['revision_hint']}"
            )
    else:
        lines.append("无。")
    lines.extend(["", "## Temporarily Hold From 100", ""])
    if hold:
        for row in hold:
            lines.append(f"- `{row['indicator_id']}`：{row['reason']}；{row['revision_hint']}")
    else:
        lines.append("无。")
    lines.extend(
        [
            "",
            "## Pre-100 Decision",
            "",
            (
                "AI-assisted audit 未发现错误集中爆发，且 high-priority 问题数量可控；在完成必要的保守修复后，可以进入 100 份扩展抽取。"
                if summary["can_enter_100"]
                else "AI-assisted audit 发现较多高优先级或可用率不足问题，暂不建议直接进入 100 份。"
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI-assisted quality audit for formal_v2 50-report LLM outputs.")
    parser.add_argument("--base-dir", default=str(DEFAULT_DIR))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--max-rows", type=int, default=200)
    args = parser.parse_args()
    summary = run_audit(Path(args.base_dir), args.model, args.ollama_url, args.max_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
