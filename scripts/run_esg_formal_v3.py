#!/usr/bin/env python3
"""Reproduce or validate the formal 200-report MinerU2.5 + Qwen3.6 batch."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import heapq
import json
import os
import platform
import signal
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard_api.model_runtime import QWEN_ALIAS, llama_server_command, runtime_assets, qwen_runtime
from src.esg_demo.formal_extraction import _build_v2_prompt, _load_indicators, _normalize_v2_result, run_sample
from src.esg_demo.blocks import flatten_report, load_content_list
from src.esg_demo.extract import select_candidate_blocks
from src.esg_demo.ollama import build_llm_client


DEFAULT_ROOT = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36"
INDICATOR_POOL = DEFAULT_ROOT / "indicator_pool.csv"
RAW_ROOT = PROJECT_ROOT / "data/raw_pdfs"
_TASK_MINERU_BIN = Path.home() / ".conda/envs/mineru/bin/mineru"
MINERU_BIN = Path(
    os.environ.get(
        "ESG_MINERU_BIN",
        shutil.which("mineru") or (str(_TASK_MINERU_BIN) if _TASK_MINERU_BIN.is_file() else "mineru"),
    )
)
EXPECTED_REPORTS = 200
EXPECTED_INDICATORS = 65
EXPECTED_RESULTS = EXPECTED_REPORTS * EXPECTED_INDICATORS

DATA001_EXPECTED = {
    "002011_盾安环境_2025_ESG报告": {
        "value": "2", "unit": "人", "page_no": "8", "block_suffix": "p8:b9",
        "block_type": "table", "quote": "女性 | 人 | 2 | 0 | 0",
        "value_origin": "direct", "unit_origin": "direct",
        "before_value": "2", "before_page_no": "4", "before_block_suffix": "p4:b3",
    },
    "603918_金桥信息_2025_ESG报告": {
        "value": "1", "unit": "人", "page_no": "38", "block_suffix": "p38:b1",
        "block_type": "table", "quote": "女性董事人数 | 人 | 1",
        "value_origin": "direct", "unit_origin": "direct",
        "before_value": "1", "before_page_no": "12", "before_block_suffix": "p12:b1",
    },
    "603990_麦迪科技_2025_ESG报告": {
        "value": "1", "unit": "人", "page_no": "47", "block_suffix": "p47:b1",
        "block_type": "table", "quote": "女性 | 人 | 0 | 1",
        "value_origin": "direct", "unit_origin": "direct",
        "before_value": "1", "before_page_no": "15", "before_block_suffix": "p15:b3",
    },
    "02651_大众口腔_2025_ESG报告": {
        "value": "3", "unit": "名", "page_no": "13", "block_suffix": "p13:b5",
        "block_type": "paragraph",
        "quote": "截至報告期末，公司董事會由七名董事構成，其中包含三位獨立董事、三位女性董事及一位職工代表董事。",
        "value_origin": "derived", "unit_origin": "direct",
        "derivation_method": "chinese_numeral_normalization",
        "derivation_expression": "三位女性董事 -> 3名女性董事",
        "before_value": "7", "before_page_no": "13", "before_block_suffix": "p13:b5",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def atomic_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    names = fieldnames or (list(rows[0].keys()) if rows else [])
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_output_root(path: Path) -> Path:
    resolved = path.resolve()
    protected = [
        (PROJECT_ROOT / "data").resolve(),
        (PROJECT_ROOT / "outputs/ai_contest").resolve(),
    ]
    if resolved == PROJECT_ROOT.resolve() or any(resolved == item or item in resolved.parents for item in protected):
        raise ValueError(f"Refusing unsafe v3 output root: {resolved}")
    if PROJECT_ROOT.resolve() not in resolved.parents:
        raise ValueError(f"v3 output root must stay inside the project: {resolved}")
    return resolved


def _pdf_pages(path: Path) -> int:
    completed = subprocess.run(
        ["pdfinfo", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for line in completed.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"pdfinfo did not report page count: {path}")


def _mineru_version() -> str:
    completed = subprocess.run(
        [str(MINERU_BIN), "--version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.stdout.strip()


def _command_text(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.stdout.strip()


def _natural_gold_files() -> list[Path]:
    root = PROJECT_ROOT / "data/evaluation/natural_gold/v1"
    return sorted(path for path in root.rglob("*") if path.is_file())


def _file_hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path.relative_to(PROJECT_ROOT)): sha256(path) for path in paths}


def enrich_manifest(root: Path, manifest: dict) -> dict:
    """Upgrade the frozen manifest with provenance without changing its cohort."""
    created = str(manifest["created_at"]).replace("-", "").replace(":", "")
    run_id = manifest.get("run_id") or f"cg-{created[:15]}Z-full200-vlm25-qwen36"
    input_rows = [
        {
            "order": row["sequence"],
            "cohort_id": "esg-claimguard-formal-200",
            "report_id": row["report_id"],
            "pdf_path": row["pdf"],
            "pdf_sha256": row["pdf_sha256"],
            "pdf_size_bytes": row["pdf_size_bytes"],
            "expected_pages": row["pages"],
            "inclusion_reason": "frozen formal 200-report competition cohort",
        }
        for row in manifest["reports"]
    ]
    input_manifest = root / "input_manifest.csv"
    atomic_csv(input_manifest, input_rows)
    model_path = Path(str(manifest["extractor"]["runtime_assets"]["model"]["path"]))
    manifest.update(
        {
            "run_id": run_id,
            "state": manifest.get("state", "prepared"),
            "scope_type": "full200",
            "cohort_id": "esg-claimguard-formal-200",
            "is_full_200": True,
            "evaluation_kind": "engineering_run_not_accuracy_evaluation",
            "natural_gold_unlocked": False,
            "promotion": "not_promoted",
            "input_manifest": {
                "path": str(input_manifest.relative_to(PROJECT_ROOT)),
                "sha256": sha256(input_manifest),
            },
            "protected_input_hashes": manifest.get("protected_input_hashes")
            or {"natural_gold": _file_hashes(_natural_gold_files())},
            "source_control": manifest.get("source_control")
            or {
                "commit": _command_text(["git", "rev-parse", "HEAD"]),
                "dirty": bool(_command_text(["git", "status", "--porcelain=v1"])),
            },
            "hardware": manifest.get("hardware")
            or {
                "platform": platform.platform(),
                "gpu": _command_text(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,driver_version",
                        "--format=csv,noheader",
                    ]
                ),
            },
            "extraction_config": {
                "prompt_version": "formal-v2-evidence-only-20260822",
                "canonical_postprocess": "model-table-bbox-backfill-v1",
                "max_candidates": 5,
                "context_tokens": 8192,
                "max_output_tokens": 1024,
                "temperature": 0,
                "model_file": str(model_path),
                "model_size_bytes": model_path.stat().st_size,
            },
        }
    )
    config_payload = {
        "report_ids": [row["report_id"] for row in manifest["reports"]],
        "input_manifest_sha256": manifest["input_manifest"]["sha256"],
        "indicator_pool_sha256": manifest["indicator_pool"]["sha256"],
        "parser": manifest["parser"],
        "extractor_alias": manifest["extractor"]["alias"],
        "extraction_config": manifest["extraction_config"],
    }
    manifest["config_sha256"] = hashlib.sha256(
        json.dumps(config_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    atomic_json(root / "run_manifest.json", manifest)
    return manifest


def verify_protected_inputs(manifest: dict) -> None:
    if sha256(INDICATOR_POOL) != manifest["indicator_pool"]["sha256"]:
        raise RuntimeError("Indicator pool changed after the v3 cohort was frozen")
    expected = manifest["protected_input_hashes"]
    for group in ("natural_gold",):
        for relative, digest in expected.get(group, {}).items():
            path = PROJECT_ROOT / relative
            if "pilot30" in relative and not path.exists():
                continue
            if not path.is_file() or sha256(path) != digest:
                raise RuntimeError(f"Protected {group} input changed: {relative}")
    for row in manifest["reports"]:
        path = PROJECT_ROOT / row["pdf"]
        if (
            not path.is_file()
            or path.stat().st_size != row["pdf_size_bytes"]
            or sha256(path) != row["pdf_sha256"]
        ):
            raise RuntimeError(f"Frozen PDF missing or changed: {row['report_id']}")


def build_manifest(root: Path) -> dict:
    manifest_path = root / "run_manifest.json"
    if manifest_path.is_file():
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict) or len(manifest.get("reports", [])) != EXPECTED_REPORTS:
            raise RuntimeError("Existing v3 manifest is malformed or not a frozen 200-report manifest")
        return manifest

    cohort_path = DEFAULT_ROOT / "cohort_manifest.json"
    cohort = read_json(cohort_path)
    report_ids = [row["report_id"] for row in cohort.get("reports", [])] if isinstance(cohort, dict) else []
    if len(report_ids) != EXPECTED_REPORTS or len(set(report_ids)) != EXPECTED_REPORTS:
        raise RuntimeError("Self-contained cohort manifest is not an exact unique 200-report source list")
    reports = []
    for index, report_id in enumerate(report_ids, start=1):
        pdf = RAW_ROOT / f"{report_id}.pdf"
        if not pdf.is_file():
            raise FileNotFoundError(pdf)
        reports.append(
            {
                "sequence": index,
                "report_id": report_id,
                "pdf": str(pdf.relative_to(PROJECT_ROOT)),
                "pdf_size_bytes": pdf.stat().st_size,
                "pdf_sha256": sha256(pdf),
                "pages": _pdf_pages(pdf),
            }
        )
    assets = runtime_assets()
    missing_assets = [name for name, state in assets.items() if not state.get("ready") and name != "mmproj"]
    if missing_assets:
        raise RuntimeError("Missing Qwen runtime assets: " + ", ".join(missing_assets))
    manifest = {
        "schema_version": "formal-v3-run-manifest-1",
        "created_at": utc_now(),
        "source_report_list": str(cohort_path.relative_to(PROJECT_ROOT)),
        "report_count": EXPECTED_REPORTS,
        "page_count": sum(int(row["pages"]) for row in reports),
        "indicator_count": EXPECTED_INDICATORS,
        "expected_result_rows": EXPECTED_RESULTS,
        "parser": {
            "name": "MinerU2.5-Pro-2605-1.2B",
            "backend": "vlm-engine",
            "binary": str(MINERU_BIN),
            "version": _mineru_version(),
            "model_source": "modelscope",
        },
        "extractor": {
            "name": "Qwen3.6-27B-Q4_K_M",
            "alias": QWEN_ALIAS,
            "api": "openai",
            "runtime_assets": assets,
        },
        "indicator_pool": {
            "path": str(INDICATOR_POOL.relative_to(PROJECT_ROOT)),
            "sha256": sha256(INDICATOR_POOL),
        },
        "isolation_contract": {
            "write_root": str(root.relative_to(PROJECT_ROOT)),
            "protected": [
                "data/raw_pdfs",
                "data/evaluation/natural_gold_v1",
                "dashboard formal database",
            ],
        },
        "reports": reports,
    }
    atomic_json(manifest_path, manifest)
    return manifest


def canonical_json(root: Path, report_id: str) -> Path:
    return root / "parsed" / report_id / f"{report_id}_content_list_v2.json"


def content_page_count(path: Path) -> int:
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    return len(payload) if isinstance(payload, list) else 0


def valid_content_list(path: Path, expected_pages: int | None = None) -> bool:
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(payload, list) or not payload:
        return False
    if expected_pages is not None and len(payload) != expected_pages:
        return False
    if not all(isinstance(page, list) for page in payload):
        return False
    blocks = [block for page in payload for block in page]
    return bool(blocks) and all(isinstance(block, dict) for block in blocks)


def _gpu_used_mib() -> int:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=used_memory", "--format=csv,noheader,nounits"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return sum(int(line.strip()) for line in completed.stdout.splitlines() if line.strip().isdigit())
    except OSError:
        return 0


def _promote_outputs(root: Path, output_dir: Path, reports: list[dict]) -> list[str]:
    promoted = []
    for report in reports:
        report_id = str(report["report_id"])
        expected_pages = int(report["pages"])
        destination = canonical_json(root, report_id)
        if valid_content_list(destination, expected_pages):
            promoted.append(report_id)
            continue
        matches = [
            path
            for path in output_dir.rglob(f"{report_id}_content_list_v2.json")
            if valid_content_list(path, expected_pages)
        ]
        if len(matches) != 1:
            continue
        destination.parent.parent.mkdir(parents=True, exist_ok=True)
        if destination.parent.exists():
            quarantine_root = root / "quarantine/invalid_parsed"
            quarantine_root.mkdir(parents=True, exist_ok=True)
            quarantine = quarantine_root / f"{report_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
            destination.parent.replace(quarantine)
            atomic_json(
                quarantine / "QUARANTINE.json",
                {
                    "quarantined_at": utc_now(),
                    "report_id": report_id,
                    "reason": "canonical content list failed the frozen page/structure contract",
                },
            )
        temporary = destination.parent.parent / f".{report_id}.{uuid.uuid4().hex}.tmp"
        shutil.copytree(matches[0].parent, temporary)
        if not valid_content_list(temporary / matches[0].name, expected_pages):
            shutil.rmtree(temporary)
            continue
        temporary.replace(destination.parent)
        promoted.append(report_id)
    return promoted


def _run_parse_attempt(root: Path, reports: list[dict], label: str) -> dict:
    attempt_id = f"{label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    attempt_dir = root / "parse_attempts" / attempt_id
    input_dir = attempt_dir / "input"
    output_dir = attempt_dir / "output"
    input_dir.mkdir(parents=True)
    output_dir.mkdir()
    report_ids = [str(row["report_id"]) for row in reports]
    for row in reports:
        source = PROJECT_ROOT / str(row["pdf"])
        (input_dir / f"{row['report_id']}.pdf").symlink_to(source)
    command = [str(MINERU_BIN), "-p", str(input_dir), "-o", str(output_dir), "-b", "vlm-engine"]
    log_path = attempt_dir / "mineru.log"
    record = {
        "attempt_id": attempt_id,
        "started_at": utc_now(),
        "status": "running",
        "report_ids": report_ids,
        "command": command,
        "log": str(log_path.relative_to(PROJECT_ROOT)),
    }
    atomic_json(attempt_dir / "attempt.json", record)
    env = os.environ.copy()
    env["MINERU_MODEL_SOURCE"] = "modelscope"
    env["PATH"] = str(MINERU_BIN.parent) + os.pathsep + env.get("PATH", "")
    started = time.monotonic()
    peak_gpu_mib = 0
    process = None
    with log_path.open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            while process.poll() is None:
                peak_gpu_mib = max(peak_gpu_mib, _gpu_used_mib())
                time.sleep(1)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
    if process is None:
        raise RuntimeError("MinerU process did not start")
    promoted = _promote_outputs(root, output_dir, reports)
    record.update(
        {
            "finished_at": utc_now(),
            "status": "completed" if process.returncode == 0 and len(promoted) == len(report_ids) else "partial",
            "returncode": process.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "peak_gpu_mib": peak_gpu_mib,
            "promoted_report_ids": promoted,
            "missing_report_ids": sorted(set(report_ids) - set(promoted)),
        }
    )
    atomic_json(attempt_dir / "attempt.json", record)
    return record


def _parse_summary(root: Path, manifest: dict, attempts: list[dict]) -> dict:
    rows = manifest["reports"]
    completed = [
        row["report_id"]
        for row in rows
        if valid_content_list(canonical_json(root, row["report_id"]), int(row["pages"]))
    ]
    summary = {
        "updated_at": utc_now(),
        "backend": "vlm-engine",
        "model": "MinerU2.5-Pro-2605-1.2B",
        "expected_reports": len(rows),
        "completed_reports": len(completed),
        "completed_report_ids": completed,
        "pending_report_ids": [row["report_id"] for row in rows if row["report_id"] not in set(completed)],
        "attempts_this_run": [attempt["attempt_id"] for attempt in attempts],
    }
    atomic_json(root / "parse_summary.json", summary)
    return summary


def write_parser_manifest(root: Path, manifest: dict) -> list[dict]:
    rows = []
    for report in manifest["reports"]:
        path = canonical_json(root, report["report_id"])
        rows.append(
            {
                "report_id": report["report_id"],
                "pdf_sha256": report["pdf_sha256"],
                "pages": report["pages"],
                "parsed_json": str(path.relative_to(PROJECT_ROOT)),
                "parsed_sha256": sha256(path),
                "actual_pages": content_page_count(path),
                "parser_backend": "vlm-engine",
                "parser_model": "MinerU2.5-Pro-2605-1.2B",
            }
        )
    path = root / "parser/report_manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    temporary.replace(path)
    return rows


def recover_parse_attempts(root: Path, manifest: dict) -> list[str]:
    """Promote complete outputs left by an interrupted historical attempt."""
    report_lookup = {row["report_id"]: row for row in manifest["reports"]}
    recovered = []
    for attempt_path in sorted((root / "parse_attempts").glob("*/attempt.json")):
        try:
            attempt = read_json(attempt_path)
        except (OSError, json.JSONDecodeError):
            continue
        report_ids = [report_id for report_id in attempt.get("report_ids", []) if report_id in report_lookup]
        output_dir = attempt_path.parent / "output"
        if not output_dir.is_dir() or not report_ids:
            continue
        promoted = _promote_outputs(root, output_dir, [report_lookup[report_id] for report_id in report_ids])
        recovered.extend(promoted)
    return sorted(set(recovered))


def _write_compact_json(path: Path, payload: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def repair_empty_vlm_tables(root: Path, manifest: dict) -> dict:
    """Backfill canonical empty tables from the same MinerU model output by page+bbox."""
    report_rows = []
    unresolved = []
    repaired_total = 0
    for report in manifest["reports"]:
        report_id = report["report_id"]
        content_path = canonical_json(root, report_id)
        model_path = content_path.parent / f"{report_id}_model.json"
        if not content_path.is_file() or not model_path.is_file():
            unresolved.append({"report_id": report_id, "reason": "canonical_or_model_json_missing"})
            continue
        content = read_json(content_path)
        model = read_json(model_path)
        if not isinstance(content, list) or not isinstance(model, list) or len(content) != len(model):
            unresolved.append({"report_id": report_id, "reason": "content_and_model_page_counts_differ"})
            continue
        before = sha256(content_path)
        repairs = []
        report_unresolved = []
        for page_index, page in enumerate(content):
            model_tables = [
                block
                for block in model[page_index]
                if isinstance(block, dict)
                and block.get("type") == "table"
                and str(block.get("content", "")).strip()
            ]
            used: set[int] = set()
            for block_index, block in enumerate(page):
                block_content = block.get("content") if isinstance(block, dict) else None
                if (
                    not isinstance(block, dict)
                    or block.get("type") != "table"
                    or not isinstance(block_content, dict)
                    or str(block_content.get("html", "")).strip()
                ):
                    continue
                bbox = block.get("bbox")
                matches = []
                if isinstance(bbox, list) and len(bbox) == 4:
                    for model_index, model_block in enumerate(model_tables):
                        if model_index in used:
                            continue
                        model_bbox = model_block.get("bbox")
                        if not isinstance(model_bbox, list) or len(model_bbox) != 4:
                            continue
                        scaled = [round(float(value) * 1000) for value in model_bbox]
                        distance = sum(abs(float(left) - right) for left, right in zip(bbox, scaled))
                        if distance <= 20:
                            matches.append((distance, model_index, model_block))
                if len(matches) != 1:
                    report_unresolved.append(
                        {
                            "report_id": report_id,
                            "page_no": page_index + 1,
                            "block_index": block_index,
                            "bbox": bbox,
                            "candidate_matches": len(matches),
                        }
                    )
                    continue
                distance, model_index, model_block = matches[0]
                used.add(model_index)
                block_content["html"] = str(model_block["content"])
                image_source = block_content.get("image_source")
                if isinstance(image_source, dict) and image_source.get("path") == "images/":
                    image_source["path"] = ""
                repairs.append(
                    {
                        "page_no": page_index + 1,
                        "block_index": block_index,
                        "bbox_distance": distance,
                        "html_sha256": hashlib.sha256(str(model_block["content"]).encode("utf-8")).hexdigest(),
                    }
                )
        if report_unresolved:
            unresolved.extend(report_unresolved)
            continue
        if repairs:
            _write_compact_json(content_path, content)
            repaired_total += len(repairs)
            report_rows.append(
                {
                    "report_id": report_id,
                    "tables_repaired": len(repairs),
                    "before_sha256": before,
                    "after_sha256": sha256(content_path),
                    "repairs": repairs,
                }
            )
    summary = {
        "schema_version": "formal-v3-table-backfill-1",
        "updated_at": utc_now(),
        "method": "same MinerU model.json table HTML matched by exact page and normalized bbox distance <= 20",
        "reports_scanned": len(manifest["reports"]),
        "reports_repaired_this_run": len(report_rows),
        "tables_repaired_this_run": repaired_total,
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "reports": report_rows,
    }
    previous_path = root / "parser/table_backfill.json"
    if previous_path.is_file():
        previous = read_json(previous_path)
        prior_rows = {row["report_id"]: row for row in previous.get("reports", [])}
        prior_rows.update({row["report_id"]: row for row in report_rows})
        summary["reports"] = [prior_rows[key] for key in sorted(prior_rows)]
        summary["reports_repaired_total"] = len(prior_rows)
        summary["tables_repaired_total"] = sum(int(row["tables_repaired"]) for row in prior_rows.values())
    else:
        summary["reports_repaired_total"] = len(report_rows)
        summary["tables_repaired_total"] = repaired_total
    atomic_json(previous_path, summary)
    if unresolved:
        raise RuntimeError(f"Unresolved empty MinerU table blocks: {len(unresolved)}")
    return summary


def parse_all(root: Path, manifest: dict, batch_size: int) -> dict:
    attempts = []
    recover_parse_attempts(root, manifest)
    pending = [
        row
        for row in manifest["reports"]
        if not valid_content_list(canonical_json(root, row["report_id"]), int(row["pages"]))
    ]
    for offset in range(0, len(pending), batch_size):
        attempts.append(_run_parse_attempt(root, pending[offset : offset + batch_size], f"batch-{offset // batch_size + 1:03d}"))
        _parse_summary(root, manifest, attempts)
    remaining = [
        row
        for row in manifest["reports"]
        if not valid_content_list(canonical_json(root, row["report_id"]), int(row["pages"]))
    ]
    for index, row in enumerate(remaining, start=1):
        attempts.append(_run_parse_attempt(root, [row], f"retry-{index:03d}"))
        _parse_summary(root, manifest, attempts)
    repair_empty_vlm_tables(root, manifest)
    summary = _parse_summary(root, manifest, attempts)
    if summary["completed_reports"] != EXPECTED_REPORTS:
        raise RuntimeError(f"MinerU full batch incomplete: {summary['completed_reports']}/{EXPECTED_REPORTS}")
    return summary


def extract_all(root: Path, manifest: dict) -> dict:
    repair_empty_vlm_tables(root, manifest)
    paths = [canonical_json(root, row["report_id"]) for row in manifest["reports"]]
    invalid = [
        str(path)
        for path, report in zip(paths, manifest["reports"])
        if not valid_content_list(path, int(report["pages"]))
    ]
    if invalid:
        raise RuntimeError(f"Cannot extract before MinerU reaches 200/200; invalid={len(invalid)}")
    extraction = root / "extraction"
    previous_context = os.environ.get("ESG_QWEN_CONTEXT")
    os.environ["ESG_QWEN_CONTEXT"] = str(manifest["extraction_config"]["context_tokens"])
    try:
        ensure_extraction_contract(root, manifest)
        last_error = None
        for runtime_attempt in range(1, 4):
            try:
                runtime_log = root / (
                    "logs/"
                    f"qwen_runtime_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
                    f"{uuid.uuid4().hex[:8]}_attempt_{runtime_attempt}.log"
                )
                with qwen_runtime(runtime_log) as inference_url:
                    run_qwen_preflight(root, manifest, inference_url, paths)
                    summary = run_sample(
                        project_root=PROJECT_ROOT,
                        indicator_pool_path=INDICATOR_POOL,
                        out_dir=extraction,
                        report_limit=EXPECTED_REPORTS,
                        model=QWEN_ALIAS,
                        ollama_url=inference_url,
                        max_blocks_per_indicator=5,
                        report_paths=paths,
                        resume=True,
                        llm_api="openai",
                    )
                if int(summary.get("llm_error_count", 0)) == 0:
                    return summary
                last_error = RuntimeError(f"Qwen extraction attempt retained {summary['llm_error_count']} error rows")
            except Exception as exc:
                last_error = exc
            if runtime_attempt < 3:
                time.sleep(2)
        raise RuntimeError("Qwen extraction did not converge to zero errors after 3 runtime attempts") from last_error
    finally:
        if previous_context is None:
            os.environ.pop("ESG_QWEN_CONTEXT", None)
        else:
            os.environ["ESG_QWEN_CONTEXT"] = previous_context


def run_qwen_preflight(root: Path, manifest: dict, inference_url: str, paths: list[Path]) -> dict:
    output = root / "extraction/qwen_preflight.json"
    if output.is_file():
        existing = read_json(output)
        if existing.get("config_sha256") != manifest["config_sha256"]:
            raise RuntimeError("Existing Qwen preflight does not match the frozen extraction config")
        if existing.get("passed"):
            return existing
        archived = output.with_name(
            f"qwen_preflight_failed_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.json"
        )
        output.replace(archived)
    indicators = _load_indicators(INDICATOR_POOL)
    longest: list[tuple[int, int, int, str, object, list[dict], str]] = []
    sequence = 0
    prompts_scanned = 0
    max_input_tokens = 0
    token_limit = (
        int(manifest["extraction_config"]["context_tokens"])
        - int(manifest["extraction_config"]["max_output_tokens"])
        - 16
    )
    token_counts = []
    for path in paths:
        report_id = path.parent.name
        blocks = flatten_report(report_id, path, load_content_list(path))
        for indicator in indicators:
            candidates = select_candidate_blocks(blocks, indicator, 5)
            if not candidates:
                continue
            prompt = _build_v2_prompt(report_id, indicator, candidates)
            sequence += 1
            prompts_scanned += 1
            input_tokens = llama_token_count(inference_url, prompt)
            token_counts.append(input_tokens)
            max_input_tokens = max(max_input_tokens, input_tokens)
            if input_tokens > token_limit:
                raise RuntimeError(
                    f"Prompt token hard gate failed: {report_id}/{indicator.indicator_id} "
                    f"uses {input_tokens}>{token_limit} tokens"
                )
            item = (input_tokens, len(prompt), sequence, report_id, indicator, candidates, prompt)
            if len(longest) < 5:
                heapq.heappush(longest, item)
            elif item[:3] > longest[0][:3]:
                heapq.heapreplace(longest, item)
    selected = sorted(longest, key=lambda row: row[0], reverse=True)
    if len(selected) != 5:
        raise RuntimeError(f"Qwen preflight could only build {len(selected)}/5 candidate prompts")
    client = build_llm_client(model=QWEN_ALIAS, url=inference_url, api="openai")
    rows = []
    for input_tokens, prompt_chars, _, report_id, indicator, candidates, prompt in selected:
        started = time.monotonic()
        raw = client.generate(prompt)
        result = _normalize_v2_result(
            report_id,
            indicator,
            raw,
            len(candidates),
            round(time.monotonic() - started, 3),
            candidates=candidates,
        )
        rows.append(
            {
                "report_id": report_id,
                "indicator_id": indicator.indicator_id,
                "prompt_chars": prompt_chars,
                "input_tokens": input_tokens,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "candidate_block_ids": [candidate.get("block_id", "") for candidate in candidates],
                "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "status": result["status"],
                "elapsed_seconds": result["elapsed_seconds"],
                "llm_reason": result["llm_reason"],
            }
        )
    failed = [row for row in rows if row["status"] == "error"]
    sorted_counts = sorted(token_counts)
    percentile = lambda fraction: sorted_counts[round((len(sorted_counts) - 1) * fraction)]
    payload = {
        "tested_at": utc_now(),
        "config_sha256": manifest["config_sha256"],
        "strategy": "five longest evidence prompts across the frozen full200 cohort",
        "ranking": "llama-server /tokenize token count",
        "prompts_scanned": prompts_scanned,
        "max_input_tokens": max_input_tokens,
        "p50_input_tokens": percentile(0.50),
        "p95_input_tokens": percentile(0.95),
        "max_prompt_report_id": rows[0]["report_id"],
        "max_prompt_indicator_id": rows[0]["indicator_id"],
        "input_token_hard_limit": token_limit,
        "template_boundary_margin_tokens": 16,
        "cases": rows,
        "passed": not failed,
    }
    atomic_json(output, payload)
    if failed:
        raise RuntimeError(f"Qwen preflight failed {len(failed)}/5 longest-prompt cases")
    return payload


def llama_token_count(inference_url: str, prompt: str) -> int:
    base = inference_url.removesuffix("/v1/chat/completions")
    opener = request.build_opener(request.ProxyHandler({}))
    template_body = json.dumps(
        {
            "messages": [
                {"role": "system", "content": "Return only the requested JSON object."},
                {"role": "user", "content": prompt},
            ],
            "add_generation_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
    ).encode("utf-8")
    template_request = request.Request(
        base + "/apply-template",
        data=template_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(template_request, timeout=60) as response:
        template_payload = json.loads(response.read().decode("utf-8"))
    rendered = template_payload.get("prompt")
    if not isinstance(rendered, str):
        raise RuntimeError("llama-server /apply-template response does not contain prompt text")
    token_body = json.dumps({"content": rendered, "add_special": False, "parse_special": True}).encode("utf-8")
    token_request = request.Request(
        base + "/tokenize",
        data=token_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(token_request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tokens = payload.get("tokens")
    if not isinstance(tokens, list):
        raise RuntimeError("llama-server /tokenize response does not contain a token list")
    return len(tokens)


def runtime_fingerprints(manifest: dict) -> dict[str, dict[str, object]]:
    current = runtime_assets()
    expected = manifest["extractor"]["runtime_assets"]
    required_names = set(current) - {"mmproj"}
    if required_names != set(expected) - {"mmproj"}:
        raise RuntimeError("Qwen runtime asset set changed after prepare")
    fingerprints = {}
    for name in sorted(required_names):
        current_path = Path(str(current[name]["path"]))
        expected_path = Path(str(expected[name]["path"]))
        if current_path != expected_path or not current_path.is_file():
            raise RuntimeError(f"Qwen runtime asset changed after prepare: {name}")
        stat = current_path.stat()
        fingerprints[name] = {
            "path": str(current_path),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": sha256(current_path),
        }
    return fingerprints


def extraction_contract_payload(root: Path, manifest: dict) -> dict:
    parsed = {
        report["report_id"]: sha256(canonical_json(root, report["report_id"]))
        for report in manifest["reports"]
    }
    runtime_command = llama_server_command(0, include_vision=False)
    context_index = runtime_command.index("--ctx-size") + 1
    runtime_command[context_index] = str(manifest["extraction_config"]["context_tokens"])
    return {
        "schema_version": "formal-v3-extraction-contract-1",
        "run_id": manifest["run_id"],
        "config_sha256": manifest["config_sha256"],
        "indicator_pool_sha256": manifest["indicator_pool"]["sha256"],
        "prompt_source_sha256": sha256(PROJECT_ROOT / "src/esg_demo/formal_extraction.py"),
        "model_alias": QWEN_ALIAS,
        "llm_api": "openai",
        "context_tokens": manifest["extraction_config"]["context_tokens"],
        "max_output_tokens": manifest["extraction_config"]["max_output_tokens"],
        "runtime_command": runtime_command,
        "runtime_fingerprints": runtime_fingerprints(manifest),
        "report_count": EXPECTED_REPORTS,
        "expected_rows": EXPECTED_RESULTS,
        "parsed_sha256": parsed,
    }


def ensure_extraction_contract(root: Path, manifest: dict) -> dict:
    path = root / "extraction/input_contract.json"
    result_path = root / "extraction/extraction_results.csv"
    current = extraction_contract_payload(root, manifest)
    if path.is_file():
        existing = read_json(path)
        if result_path.is_file():
            if existing.get("run_id") != manifest.get("run_id"):
                raise RuntimeError("Frozen extraction contract run_id differs from the formal manifest")
            if existing.get("indicator_pool_sha256") != manifest["indicator_pool"]["sha256"]:
                raise RuntimeError("Frozen extraction contract indicator pool differs from the formal manifest")
            for report_id, digest in existing.get("parsed_sha256", {}).items():
                if sha256(canonical_json(root, report_id)) != digest:
                    raise RuntimeError(f"Canonical parsed input changed: {report_id}")
            return existing
        if existing != current:
            raise RuntimeError("Extraction resume contract differs from the frozen parsed/model/prompt inputs")
        return current
    if result_path.is_file() and result_path.stat().st_size:
        raise RuntimeError("Refusing extraction resume because results exist without an input contract")
    atomic_json(path, current)
    return current


def augment_lineage(root: Path, manifest: dict) -> list[dict]:
    result_path = root / "extraction/extraction_results.csv"
    rows = _read_csv(result_path)
    report_meta = {row["report_id"]: row for row in manifest["reports"]}
    parsed_hashes = {
        report_id: sha256(canonical_json(root, report_id))
        for report_id in report_meta
    }
    for row in rows:
        report_id = row["report_id"]
        indicator_id = row["indicator_id"]
        row.update(
            {
                "run_id": manifest["run_id"],
                "result_id": hashlib.sha256(
                    f"{manifest['run_id']}|{report_id}|{indicator_id}".encode("utf-8")
                ).hexdigest(),
                "pdf_sha256": report_meta[report_id]["pdf_sha256"],
                "parsed_sha256": parsed_hashes[report_id],
                "parser_backend": "vlm-engine",
                "parser_model": "MinerU2.5-Pro-2605-1.2B",
                "llm_model": QWEN_ALIAS,
                "prompt_version": manifest["extraction_config"]["prompt_version"],
                "indicator_pool_sha256": manifest["indicator_pool"]["sha256"],
            }
        )
    atomic_csv(result_path, rows)
    atomic_json(root / "extraction/extraction_results.json", rows)
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _compact_trace_text(value: object) -> str:
    import re

    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9.%％]+", "", str(value or ""))


def _decimal_value(value: object) -> Decimal | None:
    text = str(value or "").replace(",", "").replace("，", "").strip()
    if text.endswith("%"):
        text = text[:-1]
    if "/" in text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _numeric_value_is_literal(value: object, quote: object) -> bool:
    import re

    target = _decimal_value(value)
    if target is None:
        return str(value or "").strip() in str(quote or "")
    tokens = re.findall(r"-?\d+(?:[,.，]\d+)*(?:%)?", str(quote or ""))
    return any(_decimal_value(token) == target for token in tokens if _decimal_value(token) is not None)


def evidence_contract(root: Path, manifest: dict, rows: list[dict[str, str]]) -> dict:
    found_by_report: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("status") == "found":
            found_by_report.setdefault(row["report_id"], []).append(row)
    checked = 0
    valid = 0
    failures = []
    for report in manifest["reports"]:
        report_id = report["report_id"]
        report_rows = found_by_report.get(report_id, [])
        if not report_rows:
            continue
        path = canonical_json(root, report_id)
        blocks = flatten_report(report_id, path, load_content_list(path))
        by_id = {str(block["block_id"]): block for block in blocks}
        for row in report_rows:
            checked += 1
            block = by_id.get(str(row.get("block_id", "")))
            reasons = []
            if block is None:
                reasons.append("block_id_not_found")
            else:
                if str(block["page_no"]) != str(row.get("page_no", "")):
                    reasons.append("page_no_mismatch")
                if str(block.get("block_type", "")) != str(row.get("block_type", "")):
                    reasons.append("block_type_mismatch")
                quote = str(row.get("evidence_quote", ""))
                if not quote or quote not in str(block.get("text", "")):
                    reasons.append("quote_not_in_block")
            if reasons:
                failures.append(
                    {
                        "report_id": report_id,
                        "indicator_id": row.get("indicator_id", ""),
                        "block_id": row.get("block_id", ""),
                        "reasons": "|".join(reasons),
                    }
                )
            else:
                valid += 1
    atomic_csv(
        root / "extraction/evidence_contract_failures.csv",
        failures,
        ["report_id", "indicator_id", "block_id", "reasons"],
    )
    return {"checked_found_rows": checked, "valid_found_rows": valid, "failure_count": len(failures)}


def empty_table_count(root: Path, manifest: dict) -> int:
    count = 0
    for report in manifest["reports"]:
        payload = read_json(canonical_json(root, report["report_id"]))
        count += sum(
            1
            for page in payload
            for block in page
            if block.get("type") == "table"
            and isinstance(block.get("content"), dict)
            and not str(block["content"].get("html", "")).strip()
        )
    return count


def validate_data001_corrections(
    root: Path, manifest: dict, result_rows: list[dict[str, str]]
) -> dict[str, object]:
    """Verify DATA-001 against fixed expectations and frozen canonical blocks."""
    csv_path = root / "extraction/audit_corrections.csv"
    json_path = root / "extraction/audit_corrections.json"
    if not csv_path.is_file() or not json_path.is_file():
        return {"passed": False, "failure_count": 1, "failures": ["correction_artifacts_missing"]}
    csv_rows = _read_csv(csv_path)
    payload = read_json(json_path)
    json_rows = payload.get("corrections", []) if isinstance(payload, dict) else []
    failures: list[str] = []
    if csv_rows != json_rows:
        failures.append("csv_json_corrections_not_synchronized")
    if not isinstance(payload, dict) or payload.get("issue_id") != "DATA-001":
        failures.append("json_issue_id_mismatch")
    if payload.get("correction_count") != len(DATA001_EXPECTED):
        failures.append("json_correction_count_mismatch")
    if payload.get("reviewer") != "codex-independent-audit-data-001":
        failures.append("json_reviewer_mismatch")
    audit_by_key = {(row.get("report_id"), row.get("indicator_id")): row for row in csv_rows}
    result_by_key = {(row.get("report_id"), row.get("indicator_id")): row for row in result_rows}
    expected_keys = {(report_id, "g_board_diversity") for report_id in DATA001_EXPECTED}
    if set(audit_by_key) != expected_keys or len(csv_rows) != len(expected_keys):
        failures.append("audit_target_set_mismatch")

    manifest_ids = {row["report_id"] for row in manifest["reports"]}
    for report_id, expected in DATA001_EXPECTED.items():
        key = (report_id, "g_board_diversity")
        audit = audit_by_key.get(key)
        result = result_by_key.get(key)
        if report_id not in manifest_ids or audit is None or result is None:
            failures.append(f"{report_id}:target_missing")
            continue
        expected_block_id = f"{report_id}:{expected['block_suffix']}"
        expected_after = {
            "value": expected["value"],
            "unit": expected["unit"],
            "page_no": expected["page_no"],
            "block_id": expected_block_id,
            "block_type": expected["block_type"],
            "evidence_quote": expected["quote"],
            "value_origin": expected["value_origin"],
            "unit_origin": expected["unit_origin"],
        }
        for field, value in expected_after.items():
            if result.get(field) != value or audit.get(f"after_{field}") != value:
                failures.append(f"{report_id}:after_{field}_mismatch")
        if audit.get("canonical_page_no") != expected["page_no"]:
            failures.append(f"{report_id}:canonical_page_mismatch")
        if audit.get("canonical_block_id") != expected_block_id:
            failures.append(f"{report_id}:canonical_block_mismatch")
        if audit.get("canonical_block_type") != expected["block_type"]:
            failures.append(f"{report_id}:canonical_block_type_mismatch")
        if audit.get("canonical_quote") != expected["quote"]:
            failures.append(f"{report_id}:canonical_quote_mismatch")
        before_expectations = {
            "before_value": expected["before_value"],
            "before_page_no": expected["before_page_no"],
            "before_block_id": f"{report_id}:{expected['before_block_suffix']}",
        }
        for field, value in before_expectations.items():
            if audit.get(field) != value:
                failures.append(f"{report_id}:{field}_mismatch")
        if not audit.get("correction_reason") or not audit.get("correction_method"):
            failures.append(f"{report_id}:correction_explanation_missing")
        if audit.get("reviewer") != "codex-independent-audit-data-001" or not audit.get("reviewed_at"):
            failures.append(f"{report_id}:review_provenance_mismatch")

        blocks = flatten_report(
            report_id,
            canonical_json(root, report_id),
            load_content_list(canonical_json(root, report_id)),
        )
        block = next((item for item in blocks if str(item.get("block_id")) == expected_block_id), None)
        if block is None:
            failures.append(f"{report_id}:canonical_block_not_found")
        elif (
            str(block.get("page_no")) != expected["page_no"]
            or str(block.get("block_type")) != expected["block_type"]
            or expected["quote"] not in str(block.get("text", ""))
        ):
            failures.append(f"{report_id}:canonical_source_content_mismatch")

        if expected["value_origin"] == "direct":
            if not _numeric_value_is_literal(expected["value"], expected["quote"]):
                failures.append(f"{report_id}:direct_value_not_literal")
            if result.get("derivation_method") or result.get("derivation_expression") or result.get("derivation_inputs_json"):
                failures.append(f"{report_id}:direct_row_has_derivation_payload")
        else:
            if result.get("derivation_method") != expected["derivation_method"]:
                failures.append(f"{report_id}:derivation_method_mismatch")
            if result.get("derivation_expression") != expected["derivation_expression"]:
                failures.append(f"{report_id}:derivation_expression_mismatch")
            try:
                inputs = json.loads(result.get("derivation_inputs_json", ""))
            except json.JSONDecodeError:
                inputs = {}
            if inputs.get("source_token") != "三" or inputs.get("normalized_value") != "3":
                failures.append(f"{report_id}:chinese_numeral_inputs_mismatch")

    return {
        "passed": not failures,
        "correction_count": len(csv_rows),
        "csv_sha256": sha256(csv_path),
        "json_sha256": sha256(json_path),
        "failure_count": len(failures),
        "failures": failures,
    }


def validate_all(root: Path, manifest: dict) -> dict:
    parse_summary = _parse_summary(root, manifest, [])
    result_path = root / "extraction/extraction_results.csv"
    summary_path = root / "extraction/run_summary.json"
    if not result_path.is_file() or not summary_path.is_file():
        raise RuntimeError("Extraction artifacts are missing")
    rows = _read_csv(result_path)
    keys = [(row.get("report_id", ""), row.get("indicator_id", "")) for row in rows]
    report_ids = {key[0] for key in keys}
    indicators = {key[1] for key in keys}
    errors = [row for row in rows if row.get("status") == "error"]
    found = [row for row in rows if row.get("status") == "found"]
    traceable = [
        row
        for row in found
        if str(row.get("evidence_quote", "")).strip()
        and str(row.get("page_no", "")).strip()
        and str(row.get("block_id", "")).strip()
    ]
    quantitative_found = [row for row in found if row.get("indicator_type") == "quantitative"]
    quantitative_complete = [
        row
        for row in quantitative_found
        if str(row.get("value", "")).strip()
        and str(row.get("unit", "")).strip()
        and row.get("quantitative_incomplete") != "true"
        and row.get("evidence_match_mode") == "exact_raw_substring"
        and row.get("value_origin") in {"direct", "derived"}
        and row.get("unit_origin") in {"direct", "normalized_or_inferred"}
        and (
            (
                row.get("value_origin") == "direct"
                and _numeric_value_is_literal(row.get("value", ""), row.get("evidence_quote", ""))
            )
            or (
                row.get("value_origin") == "derived"
                and str(row.get("derivation_method", "")).strip()
                and str(row.get("derivation_expression", "")).strip()
                and str(row.get("derivation_inputs_json", "")).strip()
            )
        )
    ]
    allowed_statuses = {"found", "missing", "error"}
    indicator_rows = _read_csv(INDICATOR_POOL)
    expected_indicator_ids = {row["indicator_id"] for row in indicator_rows}
    report_indicator_sets: dict[str, set[str]] = {}
    for report_id, indicator_id in keys:
        report_indicator_sets.setdefault(report_id, set()).add(indicator_id)
    missing_fields = ("value", "unit", "qualitative_text", "evidence_quote", "page_no", "block_id", "block_type")
    missing_rows_clean = all(
        not any(str(row.get(field, "")).strip() for field in missing_fields)
        for row in rows
        if row.get("status") == "missing"
    )
    evidence = evidence_contract(root, manifest, rows)
    data001 = validate_data001_corrections(root, manifest, rows)
    empty_tables = empty_table_count(root, manifest)
    run_summary = read_json(summary_path)
    cohort_manifest = read_json(root / "cohort_manifest.json") if (root / "cohort_manifest.json").is_file() else {}
    attempt_summary = (
        read_json(root / "parser/parse_attempts_summary.json")
        if (root / "parser/parse_attempts_summary.json").is_file()
        else {}
    )
    expected_report_ids = [row["report_id"] for row in manifest["reports"]]
    checks = {
        "parse_200_of_200": parse_summary["completed_reports"] == EXPECTED_REPORTS,
        "parsed_page_count_matches_manifest": sum(
            content_page_count(canonical_json(root, report["report_id"]))
            for report in manifest["reports"]
        )
        == int(manifest["page_count"]),
        "canonical_empty_table_blocks_zero": empty_tables == 0,
        "result_rows_13000": len(rows) == EXPECTED_RESULTS,
        "unique_report_indicator_keys_13000": len(set(keys)) == EXPECTED_RESULTS,
        "reports_200": report_ids == {row["report_id"] for row in manifest["reports"]},
        "indicators_exact_pool_65": indicators == expected_indicator_ids and len(indicators) == EXPECTED_INDICATORS,
        "each_report_has_exact_indicator_pool": all(
            report_indicator_sets.get(report_id, set()) == expected_indicator_ids for report_id in expected_report_ids
        ),
        "statuses_allowed": all(row.get("status") in allowed_statuses for row in rows),
        "missing_rows_have_no_evidence_payload": missing_rows_clean,
        "all_found_rows_trace_to_parsed_block": evidence["failure_count"] == 0
        and evidence["checked_found_rows"] == len(found),
        "all_found_quotes_exact_raw_substrings": evidence["failure_count"] == 0
        and all(row.get("evidence_match_mode") == "exact_raw_substring" for row in found),
        "quantitative_found_complete": len(quantitative_complete) == len(quantitative_found),
        "model_qwen36": run_summary.get("model") == QWEN_ALIAS,
        "api_openai": run_summary.get("llm_api") == "openai",
        "run_summary_exact_scope": run_summary.get("reports") == EXPECTED_REPORTS
        and run_summary.get("indicators") == EXPECTED_INDICATORS
        and run_summary.get("results") == EXPECTED_RESULTS
        and run_summary.get("report_ids") == expected_report_ids,
        "llm_error_zero": not errors and int(run_summary.get("llm_error_count", -1)) == 0,
        "lineage_complete": all(
            row.get("run_id") == manifest["run_id"]
            and row.get("pdf_sha256")
            and row.get("parsed_sha256")
            and row.get("llm_model") == QWEN_ALIAS
            for row in rows
        ),
        "formal_dataset_self_contained": (
            manifest.get("indicator_pool", {}).get("path")
            == "outputs/formal_v3_mineru25_qwen36/indicator_pool.csv"
            and sha256(root / "indicator_pool.csv") == manifest["indicator_pool"]["sha256"]
            and cohort_manifest.get("report_count") == EXPECTED_REPORTS
            and cohort_manifest.get("page_count") == int(manifest["page_count"])
        ),
        "parse_attempt_provenance_accounted": (
            int(attempt_summary.get("retained_attempt_report_coverage", -1))
            + int(attempt_summary.get("canonical_without_retained_attempt_count", -1))
            == EXPECTED_REPORTS
            and int(attempt_summary.get("canonical_report_count", -1)) == EXPECTED_REPORTS
        ),
        "data001_corrections_match_frozen_canonical_evidence": bool(data001["passed"]),
    }
    validation = {
        "validated_at": utc_now(),
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "parsed_reports": parse_summary["completed_reports"],
            "result_rows": len(rows),
            "unique_keys": len(set(keys)),
            "reports": len(report_ids),
            "indicators": len(indicators),
            "errors": len(errors),
            "canonical_empty_table_blocks": empty_tables,
            "found": len(found),
            "found_with_quote_page_block": len(traceable),
            "found_traceability_rate": round(len(traceable) / len(found), 6) if found else 1.0,
            "quantitative_found": len(quantitative_found),
            "quantitative_complete": len(quantitative_complete),
            "quantitative_direct": sum(row.get("value_origin") == "direct" for row in quantitative_found),
            "quantitative_derived": sum(row.get("value_origin") == "derived" for row in quantitative_found),
            "quantitative_normalized_or_inferred_unit": sum(
                row.get("unit_origin") == "normalized_or_inferred" for row in quantitative_found
            ),
            "quantitative_completeness_rate": round(len(quantitative_complete) / len(quantitative_found), 6)
            if quantitative_found
            else 1.0,
            "evidence_contract": evidence,
            "data001_corrections": data001,
        },
    }
    atomic_json(root / "validation.json", validation)
    if not validation["passed"]:
        raise RuntimeError("v3 validation failed: " + json.dumps(checks, ensure_ascii=False))
    return validation


def compare_legacy(root: Path) -> dict:
    existing = root / "legacy_comparison.json"
    if existing.is_file():
        return read_json(existing)
    return {"comparison_only_not_accuracy": True, "natural_gold_used": False, "legacy_removed": True}


def write_checksums(root: Path) -> dict[str, str]:
    relative_paths = [
        "run_manifest.json",
        "input_manifest.csv",
        "indicator_pool.csv",
        "cohort_manifest.csv",
        "cohort_manifest.json",
        "parse_summary.json",
        "parser/report_manifest.jsonl",
        "parser/table_backfill.json",
        "parser/parse_attempts_summary.json",
        "extraction/extraction_results.csv",
        "extraction/extraction_results.json",
        "extraction/input_contract.json",
        "extraction/qwen_preflight.json",
        "extraction/evidence_contract_failures.csv",
        "extraction/error_analysis.csv",
        "extraction/manual_reconciliation.csv",
        "extraction/manual_reconciliation.json",
        "extraction/audit_corrections.csv",
        "extraction/audit_corrections.json",
        "extraction/evidence_hardening.csv",
        "extraction/evidence_hardening.json",
        "extraction/run_summary.json",
        "extraction/llm_errors.csv",
        "validation.json",
        "legacy_comparison.json",
        "legacy_comparison.md",
        "provenance/pre_hardening_checksums.sha256",
        "provenance/migration.json",
    ]
    checksums = {}
    for relative in relative_paths:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"Cannot finalize without artifact: {relative}")
        checksums[relative] = sha256(path)
    lines = [f"{digest}  {relative}" for relative, digest in sorted(checksums.items())]
    path = root / "CHECKSUMS.sha256"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)
    return checksums


def write_run_status(root: Path, stage: str, status: str, detail: object | None = None) -> None:
    payload = {"updated_at": utc_now(), "stage": stage, "status": status}
    if detail is not None:
        payload["detail"] = detail
    atomic_json(root / "run_status.json", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full isolated MinerU2.5 + Qwen3.6 ESG-65 batch")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--stage", choices=["prepare", "parse", "extract", "validate", "all"], default="all")
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    root = safe_output_root(Path(args.root))
    root.mkdir(parents=True, exist_ok=True)
    lock_stream = (root / ".run.lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"Another formal_v3 process already holds {root / '.run.lock'}") from exc
    lock_stream.seek(0)
    lock_stream.truncate()
    lock_stream.write(f"pid={os.getpid()} started_at={utc_now()}\n")
    lock_stream.flush()
    try:
        write_run_status(root, "prepare", "running")
        manifest = build_manifest(root)
        if not manifest.get("run_id"):
            manifest = enrich_manifest(root, manifest)
        verify_protected_inputs(manifest)
        write_run_status(root, "prepare", "completed", {"reports": len(manifest["reports"]), "pages": manifest["page_count"]})
        if args.stage == "prepare":
            return 0
        if args.stage in {"parse", "all"}:
            write_run_status(root, "parse", "running")
            parse_summary = parse_all(root, manifest, args.batch_size)
            write_run_status(root, "parse", "completed", parse_summary)
        if args.stage == "parse":
            return 0
        if args.stage in {"extract", "all"}:
            write_run_status(root, "extract", "running")
            extraction_summary = extract_all(root, manifest)
            write_run_status(root, "extract", "completed", extraction_summary)
        if args.stage == "extract":
            return 0
        write_run_status(root, "validate", "running")
        verify_protected_inputs(manifest)
        ensure_extraction_contract(root, manifest)
        write_parser_manifest(root, manifest)
        augment_lineage(root, manifest)
        validation = validate_all(root, manifest)
        comparison = compare_legacy(root)
        checksums = write_checksums(root)
        complete = {
            "run_id": manifest["run_id"],
            "completed_at": utc_now(),
            "scope_type": "full200",
            "is_full_200": True,
            "reports": EXPECTED_REPORTS,
            "result_rows": EXPECTED_RESULTS,
            "validation_passed": validation["passed"],
            "evaluation_kind": "engineering_run_not_accuracy_evaluation",
            "natural_gold_unlocked": False,
            "promotion": "not_promoted",
            "checksums_sha256": sha256(root / "CHECKSUMS.sha256"),
            "artifact_count": len(checksums),
        }
        atomic_json(root / "COMPLETE.json", complete)
        write_run_status(root, "completed", "completed", {"validation": validation, "comparison": comparison})
        print(json.dumps({"validation": validation, "comparison": comparison}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        write_run_status(root, "failed", "failed", {"type": type(exc).__name__, "message": str(exc)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
