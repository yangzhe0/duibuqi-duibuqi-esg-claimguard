from __future__ import annotations

import csv
import hashlib
import io
import re
from functools import lru_cache
from typing import Any

from dashboard_api import repository


SEVERITY_ORDER = {"blocking": 0, "important": 1, "attention": 2}
ACTION_CLOSED = {"resolved", "accepted", "not_issue"}

# 第一轮只接入可以明确回到官方议题或条款的核心项。missing 表示“未找到说明”，
# 不直接解释为违规；适用性由用户在问题工作台确认。
STANDARD_REQUIREMENTS: dict[str, dict[str, str]] = {
    "g_materiality_assessment": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第五条",
        "topic": "双重重要性分析",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "e_climate_risk": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第二十一条至第二十八条",
        "topic": "应对气候变化",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "e_ghg_total": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第二十一条至第二十八条",
        "topic": "温室气体排放",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "e_energy_total": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第三十五条",
        "topic": "能源利用",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "e_water_total": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第三十六条",
        "topic": "水资源利用",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "e_waste_total": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第三十一条",
        "topic": "废弃物处理",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "e_environmental_penalty": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第三十三条",
        "topic": "环境合规管理",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "s_data_security": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第四十八条",
        "topic": "数据安全与客户隐私保护",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "s_employee_total": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第五十条",
        "topic": "员工",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "g_stakeholder_communication": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第五十三条",
        "topic": "利益相关方沟通",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
    "g_anti_corruption": {
        "standard": "上交所可持续发展报告指引第14号",
        "clause": "第五十五条",
        "topic": "反商业贿赂及反贪污",
        "source_url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/mainipo/c/c_20250516_10779150.shtml",
    },
}

ISSUE_TEXT = {
    "evidence_empty": "抽取结果没有可回溯的原文证据",
    "evidence_too_short": "证据片段过短，无法独立支持声明",
    "value_unit_missing": "定量声明缺少数值或单位",
    "value_unit_suspicious": "数值与单位组合需要核验",
    "possible_rate_as_count": "证据中的比例可能被当作数量",
    "possible_money_as_count": "证据中的金额可能被当作数量",
    "possible_zero_event": "零事件被归一化，需核对原文口径",
    "possible_table_header_loss": "表格行列标题可能在解析时丢失",
    "possible_policy_as_boolean": "机制性声明可能只有标题，没有实质内容",
    "high_risk_indicator": "该指标属于需要谨慎核验的高风险类型",
}

CONSTRAINTS = (
    {
        "id": "ghg_scope_balance",
        "total": "e_ghg_total",
        "parts": ("e_ghg_scope1", "e_ghg_scope2"),
        "title": "温室气体总量与范围一、范围二存在口径差异候选",
        "formula": "温室气体排放总量 ≈ 范围一 + 范围二",
        "tolerance": 0.05,
    },
    {
        "id": "waste_balance",
        "total": "e_waste_total",
        "parts": ("e_hazardous_waste", "e_nonhazardous_waste"),
        "title": "废弃物总量与危险、一般废弃物存在口径差异候选",
        "formula": "废弃物产生量 ≈ 危险废弃物 + 一般废弃物",
        "tolerance": 0.05,
    },
)


def preaudit_summary(action_rows: list[dict[str, Any]], report_id: str = "") -> dict[str, Any]:
    if report_id:
        payload = preaudit_issues(action_rows, report_id, include_closed=True)
        issues = payload["items"]
        graph = claim_graph(report_id)
        found = [row for row in repository.results() if row.get("report_id") == report_id and row.get("status") == "found"]
        evidenced = sum(bool(row.get("evidence_quote") and row.get("block_id")) for row in found)
        return {
            "scope": report_id,
            "report_id": report_id,
            "suggested_report_id": report_id,
            "total_issues": len(issues),
            "open_issues": sum(not item["closed"] for item in issues),
            "blocking_count": sum(item["severity"] == "blocking" and not item["closed"] for item in issues),
            "important_count": sum(item["severity"] == "important" and not item["closed"] for item in issues),
            "attention_count": sum(item["severity"] == "attention" and not item["closed"] for item in issues),
            "closed_count": sum(item["closed"] for item in issues),
            "evidence_coverage": round(evidenced / len(found), 4) if found else 0.0,
            "claim_count": graph["stats"]["claim_count"],
            "evidence_count": graph["stats"]["evidence_count"],
            "constraint_count": graph["stats"]["constraint_count"],
            "standard_count": graph["stats"]["standard_count"],
            "method_note": "问题按阻断、重要、提示三级展示；没有人工校准数据前不输出伪精确风险分。首轮自动条款映射只对沪市报告启用。",
        }

    reports = [item for item in repository.report_index() if item.get("has_pdf")]
    suggested = max(reports, key=lambda item: (item.get("risk_count", 0), item.get("missing_count", 0)), default={}).get("report_id", "")
    return {
        "scope": "all_reports",
        "report_id": "",
        "suggested_report_id": suggested,
        "report_count": len(reports),
        "method_note": "先选择一份报告完成问题发现、处置和底稿导出。",
    }


