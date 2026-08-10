#!/usr/bin/env python3
"""Deprecated evaluator for the superseded audit-priority prototype.

Use ``scripts/validate_preaudit_mvp.py`` for the current ClaimGuard contract and
coverage validation. This legacy script is retained only for reproducibility.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_api import repository
from dashboard_api.audit import audit_queue, audit_summary
from dashboard_api.reviews import ReviewStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/ai_contest"


def evaluate(output_dir: Path = DEFAULT_OUTPUT, review_rows: list[dict] | None = None) -> dict:
    reviews = review_rows if review_rows is not None else ReviewStore().list()
    global_summary = audit_summary(reviews)
    global_items = audit_queue(reviews, "", 500, include_reviewed=True)["items"]
    risk_keys = {
        (row["report_id"], row["indicator_id"])
        for row in repository.results()
        if row.get("risk_level") in {"high", "medium", "low"}
    }
    risk_recall = {}
    for k in (20, 50, 100, 200, 300, 500):
        covered = sum((item["report_id"], item["indicator_id"]) in risk_keys for item in global_items[:k])
        risk_recall[f"risk_recall_at_{k}"] = round(covered / len(risk_keys), 4) if risk_keys else None

    by_report: dict[str, list[dict]] = defaultdict(list)
    for row in repository.results():
        by_report[row["report_id"]].append(row)
    reductions = []
    report_details = []
    for report_id, rows in by_report.items():
        known = {(row["report_id"], row["indicator_id"]) for row in rows if row.get("risk_level") in {"high", "medium", "low"}}
        if not known:
            continue
        queue = audit_queue(reviews, report_id, 65, include_reviewed=True)["items"]
        positions = [index for index, item in enumerate(queue, start=1) if (item["report_id"], item["indicator_id"]) in known]
        k = max(positions) if positions else len(queue)
        reduction = 1 - k / len(rows)
        reductions.append(reduction)
        report_details.append({"report_id": report_id, "known_risks": len(known), "tasks_to_cover_all_known_risks": k, "workload_reduction": round(reduction, 4)})

    explanation_complete = sum(
        bool(item.get("priority_reasons"))
        and set(item.get("signals", {})) == {"rule_risk", "uncertainty", "peer_gap", "feedback"}
        and "priority_score" in item
        for item in global_items
    )

    feedback_test = {"executed": False}
    if global_items:
        target = global_items[0]
        synthetic_review = {"report_id": target["report_id"], "indicator_id": target["indicator_id"], "label": "correct"}
        after_default = audit_queue([*reviews, synthetic_review], target["report_id"], 65)["items"]
        after_all = audit_queue([*reviews, synthetic_review], target["report_id"], 65, include_reviewed=True)["items"]
        after_target = next(item for item in after_all if item["indicator_id"] == target["indicator_id"])
        feedback_test = {
            "executed": True,
            "target": f"{target['report_id']}|{target['indicator_id']}",
            "score_before": target["priority_score"],
            "score_after_review": after_target["priority_score"],
            "removed_from_default_queue": not any(item["indicator_id"] == target["indicator_id"] for item in after_default),
            "passed": after_target["priority_score"] < target["priority_score"] and not any(item["indicator_id"] == target["indicator_id"] for item in after_default),
            "note": "使用内存中的合成 correct 标签验证响应合同，不写入人工复核数据库。",
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_scope": {
            "reports": len(by_report),
            "report_indicator_tasks": len(repository.results()),
            "known_rule_risks": len(risk_keys),
            "actionable_gaps": global_summary["actionable_gap_count"],
            "uncertain_tasks": global_summary["uncertain_count"],
            "manual_reviews": len(reviews),
        },
        "risk_recall": risk_recall,
        "workload_reduction": {
            "reports_with_known_risks": len(reductions),
            "mean": round(sum(reductions) / len(reductions), 4) if reductions else None,
            "min": round(min(reductions), 4) if reductions else None,
            "max": round(max(reductions), 4) if reductions else None,
            "per_report": sorted(report_details, key=lambda item: item["workload_reduction"], reverse=True),
        },
        "explanation_completeness": round(explanation_complete / len(global_items), 4) if global_items else 0.0,
        "feedback_responsiveness": feedback_test,
        "limitations": [
            "known_rule_risks are automatic diagnostic labels, not human gold labels",
            "peer baseline uses the full 200-report corpus and is not an industry classification",
            "precision/recall/F1 must only be reported after manual review labels exist",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit_evaluation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "audit_evaluation.md").write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict) -> str:
    scope = payload["data_scope"]
    recall = payload["risk_recall"]
    workload = payload["workload_reduction"]
    feedback = payload["feedback_responsiveness"]
    return f"""# 【已弃用】证据风险图复核调度评估

> 本文件仅保留旧版调度实验的可复现记录，不代表当前 ESG ClaimGuard 产品，也不是模型准确率报告。当前验证入口为 `scripts/validate_preaudit_mvp.py`。

## 数据范围

- 报告数：{scope['reports']}
- report-indicator 任务：{scope['report_indicator_tasks']}
- 自动规则风险：{scope['known_rule_risks']}
- 可行动披露缺口：{scope['actionable_gaps']}
- 证据不确定任务：{scope['uncertain_tasks']}
- 已有人工复核：{scope['manual_reviews']}

## 调度效果

- Risk Recall@20：{_percent(recall['risk_recall_at_20'])}
- Risk Recall@50：{_percent(recall['risk_recall_at_50'])}
- Risk Recall@100：{_percent(recall['risk_recall_at_100'])}
- Risk Recall@200：{_percent(recall['risk_recall_at_200'])}
- Risk Recall@500：{_percent(recall['risk_recall_at_500'])}
- 含已知风险报告的平均工作量削减：{_percent(workload['mean'])}
- 解释完整率：{_percent(payload['explanation_completeness'])}
- 人工反馈响应合同：{'通过' if feedback.get('passed') else '未通过'}

## 口径边界

上述 Risk Recall 评价系统对已知自动规则风险的调度覆盖能力，不是模型准确率；自动规则风险不等于人工金标准。同行基线来自 200 份语料整体，不解释为行业排名。Precision、Recall 和 F1 仅在获得人工复核标签后报告。
"""


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deprecated: reproduce the legacy ESG audit-priority evaluation.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = evaluate(Path(args.output_dir))
    print(
        json.dumps(
            {
                "data_scope": payload["data_scope"],
                "risk_recall": payload["risk_recall"],
                "mean_workload_reduction": payload["workload_reduction"]["mean"],
                "explanation_completeness": payload["explanation_completeness"],
                "feedback_responsiveness_passed": payload["feedback_responsiveness"].get("passed"),
                "outputs": [str(Path(args.output_dir) / "audit_evaluation.json"), str(Path(args.output_dir) / "audit_evaluation.md")],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
