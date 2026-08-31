from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from dashboard_api import repository
from scripts.build_review_set import classify_row


RISK_WEIGHT = 0.35
UNCERTAINTY_WEIGHT = 0.25
GAP_WEIGHT = 0.25
FEEDBACK_WEIGHT = 0.15
ACTIONABLE_GAP_THRESHOLD = 0.60
FAILURE_LABELS = {"incorrect", "partial", "missed"}
ISSUE_LABELS = {
    "evidence_empty": "结果缺少原文证据",
    "evidence_too_short": "证据片段过短",
    "value_unit_missing": "定量值或单位不完整",
    "value_unit_suspicious": "数值与单位组合可疑",
    "possible_rate_as_count": "可能把比例误作数量",
    "possible_money_as_count": "可能把金额误作数量",
    "possible_zero_event": "零事件归一化需要核验",
    "possible_table_header_loss": "表格行列上下文可能丢失",
    "possible_policy_as_boolean": "机制证据可能只有标题",
    "high_risk_indicator": "属于需谨慎核验的指标",
}


def audit_summary(
    review_rows: list[dict[str, Any]],
    report_id: str = "",
    dataset_id: str = repository.DEFAULT_DATASET_ID,
) -> dict[str, Any]:
    metadata = repository.dataset_metadata(dataset_id)
    review_rows = _scoped_reviews(review_rows, dataset_id)
    all_rows = repository.results(dataset_id)
    peer_stats = _peer_stats(all_rows)
    selected_rows = [row for row in all_rows if not report_id or row.get("report_id") == report_id]
    review_map = _review_map(review_rows)
    scored = [_score_row(row, peer_stats, review_rows, review_map) for row in selected_rows]
    unreviewed = sorted((item for item in scored if not item["reviewed"]), key=_queue_key)
    concrete = [item for item in scored if item["signals"]["rule_risk"] > 0]
    gaps = [item for item in scored if item["signals"]["peer_gap"] >= ACTIONABLE_GAP_THRESHOLD]
    uncertain = [item for item in scored if item["signals"]["uncertainty"] >= 0.45]
    top_twenty = unreviewed[:20]
    known_keys = {(item["report_id"], item["indicator_id"]) for item in concrete}
    covered = sum((item["report_id"], item["indicator_id"]) in known_keys for item in top_twenty)
    suggested = unreviewed[0]["report_id"] if unreviewed else (selected_rows[0].get("report_id", "") if selected_rows else "")
    dimension = Counter(item.get("dimension", "") for item in scored if item.get("status") == "found")
    return {
        "dataset_id": metadata["dataset_id"],
        "run_id": metadata["run_id"],
        "dataset_scope": metadata["scope"],
        "scope": report_id or "all_reports",
        "report_id": report_id,
        "suggested_report_id": suggested,
        "total_items": len(scored),
        "unreviewed_count": len(unreviewed),
        "reviewed_count": sum(item["reviewed"] for item in scored),
        "known_risk_count": len(concrete),
        "actionable_gap_count": len(gaps),
        "uncertain_count": len(uncertain),
        "high_priority_count": sum(item["priority_band"] == "high" for item in unreviewed),
        "risk_recall_at_20": round(covered / len(known_keys), 4) if known_keys else None,
        "found_by_dimension": dict(dimension),
        "method": {
            "formula": "100 × (0.35R + 0.25U + 0.25G + 0.15F)",
            "weights": {"rule_risk": RISK_WEIGHT, "uncertainty": UNCERTAINTY_WEIGHT, "peer_gap": GAP_WEIGHT, "feedback": FEEDBACK_WEIGHT},
            "gap_threshold": ACTIONABLE_GAP_THRESHOLD,
            "note": "优先级用于分配人工复核资源，不是 ESG 评分或企业排名。",
        },
    }


def audit_queue(
    review_rows: list[dict[str, Any]],
    report_id: str = "",
    limit: int = 65,
    include_reviewed: bool = False,
    dataset_id: str = repository.DEFAULT_DATASET_ID,
) -> dict[str, Any]:
    metadata = repository.dataset_metadata(dataset_id)
    review_rows = _scoped_reviews(review_rows, dataset_id)
    all_rows = repository.results(dataset_id)
    peer_stats = _peer_stats(all_rows)
    review_map = _review_map(review_rows)
    selected = [row for row in all_rows if not report_id or row.get("report_id") == report_id]
    items = [_score_row(row, peer_stats, review_rows, review_map) for row in selected]
    if not include_reviewed:
        items = [item for item in items if not item["reviewed"]]
    items.sort(key=_queue_key)
    limited = items[: max(1, min(limit, 500))]
    examples_by_indicator = _peer_examples(all_rows, {item["indicator_id"] for item in limited if item["category"] == "gap"})
    for item in limited:
        item["peer_examples"] = examples_by_indicator.get(item["indicator_id"], []) if item["category"] == "gap" else []
    return {
        "items": limited,
        "total": len(items),
        "report_id": report_id,
        "dataset_id": metadata["dataset_id"],
        "run_id": metadata["run_id"],
        "scope": metadata["scope"],
    }


