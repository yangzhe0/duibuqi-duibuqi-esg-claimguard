#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from markdown_it import MarkdownIt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "docs/ai_contest/submission"
OUTPUT_ROOT = PROJECT_ROOT / "outputs/ai_contest/submission/drafts"
PAPER_SOURCE = PROJECT_ROOT / "latex/ESG_ClaimGuard_技术论文.md"
VALIDATION_PATH = PROJECT_ROOT / "outputs/formal_v3_mineru25_qwen36/validation.json"
DOCX_IMAGE_MAX_WIDTH_EMU = 5_800_000  # ~160 mm, safely inside the 170 mm A4 text area.

CSS = """
@page { size: A4; margin: 22mm 20mm 20mm; }
body { font-family: 'Noto Serif CJK SC', 'Source Han Serif SC', serif; color: #1d2923; font-size: 11pt; line-height: 1.65; }
h1 { text-align: center; color: #173f33; font-size: 18pt; margin: 22mm 0 10mm; white-space: nowrap; }
h2 { color: #185b46; font-size: 16pt; border-bottom: 1px solid #9cb7ac; padding-bottom: 3mm; page-break-after: avoid; }
h3 { color: #2c6653; font-size: 13pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 4mm 0; font-size: 9pt; }
img { display: block; max-width: 100%; height: auto; margin: 5mm auto; page-break-inside: avoid; }
th, td { border: 1px solid #aab9b3; padding: 2mm; vertical-align: top; }
th { background: #e5f0eb; color: #173f33; }
th:first-child, td:first-child { min-width: 24mm; }
blockquote { margin: 4mm 0; padding: 2mm 4mm; background: #f1f5f3; border-left: 3px solid #4f8873; }
pre { white-space: pre-wrap; background: #f5f7f6; border: 1px solid #d5ded9; padding: 3mm; font-family: 'Noto Sans Mono CJK SC', monospace; }
.page-break { page-break-before: always; break-before: page; }
.draft { position: fixed; top: 6mm; right: 10mm; color: #a33; font: bold 10pt sans-serif; }
.cover { min-height: 230mm; text-align: center; page-break-inside: avoid; }
.competition { padding-top: 18mm; font: 15pt 'Noto Sans CJK SC', sans-serif; letter-spacing: 1pt; }
.cover-title { margin-top: 45mm; font: bold 30pt 'Noto Sans CJK SC', sans-serif; color: #173f33; white-space: nowrap; }
.cover-subtitle { margin-top: 5mm; font: 18pt 'Noto Sans CJK SC', sans-serif; color: #2c6653; white-space: nowrap; }
.document-type { margin-top: 18mm; font: bold 22pt 'Noto Sans CJK SC', sans-serif; }
.version { margin-top: 5mm; font: 13pt 'Noto Sans CJK SC', sans-serif; }
.cover-meta { margin-top: 35mm; font: 12pt/2 'Noto Sans CJK SC', sans-serif; }
"""


def markdown_to_html(markdown: str, title: str, draft: bool) -> str:
    renderer = MarkdownIt("commonmark", {"html": True}).enable("table")
    body = renderer.render(markdown)
    # LibreOffice interprets a bare HTML pixel width against the PNG's 300-DPI
    # intrinsic height and can flatten wide figures into unreadable strips.
    # A percentage width keeps the source aspect ratio in both DOCX and PDF.
    body = body.replace("<img ", '<img style="width:100%;height:auto" ')
    marker = '<div class="draft">内部草案 · 替换占位符后方可提交</div>' if draft else ""
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><base href=\""
        + PROJECT_ROOT.as_uri()
        + "/\"><title>"
        + html.escape(title)
        + "</title><style>"
        + CSS
        + "</style></head><body>"
        + marker
        + body
        + "</body></html>"
    )


def intro_markdown(source: str, team: str, submission_date: str) -> str:
    match = re.search(r"## 300 字以内正文\s+(.*?)(?:\n> 口径说明|\Z)", source, flags=re.S)
    if not match:
        raise ValueError("cannot locate 300-character introduction body")
    return (
        "# ESG ClaimGuard<br>可持续披露一致性预审系统\n\n"
        f"**团队：{team}　日期：{submission_date}**\n\n"
        + match.group(1).strip()
        + "\n"
    )


def inject_submission_identity(markdown: str, team: str, competition_group: str, submission_date: str) -> str:
    """Resolve cover metadata from explicit build parameters."""
    context = {
        "team_name": team,
        "competition_group": competition_group,
        "submission_date": submission_date,
    }
    for key, value in context.items():
        markdown = markdown.replace("{{" + key + "}}", value)
    unresolved = sorted(set(re.findall(r"\{\{(?:team_name|competition_group|submission_date)\}\}", markdown)))
    if unresolved:
        raise ValueError(f"unresolved submission identity placeholders: {unresolved}")
    return markdown


