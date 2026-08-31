#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_api import repository
from dashboard_api.preaudit import claim_graph, preaudit_issues, preaudit_summary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/ai_contest"


def validate(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    reports = [item["report_id"] for item in repository.report_index() if item.get("has_pdf")]
    severity = Counter()
    issue_types = Counter()
    graph_totals = Counter()
    total_issues = 0
    traceable = 0
    calculation_total = 0
    calculation_reproducible = 0
    report_rows = []

    for report_id in reports:
        issues = preaudit_issues([], report_id, include_closed=True)["items"]
        graph = claim_graph(report_id)
        for key, value in graph["stats"].items():
            graph_totals[key] += value
        for issue in issues:
            total_issues += 1
            severity[issue["severity"]] += 1
            issue_types[issue["issue_type"]] += 1
            traceable += bool(issue.get("evidence") or issue.get("requirement"))
            if issue.get("calculation"):
                calculation_total += 1
                calculation = issue["calculation"]
                calculation_reproducible += bool(
                    calculation.get("formula")
                    and calculation.get("display")
                    and calculation.get("tolerance") is not None
                    and len(issue.get("evidence", [])) >= 3
                )
        report_rows.append(
            {
                "report_id": report_id,
                "issues": len(issues),
                "blocking": sum(item["severity"] == "blocking" for item in issues),
                "important": sum(item["severity"] == "important" for item in issues),
                "attention": sum(item["severity"] == "attention" for item in issues),
            }
        )

    suggested = preaudit_summary([], "")["suggested_report_id"]
    before = preaudit_summary([], suggested)
    first = preaudit_issues([], suggested, include_closed=True)["items"][0]
    synthetic_action = {
        "issue_id": first["issue_id"],
        "report_id": suggested,
        "action": "resolved",
        "note": "in-memory contract validation",
        "reviewer": "validator",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    after = preaudit_summary([synthetic_action], suggested)
    action_contract = {
        "report_id": suggested,
        "issue_id": first["issue_id"],
        "open_before": before["open_issues"],
        "open_after": after["open_issues"],
        "closed_before": before["closed_count"],
        "closed_after": after["closed_count"],
        "passed": after["open_issues"] == before["open_issues"] - 1 and after["closed_count"] == before["closed_count"] + 1,
        "note": "使用内存 action 验证状态合同，不写入正式数据库。",
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validation_kind": "contract_and_coverage_validation_not_accuracy_evaluation",
        "data_scope": {"reports": len(reports), "extraction_rows": len(repository.results())},
        "graph": dict(graph_totals),
        "issues": {
            "total": total_issues,
            "by_severity": dict(severity),
            "by_type": dict(issue_types),
            "traceability_completeness": round(traceable / total_issues, 4) if total_issues else 0.0,
            "calculation_candidates": calculation_total,
            "calculation_reproducibility": round(calculation_reproducible / calculation_total, 4) if calculation_total else None,
        },
        "action_contract": action_contract,
        "reports_with_most_blocking_issues": sorted(report_rows, key=lambda row: (-row["blocking"], -row["important"], row["report_id"]))[:10],
        "limitations": [
            "This validation measures implementation coverage and traceability, not model accuracy.",
            "Independent human accuracy evaluation is outside this submission scope; precision/recall/F1 are intentionally omitted.",
            "Cross-claim arithmetic checks are scope-difference candidates until subject, period and scope fields are fully extracted.",
            "Automatic rule mapping is enabled only for Shanghai-listed reports in the first MVP.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "preaudit_mvp_validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "preaudit_mvp_validation.md").write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict) -> str:
    scope = payload["data_scope"]
    graph = payload["graph"]
    issues = payload["issues"]
    action = payload["action_contract"]
    return f"""# ESG ClaimGuard MVP 合同与覆盖验证

> 本报告只验证实现覆盖、可追溯性和状态合同，不是准确率评估。

## 数据范围

- 报告：{scope['reports']} 份
- 抽取记录：{scope['extraction_rows']} 条
- 图节点：{graph.get('node_count', 0)}
- 图关系：{graph.get('edge_count', 0)}
- 声明节点：{graph.get('claim_count', 0)}
- 证据节点：{graph.get('evidence_count', 0)}
- 可计算约束实例：{graph.get('constraint_count', 0)}
- 标准节点：{graph.get('standard_count', 0)}

## 问题合同

- 问题总数：{issues['total']}
- 严重度分布：{issues['by_severity']}
- 可追溯完整率：{issues['traceability_completeness'] * 100:.1f}%
- 计算候选：{issues['calculation_candidates']}
- 可复算完整率：{'—' if issues['calculation_reproducibility'] is None else f"{issues['calculation_reproducibility'] * 100:.1f}%"}
- 处置状态合同：{'通过' if action['passed'] else '未通过'}（开放问题 {action['open_before']} → {action['open_after']}，关闭问题 {action['closed_before']} → {action['closed_after']}）

## 口径边界

- 独立人工准确率评测不属于本次参赛交付范围，因此不报告 Precision、Recall 或 F1。
- 数值总分检查是口径差异候选；subject、period、scope 未完整抽取前不认定报告错误。
- 第一版自动条款映射只对沪市报告启用。
- 人工处置合同使用内存数据验证，没有写入正式复核数据库。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ESG ClaimGuard MVP contracts without claiming accuracy.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = validate(Path(args.output_dir))
    print(json.dumps({"data_scope": payload["data_scope"], "graph": payload["graph"], "issues": payload["issues"], "action_contract": payload["action_contract"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
