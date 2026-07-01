#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


FORMAL_V1_DIR = Path("outputs/formal_v1")
FORMAL_V2_DIR = Path("outputs/formal_v2")
BOOLEAN_INDICATORS = {
    "e_carbon_management",
    "e_climate_risk",
    "e_environmental_penalty",
    "e_biodiversity",
    "e_green_office",
    "s_data_security",
    "s_supplier",
    "s_human_rights",
    "g_esg_governance",
    "g_anti_corruption",
    "g_compliance_management",
    "g_risk_management",
    "g_business_ethics",
    "g_audit_committee",
    "g_party_building",
}
BOOLEAN_KEYWORD_ADDITIONS = {
    "e_carbon_management": ("碳排放管理机制", "碳排放管理制度", "节能降碳措施"),
    "e_climate_risk": ("气候风险管理机制", "气候风险管理体系", "气候风险应对措施"),
    "e_environmental_penalty": ("环境处罚记录", "环保处罚记录", "环境违法违规"),
    "e_biodiversity": ("生物多样性保护措施", "生态保护措施", "生态修复措施"),
    "e_green_office": ("绿色办公措施", "无纸化办公措施", "低碳办公措施"),
    "s_data_security": ("数据安全管理制度", "隐私保护机制", "信息安全管理体系"),
    "s_supplier": ("供应商管理制度", "供应商审核机制", "责任供应链管理"),
    "s_human_rights": ("人权保护政策", "禁止童工", "禁止强迫劳动"),
    "g_esg_governance": ("ESG治理架构", "ESG治理机制", "可持续发展治理架构"),
    "g_anti_corruption": ("反腐败机制", "反商业贿赂制度", "廉洁从业制度"),
    "g_compliance_management": ("合规管理体系", "合规管理制度", "合规风险管理"),
    "g_risk_management": ("风险管理体系", "风险管理机制", "内部控制体系"),
    "g_business_ethics": ("商业道德准则", "诚信经营制度", "职业道德规范"),
    "g_audit_committee": ("审计委员会职责", "审计委员会机制", "内部审计机制"),
    "g_party_building": ("党建工作机制", "党组织建设", "党建责任制"),
}
REVISE_KEEP_IDS = {
    "e_ghg_scope1",
    "e_ghg_scope2",
    "e_renewable_energy",
    "s_training",
    "g_materiality_assessment",
}
KEYWORD_REVISIONS = {
    "e_ghg_scope1": ("范围一排放|范围1排放|直接温室气体排放|直接排放量|吨二氧化碳当量|tCO2e", "删除“范围一/范围1”泛词，增加排放量和单位限定。"),
    "e_ghg_scope2": ("范围二排放|范围2排放|间接温室气体排放|外购电力排放|吨二氧化碳当量|tCO2e", "删除“范围二/范围2”泛词，增加排放来源和单位限定。"),
    "e_renewable_energy": ("可再生能源使用量|绿电使用量|绿色电力采购量|可再生能源占比|兆瓦时|MWh|千瓦时", "删除“清洁能源”泛词，增加使用量、占比和电量单位限定。"),
    "e_wastewater": ("废水排放量|污水排放量|废水排放总量|立方米|吨", "增加排放量和单位限定，减少“排水量”泛化误命中。"),
    "s_training": ("员工培训总时长|人均培训时长|培训人次|培训小时|培训覆盖人数", "删除单独“员工培训”泛词，增加时长、人次和人数限定。"),
    "s_social_insurance": ("社会保险覆盖|五险一金覆盖|社保缴纳|住房公积金缴纳|员工保障制度", "增加覆盖和缴纳限定，避免泛化福利段落误命中。"),
    "s_safety_training": ("安全培训次数|安全培训人次|安全教育培训|应急演练次数|安全生产培训小时", "增加次数、人次、小时等定量限定。"),
    "g_materiality_assessment": ("实质性议题评估|重要性议题评估|双重重要性评估|议题矩阵|重要性矩阵", "删除单独“实质性议题”泛词，增加评估和矩阵限定。"),
    "g_intellectual_property_protection": ("知识产权保护机制|知识产权管理制度|专利保护制度|商标保护制度", "增加机制和制度限定，改善上下文不足问题。"),
}