def inject_validation_counts(markdown: str) -> str:
    """Resolve formal-data placeholders at render time from validation.json."""
    validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
    counts = validation["counts"]
    normalized_units = counts["quantitative_normalized_or_inferred_unit"]
    context = {
        "found": counts["found"],
        "missing": counts["result_rows"] - counts["found"] - counts["errors"],
        "errors": counts["errors"],
        "quantitative_found": counts["quantitative_found"],
        "quantitative_direct": counts["quantitative_direct"],
        "quantitative_derived": counts["quantitative_derived"],
        "quantitative_unit_direct": counts["quantitative_found"] - normalized_units,
        "quantitative_normalized_or_inferred_unit": normalized_units,
        "evidence_failure_count": counts["evidence_contract"]["failure_count"],
    }
    for key, value in context.items():
        markdown = markdown.replace("{{" + key + "}}", f"{value:,}")
    unresolved = sorted(set(re.findall(r"\{\{[a-z_]+\}\}", markdown)))
    if unresolved:
        raise ValueError(f"unresolved validation placeholders: {unresolved}")
    return markdown


def libreoffice_convert(source: Path, target_format: str, output_dir: Path, profile: Path) -> Path:
    filter_name = {
        "docx": "docx:Office Open XML Text",
        "pdf": "pdf:writer_pdf_Export",
    }[target_format]
    command = [
        "libreoffice",
        f"-env:UserInstallation={profile.as_uri()}",
        "--headless",
        "--convert-to",
        filter_name,
        "--outdir",
        str(output_dir),
        str(source),
    ]
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(result.stdout)
    target = output_dir / f"{source.stem}.{target_format}"
    if not target.is_file():
        raise RuntimeError(f"LibreOffice did not create {target}: {result.stdout}")
    return target


