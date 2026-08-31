#!/usr/bin/env python3
"""Make the accepted formal run self-contained under its current run root."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36"
HISTORICAL_SOURCE_POOL = PROJECT_ROOT / "outputs/formal_v2/indicator_pool_v2.csv"
FORMAL_COHORT_ID = "esg-claimguard-formal-200"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
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


def atomic_json(path: Path, payload: object) -> None:
    atomic_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def atomic_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    from io import StringIO

    buffer = StringIO(newline="")
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_bytes(path, buffer.getvalue().encode("utf-8"))


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    validation = json.loads((RUN_ROOT / "validation.json").read_text())
    complete = json.loads((RUN_ROOT / "COMPLETE.json").read_text())
    if validation.get("passed") is not True or complete.get("validation_passed") is not True:
        raise ValueError("formal run has not passed its completion gate")

    target_pool = RUN_ROOT / "indicator_pool.csv"
    source_pool = HISTORICAL_SOURCE_POOL if HISTORICAL_SOURCE_POOL.is_file() else target_pool
    source_pool_sha = sha256(source_pool)
    atomic_bytes(target_pool, source_pool.read_bytes())
    if sha256(target_pool) != source_pool_sha:
        raise ValueError("indicator pool changed during migration")

    input_rows = read_csv(RUN_ROOT / "input_manifest.csv")
    cohort_rows = []
    for row in input_rows:
        migrated = dict(row)
        migrated["cohort_id"] = FORMAL_COHORT_ID
        migrated["inclusion_reason"] = "frozen formal 200-report competition cohort"
        cohort_rows.append(migrated)
    cohort_fields = list(input_rows[0])
    atomic_csv(RUN_ROOT / "cohort_manifest.csv", cohort_rows, cohort_fields)
    cohort_json = {
        "schema_version": "esg-claimguard-cohort-1",
        "cohort_id": FORMAL_COHORT_ID,
        "report_count": len(cohort_rows),
        "page_count": sum(int(row["expected_pages"]) for row in cohort_rows),
        "indicator_count": 65,
        "expected_result_rows": 13_000,
        "reports": cohort_rows,
    }
    atomic_json(RUN_ROOT / "cohort_manifest.json", cohort_json)

    attempts = []
    promoted = set()
    for path in sorted((RUN_ROOT / "parse_attempts").glob("*/attempt.json")):
        payload = json.loads(path.read_text())
        log = RUN_ROOT / payload["log"] if not Path(payload["log"]).is_absolute() else Path(payload["log"])
        if not log.exists():
            log = PROJECT_ROOT / payload["log"]
        promoted.update(payload.get("promoted_report_ids", []))
        attempts.append(
            {
                "attempt_id": payload.get("attempt_id", path.parent.name),
                "status": payload.get("status", ""),
                "returncode": payload.get("returncode"),
                "started_at": payload.get("started_at", ""),
                "finished_at": payload.get("finished_at", ""),
                "elapsed_seconds": payload.get("elapsed_seconds"),
                "peak_gpu_mib": payload.get("peak_gpu_mib"),
                "report_count": len(payload.get("report_ids", [])),
                "promoted_report_count": len(payload.get("promoted_report_ids", [])),
                "attempt_json_sha256": sha256(path),
                "log_sha256": sha256(log) if log.is_file() else "",
            }
        )
    formal_reports = {row["report_id"] for row in cohort_rows}
    uncovered = sorted(formal_reports - promoted)
    attempt_summary = {
        "schema_version": "esg-claimguard-parse-attempt-summary-1",
        "generated_at": now,
        "attempt_count": len(attempts),
        "completed_attempts": sum(item["status"] == "completed" and item["returncode"] == 0 for item in attempts),
        "retained_attempt_report_coverage": len(formal_reports & promoted),
        "canonical_report_count": len(formal_reports),
        "canonical_without_retained_attempt_count": len(uncovered),
        "canonical_without_retained_attempt_ids": uncovered,
        "provenance_note": (
            "Canonical files and parser-manifest hashes validate all 200 reports; retained attempt directories "
            "cover 190 reports. No attempt record was fabricated for the remaining 10 reports."
        ),
        "attempts": attempts,
    }
    atomic_json(RUN_ROOT / "parser/parse_attempts_summary.json", attempt_summary)

    run_manifest_path = RUN_ROOT / "run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text())
    original_manifest_sha = sha256(run_manifest_path)
    original_indicator_path = run_manifest["indicator_pool"]["path"]
    run_manifest["cohort_id"] = FORMAL_COHORT_ID
    run_manifest["indicator_pool"] = {
        "path": "outputs/formal_v3_mineru25_qwen36/indicator_pool.csv",
        "sha256": source_pool_sha,
    }
    run_manifest["cohort_manifest"] = {
        "csv_path": "outputs/formal_v3_mineru25_qwen36/cohort_manifest.csv",
        "csv_sha256": sha256(RUN_ROOT / "cohort_manifest.csv"),
        "json_path": "outputs/formal_v3_mineru25_qwen36/cohort_manifest.json",
        "json_sha256": sha256(RUN_ROOT / "cohort_manifest.json"),
    }
    run_manifest["historical_input_provenance"] = {
        "source_report_list": run_manifest.pop("source_report_list", ""),
        "indicator_pool_path": original_indicator_path,
        "original_run_manifest_sha256": original_manifest_sha,
    }
    atomic_json(run_manifest_path, run_manifest)

    migration = {
        "schema_version": "esg-claimguard-formal-migration-1",
        "migrated_at": now,
        "executor": "codex",
        "run_id": complete["run_id"],
        "source": {
            "indicator_pool_path": "outputs/formal_v2/indicator_pool_v2.csv",
            "indicator_pool_sha256": source_pool_sha,
            "original_run_manifest_sha256": original_manifest_sha,
            "pre_hardening_checksums_path": "provenance/pre_hardening_checksums.sha256",
            "pre_hardening_checksums_sha256": sha256(RUN_ROOT / "provenance/pre_hardening_checksums.sha256"),
        },
        "destination": {
            "formal_root": "outputs/formal_v3_mineru25_qwen36",
            "indicator_pool_path": "outputs/formal_v3_mineru25_qwen36/indicator_pool.csv",
            "indicator_pool_sha256": sha256(target_pool),
            "cohort_manifest_csv_sha256": sha256(RUN_ROOT / "cohort_manifest.csv"),
            "cohort_manifest_json_sha256": sha256(RUN_ROOT / "cohort_manifest.json"),
            "parse_attempts_summary_sha256": sha256(RUN_ROOT / "parser/parse_attempts_summary.json"),
        },
        "hardening": {
            "strict_quote_contract": True,
            "evidence_hardening_csv_sha256": sha256(RUN_ROOT / "extraction/evidence_hardening.csv"),
            "evidence_hardening_json_sha256": sha256(RUN_ROOT / "extraction/evidence_hardening.json"),
        },
        "deletion_status": "pending_consumer_migration_and_tests",
        "planned_deletions": ["outputs/formal_v2", "data/parsed_reports_v1", "parse_attempts"],
    }
    atomic_json(RUN_ROOT / "provenance/migration.json", migration)
    print(json.dumps({"indicator_pool_sha256": source_pool_sha, "reports": len(cohort_rows), "pages": cohort_json["page_count"], "attempts": len(attempts), "retained_attempt_coverage": len(promoted), "uncovered": len(uncovered)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
