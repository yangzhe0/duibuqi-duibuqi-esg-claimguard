#!/usr/bin/env python3
"""Make formal evidence quotes exact canonical substrings and record derivations.

This is a deterministic post-processing step.  It never calls MinerU or an LLM.
Existing quote characters are mapped back to the same canonical block while
restoring layout whitespace and punctuation that extraction normalization
removed.  Quantitative values not literally present in the quote are retained
only with explicit derivation metadata.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.esg_demo.blocks import flatten_report, load_content_list


RUN_ROOT = PROJECT_ROOT / "outputs/final_results"
RESULTS = RUN_ROOT / "extraction/extraction_results.csv"
AUDIT_CSV = RUN_ROOT / "extraction/evidence_hardening.csv"
AUDIT_JSON = RUN_ROOT / "extraction/evidence_hardening.json"
NEW_FIELDS = (
    "evidence_match_mode",
    "value_origin",
    "unit_origin",
    "derivation_method",
    "derivation_expression",
    "derivation_inputs_json",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _atomic_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    from io import StringIO

    buffer = StringIO(newline="")
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    _atomic_text(path, buffer.getvalue())


def _atomic_json(path: Path, payload: object) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _kept(character: str) -> bool:
    return bool(re.match(r"[\u4e00-\u9fffA-Za-z0-9.%％]", character))


def _compact(value: object) -> str:
    return "".join(character for character in str(value or "") if _kept(character))


def _exact_canonical_quote(quote: str, block_text: str) -> str:
    if quote and quote in block_text:
        return quote
    compact_quote = _compact(quote)
    compact_block_chars: list[str] = []
    raw_indexes: list[int] = []
    for index, character in enumerate(block_text):
        if _kept(character):
            compact_block_chars.append(character)
            raw_indexes.append(index)
    compact_block = "".join(compact_block_chars)
    offset = compact_block.find(compact_quote)
    if not compact_quote or offset < 0:
        raise ValueError("quote cannot be mapped back to its canonical block")
    start = raw_indexes[offset]
    end = raw_indexes[offset + len(compact_quote) - 1] + 1
    exact = block_text[start:end]
    if not exact or exact not in block_text or _compact(exact) != compact_quote:
        raise ValueError("canonical quote reconstruction failed")
    return exact


def _decimal(value: str) -> Decimal | None:
    text = str(value or "").replace(",", "").replace("，", "").strip()
    if text.endswith("%"):
        text = text[:-1]
    if "/" in text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _numeric_tokens(text: str) -> list[str]:
    return re.findall(r"-?\d+(?:[,.，]\d+)*(?:%)?", text or "")


def _value_is_literal(value: str, quote: str) -> bool:
    target = _decimal(value)
    if target is None:
        return str(value).strip() in quote
    return any(_decimal(token) == target for token in _numeric_tokens(quote) if _decimal(token) is not None)


def _derivation_method(row: dict[str, str], quote: str) -> str:
    indicator_id = row.get("indicator_id", "")
    reason = row.get("llm_reason", "")
    value = row.get("value", "")
    if _decimal(value) == 0 and any(term in quote for term in ("未发生", "未收到", "没有发生", "无投诉")):
        return "zero_event_normalization"
    if indicator_id == "g_independent_director_ratio" or "占比" in reason or "比例" in reason:
        return "ratio_from_disclosed_counts_or_fraction"
    if any(term in reason for term in ("求和", "加总", "相加", "合计", "总和", "统计")):
        return "aggregation_of_disclosed_components"
    if "万" in quote:
        return "unit_scale_normalization"
    return "deterministic_normalization_from_disclosed_evidence"


def _load_blocks(report_id: str) -> dict[str, dict]:
    path = RUN_ROOT / "parsed" / report_id / f"{report_id}_content_list_v2.json"
    return {
        str(block["block_id"]): block
        for block in flatten_report(report_id, path, load_content_list(path))
    }


def main() -> int:
    rows = _read_csv(RESULTS)
    if len(rows) != 13_000:
        raise ValueError(f"expected 13000 result rows, got {len(rows)}")
    original_fields = list(rows[0])
    fields = original_fields + [field for field in NEW_FIELDS if field not in original_fields]
    block_cache: dict[str, dict[str, dict]] = {}
    audit: list[dict[str, object]] = []
    reviewed_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        for field in NEW_FIELDS:
            row.setdefault(field, "")
        if row.get("status") != "found":
            continue
        report_id = row["report_id"]
        if report_id not in block_cache:
            block_cache[report_id] = _load_blocks(report_id)
        block = block_cache[report_id].get(row.get("block_id", ""))
        if block is None:
            raise ValueError(f"missing block for {report_id}/{row.get('indicator_id')}")
        block_text = str(block.get("text", ""))
        original_quote = row.get("evidence_quote", "")
        exact_quote = _exact_canonical_quote(original_quote, block_text)
        row["evidence_quote"] = exact_quote
        row["evidence_match_mode"] = "exact_raw_substring"
        if row.get("indicator_type") == "quantitative":
            literal = _value_is_literal(row.get("value", ""), exact_quote)
            unit_literal = _compact(row.get("unit", "")) in _compact(exact_quote)
            row["value_origin"] = "direct" if literal else "derived"
            row["unit_origin"] = "direct" if unit_literal else "normalized_or_inferred"
            if not literal:
                row["derivation_method"] = _derivation_method(row, exact_quote)
                row["derivation_expression"] = row.get("llm_reason", "").strip()
                row["derivation_inputs_json"] = json.dumps(
                    {"numeric_tokens": _numeric_tokens(exact_quote), "evidence_quote": exact_quote},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        if exact_quote != original_quote or row.get("value_origin") == "derived" or row.get("unit_origin") == "normalized_or_inferred":
            audit.append(
                {
                    "report_id": report_id,
                    "indicator_id": row.get("indicator_id", ""),
                    "quote_changed": exact_quote != original_quote,
                    "original_evidence_quote": original_quote,
                    "final_evidence_quote": exact_quote,
                    "value_origin": row.get("value_origin", ""),
                    "unit_origin": row.get("unit_origin", ""),
                    "derivation_method": row.get("derivation_method", ""),
                    "derivation_expression": row.get("derivation_expression", ""),
                    "derivation_inputs_json": row.get("derivation_inputs_json", ""),
                    "review_kind": "deterministic_canonical_hardening",
                    "reviewed_at": reviewed_at,
                }
            )
    if any(row["status"] == "found" and row["evidence_quote"] not in block_cache[row["report_id"]][row["block_id"]]["text"] for row in rows):
        raise ValueError("strict evidence invariant failed after hardening")
    _atomic_csv(RESULTS, rows, fields)
    _atomic_json(RUN_ROOT / "extraction/extraction_results.json", rows)
    audit_fields = list(audit[0]) if audit else []
    _atomic_csv(AUDIT_CSV, audit, audit_fields)
    _atomic_json(AUDIT_JSON, audit)
    print(json.dumps({"rows": len(rows), "audit_rows": len(audit), "quote_changes": sum(bool(x["quote_changed"]) for x in audit), "derived_values": sum(x["value_origin"] == "derived" for x in audit)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