def force_a4_docx(path: Path) -> None:
    """Normalize A4 geometry, embed linked figures, and add centered page numbers."""
    with zipfile.ZipFile(path, "r") as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]
    payload_by_name = {item.filename: payload for item, payload in entries}
    relationships_name = "word/_rels/document.xml.rels"
    relationships = payload_by_name[relationships_name].decode("utf-8")
    embedded_images: dict[str, tuple[str, bytes]] = {}

    def embed_relationship(match: re.Match[str]) -> str:
        tag = match.group(0)
        relation_id = re.search(r'\bId="([^"]+)"', tag)
        target = re.search(r'\bTarget="([^"]+)"', tag)
        if (
            not relation_id
            or not target
            or "relationships/image" not in tag
            or 'TargetMode="External"' not in tag
        ):
            return tag
        source_uri = html.unescape(target.group(1))
        parsed = urlparse(source_uri)
        source_path = Path(unquote(parsed.path if parsed.scheme == "file" else source_uri))
        if not source_path.is_file():
            raise FileNotFoundError(f"linked DOCX image is missing: {source_path}")
        suffix = source_path.suffix.lower() or ".png"
        archive_relative = f"media/claimguard-{relation_id.group(1)}{suffix}"
        embedded_images[relation_id.group(1)] = (f"word/{archive_relative}", source_path.read_bytes())
        tag = re.sub(r'\s+TargetMode="External"', "", tag)
        return re.sub(r'\bTarget="[^"]+"', f'Target="{archive_relative}"', tag)

    relationships = re.sub(r"<Relationship\b[^>]*/>", embed_relationship, relationships)

    def fit_drawing(match: re.Match[str]) -> str:
        drawing = match.group(0)
        extent = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', drawing)
        if not extent:
            return drawing
        width, height = int(extent.group(1)), int(extent.group(2))
        if width <= DOCX_IMAGE_MAX_WIDTH_EMU:
            return drawing
        ratio = DOCX_IMAGE_MAX_WIDTH_EMU / width
        fitted_width = DOCX_IMAGE_MAX_WIDTH_EMU
        fitted_height = round(height * ratio)
        drawing = drawing.replace(
            f'<wp:extent cx="{width}" cy="{height}"/>',
            f'<wp:extent cx="{fitted_width}" cy="{fitted_height}"/>',
        )
        drawing = drawing.replace(
            f'<a:ext cx="{width}" cy="{height}"/>',
            f'<a:ext cx="{fitted_width}" cy="{fitted_height}"/>',
        )
        return drawing

    changed = False
    rewritten: list[tuple[zipfile.ZipInfo, bytes]] = []
    for item, payload in entries:
        if item.filename == "word/document.xml":
            xml = payload.decode("utf-8")
            xml, replacements = re.subn(
                r"<w:pgSz\b[^>]*/>",
                '<w:pgSz w:w="11906" w:h="16838"/>',
                xml,
            )
            if not replacements:
                raise RuntimeError("DOCX has no section page-size element")
            def add_footer_reference(match: re.Match[str]) -> str:
                section = match.group(0)
                if "footerReference" in section:
                    return section
                opening_end = section.index(">") + 1
                reference = '<w:footerReference w:type="default" r:id="rIdClaimGuardFooter"/>'
                return section[:opening_end] + reference + section[opening_end:]

            xml, section_count = re.subn(
                r"<w:sectPr\b[^>]*>.*?</w:sectPr>",
                add_footer_reference,
                xml,
                flags=re.S,
            )
            if not section_count:
                raise RuntimeError("DOCX has no section properties")
            xml = re.sub(r"<w:drawing>.*?</w:drawing>", fit_drawing, xml, flags=re.S)
            for relation_id in embedded_images:
                xml = xml.replace(f'r:link="{relation_id}"', f'r:embed="{relation_id}"')
            payload = xml.encode("utf-8")
            changed = True
        elif item.filename == "word/_rels/document.xml.rels":
            xml = relationships
            if "rIdClaimGuardFooter" not in xml:
                relationship = (
                    '<Relationship Id="rIdClaimGuardFooter" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
                    'Target="footer1.xml"/>'
                )
                xml = xml.replace("</Relationships>", relationship + "</Relationships>")
            payload = xml.encode("utf-8")
        elif item.filename == "[Content_Types].xml":
            xml = payload.decode("utf-8")
            if '<Default Extension="png"' not in xml:
                xml = xml.replace(
                    "</Types>",
                    '<Default Extension="png" ContentType="image/png"/></Types>',
                )
            if 'PartName="/word/footer1.xml"' not in xml:
                override = (
                    '<Override PartName="/word/footer1.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                )
                xml = xml.replace("</Types>", override + "</Types>")
            payload = xml.encode("utf-8")
        rewritten.append((item, payload))
    if not changed:
        raise RuntimeError("DOCX document.xml was not found")
    temporary = path.with_suffix(".a4.tmp")
    footer_xml = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:pPr><w:jc w:val="center"/></w:pPr>
    <w:r><w:fldChar w:fldCharType="begin"/></w:r>
    <w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
    <w:r><w:fldChar w:fldCharType="end"/></w:r>
  </w:p>
</w:ftr>'''
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for item, payload in rewritten:
            target.writestr(item, payload)
        for archive_name, payload in embedded_images.values():
            target.writestr(archive_name, payload)
        if not any(item.filename == "word/footer1.xml" for item, _ in rewritten):
            target.writestr("word/footer1.xml", footer_xml)
    temporary.replace(path)


def render_one(markdown: str, stem: str, output_dir: Path, draft: bool) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="claimguard-render-") as temporary_dir:
        temporary = Path(temporary_dir)
        html_path = temporary / f"{stem}.html"
        html_path.write_text(markdown_to_html(markdown, stem, draft), encoding="utf-8")
        profile = temporary / "lo-profile"
        profile.mkdir()
        docx_path = libreoffice_convert(html_path, "docx", output_dir, profile)
        force_a4_docx(docx_path)
        pdf_path = libreoffice_convert(docx_path, "pdf", output_dir, profile)
        # Older revisions persisted the conversion HTML beside deliverables.  It
        # contained a machine-local absolute base URI; remove it only after both
        # durable formats have been created successfully.
        (output_dir / f"{stem}.html").unlink(missing_ok=True)
    return {"docx": str(docx_path), "pdf": str(pdf_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render AI-contest project, introduction, and technical-paper documents to DOCX/PDF.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--team", default="队不起队不起")
    parser.add_argument("--competition-group", default="开放赛题-生成式大语言模型与智能体")
    parser.add_argument("--submission-date", default="2026年8月31日")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    if args.final and any(marker in value for value in (args.team, args.competition_group, args.submission_date) for marker in ("待定", "待确认", "YYYY")):
        parser.error("--final requires confirmed --team, --competition-group, and --submission-date values")
    if any(character in args.team for character in "/\\"):
        parser.error("--team cannot contain path separators")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    project_source = (SOURCE_ROOT / "ESG_ClaimGuard_项目文档.md").read_text(encoding="utf-8")
    project_md = inject_validation_counts(
        inject_submission_identity(project_source, args.team, args.competition_group, args.submission_date)
    )
    intro_source = (SOURCE_ROOT / "ESG_ClaimGuard_参赛作品简介_300字.md").read_text(encoding="utf-8")
    paper_md = inject_validation_counts(PAPER_SOURCE.read_text(encoding="utf-8"))
    suffix = "" if args.final else "_草案"
    project_stem = f"{args.team}_ESG ClaimGuard_项目文档{suffix}"
    intro_stem = f"{args.team}_ESG ClaimGuard_参赛作品简介{suffix}"
    results = [
        render_one(project_md, project_stem, args.output_dir, not args.final),
        render_one(intro_markdown(intro_source, args.team, args.submission_date), intro_stem, args.output_dir, not args.final),
        render_one(paper_md, f"ESG_ClaimGuard_技术论文{suffix}", args.output_dir, not args.final),
    ]
    for result in results:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
