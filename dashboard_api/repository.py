from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36/extraction/extraction_results.csv"
# Kept as a compatibility constant for task management. Dashboard datasets must
# never discover or merge task outputs implicitly.
TASK_RESULTS_ROOT = PROJECT_ROOT / "outputs/dashboard/tasks"
METRICS_PATH = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36/validation.json"
RISK_CASES_PATH: Path | None = None
PARSED_ROOT = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36/parsed"
PDF_ROOT = PROJECT_ROOT / "data/raw_pdfs"
FORMAL_V3_ROOT = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36"

CURRENT_DATASET_ID = "formal_current"
DEFAULT_DATASET_ID = CURRENT_DATASET_ID


@dataclass(frozen=True)
class DatasetSnapshot:
    dataset_id: str
    run_id: str
    scope: str
    results_path: Path
    parsed_root: Path
    quality_path: Path | None = None
    risk_cases_path: Path | None = None
    completed_at: str = ""

    def metadata(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "run_id": self.run_id,
            "scope": self.scope,
            "completed_at": self.completed_at,
            "is_default": self.dataset_id == DEFAULT_DATASET_ID,
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> Any:
    if not path.exists() or not path.stat().st_size:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def dataset_snapshot(dataset_id: str = DEFAULT_DATASET_ID) -> DatasetSnapshot:
    selected = str(dataset_id or DEFAULT_DATASET_ID).strip()
    if selected != CURRENT_DATASET_ID:
        raise ValueError(f"unknown dataset_id: {selected}")

    complete = _read_json(FORMAL_V3_ROOT / "COMPLETE.json")
    validation = _read_json(FORMAL_V3_ROOT / "validation.json")
    manifest = _read_json(FORMAL_V3_ROOT / "run_manifest.json")
    results_path = FORMAL_V3_ROOT / "extraction/extraction_results.csv"
    run_id = str(complete.get("run_id", "")) if isinstance(complete, dict) else ""
    ready = (
        isinstance(complete, dict)
        and complete.get("validation_passed") is True
        and complete.get("is_full_200") is True
        and isinstance(validation, dict)
        and validation.get("passed") is True
        and isinstance(manifest, dict)
        and run_id
        and manifest.get("run_id") == run_id
        and results_path.is_file()
    )
    if not ready:
        raise ValueError(
            f"dataset_id {CURRENT_DATASET_ID} is unavailable until COMPLETE.json and validation.json both pass"
        )
    return DatasetSnapshot(
        dataset_id=CURRENT_DATASET_ID,
        run_id=run_id,
        scope=str(complete.get("scope_type", "full200")),
        results_path=results_path,
        parsed_root=FORMAL_V3_ROOT / "parsed",
        quality_path=FORMAL_V3_ROOT / "validation.json",
        completed_at=str(complete.get("completed_at", "")),
    )


def available_datasets() -> dict[str, Any]:
    items = []
    try:
        items.append(dataset_snapshot(CURRENT_DATASET_ID).metadata())
    except ValueError:
        pass
    return {"default_dataset_id": DEFAULT_DATASET_ID, "items": items, "total": len(items)}


def dataset_metadata(dataset_id: str = DEFAULT_DATASET_ID) -> dict[str, Any]:
    return dataset_snapshot(dataset_id).metadata()


@lru_cache(maxsize=4)
def results(dataset_id: str = DEFAULT_DATASET_ID) -> list[dict[str, Any]]:
    snapshot = dataset_snapshot(dataset_id)
    risk_by_key = {
        (row.get("report_id", ""), row.get("indicator_id", "")): row
        for row in (_read_csv(snapshot.risk_cases_path) if snapshot.risk_cases_path else [])
    }
    enriched: list[dict[str, Any]] = []
    for row in _read_csv(snapshot.results_path):
        item: dict[str, Any] = dict(row)
        risk = risk_by_key.get((row.get("report_id", ""), row.get("indicator_id", "")), {})
        item["risk_tag"] = risk.get("risk_tag", item.get("risk_tag", "normal"))
        item["risk_level"] = risk.get("risk_level", item.get("risk_level", ""))
        item["risk_reason"] = risk.get("risk_reason", item.get("risk_reason", ""))
        item["suspected_issue_type"] = risk.get(
            "suspected_issue_type", item.get("suspected_issue_type", "normal_sample")
        )
        item["dataset_id"] = snapshot.dataset_id
        item["run_id"] = snapshot.run_id
        item["dataset_scope"] = snapshot.scope
        enriched.append(item)
    return enriched


def clear_caches() -> None:
    results.cache_clear()
    quality_metrics.cache_clear()
    report_index.cache_clear()
    indicator_index.cache_clear()


@lru_cache(maxsize=4)
def quality_metrics(dataset_id: str = DEFAULT_DATASET_ID) -> dict[str, Any]:
    snapshot = dataset_snapshot(dataset_id)
    payload = _read_json(snapshot.quality_path) if snapshot.quality_path else {}
    if not isinstance(payload, dict):
        payload = {}
    return {**payload, **snapshot.metadata()}


@lru_cache(maxsize=4)
def report_index(dataset_id: str = DEFAULT_DATASET_ID) -> list[dict[str, Any]]:
    snapshot = dataset_snapshot(dataset_id)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results(dataset_id):
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
                **snapshot.metadata(),
            }
        )
    return output


