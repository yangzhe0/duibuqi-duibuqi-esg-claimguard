from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = PROJECT_ROOT / "outputs/formal_v2/llm_200/extraction_results.csv"
TASK_RESULTS_ROOT = PROJECT_ROOT / "outputs/dashboard/tasks"
METRICS_PATH = PROJECT_ROOT / "outputs/review/quality_metrics.json"
RISK_CASES_PATH = PROJECT_ROOT / "outputs/review/risk_cases.csv"
PARSED_ROOT = PROJECT_ROOT / "data/parsed_reports_v1/reports"
PDF_ROOT = PROJECT_ROOT / "data/raw_pdfs"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> Any:
    if not path.exists() or not path.stat().st_size:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def results() -> list[dict[str, Any]]:
    risk_by_key = {
        (row.get("report_id", ""), row.get("indicator_id", "")): row
        for row in _read_csv(RISK_CASES_PATH)
    }
    enriched: list[dict[str, Any]] = []
    paths = [RESULTS_PATH, *sorted(TASK_RESULTS_ROOT.glob("*/extraction/extraction_results.csv"))]
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for path in paths:
        for row in _read_csv(path):
            merged[(row.get("report_id", ""), row.get("indicator_id", ""))] = row
    for row in merged.values():
        item: dict[str, Any] = dict(row)
        risk = risk_by_key.get((row.get("report_id", ""), row.get("indicator_id", "")), {})
        item["risk_tag"] = risk.get("risk_tag", "normal")
        item["risk_level"] = risk.get("risk_level", "")
        item["risk_reason"] = risk.get("risk_reason", "")
        item["suspected_issue_type"] = risk.get("suspected_issue_type", "normal_sample")
        enriched.append(item)
    return enriched


def clear_caches() -> None:
    results.cache_clear()
    quality_metrics.cache_clear()
    report_index.cache_clear()
    indicator_index.cache_clear()


@lru_cache(maxsize=1)
def quality_metrics() -> dict[str, Any]:
    return _read_json(METRICS_PATH)


@lru_cache(maxsize=1)
def report_index() -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results():
        grouped.setdefault(row["report_id"], []).append(row)
    output = []
    for report_id, rows in sorted(grouped.items()):
        pdf = PDF_ROOT / f"{report_id}.pdf"
        output.append(
            {
                "report_id": report_id,
                "found_count": sum(row["status"] == "found" for row in rows),
                "missing_count": sum(row["status"] == "missing" for row in rows),
                "risk_count": sum(row.get("risk_tag") not in ("", "normal") for row in rows),
                "has_pdf": pdf.is_file(),
            }
        )
    return output


@lru_cache(maxsize=1)
def indicator_index() -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results():
        grouped.setdefault(row["indicator_id"], []).append(row)
    output = []
    for indicator_id, rows in sorted(grouped.items()):
        first = rows[0]
        found = sum(row["status"] == "found" for row in rows)
        output.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": first["indicator_name"],
                "dimension": first["dimension"],
                "indicator_type": first["indicator_type"],
                "found_count": found,
                "found_rate": round(found / len(rows), 4),
            }
        )
    return output


def summary() -> dict[str, Any]:
    rows = results()
    status = Counter(row["status"] for row in rows)
    dimension = Counter(row["dimension"] for row in rows if row["status"] == "found")
    indicator_type = Counter(row["indicator_type"] for row in rows if row["status"] == "found")
    metrics = quality_metrics()
    model_rows = [row for row in rows if _safe_int(row.get("source_candidate_count"), 0) > 0]
    elapsed = [_safe_float(row.get("elapsed_seconds"), 0.0) for row in model_rows]
    return {
        "report_count": len(report_index()),
        "indicator_count": len(indicator_index()),
        "total_results": len(rows),
        "found_count": status["found"],
        "missing_count": status["missing"],
        "error_count": status["error"],
        "found_rate": round(status["found"] / len(rows), 4) if rows else 0,
        "risk_count": metrics.get("concrete_risk_cases_count", 0),
        "dimension_found": dict(dimension),
        "type_found": dict(indicator_type),
        "model_call_count": len(model_rows),
        "avg_inference_seconds": round(sum(elapsed) / len(elapsed), 3) if elapsed else 0.0,
    }


def query_results(params: dict[str, str]) -> dict[str, Any]:
    rows = filtered_results(params)
    total = len(rows)
    offset = max(_safe_int(params.get("offset"), 0), 0)
    limit = min(max(_safe_int(params.get("limit"), 100), 1), 1000)
    return {"items": rows[offset : offset + limit], "total": total, "offset": offset, "limit": limit}


def filtered_results(params: dict[str, str]) -> list[dict[str, Any]]:
    rows = results()
    for key in ("report_id", "indicator_id", "dimension", "indicator_type", "status", "risk_level"):
        value = params.get(key, "").strip()
        if value:
            rows = [row for row in rows if str(row.get(key, "")) == value]
    search = params.get("search", "").strip().lower()
    if search:
        rows = [
            row
            for row in rows
            if search in " ".join(str(row.get(k, "")) for k in ("report_id", "indicator_name", "evidence_quote")).lower()
        ]
    return rows


def export_csv(params: dict[str, str]) -> bytes:
    rows = filtered_results(params)
    if not rows:
        return b""
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def result_detail(report_id: str, indicator_id: str) -> dict[str, Any] | None:
    return next(
        (row for row in results() if row["report_id"] == report_id and row["indicator_id"] == indicator_id),
        None,
    )


def pdf_path(report_id: str) -> Path | None:
    if not _valid_report_id(report_id):
        return None
    path = PDF_ROOT / f"{report_id}.pdf"
    return path if path.is_file() else None


def evidence(report_id: str, block_id: str) -> dict[str, Any] | None:
    if not _valid_report_id(report_id):
        return None
    match = re.fullmatch(r".+:p(\d+):b(\d+)", block_id)
    if not match:
        return None
    page_no, block_index = map(int, match.groups())
    path = PARSED_ROOT / report_id / f"{report_id}_content_list_v2.json"
    if not path.is_file():
        return None
    pages = _read_json(path)
    if page_no < 1 or page_no > len(pages) or block_index < 0 or block_index >= len(pages[page_no - 1]):
        return None
    block = pages[page_no - 1][block_index]
    return {
        "report_id": report_id,
        "block_id": block_id,
        "page_no": page_no,
        "block_index": block_index,
        "block_type": block.get("type", ""),
        "bbox": block.get("bbox", []),
        "coordinate_space": [0, 0, 1000, 1000],
        "text": _block_text(block),
    }


def page_blocks(report_id: str, page_no: int) -> list[dict[str, Any]]:
    if not _valid_report_id(report_id):
        return []
    path = PARSED_ROOT / report_id / f"{report_id}_content_list_v2.json"
    if not path.is_file():
        return []
    pages = _read_json(path)
    if page_no < 1 or page_no > len(pages):
        return []
    return [
        {
            "block_id": f"{report_id}:p{page_no}:b{index}",
            "block_index": index,
            "block_type": block.get("type", ""),
            "bbox": block.get("bbox", []),
            "text": _block_text(block),
        }
        for index, block in enumerate(pages[page_no - 1])
    ]


def _block_text(block: dict[str, Any]) -> str:
    content = block.get("content", {})
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""
    chunks: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            chunks.append(re.sub(r"<[^>]+>", " ", value))
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(content)
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()[:1000]


def _valid_report_id(value: str) -> bool:
    return bool(value) and Path(value).name == value and "/" not in value and "\\" not in value


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _safe_float(value: str | None, default: float) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default
