#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "outputs/contest_materials/submission/final"
MAX_BYTES = 200 * 1024 * 1024
PROJECT_NAME = "ESG ClaimGuard"

INCLUDE_FILES = [
    "docs/contest_materials/submission/ESG_ClaimGuard_其他材料说明.md",
    "docs/contest_materials/submission/requirements-submission.txt",
    "data/README.md",
    "dashboard_web/README.md",
    "dashboard_web/package.json",
    "dashboard_web/package-lock.json",
    "dashboard_web/tsconfig.json",
    "dashboard_web/tsconfig.app.json",
    "dashboard_web/tsconfig.node.json",
    "dashboard_web/vite.config.ts",
    "outputs/final_results/indicator_pool.csv",
    "outputs/final_results/input_manifest.csv",
    "outputs/final_results/cohort_manifest.csv",
    "outputs/final_results/cohort_manifest.json",
    "outputs/final_results/parse_summary.json",
    "outputs/final_results/run_manifest.json",
    "outputs/final_results/parser/table_backfill.json",
    "outputs/final_results/parser/parse_attempts_summary.json",
    "outputs/final_results/extraction/run_summary.json",
    "outputs/final_results/extraction/extraction_results.csv",
    "outputs/final_results/extraction/evidence_hardening.json",
    "outputs/final_results/extraction/manual_reconciliation.csv",
    "outputs/final_results/extraction/audit_corrections.csv",
    "outputs/final_results/extraction/audit_corrections.json",
    "outputs/final_results/extraction/evidence_contract_failures.csv",
    "outputs/final_results/validation.json",
    "outputs/final_results/CHECKSUMS.sha256",
    "outputs/final_results/COMPLETE.json",
    "outputs/contest_materials/competition_readiness.md",
    "outputs/contest_materials/dashboard_smoke.md",
    "outputs/contest_materials/frontend_dependency_licenses.md",
    "outputs/contest_materials/submission/latex_build_report.json",
    "outputs/contest_materials/submission/ESG_ClaimGuard_仓库整理与交付报告_20260831.md",
    "docs/contest_materials/术语表格.md",
    "docs/contest_materials/题目分析.md",
    "docs/contest_materials/submission/ESG_ClaimGuard_项目文档.md",
    "docs/contest_materials/submission/ESG_ClaimGuard_参赛作品简介_300字.md",
    "docs/contest_materials/submission/ESG_ClaimGuard_5分钟视频分镜与口播.md",
    "docs/contest_materials/submission/ESG_ClaimGuard_创新与基线对比矩阵.md",
    "docs/contest_materials/submission/ESG_ClaimGuard_来源与借鉴台账.md",
    "docs/contest_materials/submission/ESG_ClaimGuard_第三方依赖与许可.md",
    "latex/ESG_ClaimGuard_技术论文.md",
    "outputs/contest_materials/submission/supporting/ESG_ClaimGuard_技术论文.pdf",
]
INCLUDE_TREES = [
    "dashboard_api",
    "dashboard_web/src",
    "src/esg_demo",
    "scripts",
    "tests",
    "latex/figures",
    "latex/submission",
    "docs/contest_materials/assets",
]
ALLOWED_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".html", ".sh", ".md", ".txt", ".srt", ".tex", ".json", ".csv", ".svg", ".png", ".pdf"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".html", ".sh", ".md", ".txt", ".srt", ".tex", ".json", ".csv", ".svg"}
EXCLUDED_PARTS = {"__pycache__", "node_modules", ".git", "dist", "tasks"}
EXCLUDED_FILES: set[str] = set()
ARCHIVE_ALIASES = {
    "docs/contest_materials/submission/ESG_ClaimGuard_其他材料说明.md": "README.md",
    "docs/contest_materials/submission/requirements-submission.txt": "requirements-submission.txt",
}


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", value.strip()).strip("_")
    if not cleaned:
        raise ValueError("team name cannot be empty")
    return cleaned