def _score_row(
    row: dict[str, Any],
    peer_stats: dict[str, dict[str, float]],
    review_rows: list[dict[str, Any]],
    review_map: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    classified = classify_row(row)
    issue = row.get("suspected_issue_type") or classified.get("suspected_issue_type", "normal_sample")
    risk_level = row.get("risk_level") or classified.get("risk_level", "")
    risk = {"high": 1.0, "medium": 0.70, "low": 0.40}.get(str(risk_level), 0.0)
    if not risk and issue == "high_risk_indicator":
        risk = 0.20

    candidate_count = _integer(row.get("source_candidate_count"))
    confidence = _number(row.get("llm_confidence"))
    uncertainty = 0.0
    uncertainty_reasons: list[str] = []
    if row.get("status") == "found":
        if 0 < confidence < 0.80:
            uncertainty += min((0.80 - confidence) / 0.80, 0.55)
            uncertainty_reasons.append(f"模型置信度仅 {confidence:.0%}")
        elif confidence <= 0:
            uncertainty += 0.22
            uncertainty_reasons.append("模型未提供有效置信度")
    if candidate_count >= 2:
        uncertainty += min(candidate_count / 5, 1.0) * 0.30
        if candidate_count >= 5:
            uncertainty_reasons.append(f"存在 {candidate_count} 个竞争候选证据")
    if _truthy(row.get("postprocess_repaired")):
        uncertainty += 0.28
        uncertainty_reasons.append("结果经过规则后处理修复")
    if _truthy(row.get("quantitative_incomplete")):
        uncertainty += 0.55
        uncertainty_reasons.append("定量字段不完整")
    uncertainty = min(uncertainty, 1.0)

    stats = peer_stats.get(str(row.get("indicator_id", "")), {"found_rate": 0.0})
    peer_rate = stats["found_rate"]
    gap = peer_rate if row.get("status") == "missing" and peer_rate >= ACTIONABLE_GAP_THRESHOLD else 0.0

    indicator_reviews = [item for item in review_rows if item.get("indicator_id") == row.get("indicator_id")]
    failures = sum(item.get("label") in FAILURE_LABELS for item in indicator_reviews)
    review_count = len(indicator_reviews)
    posterior_error = (failures + 1) / (review_count + 2)
    exploration = 1 / math.sqrt(review_count + 1)
    feedback = min(0.70 * posterior_error + 0.30 * exploration, 1.0)

    key = (str(row.get("report_id", "")), str(row.get("indicator_id", "")))
    review = review_map.get(key)
    raw_score = 100 * (
        RISK_WEIGHT * risk
        + UNCERTAINTY_WEIGHT * uncertainty
        + GAP_WEIGHT * gap
        + FEEDBACK_WEIGHT * feedback
    )
    score = raw_score * (0.20 if review else 1.0)

    reasons: list[str] = []
    if risk:
        reasons.append(ISSUE_LABELS.get(str(issue), "规则识别到需要核验的结构风险"))
    reasons.extend(uncertainty_reasons[:2])
    if gap:
        reasons.append(f"该指标在语料中 {peer_rate:.0%} 的报告有披露，本报告未命中")
    if review_count:
        reasons.append(f"该指标已有 {review_count} 条人工反馈，平滑错误风险 {posterior_error:.0%}")
    else:
        reasons.append("该指标尚无人工反馈，保留探索优先级")
    if not reasons:
        reasons.append("常规抽样核验任务")

    if risk:
        category = "risk"
    elif gap:
        category = "gap"
    elif uncertainty >= 0.45:
        category = "uncertainty"
    else:
        category = "routine"

    output = dict(row)
    output.update(
        {
            "priority_score": round(score, 1),
            "priority_band": "high" if score >= 60 else "medium" if score >= 35 else "low",
            "category": category,
            "category_label": {"risk": "结构风险", "gap": "披露缺口", "uncertainty": "证据不确定", "routine": "常规抽样"}[category],
            "signals": {
                "rule_risk": round(risk, 4),
                "uncertainty": round(uncertainty, 4),
                "peer_gap": round(gap, 4),
                "feedback": round(feedback, 4),
            },
            "peer_found_rate": round(peer_rate, 4),
            "peer_found_count": int(stats.get("found", 0)),
            "peer_total": int(stats.get("total", 0)),
            "review_count_for_indicator": review_count,
            "feedback_error_probability": round(posterior_error, 4),
            "reviewed": bool(review),
            "review_label": review.get("label", "") if review else "",
            "priority_reasons": reasons[:4],
            "peer_examples": [],
        }
    )
    return output


def _peer_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("indicator_id", ""))].append(row)
    return {
        indicator_id: {
            "found": float(sum(row.get("status") == "found" for row in items)),
            "total": float(len(items)),
            "found_rate": sum(row.get("status") == "found" for row in items) / len(items) if items else 0.0,
        }
        for indicator_id, items in grouped.items()
    }


def _peer_examples(rows: list[dict[str, Any]], indicator_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        indicator_id = str(row.get("indicator_id", ""))
        if indicator_id not in indicator_ids or row.get("status") != "found" or not row.get("evidence_quote"):
            continue
        if len(output[indicator_id]) >= 2:
            continue
        output[indicator_id].append(
            {
                "report_id": row.get("report_id", ""),
                "value": row.get("value", ""),
                "unit": row.get("unit", ""),
                "evidence_quote": row.get("evidence_quote", ""),
                "page_no": row.get("page_no", ""),
                "block_id": row.get("block_id", ""),
            }
        )
    return dict(output)


def _review_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(str(row.get("report_id", "")), str(row.get("indicator_id", ""))): row for row in rows}


def _scoped_reviews(rows: list[dict[str, Any]], dataset_id: str) -> list[dict[str, Any]]:
    """Legacy unscoped reviews belong only to the historical baseline."""
    if dataset_id == repository.CURRENT_DATASET_ID:
        return [row for row in rows if row.get("dataset_id", dataset_id) == dataset_id]
    return [row for row in rows if row.get("dataset_id") == dataset_id]


def _queue_key(item: dict[str, Any]) -> tuple[float, str, str]:
    return (-float(item["priority_score"]), str(item.get("report_id", "")), str(item.get("indicator_id", "")))


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
