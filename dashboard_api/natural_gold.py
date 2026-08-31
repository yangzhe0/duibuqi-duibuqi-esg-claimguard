from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dashboard_api import repository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_VERSION = "natural-gold-v1"
SAMPLING_SEED = "esg-claimguard-natural-gold-v1-20260809"
DEFAULT_SAMPLE_SIZE = 300
DEFAULT_DATASET_DIR = PROJECT_ROOT / "data/evaluation/natural_gold/v1"
MANIFEST_PATH = DEFAULT_DATASET_DIR / "manifest.csv"
METADATA_PATH = DEFAULT_DATASET_DIR / "dataset.json"

ROLES = {"annotator_a", "annotator_b", "adjudicator"}
DISCLOSURES = {"found", "missing", "uncertain"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
COMPARISON_FIELDS = (
    "disclosure",
    "subject",
    "period",
    "scope",
    "value",
    "unit",
    "evidence_pages",
    "evidence_text",
)
MANIFEST_FIELDS = (
    "sample_order",
    "task_id",
    "dataset_version",
    "report_id",
    "indicator_id",
    "indicator_name",
    "dimension",
    "indicator_type",
    "stratum",
    "pdf_path",
)


def build_manifest(
    output_dir: Path = DEFAULT_DATASET_DIR,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: str = SAMPLING_SEED,
) -> dict[str, Any]:
    """Build a deterministic, model-output-blind Natural-Gold manifest."""
    if sample_size < 3 or sample_size % 3:
        raise ValueError("sample_size must be divisible by 3 so E/S/G quotas are equal")
    report_items = repository.report_index()
    reports = [item["report_id"] for item in report_items if item.get("has_pdf")]
    if not reports:
        reports = [item["report_id"] for item in report_items]
    indicators = repository.indicator_index()
    if not reports or not indicators:
        raise ValueError("reports and indicators are required")

    by_dimension: dict[str, list[dict[str, Any]]] = {dimension: [] for dimension in "ESG"}
    for indicator in indicators:
        by_dimension.setdefault(str(indicator["dimension"]), []).append(indicator)
    dimension_quota = sample_size // 3
    rows: list[dict[str, str]] = []

    for dimension in "ESG":
        dimension_indicators = sorted(by_dimension.get(dimension, []), key=lambda item: item["indicator_id"])
        if not dimension_indicators:
            raise ValueError(f"no indicators for dimension {dimension}")
        base, remainder = divmod(dimension_quota, len(dimension_indicators))
        for indicator_index, indicator in enumerate(dimension_indicators):
            quota = base + (1 if indicator_index < remainder else 0)
            if quota > len(reports):
                raise ValueError(f"not enough reports for indicator {indicator['indicator_id']}")
            ranked_reports = sorted(
                reports,
                key=lambda report_id: _digest(seed, str(indicator["indicator_id"]), report_id),
            )
            for report_id in ranked_reports[:quota]:
                task_digest = _digest(DATASET_VERSION, report_id, str(indicator["indicator_id"]))[:14]
                rows.append(
                    {
                        "sample_order": "",
                        "task_id": f"ng1-{task_digest}",
                        "dataset_version": DATASET_VERSION,
                        "report_id": report_id,
                        "indicator_id": str(indicator["indicator_id"]),
                        "indicator_name": str(indicator["indicator_name"]),
                        "dimension": dimension,
                        "indicator_type": str(indicator["indicator_type"]),
                        "stratum": f"{dimension}/{indicator['indicator_type']}",
                        "pdf_path": f"data/raw_pdfs/{report_id}.pdf",
                    }
                )

    rows.sort(key=lambda item: _digest(seed, item["task_id"]))
    for index, row in enumerate(rows, start=1):
        row["sample_order"] = str(index)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    manifest_bytes = _manifest_csv(rows)
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    metadata = {
        "dataset_version": DATASET_VERSION,
        "manifest_state": "frozen",
        "manifest_sha256": manifest_sha256,
        "sample_size": len(rows),
        "sampling_seed": seed,
        "sampling_method": "equal E/S/G quota; equal allocation within every indicator; deterministic report hash ranking",
        "model_output_in_manifest": False,
        "roles": ["annotator_a", "annotator_b", "adjudicator"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "change_policy": "Do not overwrite after annotation starts; create a new version instead.",
    }
    (output_dir / "dataset.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"metadata": metadata, "rows": rows, "manifest_path": str(manifest_path)}


def load_manifest(path: Path = MANIFEST_PATH) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_metadata(path: Path = METADATA_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def validate_annotation(payload: dict[str, Any], task: dict[str, str], existing: list[dict[str, Any]]) -> dict[str, str]:
    role = str(payload.get("role", "")).strip()
    disclosure = str(payload.get("disclosure", "")).strip()
    confidence = str(payload.get("confidence", "medium")).strip()
    reviewer = str(payload.get("reviewer", "")).strip()
    if role not in ROLES:
        raise ValueError(f"invalid Natural-Gold role: {role}")
    if disclosure not in DISCLOSURES:
        raise ValueError(f"invalid disclosure label: {disclosure}")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"invalid confidence: {confidence}")
    if not reviewer:
        raise ValueError("reviewer is required")

    by_role = {row["role"]: row for row in existing}
    if role in {"annotator_a", "annotator_b"}:
        peer_role = "annotator_b" if role == "annotator_a" else "annotator_a"
        peer = by_role.get(peer_role)
        if peer and _normal(peer.get("reviewer", "")) == _normal(reviewer):
            raise ValueError("annotator A and annotator B must be different people")
    if role == "adjudicator":
        if not {"annotator_a", "annotator_b"}.issubset(by_role):
            raise ValueError("both independent annotations are required before adjudication")
        if not disagreement_fields(by_role["annotator_a"], by_role["annotator_b"]):
            raise ValueError("adjudication is only required when the two independent annotations disagree")
        peer_reviewers = {_normal(by_role[key].get("reviewer", "")) for key in ("annotator_a", "annotator_b")}
        if _normal(reviewer) in peer_reviewers:
            raise ValueError("the adjudicator must be different from both annotators")

    values = {
        "task_id": task["task_id"],
        "role": role,
        "disclosure": disclosure,
        "subject": str(payload.get("subject", "")).strip(),
        "period": str(payload.get("period", "")).strip(),
        "scope": str(payload.get("scope", "")).strip(),
        "value": str(payload.get("value", "")).strip(),
        "unit": str(payload.get("unit", "")).strip(),
        "evidence_pages": _normal_pages(str(payload.get("evidence_pages", ""))),
        "evidence_text": str(payload.get("evidence_text", "")).strip(),
        "confidence": confidence,
        "note": str(payload.get("note", "")).strip(),
        "reviewer": reviewer,
    }
    if disclosure == "found":
        if not values["evidence_pages"] or not values["evidence_text"]:
            raise ValueError("found labels require evidence_pages and evidence_text")
        if task.get("indicator_type") == "quantitative" and not values["value"]:
            raise ValueError("quantitative found labels require a value")
    if disclosure == "uncertain" and not values["note"]:
        raise ValueError("uncertain labels require a note")
    return values


def disagreement_fields(annotation_a: dict[str, Any], annotation_b: dict[str, Any]) -> list[str]:
    if annotation_a.get("disclosure") != annotation_b.get("disclosure"):
        return ["disclosure"]
    if annotation_a.get("disclosure") != "found":
        return []
    return [field for field in COMPARISON_FIELDS[1:] if _field_value(field, annotation_a) != _field_value(field, annotation_b)]


def natural_gold_summary(
    annotations: list[dict[str, Any]],
    manifest_rows: list[dict[str, str]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_rows = manifest_rows if manifest_rows is not None else load_manifest()
    metadata = metadata if metadata is not None else load_metadata()
    by_task = _annotations_by_task(annotations)
    role_counts = Counter(row["role"] for row in annotations if row.get("role") in ROLES)
    both_complete = 0
    agreements = 0
    disagreements = 0
    adjudicated = 0
    gold_count = 0
    disclosure_pairs: list[tuple[str, str]] = []

    for task in manifest_rows:
        roles = by_task.get(task["task_id"], {})
        a, b = roles.get("annotator_a"), roles.get("annotator_b")
        if not a or not b:
            continue
        both_complete += 1
        disclosure_pairs.append((a["disclosure"], b["disclosure"]))
        differs = bool(disagreement_fields(a, b))
        if differs:
            disagreements += 1
            if roles.get("adjudicator"):
                adjudicated += 1
                gold_count += 1
        else:
            agreements += 1
            gold_count += 1

    total = len(manifest_rows)
    dimension_counts = Counter(row.get("dimension", "") for row in manifest_rows)
    type_counts = Counter(row.get("indicator_type", "") for row in manifest_rows)
    return {
        "dataset_version": metadata.get("dataset_version", DATASET_VERSION),
        "manifest_state": metadata.get("manifest_state", "missing" if not manifest_rows else "unknown"),
        "manifest_sha256": metadata.get("manifest_sha256", ""),
        "total_tasks": total,
        "role_completed": {
            "annotator_a": role_counts["annotator_a"],
            "annotator_b": role_counts["annotator_b"],
            "adjudicator": role_counts["adjudicator"],
        },
        "both_complete": both_complete,
        "exact_agreements": agreements,
        "disagreements": disagreements,
        "pending_adjudication": max(disagreements - adjudicated, 0),
        "adjudicated": adjudicated,
        "gold_count": gold_count,
        "gold_progress": round(gold_count / total, 4) if total else 0.0,
        "disclosure_kappa": _cohen_kappa(disclosure_pairs),
        "ready_to_evaluate": bool(total) and gold_count == total,
        "metrics_status": "ready" if total and gold_count == total else "withheld_until_gold_complete",
        "sampling": {
            "dimensions": dict(dimension_counts),
            "indicator_types": dict(type_counts),
            "unique_reports": len({row.get("report_id", "") for row in manifest_rows}),
            "unique_indicators": len({row.get("indicator_id", "") for row in manifest_rows}),
            "model_output_blinded": True,
        },
        "note": "该独立评测组件不属于本次参赛交付范围；当前作品不报告模型 Precision、Recall 或 F1。",
    }


def natural_gold_tasks(
    annotations: list[dict[str, Any]],
    role: str,
    status: str = "all",
    manifest_rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"invalid Natural-Gold role: {role}")
    if status not in {"all", "pending", "completed", "waiting", "agreed", "disagreement", "adjudicated"}:
        raise ValueError(f"invalid Natural-Gold task status: {status}")
    manifest_rows = manifest_rows if manifest_rows is not None else load_manifest()
    by_task = _annotations_by_task(annotations)
    items: list[dict[str, Any]] = []

    for task in manifest_rows:
        roles = by_task.get(task["task_id"], {})
        own = roles.get(role)
        if role == "adjudicator":
            a, b = roles.get("annotator_a"), roles.get("annotator_b")
            if not a or not b:
                task_status = "waiting"
                differences: list[str] = []
            else:
                differences = disagreement_fields(a, b)
                task_status = "adjudicated" if own else "disagreement" if differences else "agreed"
        else:
            task_status = "completed" if own else "pending"
            differences = []
        if status != "all" and task_status != status:
            continue

        item: dict[str, Any] = {
            **task,
            "status": task_status,
            "annotation": own or {},
            "blinded": role != "adjudicator",
            "model_output_visible": False,
        }
        if role == "adjudicator":
            item["annotations"] = {
                "annotator_a": roles.get("annotator_a", {}),
                "annotator_b": roles.get("annotator_b", {}),
                "adjudicator": own or {},
            }
            item["disagreement_fields"] = differences
        items.append(item)
    return {"items": items, "total": len(items), "role": role, "status": status}


def natural_gold_evaluation(
    annotations: list[dict[str, Any]],
    manifest_rows: list[dict[str, str]] | None = None,
    prediction_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest_rows = manifest_rows if manifest_rows is not None else load_manifest()
    summary = natural_gold_summary(annotations, manifest_rows)
    if not summary["ready_to_evaluate"]:
        return {
            "status": "not_ready",
            "gold_count": summary["gold_count"],
            "required_count": summary["total_tasks"],
            "metrics": {},
            "note": summary["note"],
        }

    by_task = _annotations_by_task(annotations)
    predictions = {
        (row.get("report_id", ""), row.get("indicator_id", "")): row
        for row in (prediction_rows if prediction_rows is not None else repository.results())
    }
    gold_rows = []
    for task in manifest_rows:
        roles = by_task[task["task_id"]]
        a, b = roles["annotator_a"], roles["annotator_b"]
        gold = a if not disagreement_fields(a, b) else roles["adjudicator"]
        gold_rows.append((task, gold, predictions.get((task["report_id"], task["indicator_id"]), {})))

    eligible = [(task, gold, pred) for task, gold, pred in gold_rows if gold["disclosure"] != "uncertain"]
    tp = sum(gold["disclosure"] == "found" and pred.get("status") == "found" for _, gold, pred in eligible)
    fp = sum(gold["disclosure"] == "missing" and pred.get("status") == "found" for _, gold, pred in eligible)
    fn = sum(gold["disclosure"] == "found" and pred.get("status") != "found" for _, gold, pred in eligible)
    tn = sum(gold["disclosure"] == "missing" and pred.get("status") != "found" for _, gold, pred in eligible)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    found_gold = [(task, gold, pred) for task, gold, pred in eligible if gold["disclosure"] == "found"]
    quantitative = [(task, gold, pred) for task, gold, pred in found_gold if task["indicator_type"] == "quantitative"]
    metrics = {
        "disclosure_detection": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "n": len(eligible),
        },
        "value_exact_match": _mean_match(quantitative, "value", "value"),
        "unit_exact_match": _mean_match(quantitative, "unit", "unit"),
        "evidence_page_exact_match": _evidence_page_match(found_gold),
        "evidence_text_char_bigram_f1": _evidence_f1(found_gold),
        "unavailable_prediction_fields": ["subject", "period", "scope"],
    }
    return {
        "status": "ready",
        "gold_count": len(gold_rows),
        "required_count": len(manifest_rows),
        "metrics": metrics,
        "note": "Natural-Gold 与 ESG-Inject 必须分别报告；本结果只覆盖自然样本。",
    }


def export_manifest_csv(manifest_rows: list[dict[str, str]] | None = None) -> bytes:
    return _manifest_csv(manifest_rows if manifest_rows is not None else load_manifest())


def _manifest_csv(rows: Iterable[dict[str, str]]) -> bytes:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _annotations_by_task(annotations: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    for row in annotations:
        if row.get("role") in ROLES:
            output.setdefault(str(row.get("task_id", "")), {})[str(row["role"])] = row
    return output


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _normal(value: Any) -> str:
    return re.sub(r"[\s,，。；;：:]", "", str(value or "")).casefold()


def _normal_pages(value: str) -> str:
    if not value.strip():
        return ""
    parts = [part for part in re.split(r"[,，;；\s]+", value.strip()) if part]
    if not parts or any(not part.isdigit() or int(part) < 1 for part in parts):
        raise ValueError("evidence_pages must be positive page numbers separated by commas")
    return ",".join(str(number) for number in sorted({int(part) for part in parts}))


def _field_value(field: str, row: dict[str, Any]) -> str:
    if field == "evidence_pages":
        try:
            return _normal_pages(str(row.get(field, "")))
        except ValueError:
            return _normal(row.get(field, ""))
    return _normal(row.get(field, ""))


def _cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    labels = sorted(DISCLOSURES)
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    expected = sum((left_counts[label] / len(pairs)) * (right_counts[label] / len(pairs)) for label in labels)
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else 0.0
    return round((observed - expected) / (1 - expected), 4)


def _mean_match(rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]], gold_field: str, pred_field: str) -> dict[str, Any]:
    eligible = [(gold, pred) for _, gold, pred in rows if str(gold.get(gold_field, "")).strip()]
    matches = sum(_normal(gold.get(gold_field, "")) == _normal(pred.get(pred_field, "")) for gold, pred in eligible)
    return {"score": round(matches / len(eligible), 4) if eligible else None, "matches": matches, "n": len(eligible)}


def _evidence_page_match(rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    eligible = [(gold, pred) for _, gold, pred in rows if gold.get("evidence_pages")]
    matches = 0
    for gold, pred in eligible:
        pages = set(str(gold["evidence_pages"]).split(","))
        matches += str(pred.get("page_no", "")) in pages
    return {"score": round(matches / len(eligible), 4) if eligible else None, "matches": matches, "n": len(eligible)}


def _evidence_f1(rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    scores = []
    for _, gold, pred in rows:
        gold_grams = _char_bigrams(str(gold.get("evidence_text", "")))
        pred_grams = _char_bigrams(str(pred.get("evidence_quote", "")))
        if not gold_grams:
            continue
        overlap = len(gold_grams & pred_grams)
        precision = overlap / len(pred_grams) if pred_grams else 0.0
        recall = overlap / len(gold_grams)
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return {"score": round(sum(scores) / len(scores), 4) if scores else None, "n": len(scores)}


def _char_bigrams(value: str) -> set[str]:
    text = _normal(value)
    if len(text) < 2:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}
