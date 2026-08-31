#!/usr/bin/env python3
"""Build a clean, review-ready repository snapshot without Git history or heavy runtime assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from build_ai_contest_submission import PROJECT_ROOT, archive_bytes, collect_files


DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/public_repository/ESG_ClaimGuard_公开代码仓库.zip"
MAX_BYTES = 200 * 1024 * 1024
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".css", ".html", ".sh", ".md", ".txt", ".tex",
    ".json", ".csv", ".svg", ".yml", ".yaml", ".toml",
}
VIDEO_SUFFIXES = {".ts", ".tsx", ".json", ".png", ".webm"}
EXTRA_FILES = [
    ".env.example",
    ".gitignore",
    "NOTICE.md",
    "README.md",
    "docs/PUBLIC_REPOSITORY.md",
    "data/download_log.csv",
    "data/report_index.csv",
    "dashboard_web/index.html",
    "outputs/ai_contest/submission/OFFICIAL_SHA256SUMS.txt",
    "outputs/ai_contest/submission/final_submission_checklist.json",
    "outputs/ai_contest/submission/final_submission_checklist.md",
    "outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_参赛作品简介.pdf",
    "outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_项目文档.pdf",
]
EXCLUDED_PUBLIC_FILES = {
    "dashboard_web/src/pages/NaturalGoldPage.tsx",
    "scripts/build_natural_gold.py",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_files() -> list[Path]:
    root = PROJECT_ROOT / "video/claimguard-remotion"
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in VIDEO_SUFFIXES
        and "node_modules" not in path.parts
        and ".cache" not in path.parts
    )


def collect_public_files() -> list[Path]:
    files = set(collect_files())
    files.update(video_files())
    missing: list[str] = []
    for relative in EXTRA_FILES:
        path = PROJECT_ROOT / relative
        if path.is_file():
            files.add(path)
        else:
            missing.append(relative)
    if missing:
        raise FileNotFoundError(f"public snapshot files missing: {missing}")
    return sorted(
        (path for path in files if str(path.relative_to(PROJECT_ROOT)) not in EXCLUDED_PUBLIC_FILES),
        key=lambda path: str(path.relative_to(PROJECT_ROOT)),
    )


def validate_path(relative: str, path: Path) -> None:
    parts = Path(relative).parts
    forbidden = {".git", "node_modules", "__pycache__", ".cache", "logs", "parsed", "raw_pdfs", "models"}
    if path.is_symlink() or forbidden.intersection(parts):
        raise RuntimeError(f"unsafe public repository path: {relative}")
    if relative.startswith(("/", "\\")) or ".." in parts or "\\" in relative:
        raise RuntimeError(f"non-portable archive path: {relative}")
    if re.search(r"(^|/)(?:\.env(?:\.|$)|id_rsa|id_ed25519|credentials?|secrets?)(/|$)|\.(?:pem|key)$", relative, re.I):
        raise RuntimeError(f"sensitive filename in public repository: {relative}")


def validate_text(relative: str, payload: bytes) -> None:
    if Path(relative).suffix.lower() not in TEXT_SUFFIXES:
        return
    text = payload.decode("utf-8", errors="replace")
    markers = [
        "/data/" + "sues01",
        "/home/" + "sues01",
        "BEGIN " + "OPENSSH PRIVATE KEY",
        "BEGIN " + "RSA PRIVATE KEY",
    ]
    found = [marker for marker in markers if marker in text]
    if re.search(r"Bearer\s+[A-Za-z0-9._-]{12,}", text):
        found.append("Bearer token")
    if found:
        raise RuntimeError(f"sensitive or local content in {relative}: {found}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized public repository ZIP.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--team", default="队不起队不起")
    parser.add_argument("--competition-group", default="开放赛题-生成式大语言模型与智能体")
    parser.add_argument("--submission-date", default="2026年8月31日")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    identity = {
        "team_name": args.team,
        "competition_group": args.competition_group,
        "submission_date": args.submission_date,
    }
    entries: list[dict[str, object]] = []
    payloads: list[tuple[str, bytes]] = []
    for path in collect_public_files():
        relative = str(path.relative_to(PROJECT_ROOT))
        validate_path(relative, path)
        payload = archive_bytes(path, identity)
        validate_text(relative, payload)
        payloads.append((relative, payload))
        entries.append({"path": relative, "bytes": len(payload), "sha256": sha256_bytes(payload)})
    paths = [relative for relative, _ in payloads]
    if len(paths) != len(set(paths)):
        raise RuntimeError("public repository paths are not unique")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": "ESG ClaimGuard",
        "team": args.team,
        "kind": "clean_public_repository_snapshot_without_git_history_or_heavy_runtime_assets",
        "excluded": [".git", "raw_pdfs", "parsed", "models", "logs", "node_modules", "caches", "final video and voiceover"],
        "files": entries,
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, payload in payloads:
            archive.writestr(relative, payload)
        archive.writestr("PUBLIC_REPOSITORY_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    size = output.stat().st_size
    if size > MAX_BYTES:
        raise RuntimeError(f"public repository exceeds 200 MiB: {size}")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("public repository ZIP integrity check failed")
    report = {
        "output": str(output.relative_to(PROJECT_ROOT)),
        "files": len(entries) + 1,
        "bytes": size,
        "mib": round(size / 1024 / 1024, 3),
        "sha256": sha256_file(output),
        "under_200_mib": True,
        "sensitive_scan_passed": True,
        "zip_integrity": True,
    }
    report_path = output.with_suffix(".validation.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
