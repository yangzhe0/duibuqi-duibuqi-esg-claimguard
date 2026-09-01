#!/usr/bin/env python3
"""Apply the four evidence-backed DATA-001 board-diversity corrections.

This is a deterministic data correction over the frozen extraction results.  It
does not invoke MinerU or Qwen, and does not regenerate the frozen correction records.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "outputs/final_results"
REVIEWER = "codex-independent-audit-data-001"

SPECS = {
    "002011_盾安环境_2025_ESG报告": {
        "value": "2",
        "unit": "人",
        "qualitative_text": "2025年女性董事人数为2人。",
        "evidence_quote": "女性 | 人 | 2 | 0 | 0",
        "page_no": "8",
        "block_id": "002011_盾安环境_2025_ESG报告:p8:b9",
        "block_type": "table",
        "value_origin": "direct",
        "unit_origin": "direct",
        "derivation_method": "",
        "derivation_expression": "",
        "derivation_inputs_json": "",
        "reason": "canonical 2025 gender table directly reports 女性=2人; replaces weaker percentage evidence and inferred provenance",
        "method": "canonical_table_direct_read",
    },
    "603918_金桥信息_2025_ESG报告": {
        "value": "1",
        "unit": "人",
        "qualitative_text": "2025年女性董事人数为1人。",
        "evidence_quote": "女性董事人数 | 人 | 1",
        "page_no": "38",
        "block_id": "603918_金桥信息_2025_ESG报告:p38:b1",
        "block_type": "table",
        "value_origin": "direct",
        "unit_origin": "direct",
        "derivation_method": "",
        "derivation_expression": "",
        "derivation_inputs_json": "",
        "reason": "canonical governance performance table directly reports 女性董事人数=1人; replaces non-quantitative background evidence",
        "method": "canonical_table_direct_read",
    },
    "603990_麦迪科技_2025_ESG报告": {
        "value": "1",
        "unit": "人",
        "qualitative_text": "2025年女性董事人数为1人。",
        "evidence_quote": "女性 | 人 | 0 | 1",
        "page_no": "47",
        "block_id": "603990_麦迪科技_2025_ESG报告:p47:b1",
        "block_type": "table",
        "value_origin": "direct",
        "unit_origin": "direct",
        "derivation_method": "",
        "derivation_expression": "",
        "derivation_inputs_json": "",
        "reason": "canonical 2024/2025 governance table directly reports the 2025 female-director value as 1人; replaces truncated paragraph evidence",
        "method": "canonical_table_direct_read",
    },
    "02651_大众口腔_2025_ESG报告": {
        "value": "3",
        "unit": "名",
        "qualitative_text": "截至报告期末，公司董事会包含三位女性董事。",
        "evidence_quote": "截至報告期末，公司董事會由七名董事構成，其中包含三位獨立董事、三位女性董事及一位職工代表董事。",
        "page_no": "13",
        "block_id": "02651_大众口腔_2025_ESG报告:p13:b5",
        "block_type": "paragraph",
        "value_origin": "derived",
        "unit_origin": "direct",
        "derivation_method": "chinese_numeral_normalization",
        "derivation_expression": "三位女性董事 -> 3名女性董事",
        "derivation_inputs_json": json.dumps(
            {"source_token": "三", "normalized_value": "3", "entity": "女性董事", "source_unit": "位", "output_unit": "名"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "reason": "the prior value 7 was total board size; the same canonical sentence states 三位女性董事, normalized deterministically to 3名",
        "method": "canonical_paragraph_chinese_numeral_normalization",
    },
}

RESULT_UPDATE_FIELDS = (
    "value",
    "unit",
    "qualitative_text",
    "evidence_quote",
    "page_no",
    "block_id",
    "block_type",
    "value_origin",
    "unit_origin",
    "derivation_method",
    "derivation_expression",
    "derivation_inputs_json",
)

AUDIT_FIELDS = (
    "report_id",
    "indicator_id",
    "reviewed_at",
    "reviewer",
    "correction_reason",
    "correction_method",
    "canonical_page_no",
    "canonical_block_id",
    "canonical_block_type",
    "canonical_quote",
    "before_value",
    "before_unit",
    "before_evidence_quote",
    "before_page_no",
    "before_block_id",
    "before_block_type",
    "before_value_origin",
    "before_unit_origin",
    "before_derivation_method",
    "before_derivation_expression",
    "before_derivation_inputs_json",
    "after_value",
    "after_unit",
    "after_evidence_quote",
    "after_page_no",
    "after_block_id",
    "after_block_type",
    "after_value_origin",
    "after_unit_origin",
    "after_derivation_method",
    "after_derivation_expression",
    "after_derivation_inputs_json",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | tuple[str, ...]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--reviewed-at", default=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    results_csv = root / "extraction/extraction_results.csv"
    results_json = root / "extraction/extraction_results.json"
    rows = read_csv(results_csv)
    fields = list(rows[0])
    found: set[str] = set()
    audits: list[dict[str, str]] = []

    for row in rows:
        spec = SPECS.get(row.get("report_id", ""))
        if spec is None or row.get("indicator_id") != "g_board_diversity":
            continue
        report_id = row["report_id"]
        if report_id in found:
            raise RuntimeError(f"duplicate DATA-001 target: {report_id}")
        before = dict(row)
        row.update({field: str(spec[field]) for field in RESULT_UPDATE_FIELDS})
        row.update(
            {
                "status": "found",
                "postprocess_repaired": "true",
                "quantitative_incomplete": "false",
                "repair_method": str(spec["method"]),
                "repair_reason": str(spec["reason"]),
                "llm_reason": "DATA-001 independent audit correction from frozen canonical evidence.",
            }
        )
        audit = {
            "report_id": report_id,
            "indicator_id": "g_board_diversity",
            "reviewed_at": args.reviewed_at,
            "reviewer": REVIEWER,
            "correction_reason": str(spec["reason"]),
            "correction_method": str(spec["method"]),
            "canonical_page_no": str(spec["page_no"]),
            "canonical_block_id": str(spec["block_id"]),
            "canonical_block_type": str(spec["block_type"]),
            "canonical_quote": str(spec["evidence_quote"]),
        }
        for prefix, source in (("before", before), ("after", row)):
            for field in (
                "value", "unit", "evidence_quote", "page_no", "block_id", "block_type",
                "value_origin", "unit_origin", "derivation_method", "derivation_expression", "derivation_inputs_json",
            ):
                audit[f"{prefix}_{field}"] = str(source.get(field, ""))
        audits.append(audit)
        found.add(report_id)

    if found != set(SPECS):
        raise RuntimeError(f"DATA-001 target mismatch: found={sorted(found)}, expected={sorted(SPECS)}")
    audits.sort(key=lambda row: row["report_id"])
    write_csv(results_csv, rows, fields)
    write_json(results_json, rows)
    write_csv(root / "extraction/audit_corrections.csv", audits, AUDIT_FIELDS)
    write_json(
        root / "extraction/audit_corrections.json",
        {
            "schema_version": "esg-claimguard-audit-corrections-1",
            "issue_id": "DATA-001",
            "correction_count": len(audits),
            "reviewer": REVIEWER,
            "reviewed_at": args.reviewed_at,
            "source_policy": "frozen canonical content_list_v2 evidence only; no model or parser rerun",
            "corrections": audits,
        },
    )
    print(json.dumps({"issue_id": "DATA-001", "corrected": sorted(found), "reviewed_at": args.reviewed_at}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