@lru_cache(maxsize=4)
def indicator_index(dataset_id: str = DEFAULT_DATASET_ID) -> list[dict[str, Any]]:
    snapshot = dataset_snapshot(dataset_id)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results(dataset_id):
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
                **snapshot.metadata(),
            }
        )
    return output


def summary(dataset_id: str = DEFAULT_DATASET_ID) -> dict[str, Any]:
    snapshot = dataset_snapshot(dataset_id)
    rows = results(dataset_id)
    status = Counter(row["status"] for row in rows)
    dimension = Counter(row["dimension"] for row in rows if row["status"] == "found")
    indicator_type = Counter(row["indicator_type"] for row in rows if row["status"] == "found")
    metrics = quality_metrics(dataset_id)
    model_rows = [row for row in rows if _safe_int(row.get("source_candidate_count"), 0) > 0]
    elapsed = [_safe_float(row.get("elapsed_seconds"), 0.0) for row in model_rows]
    return {
        **snapshot.metadata(),
        "report_count": len(report_index(dataset_id)),
        "indicator_count": len(indicator_index(dataset_id)),
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
    snapshot = dataset_snapshot(params.get("dataset_id", DEFAULT_DATASET_ID))
    rows = filtered_results(params)
    total = len(rows)
    offset = max(_safe_int(params.get("offset"), 0), 0)
    limit = min(max(_safe_int(params.get("limit"), 100), 1), 1000)
    return {
        "items": rows[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
        **snapshot.metadata(),
    }


def filtered_results(params: dict[str, str]) -> list[dict[str, Any]]:
    rows = results(params.get("dataset_id", DEFAULT_DATASET_ID))
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


def result_detail(
    report_id: str,
    indicator_id: str,
    dataset_id: str = DEFAULT_DATASET_ID,
) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in results(dataset_id)
            if row["report_id"] == report_id and row["indicator_id"] == indicator_id
        ),
        None,
    )


def pdf_path(report_id: str) -> Path | None:
    if not _valid_report_id(report_id):
        return None
    path = PDF_ROOT / f"{report_id}.pdf"
    return path if path.is_file() else None


def evidence(
    report_id: str,
    block_id: str,
    dataset_id: str = DEFAULT_DATASET_ID,
) -> dict[str, Any] | None:
    if not _valid_report_id(report_id):
        return None
    match = re.fullmatch(r".+:p(\d+):b(\d+)", block_id)
    if not match:
        return None
    page_no, block_index = map(int, match.groups())
    snapshot = dataset_snapshot(dataset_id)
    path = snapshot.parsed_root / report_id / f"{report_id}_content_list_v2.json"
    if not path.is_file():
        return None
    pages = _read_json(path)
    if page_no < 1 or page_no > len(pages) or block_index < 0 or block_index >= len(pages[page_no - 1]):
        return None
    block = pages[page_no - 1][block_index]
    return {
        **snapshot.metadata(),
        "report_id": report_id,
        "block_id": block_id,
        "page_no": page_no,
        "block_index": block_index,
        "block_type": block.get("type", ""),
        "bbox": block.get("bbox", []),
        "coordinate_space": [0, 0, 1000, 1000],
        "text": _block_text(block),
    }


def page_blocks(
    report_id: str,
    page_no: int,
    dataset_id: str = DEFAULT_DATASET_ID,
) -> list[dict[str, Any]]:
    if not _valid_report_id(report_id):
        return []
    snapshot = dataset_snapshot(dataset_id)
    path = snapshot.parsed_root / report_id / f"{report_id}_content_list_v2.json"
    if not path.is_file():
        return []
    pages = _read_json(path)
    if page_no < 1 or page_no > len(pages):
        return []
    return [
        {
            **snapshot.metadata(),
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