def build_formal_v2(
    project_root: Path,
    formal_v1_dir: Path = FORMAL_V1_DIR,
    formal_v2_dir: Path = FORMAL_V2_DIR,
) -> dict:
    v1 = project_root / formal_v1_dir
    v2 = project_root / formal_v2_dir
    v2.mkdir(parents=True, exist_ok=True)
    pruning = _read_csv(v1 / "indicator_pruning_suggestions.csv")
    pool = {row["indicator_id"]: row for row in _read_csv(v1 / "indicator_pool.csv")}
    metrics = {row["indicator_id"]: row for row in _read_csv(v1 / "quality_review_metrics.csv")}
    coverage_rows = _read_csv(v1 / "candidate_coverage.csv")
    coverage = _coverage_summary(coverage_rows)

    selected_ids = [row["indicator_id"] for row in pruning if row["decision"] == "keep"]
    for row in pruning:
        iid = row["indicator_id"]
        if row["decision"] == "revise_keywords" and iid in REVISE_KEEP_IDS:
            selected_ids.append(iid)
    selected_ids = selected_ids[:65]

    selected_rows = []
    revision_rows = []
    pruning_by_id = {row["indicator_id"]: row for row in pruning}
    for iid in selected_ids:
        source = pool[iid]
        prune = pruning_by_id[iid]
        metric = metrics.get(iid, {})
        original_keywords = source["keywords"]
        revised_keywords, revision_reason = _revised_keywords(iid, original_keywords)
        indicator_type = "boolean" if iid in BOOLEAN_INDICATORS else source["indicator_type"]
        row = {
            "indicator_id": iid,
            "indicator_name": source["indicator_name"],
            "dimension": source["dimension"],
            "indicator_type": indicator_type,
            "original_indicator_type": source["indicator_type"],
            "keywords": revised_keywords,
            "common_units": source.get("common_units", ""),
            "is_core": source.get("is_core", "True"),
            "source_decision": prune["decision"],
            "coverage_rate": prune["coverage_rate"],
            "usable_rate": prune["usable_rate"],
            "dominant_error_type": prune["dominant_error_type"],
            "selection_reason": _selection_reason(prune, metric, indicator_type),
            "original_keywords": original_keywords,
            "keyword_revision_reason": revision_reason,
        }
        selected_rows.append(row)
        if revised_keywords != original_keywords or prune["decision"] == "revise_keywords":
            revision_rows.append(
                {
                    "indicator_id": iid,
                    "indicator_name": source["indicator_name"],
                    "selected": "yes",
                    "source_decision": prune["decision"],
                    "dominant_error_type": prune["dominant_error_type"],
                    "original_keywords": original_keywords,
                    "revised_keywords": revised_keywords,
                    "revision_reason": revision_reason,
                }
            )

    for row in pruning:
        iid = row["indicator_id"]
        if row["decision"] == "revise_keywords" and iid not in selected_ids:
            source = pool[iid]
            revised_keywords, revision_reason = _revised_keywords(iid, source["keywords"])
            revision_rows.append(
                {
                    "indicator_id": iid,
                    "indicator_name": source["indicator_name"],
                    "selected": "no",
                    "source_decision": row["decision"],
                    "dominant_error_type": row["dominant_error_type"],
                    "original_keywords": source["keywords"],
                    "revised_keywords": revised_keywords,
                    "revision_reason": revision_reason + "；本轮未进入 formal_v2，需补充复核后再纳入。",
                }
            )

    _write_json(v2 / "indicator_pool_v2.json", selected_rows)
    _write_csv(v2 / "indicator_pool_v2.csv", selected_rows)
    _write_csv(v2 / "keyword_revision_log.csv", revision_rows)
    _write_report(v2 / "indicator_selection_report.md", selected_rows, pruning, revision_rows, coverage)
    return {
        "selected_count": len(selected_rows),
        "dimensions": sorted({row["dimension"] for row in selected_rows}),
        "indicator_types": sorted({row["indicator_type"] for row in selected_rows}),
        "revision_count": len(revision_rows),
    }