def preaudit_issues(
    action_rows: list[dict[str, Any]],
    report_id: str,
    include_closed: bool = False,
) -> dict[str, Any]:
    if not report_id:
        return {"items": [], "total": 0, "report_id": ""}
    action_map = {str(row.get("issue_id", "")): row for row in action_rows if row.get("report_id") == report_id}
    items: list[dict[str, Any]] = []
    for raw in _base_issues(report_id):
        item = dict(raw)
        action = action_map.get(item["issue_id"], {})
        item["action"] = action.get("action", "open")
        item["action_note"] = action.get("note", "")
        item["reviewer"] = action.get("reviewer", "")
        item["updated_at"] = action.get("updated_at", "")
        item["closed"] = item["action"] in ACTION_CLOSED
        if include_closed or not item["closed"]:
            items.append(item)
    items.sort(key=lambda item: (item["closed"], SEVERITY_ORDER[item["severity"]], item["issue_type"], item["issue_id"]))
    return {"items": items, "total": len(items), "report_id": report_id}


@lru_cache(maxsize=256)
def claim_graph(report_id: str) -> dict[str, Any]:
    rows = [row for row in repository.results() if row.get("report_id") == report_id]
    nodes: list[dict[str, Any]] = [{"id": f"report:{report_id}", "type": "report", "label": report_id}]
    edges: list[dict[str, Any]] = []
    standards_seen: set[str] = set()
    evidence_seen: set[str] = set()
    claims = 0

    for row in rows:
        indicator_id = str(row.get("indicator_id", ""))
        if row.get("status") != "found":
            continue
        claims += 1
        claim_id = f"claim:{indicator_id}"
        nodes.append(
            {
                "id": claim_id,
                "type": "claim",
                "label": row.get("indicator_name", ""),
                "indicator_id": indicator_id,
                "value": row.get("value", ""),
                "unit": row.get("unit", ""),
                "page_no": row.get("page_no", ""),
            }
        )
        edges.append({"source": f"report:{report_id}", "target": claim_id, "type": "contains"})
        block_id = str(row.get("block_id", ""))
        if block_id:
            evidence_id = f"evidence:{block_id}"
            if evidence_id not in evidence_seen:
                evidence_seen.add(evidence_id)
                nodes.append(
                    {
                        "id": evidence_id,
                        "type": "evidence",
                        "label": f"第 {row.get('page_no', '—')} 页证据",
                        "block_id": block_id,
                        "page_no": row.get("page_no", ""),
                        "quote": row.get("evidence_quote", ""),
                    }
                )
            edges.append({"source": evidence_id, "target": claim_id, "type": "supports"})
        requirement = _standard_requirement(report_id, indicator_id)
        if requirement:
            standard_id = f"standard:{requirement['clause']}"
            if standard_id not in standards_seen:
                standards_seen.add(standard_id)
                nodes.append({"id": standard_id, "type": "standard", "label": requirement["topic"], **requirement})
            edges.append({"source": claim_id, "target": standard_id, "type": "governed_by"})

    by_id = {str(row.get("indicator_id", "")): row for row in rows}
    constraint_count = 0
    for spec in CONSTRAINTS:
        if all(by_id.get(key, {}).get("status") == "found" for key in (spec["total"], *spec["parts"])):
            constraint_count += 1
            constraint_id = f"constraint:{spec['id']}"
            nodes.append({"id": constraint_id, "type": "constraint", "label": spec["formula"]})
            edges.append({"source": f"claim:{spec['total']}", "target": constraint_id, "type": "constrained_by"})
            for part in spec["parts"]:
                edges.append({"source": f"claim:{part}", "target": f"claim:{spec['total']}", "type": "part_of"})

    return {
        "report_id": report_id,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "claim_count": claims,
            "evidence_count": len(evidence_seen),
            "constraint_count": constraint_count,
            "standard_count": len(standards_seen),
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "note": "图中 supports、part_of、constrained_by 和 governed_by 均为可查询关系，不等同于可视化文案。",
    }


