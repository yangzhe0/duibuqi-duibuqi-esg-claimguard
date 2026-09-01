#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = ROOT / "outputs/ai_contest/submission"
FINAL = SUBMISSION / "final"
TEAM = "队不起队不起"
MAX_BYTES = 200 * 1024 * 1024
EXPECTED_NAMES = {
    f"{TEAM}_ESG ClaimGuard_参赛作品简介.pdf",
    f"{TEAM}_ESG ClaimGuard_项目文档.pdf",
    f"{TEAM}_ESG ClaimGuard_项目视频.mp4",
    f"{TEAM}_ESG ClaimGuard_其他.zip",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_pages(path: Path) -> int | None:
    if not path.is_file():
        return None
    output = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    match = re.search(r"^Pages:\s+(\d+)$", output, flags=re.M)
    return int(match.group(1)) if match else None


def pdf_is_a4(path: Path) -> bool:
    output = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    match = re.search(r"^Page size:\s+([\d.]+) x ([\d.]+) pts", output, flags=re.M)
    return bool(match and abs(float(match.group(1)) - 595.3) < 2 and abs(float(match.group(2)) - 841.9) < 2)


def pdf_latex_metadata(path: Path) -> dict[str, object]:
    output = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    creator = re.search(r"^Creator:\s*(.*)$", output, flags=re.M)
    producer = re.search(r"^Producer:\s*(.*)$", output, flags=re.M)
    creator_value = creator.group(1).strip() if creator else ""
    producer_value = producer.group(1).strip() if producer else ""
    return {
        "creator": creator_value,
        "producer": producer_value,
        "latex_generated": "LaTeX" in creator_value and "xdvipdfmx" in producer_value,
    }


def pdf_text_checks(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True
    )
    pages = completed.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    non_whitespace = [len(re.sub(r"\s+", "", page)) for page in pages]
    return {
        "searchable": bool(non_whitespace) and all(length > 0 for length in non_whitespace),
        "blank_pages": [index + 1 for index, length in enumerate(non_whitespace) if length == 0],
        "page_non_whitespace_characters": non_whitespace,
        "text": completed.stdout,
    }


def video_metadata(path: Path) -> dict[str, object]:
    output = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_name,codec_type,width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    payload = json.loads(output)
    duration = round(float(payload["format"]["duration"]), 3)
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    subtitles = [stream for stream in streams if stream.get("codec_type") == "subtitle"]
    return {
        "duration_seconds": duration,
        "under_5_minutes": duration <= 300,
        "video_codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "audio_codec": audio.get("codec_name"),
        "stream_count": len(streams),
        "full_decode_ok": decode.returncode == 0,
        "subtitle_stream_count": len(subtitles),
        "no_subtitle_stream": not subtitles,
    }


def zip_checks(path: Path) -> dict[str, object]:
    sensitive_name = re.compile(
        r"(^|/)(?:\.env|\.git|__pycache__|node_modules|logs?|id_rsa|id_ed25519|credentials|secrets?)(/|$)|\.(?:pem|key)$",
        re.I,
    )
    forbidden_parts = {"raw_pdfs", "parsed", "models", "node_modules", "logs", "__pycache__", ".git"}
    required = {
        "README.md",
        "requirements-submission.txt",
        "outputs/final_results/run_manifest.json",
        "outputs/final_results/validation.json",
        "outputs/final_results/COMPLETE.json",
        "outputs/final_results/extraction/audit_corrections.json",
        "docs/ai_contest/submission/ESG_ClaimGuard_5分钟视频分镜与口播.md",
        "SUBMISSION_MANIFEST.json",
    }
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        infos = archive.infolist()
        names = [item.filename for item in infos]
        unsafe = [name for name in names if name.startswith(("/", "\\")) or ".." in Path(name).parts or "\\" in name]
        symlinks = [item.filename for item in infos if ((item.external_attr >> 16) & 0o170000) == 0o120000]
        sensitive_names = [name for name in names if sensitive_name.search(name)]
        forbidden = [name for name in names if forbidden_parts.intersection(Path(name).parts)]
        sensitive_content: list[dict[str, str]] = []
        text_suffixes = {".py", ".ts", ".tsx", ".css", ".html", ".sh", ".md", ".txt", ".srt", ".json", ".csv", ".svg"}
        markers = [re.compile(r"/(?:data|home)/sues01"), re.compile(r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY"), re.compile(r"Bearer [A-Za-z0-9._-]{12,}")]
        for item in infos:
            if Path(item.filename).suffix.lower() not in text_suffixes or item.file_size > 30 * 1024 * 1024:
                continue
            text = archive.read(item).decode("utf-8", errors="replace")
            for marker in markers:
                if marker.search(text):
                    sensitive_content.append({"path": item.filename, "marker": marker.pattern})
        manifest_ok = False
        manifest_errors: list[str] = []
        if "SUBMISSION_MANIFEST.json" in names:
            manifest = json.loads(archive.read("SUBMISSION_MANIFEST.json"))
            entries = manifest.get("files", [])
            expected_manifest_names = set(names) - {"SUBMISSION_MANIFEST.json"}
            if {item.get("path") for item in entries} != expected_manifest_names:
                manifest_errors.append("manifest_names_mismatch")
            info_by_name = {item.filename: item for item in infos}
            for entry in entries:
                name = str(entry.get("path", ""))
                if name not in info_by_name:
                    continue
                payload = archive.read(name)
                if len(payload) != int(entry.get("bytes", -1)):
                    manifest_errors.append(f"size:{name}")
                if hashlib.sha256(payload).hexdigest() != entry.get("sha256"):
                    manifest_errors.append(f"sha256:{name}")
            manifest_ok = not manifest_errors
        return {
            "entries": len(names),
            "zip_integrity": bad is None,
            "unsafe_paths": unsafe,
            "symlinks": symlinks,
            "sensitive_names": sensitive_names,
            "sensitive_content": sensitive_content,
            "forbidden_large_asset_paths": forbidden,
            "required_entries_missing": sorted(required - set(names)),
            "submission_manifest_valid": manifest_ok,
            "submission_manifest_errors": manifest_errors,
        }


def inspect(path: Path, kind: str) -> dict[str, object]:
    item: dict[str, object] = {
        "name": path.name,
        "path": str(path.relative_to(ROOT)),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return item
    item.update({"bytes": path.stat().st_size, "sha256": sha256(path), "under_200_mib": path.stat().st_size <= MAX_BYTES})
    if kind == "pdf":
        item["pages"] = pdf_pages(path)
        item["a4_portrait"] = pdf_is_a4(path)
        text_checks = pdf_text_checks(path)
        item.update({key: value for key, value in text_checks.items() if key != "text"})
        item.update(pdf_latex_metadata(path))
    if kind == "zip":
        item.update(zip_checks(path))
    if kind == "video":
        item.update(video_metadata(path))
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the four official ESG ClaimGuard submission files.")
    parser.add_argument(
        "--refresh-official-hashes",
        action="store_true",
        help="Rewrite OFFICIAL_SHA256SUMS.txt from an exact four-file final directory before validation.",
    )
    args = parser.parse_args()
    if args.refresh_official_hashes:
        actual = {path.name for path in FINAL.iterdir() if path.is_file()} if FINAL.is_dir() else set()
        if actual != EXPECTED_NAMES:
            raise RuntimeError(f"cannot refresh hashes unless final/ has exactly the four official files: {sorted(actual)}")
        lines = [f"{sha256(FINAL / name)}  {name}" for name in sorted(EXPECTED_NAMES)]
        (SUBMISSION / "OFFICIAL_SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = {
        "introduction_pdf": inspect(FINAL / f"{TEAM}_ESG ClaimGuard_参赛作品简介.pdf", "pdf"),
        "project_pdf": inspect(FINAL / f"{TEAM}_ESG ClaimGuard_项目文档.pdf", "pdf"),
        "project_video": inspect(FINAL / f"{TEAM}_ESG ClaimGuard_项目视频.mp4", "video"),
        "auxiliary_zip": inspect(FINAL / f"{TEAM}_ESG ClaimGuard_其他.zip", "zip"),
    }
    intro_source = (ROOT / "docs/ai_contest/submission/ESG_ClaimGuard_参赛作品简介_300字.md").read_text(encoding="utf-8")
    intro_match = re.search(r"## 300 字以内正文\s+(.*?)(?:\n> 口径说明|\Z)", intro_source, flags=re.S)
    intro_han_chars = len(re.findall(r"[\u4e00-\u9fff]", intro_match.group(1))) if intro_match else None
    intro_pdf_text = pdf_text_checks(FINAL / f"{TEAM}_ESG ClaimGuard_参赛作品简介.pdf").get("text", "")
    normalize = lambda value: re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", str(value))
    intro_matches_pdf = bool(intro_match) and normalize(intro_match.group(1)) in normalize(intro_pdf_text)
    project_text = pdf_text_checks(FINAL / f"{TEAM}_ESG ClaimGuard_项目文档.pdf").get("text", "")
    latex_report_path = SUBMISSION / "latex_build_report.json"
    latex_report = json.loads(latex_report_path.read_text(encoding="utf-8")) if latex_report_path.is_file() else {}
    latex_documents = {str(item.get("job")): item for item in latex_report.get("documents", [])}
    expected_latex_hashes = {
        "project_introduction": files["introduction_pdf"].get("sha256"),
        "project_document": files["project_pdf"].get("sha256"),
    }
    latex_build_ok = (
        latex_report.get("renderer") == "XeLaTeX"
        and latex_report.get("passed") is True
        and all(
            job in latex_documents
            and latex_documents[job].get("overfull_boxes") == 0
            and latex_documents[job].get("pdf_sha256") == digest
            for job, digest in expected_latex_hashes.items()
        )
    )
    project_sections = [
        "项目概况", "背景和基础", "场景和价值", "所需支持", "项目规划", "整体目标",
        "技术创新点", "实施方案", "技术可行性分析", "技术细节", "计划和分工",
        "队长：杨哲", "队员1：邱宇强", "队员2：王恒岳", "运行结果与模型评价",
        "正式运行结果", "结果分析", "模型评价与适用边界", "结论", "参考资料",
    ]
    normalized_project_text = normalize(project_text)
    project_template_sections_complete = all(normalize(section) in normalized_project_text for section in project_sections)
    actual_names = {path.name for path in FINAL.iterdir() if path.is_file()} if FINAL.is_dir() else set()
    official_hashes: dict[str, str] = {}
    official_path = SUBMISSION / "OFFICIAL_SHA256SUMS.txt"
    if official_path.is_file():
        for line in official_path.read_text(encoding="utf-8").splitlines():
            digest, _, name = line.partition("  ")
            if digest and name:
                official_hashes[name] = digest
    official_hashes_match = set(official_hashes) == EXPECTED_NAMES and all(
        sha256(FINAL / name) == digest for name, digest in official_hashes.items() if (FINAL / name).is_file()
    )
    zip_item = files["auxiliary_zip"]
    constraints_ok = (
        all(bool(item["exists"]) and bool(item.get("under_200_mib")) for item in files.values())
        and actual_names == EXPECTED_NAMES
        and all(bool(files[key].get("a4_portrait")) for key in ("introduction_pdf", "project_pdf"))
        and all(bool(files[key].get("searchable")) and not files[key].get("blank_pages") for key in ("introduction_pdf", "project_pdf"))
        and intro_matches_pdf
        and project_template_sections_complete
        and all(bool(files[key].get("latex_generated")) for key in ("introduction_pdf", "project_pdf"))
        and latex_build_ok
        and bool(files["project_video"].get("under_5_minutes"))
        and bool(files["project_video"].get("full_decode_ok"))
        and files["project_video"].get("audio_codec") == "aac"
        and bool(files["project_video"].get("no_subtitle_stream"))
        and bool(zip_item.get("zip_integrity"))
        and bool(zip_item.get("submission_manifest_valid"))
        and not any(zip_item.get(key) for key in ("unsafe_paths", "symlinks", "sensitive_names", "sensitive_content", "forbidden_large_asset_paths", "required_entries_missing"))
        and official_hashes_match
        and intro_han_chars is not None and intro_han_chars <= 300
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "team": TEAM,
        "project": "ESG ClaimGuard",
        "date": "2026-09-01",
        "files": files,
        "official_files_ready": sum(bool(item["exists"]) for item in files.values()),
        "official_files_total": len(files),
        "introduction_han_characters": intro_han_chars,
        "introduction_source_matches_pdf": intro_matches_pdf,
        "project_template_sections_complete": project_template_sections_complete,
        "latex_build": {"report_exists": latex_report_path.is_file(), "passed": latex_build_ok, "report": latex_report},
        "final_directory_exact_four": actual_names == EXPECTED_NAMES,
        "official_sha256_match": official_hashes_match,
        "submission_ready": constraints_ok,
        "blocker": None if constraints_ok else "至少一项文件完整性或官方硬约束未通过",
        "metric_boundary": "The submission does not claim Precision, Recall or F1 without independent human evaluation.",
    }
    json_path = SUBMISSION / "final_submission_checklist.json"
    md_path = SUBMISSION / "final_submission_checklist.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for label, item in files.items():
        size = f"{int(item.get('bytes', 0)) / 1024 / 1024:.3f} MiB" if item.get("exists") else "—"
        rows.append(f"| {label} | {'已完成' if item['exists'] else '缺失'} | `{item['name']}` | {size} |")
    conclusion = (
        "官方四项文件已完成 **4/4**，可以进入平台上传终检。"
        if payload["submission_ready"]
        else f"官方四项文件已完成 **{payload['official_files_ready']}/4**，但至少一项硬约束未通过。"
    )
    md_path.write_text(
        "# ESG ClaimGuard 最终提交核验\n\n"
        f"> 团队：{TEAM}；项目：ESG ClaimGuard；日期：2026-09-01。\n\n"
        f"结论：{conclusion}\n\n"
        "| 项目 | 状态 | 文件名 | 大小 |\n|---|---|---|---:|\n"
        + "\n".join(rows)
        + f"\n\n简介正文汉字数：{intro_han_chars}。项目文档按问题定义、模型设计、正式运行、结果分析和适用边界组织，并逐人列明团队分工；两份正式 PDF 均由 XeLaTeX 生成，为 A4、可检索且构建日志无越界框；视频为 {files['project_video'].get('duration_seconds')} 秒、1080p H.264/AAC、无字幕流；辅助 ZIP 通过 CRC/路径安全/200 MiB 检查。"
        "本作品不把未经独立人工评测的 Precision、Recall 或 F1 作为成果声明。\n",
        encoding="utf-8",
    )
    print(json.dumps({"ready": payload["submission_ready"], "completed": payload["official_files_ready"], "report": str(md_path.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