def collect_files() -> list[Path]:
    paths = []
    missing = []
    for name in INCLUDE_FILES:
        path = PROJECT_ROOT / name
        if path.is_file():
            paths.append(path)
        else:
            missing.append(name)
    if missing:
        raise FileNotFoundError(f"required submission files are missing: {missing}")
    for tree in INCLUDE_TREES:
        root = PROJECT_ROOT / tree
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if any(part in EXCLUDED_PARTS for part in path.relative_to(PROJECT_ROOT).parts):
                continue
            if str(path.relative_to(PROJECT_ROOT)) in EXCLUDED_FILES:
                continue
            paths.append(path)
    return sorted(set(paths), key=lambda path: str(path.relative_to(PROJECT_ROOT)))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_bytes(path: Path, identity: dict[str, str]) -> bytes:
    """Return portable archive content without mutating frozen source artifacts."""
    payload = path.read_bytes()
    relative = str(path.relative_to(PROJECT_ROOT))
    if relative == "outputs/final_results/run_manifest.json":
        data = json.loads(payload.decode("utf-8"))
        if isinstance(data.get("parser"), dict) and "binary" in data["parser"]:
            data["parser"]["binary"] = "${MINERU_BIN}"
        payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if relative == "docs/contest_materials/submission/ESG_ClaimGuard_项目文档.md":
        text = payload.decode("utf-8")
        for key, value in identity.items():
            text = text.replace("{{" + key + "}}", value)
        payload = text.encode("utf-8")
    return payload


def bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the <=200 MiB AI contest auxiliary-material ZIP from a strict whitelist.")
    parser.add_argument("--team", default="队不起队不起")
    parser.add_argument("--competition-group", default="开放赛题-生成式大语言模型与智能体")
    parser.add_argument("--submission-date", default="2026年8月31日")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    if any(marker in value for value in (args.team, args.competition_group, args.submission_date) for marker in ("待定", "待确认", "YYYY")):
        parser.error("final package requires confirmed identity values")
    team = safe_component(args.team)
    output_name = f"{team}_ESG ClaimGuard_其他.zip"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / output_name
    files = collect_files()
    identity = {
        "team_name": args.team,
        "competition_group": args.competition_group,
        "submission_date": args.submission_date,
    }
    payloads = [archive_bytes(path, identity) for path in files]
    violations = []
    for path, payload in zip(files, payloads, strict=True):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = payload.decode("utf-8", errors="replace")
        markers = ["/data/" + "sues01", "/home/" + "sues01"]
        relative = str(path.relative_to(PROJECT_ROOT))
        if relative.startswith("docs/contest_materials/submission/"):
            markers.extend(["待定", "待确认", "YYYY"])
        found = [marker for marker in markers if marker in content]
        if found:
            violations.append({"path": str(path.relative_to(PROJECT_ROOT)), "markers": found})
    if violations:
        raise RuntimeError(f"submission text validation failed: {violations}")
    archive_entries = [
        {
            "source_path": str(path.relative_to(PROJECT_ROOT)),
            "path": ARCHIVE_ALIASES.get(
                str(path.relative_to(PROJECT_ROOT)), str(path.relative_to(PROJECT_ROOT))
            ),
            "bytes": len(payload),
            "sha256": bytes_sha256(payload),
        }
        for path, payload in zip(files, payloads, strict=True)
    ]
    archive_paths = [item["path"] for item in archive_entries]
    if len(archive_paths) != len(set(archive_paths)):
        raise RuntimeError("submission archive paths are not unique")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "team": args.team,
        "competition_group": args.competition_group,
        "submission_date": args.submission_date,
        "project": PROJECT_NAME,
        "boundary": "The completed formal run proves engineering completeness and evidence traceability; the submission does not claim accuracy without independent human evaluation.",
        "package_kind": "lightweight_review_bundle_without_raw_pdf_parsed_or_models",
        "files": archive_entries,
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for payload, item in zip(payloads, archive_entries, strict=True):
            archive.writestr(item["path"], payload)
        archive.writestr("SUBMISSION_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    size = output.stat().st_size
    if size > MAX_BYTES:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"package exceeds 200 MiB: {size} bytes")
    result = {
        "status": "final",
        "output": str(output.relative_to(PROJECT_ROOT)),
        "files": len(files) + 1,
        "bytes": size,
        "mib": round(size / 1024 / 1024, 3),
        "sha256": sha256(output),
        "under_200_mib": True,
    }
    validation_path = PROJECT_ROOT / "outputs/contest_materials/submission/package_validation.json"
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