def _revised_keywords(indicator_id: str, original: str) -> tuple[str, str]:
    if indicator_id in KEYWORD_REVISIONS:
        return KEYWORD_REVISIONS[indicator_id]
    if indicator_id in BOOLEAN_INDICATORS:
        items = _split_pipe(original)
        for item in BOOLEAN_KEYWORD_ADDITIONS.get(indicator_id, ()):
            if item not in items:
                items.append(item)
        return "|".join(items), "boolean 指标增加与原指标绑定的机制、制度、措施类限定词，避免使用泛词。"
    return original, "未修改；formal_v1 辅助质检显示证据可用率较高。"


def _selection_reason(prune: dict, metric: dict, indicator_type: str) -> str:
    if prune["decision"] == "keep":
        if indicator_type == "boolean":
            return "formal_v1 建议 keep；该指标更适合判定机制/制度是否披露，formal_v2 转为 boolean。"
        return "formal_v1 建议 keep，证据可用率满足 formal_v2 要求。"
    return f"formal_v1 建议 revise_keywords；usable_rate={prune['usable_rate']}，通过最小关键词收窄后纳入小样本验证。"


def _coverage_summary(rows: list[dict]) -> Counter:
    summary = Counter()
    for row in rows:
        summary[row["status"]] += 1
    return summary


def _write_report(path: Path, selected: list[dict], pruning: list[dict], revisions: list[dict], coverage: Counter) -> None:
    decision_counts = Counter(row["source_decision"] for row in selected)
    dimension_counts = Counter(row["dimension"] for row in selected)
    type_counts = Counter(row["indicator_type"] for row in selected)
    all_decisions = Counter(row["decision"] for row in pruning)
    lines = [
        "# formal_v2 Indicator Selection Report",
        "",
        "本报告基于 formal_v1 `AI-assisted quality review` 和 `辅助质检预标注` 结果生成，不是人工 gold 标注。",
        "",
        "## Inputs",
        "",
        "- `outputs/formal_v1/indicator_pruning_suggestions.csv`",
        "- `outputs/formal_v1/indicator_pool.csv`",
        "- `outputs/formal_v1/quality_review_metrics.csv`",
        "- `outputs/formal_v1/candidate_coverage.csv`",
        "",
        "## Selection Summary",
        "",
        f"- formal_v1 决策分布：{dict(all_decisions)}",
        f"- formal_v1 候选覆盖分布：{dict(coverage)}",
        f"- formal_v2 指标数量：{len(selected)}",
        f"- 来源决策分布：{dict(decision_counts)}",
        f"- E/S/G 分布：{dict(dimension_counts)}",
        f"- indicator_type 分布：{dict(type_counts)}",
        f"- 关键词修订记录数：{len(revisions)}",
        "",
        "## Selection Policy",
        "",
        "- 默认保留 `decision=keep` 的指标。",
        "- 仅纳入少量 `revise_keywords` 且可通过关键词收窄修复的指标。",
        "- `need_more_review` 不进入 formal_v2；`drop` 不进入 formal_v2。",
        "- 部分机制、制度、管理类定性指标在 formal_v2 中转为 `boolean`，用于验证报告是否披露该机制或措施。",
        "",
        "## Next Step",
        "",
        "使用 `scripts/run_esg_formal_v2.py` 对 10-20 份报告运行 qwen3 小规模正式抽取，并根据 found 结果进行下一轮复核。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_json(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build formal_v2 ESG indicator pool from formal_v1 quality review outputs.")
    parser.add_argument("--formal-v1-dir", default=str(FORMAL_V1_DIR))
    parser.add_argument("--formal-v2-dir", default=str(FORMAL_V2_DIR))
    args = parser.parse_args()
    summary = build_formal_v2(Path("."), Path(args.formal_v1_dir), Path(args.formal_v2_dir))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