def export_workpaper_csv(action_rows: list[dict[str, Any]], report_id: str) -> bytes:
    issues = preaudit_issues(action_rows, report_id, include_closed=True)["items"]
    fields = [
        "issue_id", "report_id", "severity", "issue_type", "title", "finding", "action", "action_note",
        "reviewer", "updated_at", "indicator_names", "evidence_a", "evidence_a_page", "evidence_b",
        "evidence_b_page", "calculation", "standard", "clause", "source_url",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for item in issues:
        evidence = item.get("evidence", [])
        requirement = item.get("requirement", {})
        writer.writerow(
            {
                "issue_id": item["issue_id"],
                "report_id": item["report_id"],
                "severity": item["severity"],
                "issue_type": item["issue_type"],
                "title": item["title"],
                "finding": item["finding"],
                "action": item["action"],
                "action_note": item["action_note"],
                "reviewer": item["reviewer"],
                "updated_at": item["updated_at"],
                "indicator_names": " | ".join(item.get("indicator_names", [])),
                "evidence_a": evidence[0].get("quote", "") if evidence else "",
                "evidence_a_page": evidence[0].get("page_no", "") if evidence else "",
                "evidence_b": " | ".join(f"{row.get('label', '')}: {row.get('quote', '')}" for row in evidence[1:]),
                "evidence_b_page": " | ".join(str(row.get("page_no", "")) for row in evidence[1:]),
                "calculation": item.get("calculation", {}).get("display", ""),
                "standard": requirement.get("standard", ""),
                "clause": requirement.get("clause", ""),
                "source_url": requirement.get("source_url", ""),
            }
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


@lru_cache(maxsize=256)
def _base_issues(report_id: str) -> tuple[dict[str, Any], ...]:
    rows = [row for row in repository.results() if row.get("report_id") == report_id]
    by_id = {str(row.get("indicator_id", "")): row for row in rows}
    issues: list[dict[str, Any]] = []

    for row in rows:
        if row.get("status") != "found":
            continue
        indicator_id = str(row.get("indicator_id", ""))
        indicator_name = str(row.get("indicator_name", ""))
        evidence = _evidence_item(row, "声明与原文")
        if not row.get("evidence_quote") or not row.get("block_id"):
            issues.append(
                _issue(
                    report_id,
                    "evidence_integrity",
                    "blocking",
                    "声明缺少可回溯证据",
                    f"{indicator_name} 已产生结构化结果，但缺少 evidence_quote 或 block_id，无法形成预审底稿。",
                    [indicator_id],
                    [indicator_name],
                    [evidence],
                )
            )
            continue

        if row.get("indicator_type") == "quantitative" and (
            not str(row.get("value", "")).strip()
            or not str(row.get("unit", "")).strip()
            or _truthy(row.get("quantitative_incomplete"))
        ):
            issues.append(
                _issue(
                    report_id,
                    "field_completeness",
                    "important",
                    "定量声明字段不完整",
                    f"{indicator_name}的数值或单位不完整，当前声明不能用于跨页或总分关系核验。",
                    [indicator_id],
                    [indicator_name],
                    [evidence],
                )
            )
        elif row.get("indicator_type") == "quantitative" and not _value_visible(row.get("value", ""), row.get("evidence_quote", "")):
            issues.append(
                _issue(
                    report_id,
                    "claim_evidence_mismatch",
                    "blocking",
                    "结构化数值无法在证据中定位",
                    f"{indicator_name}的结构化值为 {row.get('value')} {row.get('unit', '')}，但当前证据片段中没有同一数值。",
                    [indicator_id],
                    [indicator_name],
                    [evidence],
                )
            )

        issue_type = str(row.get("suspected_issue_type", ""))
        risk_level = str(row.get("risk_level", ""))
        if issue_type and issue_type not in {"normal_sample", "value_unit_missing"} and risk_level in {"high", "medium", "low"}:
            issues.append(
                _issue(
                    report_id,
                    f"diagnostic_{issue_type}",
                    "important" if risk_level == "high" else "attention",
                    ISSUE_TEXT.get(issue_type, "抽取结构需要人工核验"),
                    f"规则发现“{indicator_name}”的声明结构与证据语义可能失配；请回到原文确认指标对象、单位和统计口径。",
                    [indicator_id],
                    [indicator_name],
                    [evidence],
                )
            )

    for spec in CONSTRAINTS:
        keys = (spec["total"], *spec["parts"])
        constraint_rows = [by_id.get(key, {}) for key in keys]
        if not all(row.get("status") == "found" for row in constraint_rows):
            continue
        normalized = [_normalized_mass(row.get("value", ""), row.get("unit", "")) for row in constraint_rows]
        if any(value is None for value in normalized):
            continue
        total = float(normalized[0])
        part_sum = sum(float(value) for value in normalized[1:])
        relative_gap = abs(total - part_sum) / max(abs(total), 1e-9)
        if relative_gap <= float(spec["tolerance"]):
            continue
        display = f"{total:,.4g} - ({' + '.join(f'{float(value):,.4g}' for value in normalized[1:])}) = {total - part_sum:,.4g} 吨；相对差异 {relative_gap:.1%}"
        issues.append(
            _issue(
                report_id,
                f"constraint_{spec['id']}",
                "important",
                str(spec["title"]),
                "同一报告中的总量与分项在单位归一化后超出容差。由于当前声明尚未完整抽取主体、期间和 scope，系统只生成口径差异候选，不直接认定错误。",
                list(keys),
                [str(row.get("indicator_name", "")) for row in constraint_rows],
                [_evidence_item(row, "总量" if index == 0 else f"分项 {index}") for index, row in enumerate(constraint_rows)],
                calculation={
                    "formula": spec["formula"],
                    "display": display,
                    "relative_gap": round(relative_gap, 6),
                    "tolerance": spec["tolerance"],
                    "verdict": "exceeds_tolerance",
                },
            )
        )

    for indicator_id in STANDARD_REQUIREMENTS:
        requirement = _standard_requirement(report_id, indicator_id)
        if not requirement:
            continue
        row = by_id.get(indicator_id)
        if not row or row.get("status") != "missing":
            continue
        indicator_name = str(row.get("indicator_name", indicator_id))
        issues.append(
            _issue(
                report_id,
                "standard_explanation_gap",
                "attention",
                f"未找到“{requirement['topic']}”披露或省略说明",
                "系统在当前指标证据范围内未找到披露。该结果只是适用性核验入口，不代表违规；请确认公司板块、行业和不适用说明。",
                [indicator_id],
                [indicator_name],
                [],
                requirement=requirement,
            )
        )

    deduplicated: dict[str, dict[str, Any]] = {}
    for issue in issues:
        deduplicated[issue["issue_id"]] = issue
    return tuple(deduplicated.values())


def _issue(
    report_id: str,
    issue_type: str,
    severity: str,
    title: str,
    finding: str,
    indicator_ids: list[str],
    indicator_names: list[str],
    evidence: list[dict[str, Any]],
    calculation: dict[str, Any] | None = None,
    requirement: dict[str, str] | None = None,
) -> dict[str, Any]:
    stable_key = "|".join([report_id, issue_type, *sorted(indicator_ids)])
    issue_id = "issue-" + hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:16]
    return {
        "issue_id": issue_id,
        "report_id": report_id,
        "issue_type": issue_type,
        "severity": severity,
        "severity_label": {"blocking": "阻断", "important": "重要", "attention": "提示"}[severity],
        "title": title,
        "finding": finding,
        "indicator_ids": indicator_ids,
        "indicator_names": indicator_names,
        "evidence": evidence,
        "calculation": calculation or {},
        "requirement": requirement or {},
    }


def _evidence_item(row: dict[str, Any], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "indicator_id": row.get("indicator_id", ""),
        "indicator_name": row.get("indicator_name", ""),
        "value": row.get("value", ""),
        "unit": row.get("unit", ""),
        "quote": row.get("evidence_quote", ""),
        "page_no": row.get("page_no", ""),
        "block_id": row.get("block_id", ""),
        "block_type": row.get("block_type", ""),
    }


def _value_visible(value: Any, evidence: Any) -> bool:
    normalized_value = re.sub(r"[\s,，]", "", str(value or ""))
    normalized_evidence = re.sub(r"[\s,，]", "", str(evidence or ""))
    if not normalized_value or normalized_value.lower() in {"true", "false"}:
        return True
    return normalized_value in normalized_evidence


def _normalized_mass(value: Any, unit: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("，", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    unit_text = f"{value} {unit}".lower().replace(" ", "")
    if "万吨" in unit_text:
        return number * 10000
    if any(token in unit_text for token in ("千克", "公斤", "kg")):
        return number / 1000
    if any(token in unit_text for token in ("吨", "tco2e", "tco₂e")):
        return number
    return None


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _standard_requirement(report_id: str, indicator_id: str) -> dict[str, str] | None:
    stock_code = report_id.split("_", 1)[0]
    if not stock_code.startswith("6"):
        return None
    return STANDARD_REQUIREMENTS.get(indicator_id)
