#!/usr/bin/env python3
"""Render all formal ESG ClaimGuard documents through a deterministic XeLaTeX pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/ai_contest/submission"
PAPER_SOURCE = ROOT / "latex/ESG_ClaimGuard_技术论文.md"
TEX_SOURCE = ROOT / "latex/submission"
VALIDATION = ROOT / "outputs/formal_v3_mineru25_qwen36/validation.json"
DEFAULT_OUTPUT = ROOT / "outputs/ai_contest/submission/latex_stage"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def inject_identity(markdown: str, team: str, competition_group: str, submission_date: str) -> str:
    values = {
        "team_name": team,
        "competition_group": competition_group,
        "submission_date": submission_date,
    }
    for key, value in values.items():
        markdown = markdown.replace("{{" + key + "}}", value)
    return markdown


def inject_counts(markdown: str) -> str:
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    counts = validation["counts"]
    normalized = counts["quantitative_normalized_or_inferred_unit"]
    values = {
        "found": counts["found"],
        "missing": counts["result_rows"] - counts["found"] - counts["errors"],
        "errors": counts["errors"],
        "quantitative_found": counts["quantitative_found"],
        "quantitative_direct": counts["quantitative_direct"],
        "quantitative_derived": counts["quantitative_derived"],
        "quantitative_unit_direct": counts["quantitative_found"] - normalized,
        "quantitative_normalized_or_inferred_unit": normalized,
        "evidence_failure_count": counts["evidence_contract"]["failure_count"],
    }
    for key, value in values.items():
        markdown = markdown.replace("{{" + key + "}}", f"{value:,}")
    unresolved = re.findall(r"\{\{[a-z_]+\}\}", markdown)
    if unresolved:
        raise ValueError(f"unresolved placeholders: {sorted(set(unresolved))}")
    return markdown


def inline_latex(token) -> str:
    output: list[str] = []
    for child in token.children or []:
        kind = child.type
        if kind == "text":
            output.append(escape_latex(child.content))
        elif kind in {"softbreak", "hardbreak"}:
            output.append(" " if kind == "softbreak" else r"\newline ")
        elif kind == "strong_open":
            output.append(r"\textbf{")
        elif kind == "strong_close":
            output.append("}")
        elif kind == "em_open":
            output.append(r"\emph{")
        elif kind == "em_close":
            output.append("}")
        elif kind == "code_inline":
            output.append(r"\texttt{" + escape_latex(child.content) + "}")
        elif kind == "link_open":
            output.append("")
        elif kind == "link_close":
            output.append("")
        elif kind == "html_inline" and child.content.lower().startswith("<br"):
            output.append(r"\\")
        elif kind == "image":
            output.append(escape_latex(child.content))
        else:
            output.append(escape_latex(child.content or ""))
    return "".join(output).strip()


def strip_heading_number(text: str) -> str:
    return re.sub(r"^\d+(?:\.\d+)*\s+", "", text).strip()


def render_table(tokens, start: int) -> tuple[str, int]:
    rows: list[tuple[list[str], bool]] = []
    row: list[str] | None = None
    header_row = False
    index = start + 1
    while index < len(tokens) and tokens[index].type != "table_close":
        kind = tokens[index].type
        if kind == "tr_open":
            row = []
            header_row = False
        elif kind in {"th_open", "td_open"} and row is not None:
            header_row = header_row or kind == "th_open"
            if index + 1 < len(tokens) and tokens[index + 1].type == "inline":
                row.append(inline_latex(tokens[index + 1]))
        elif kind == "tr_close" and row is not None:
            rows.append((row, header_row))
            row = None
        index += 1
    columns = max((len(items) for items, _ in rows), default=1)
    size = r"\scriptsize" if columns >= 5 else r"\small"
    specification = "@{}" + "Y" * columns + "@{}"
    lines = [r"\begin{center}", size, r"\setlength{\tabcolsep}{4pt}", rf"\begin{{tabularx}}{{\textwidth}}{{{specification}}}", r"\toprule"]
    for row_index, (items, is_header) in enumerate(rows):
        padded = items + [""] * (columns - len(items))
        if is_header:
            lines.append(r"\rowcolor{brandpale} " + " & ".join(r"\textbf{" + item + "}" for item in padded) + r" \\")
            lines.append(r"\midrule")
        else:
            lines.append(" & ".join(padded) + r" \\")
            if row_index < len(rows) - 1:
                lines.append(r"\addlinespace[2pt]")
    lines.extend([r"\bottomrule", r"\end{tabularx}", r"\end{center}", ""])
    return "\n".join(lines), index + 1


def render_markdown(markdown: str) -> str:
    tokens = MarkdownIt("commonmark", {"html": True}).enable("table").parse(markdown)
    output: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        kind = token.type
        if kind == "heading_open" and index + 1 < len(tokens):
            level = int(token.tag[1])
            title = strip_heading_number(inline_latex(tokens[index + 1]))
            if title == "记录更改历史":
                output.append(r"\section*{记录更改历史}")
            else:
                command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
                output.append(rf"\{command}{{{title}}}")
            index += 3
            continue
        if kind == "paragraph_open" and index + 1 < len(tokens):
            inline = tokens[index + 1]
            images = [child for child in inline.children or [] if child.type == "image"]
            if images:
                for image in images:
                    source = image.attrGet("src") or ""
                    alt = escape_latex(image.content or "项目图表")
                    output.extend([
                        r"\begin{center}",
                        rf"\includegraphics[width=0.96\linewidth,height=0.72\textheight,keepaspectratio]{{\detokenize{{{source}}}}}",
                        rf"\par\small\color{{brandgray}} {alt}",
                        r"\end{center}",
                    ])
            else:
                content = inline_latex(inline)
                if content:
                    output.append(content + r"\par")
            index += 3
            continue
        if kind == "table_open":
            rendered, index = render_table(tokens, index)
            output.append(rendered)
            continue
        if kind == "ordered_list_open":
            output.append(r"\begin{enumerate}")
        elif kind == "ordered_list_close":
            output.append(r"\end{enumerate}")
        elif kind == "bullet_list_open":
            output.append(r"\begin{itemize}")
        elif kind == "bullet_list_close":
            output.append(r"\end{itemize}")
        elif kind == "list_item_open":
            output.append(r"\item ")
        elif kind == "blockquote_open":
            output.append(r"\begin{quote}\color{brandgray}")
        elif kind == "blockquote_close":
            output.append(r"\end{quote}")
        elif kind in {"fence", "code_block"}:
            output.append(r"\begin{verbatim}" + "\n" + token.content.rstrip() + "\n" + r"\end{verbatim}")
        elif kind == "html_block":
            lowered = token.content.lower()
            if "page-break" in lowered:
                output.append(r"\clearpage")
            elif "auto-toc" in lowered:
                output.extend([r"\tableofcontents", r"\clearpage"])
        index += 1
    return "\n\n".join(output)


def preamble(title: str) -> str:
    return rf"""\documentclass[UTF8,a4paper,11pt]{{ctexart}}
