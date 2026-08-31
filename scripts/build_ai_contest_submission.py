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
OUTPUT_ROOT = PROJECT_ROOT / "outputs/ai_contest/submission/final"
MAX_BYTES = 200 * 1024 * 1024
PROJECT_NAME = "ESG ClaimGuard"

INCLUDE_FILES = [
    "docs/ai_contest/submission/ESG_ClaimGuard_其他材料说明.md",
    "docs/ai_contest/submission/requirements-submission.txt",
    "data/README.md",
    "dashboard_web/README.md",
    "dashboard_web/package.json",
    "dashboard_web/package-lock.json",
    "dashboard_web/tsconfig.json",
    "dashboard_web/tsconfig.app.json",
    "dashboard_web/tsconfig.node.json",
    "dashboard_web/vite.config.ts",
    "outputs/formal_v3_mineru25_qwen36/indicator_pool.csv",
    "outputs/formal_v3_mineru25_qwen36/input_manifest.csv",
    "outputs/formal_v3_mineru25_qwen36/cohort_manifest.csv",
    "outputs/formal_v3_mineru25_qwen36/cohort_manifest.json",
    "outputs/formal_v3_mineru25_qwen36/parse_summary.json",
    "outputs/formal_v3_mineru25_qwen36/run_manifest.json",
    "outputs/formal_v3_mineru25_qwen36/parser/table_backfill.json",
    "outputs/formal_v3_mineru25_qwen36/parser/parse_attempts_summary.json",
    "outputs/formal_v3_mineru25_qwen36/extraction/run_summary.json",
    "outputs/formal_v3_mineru25_qwen36/extraction/extraction_results.csv",
    "outputs/formal_v3_mineru25_qwen36/extraction/evidence_hardening.json",
    "outputs/formal_v3_mineru25_qwen36/extraction/manual_reconciliation.csv",
    "outputs/formal_v3_mineru25_qwen36/extraction/audit_corrections.csv",
    "outputs/formal_v3_mineru25_qwen36/extraction/audit_corrections.json",
    "outputs/formal_v3_mineru25_qwen36/extraction/evidence_contract_failures.csv",
    "outputs/formal_v3_mineru25_qwen36/validation.json",
    "outputs/formal_v3_mineru25_qwen36/provenance/migration.json",
    "outputs/formal_v3_mineru25_qwen36/CHECKSUMS.sha256",
    "outputs/formal_v3_mineru25_qwen36/COMPLETE.json",
    "outputs/ai_contest/competition_readiness.md",
    "outputs/ai_contest/dashboard_smoke.md",
    "outputs/ai_contest/frontend_dependency_licenses.md",
    "outputs/ai_contest/submission/latex_build_report.json",
    "outputs/ai_contest/submission/ESG_ClaimGuard_仓库整理与交付报告_20260831.md",
    "docs/ai_contest/术语表格.md",
    "docs/ai_contest/题目分析.md",
    "docs/ai_contest/submission/ESG_ClaimGuard_项目文档.md",
    "docs/ai_contest/submission/ESG_ClaimGuard_参赛作品简介_300字.md",
    "docs/ai_contest/submission/ESG_ClaimGuard_5分钟视频分镜与口播.md",
    "docs/ai_contest/submission/ESG_ClaimGuard_创新与基线对比矩阵.md",
    "docs/ai_contest/submission/ESG_ClaimGuard_来源与借鉴台账.md",
    "docs/ai_contest/submission/ESG_ClaimGuard_第三方依赖与许可.md",
    "latex/ESG_ClaimGuard_技术论文.md",
    "outputs/ai_contest/submission/supporting/ESG_ClaimGuard_技术论文.pdf",
]
INCLUDE_TREES = [
    "dashboard_api",
    "dashboard_web/src",
    "src/esg_demo",
    "scripts",
    "tests",
    "latex/figures",
    "latex/submission",
    "docs/ai_contest/assets",
]
ALLOWED_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".html", ".sh", ".md", ".txt", ".srt", ".tex", ".json", ".csv", ".svg", ".png", ".pdf"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".html", ".sh", ".md", ".txt", ".srt", ".tex", ".json", ".csv", ".svg"}
EXCLUDED_PARTS = {"__pycache__", "node_modules", ".git", "dist", "tasks"}
EXCLUDED_FILES: set[str] = set()
ARCHIVE_ALIASES = {
    "docs/ai_contest/submission/ESG_ClaimGuard_其他材料说明.md": "README.md",
    "docs/ai_contest/submission/requirements-submission.txt": "requirements-submission.txt",
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
    if relative == "outputs/formal_v3_mineru25_qwen36/run_manifest.json":
        data = json.loads(payload.decode("utf-8"))
        if isinstance(data.get("parser"), dict) and "binary" in data["parser"]:
            data["parser"]["binary"] = "${MINERU_BIN}"
        payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if relative == "docs/ai_contest/submission/ESG_ClaimGuard_项目文档.md":
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
    parser.add_argument("--draft", action="store_true", help="Allow placeholder team name and mark output as draft.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    if not args.draft and any(marker in value for value in (args.team, args.competition_group, args.submission_date) for marker in ("待定", "待确认", "YYYY")):
        parser.error("final package requires confirmed identity values; use --draft for placeholders")
    team = safe_component(args.team)
    suffix = "_草案" if args.draft else ""
    output_name = f"{team}_ESG ClaimGuard_其他{suffix}.zip"
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
        if relative.startswith("docs/ai_contest/submission/"):
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
        "draft": args.draft,
        "team": args.team,
        "competition_group": args.competition_group,
        "submission_date": args.submission_date,
        "project": PROJECT_NAME,
        "boundary": "The full V3 run proves engineering completeness and evidence traceability; the submission does not claim accuracy without independent human evaluation.",
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
        "status": "draft" if args.draft else "final",
        "output": str(output.relative_to(PROJECT_ROOT)),
        "files": len(files) + 1,
        "bytes": size,
        "mib": round(size / 1024 / 1024, 3),
        "sha256": sha256(output),
        "under_200_mib": True,
    }
    validation_path = PROJECT_ROOT / "outputs/ai_contest/submission/package_validation.json"
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