\usepackage[a4paper,top=22mm,bottom=20mm,left=20mm,right=20mm,headheight=15pt]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{tabularx}}
\usepackage{{array}}
\usepackage[table]{{xcolor}}
\usepackage{{enumitem}}
\usepackage{{fancyhdr}}
\usepackage{{hyperref}}
\setmainfont{{Noto Serif CJK SC}}
\setsansfont{{Noto Sans CJK SC}}
\setmonofont{{DejaVu Sans Mono}}
\setCJKmainfont{{Noto Serif CJK SC}}
\setCJKsansfont{{Noto Sans CJK SC}}
\definecolor{{brand}}{{HTML}}{{185B46}}
\definecolor{{branddark}}{{HTML}}{{173F33}}
\definecolor{{brandpale}}{{HTML}}{{E5F0EB}}
\definecolor{{brandgray}}{{HTML}}{{566B62}}
\hypersetup{{unicode=true,colorlinks=true,linkcolor=brand,urlcolor=brand,pdftitle={{{escape_latex(title)}}}}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyfoot[C]{{\thepage}}
\renewcommand{{\headrulewidth}}{{0pt}}
\setlength{{\parindent}}{{2em}}
\setlength{{\parskip}}{{0.35em}}
\renewcommand{{\arraystretch}}{{1.35}}
\newcolumntype{{Y}}{{>{{\raggedright\arraybackslash}}X}}
\setlist{{leftmargin=2.2em,itemsep=0.25em,topsep=0.35em}}
\ctexset{{
  section={{format=\Large\bfseries\color{{branddark}},beforeskip=1.4em,afterskip=0.7em}},
  subsection={{format=\large\bfseries\color{{brand}},beforeskip=1.1em,afterskip=0.5em}},
  subsubsection={{format=\normalsize\bfseries\color{{brand}},beforeskip=0.9em,afterskip=0.4em}}
}}
\emergencystretch=3em
\raggedbottom
\begin{{document}}
"""


def project_cover(team: str, competition_group: str, submission_date: str) -> str:
    return rf"""\begin{{titlepage}}
\thispagestyle{{empty}}
\centering
{{\Large\sffamily 第八届中国研究生人工智能创新大赛\par}}
\vspace{{40mm}}
{{\fontsize{{30}}{{36}}\selectfont\bfseries\sffamily\color{{branddark}} ESG ClaimGuard\par}}
\vspace{{5mm}}
{{\LARGE\sffamily\color{{brand}} 可持续披露一致性预审系统\par}}
\vspace{{18mm}}
{{\LARGE\bfseries\sffamily 项目文档\par}}
\vspace{{5mm}}
{{\large\sffamily 版本 v1.0\par}}
\vfill
\begin{{tabular}}{{rl}}
日期： & {escape_latex(submission_date)} \\
团队名称： & {escape_latex(team)} \\
参赛组别： & {escape_latex(competition_group)}
\end{{tabular}}
\vspace{{18mm}}
\end{{titlepage}}
"""


def simple_cover(title: str, subtitle: str = "") -> str:
    subtitle_line = rf"\vspace{{6mm}}{{\Large\color{{brand}} {escape_latex(subtitle)}\par}}" if subtitle else ""
    return rf"""\begin{{center}}
{{\fontsize{{23}}{{30}}\selectfont\bfseries\sffamily\color{{branddark}} {escape_latex(title)}\par}}
{subtitle_line}
\vspace{{10mm}}
\end{{center}}
"""


def prepare_project(markdown: str) -> str:
    markdown = re.sub(
        r"\A<div class=\"cover\">.*?<div class=\"page-break\"></div>",
        "",
        markdown,
        flags=re.S,
    )
    markdown = re.sub(
        r"# 目录.*?<div class=\"page-break\"></div>",
        '<div class="auto-toc"></div>',
        markdown,
        count=1,
        flags=re.S,
    )
    return markdown.strip()


def introduction_body(markdown: str) -> str:
    match = re.search(r"## 300 字以内正文\s+(.*?)(?:\n> 口径说明|\Z)", markdown, flags=re.S)
    if not match:
        raise ValueError("cannot locate introduction body")
    return match.group(1).strip()


def paper_body(markdown: str) -> tuple[str, str]:
    match = re.match(r"#\s+(.+?)\n", markdown)
    if not match:
        raise ValueError("paper title is missing")
    return match.group(1).strip(), markdown[match.end():].strip()


def compile_tex(tex_path: Path, output_dir: Path, jobname: str) -> tuple[Path, dict[str, object]]:
    build_dir = output_dir / "latex-build" / jobname
    build_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
        f"-outdir={build_dir}", f"-jobname={jobname}", str(tex_path),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path = build_dir / f"{jobname}.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else result.stdout
    overfull = re.findall(r"Overfull \\[hv]box", log)
    if result.returncode or overfull:
        raise RuntimeError(
            f"XeLaTeX failed for {jobname}: returncode={result.returncode}, overfull_boxes={len(overfull)}\n"
            + result.stdout[-5000:]
        )
    pdf_path = build_dir / f"{jobname}.pdf"
    if not pdf_path.is_file():
        raise RuntimeError(f"XeLaTeX did not create {pdf_path}")
    return pdf_path, {"overfull_boxes": 0, "log": str(log_path.relative_to(ROOT))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render formal submission PDFs with XeLaTeX.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--team", default="队不起队不起")
    parser.add_argument("--competition-group", default="开放赛题-生成式大语言模型与智能体")
    parser.add_argument("--submission-date", default="2026年8月31日")
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    TEX_SOURCE.mkdir(parents=True, exist_ok=True)

    project_md = inject_counts(inject_identity((SOURCE / "ESG_ClaimGuard_项目文档.md").read_text(encoding="utf-8"), args.team, args.competition_group, args.submission_date))
    intro_md = (SOURCE / "ESG_ClaimGuard_参赛作品简介_300字.md").read_text(encoding="utf-8")
    paper_md = inject_counts(PAPER_SOURCE.read_text(encoding="utf-8"))
    paper_title, paper_content = paper_body(paper_md)

    documents = [
        {
            "job": "project_document",
            "tex_name": "ESG_ClaimGuard_项目文档.tex",
            "output_name": f"{args.team}_ESG ClaimGuard_项目文档.pdf",
            "tex": preamble("ESG ClaimGuard 项目文档")
            + project_cover(args.team, args.competition_group, args.submission_date)
            + render_markdown(prepare_project(project_md))
            + "\n\\end{document}\n",
        },
        {
            "job": "project_introduction",
            "tex_name": "ESG_ClaimGuard_参赛作品简介.tex",
            "output_name": f"{args.team}_ESG ClaimGuard_参赛作品简介.pdf",
            "tex": preamble("ESG ClaimGuard 参赛作品简介")
            + simple_cover("ESG ClaimGuard", "可持续披露一致性预审系统")
            + render_markdown(introduction_body(intro_md))
            + "\n\\end{document}\n",
        },
        {
            "job": "technical_paper",
            "tex_name": "ESG_ClaimGuard_技术论文.tex",
            "output_name": "ESG_ClaimGuard_技术论文.pdf",
            "tex": preamble(paper_title)
            + simple_cover(paper_title)
            + render_markdown(paper_content)
            + "\n\\end{document}\n",
        },
    ]

    results = []
    for document in documents:
        tex_path = TEX_SOURCE / str(document["tex_name"])
        tex_path.write_text(str(document["tex"]), encoding="utf-8")
        compiled, checks = compile_tex(tex_path, args.output_dir, str(document["job"]))
        destination = args.output_dir / str(document["output_name"])
        shutil.copy2(compiled, destination)
        results.append({
            "job": document["job"],
            "tex": str(tex_path.relative_to(ROOT)),
            "pdf": str(destination.relative_to(ROOT)),
            "pdf_sha256": sha256(destination),
            **checks,
        })
    report = {"renderer": "XeLaTeX", "passed": True, "documents": results}
    report_path = args.output_dir / "latex_build_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
