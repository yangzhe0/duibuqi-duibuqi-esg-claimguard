from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = [
    "超过赛题最低要求",
    "没有重跑",
    "简单实现",
    "初步探索",
    "由于时间有限",
    "本文只是",
    "随便选取",
    "效果很好",
    "准确率很高",
    "Precision",
    "Recall",
    "F1",
    "architecture_svg_style_general",
    "dashboard.html",
    "fig_market_year_distribution",
    "复现命令",
    "bash build.sh",
    "latex_final/scripts",
    "outputs/formal_v2",
    "data/raw_pdfs",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    required = [
        "MathModel.tex",
        "MathModel.pdf",
        "references.bib",
        "figure_contracts.md",
        "figure_gallery.html",
        "SELF_CHECK.md",
        "build.sh",
        "tables/stats.json",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            fail(f"missing {rel}")

    text = (ROOT / "MathModel.tex").read_text(encoding="utf-8")
    self_check = (ROOT / "SELF_CHECK.md").read_text(encoding="utf-8")
    combined = text + "\n" + self_check
    for word in FORBIDDEN:
        if word in combined:
            fail(f"forbidden expression found: {word}")
    if re.search(r"found/missing/error.{0,20}(准确率|精确率|召回率|F1)", combined):
        fail("found/missing/error is described with forbidden evaluation language")

    contracts = json.loads((ROOT / "tables/figure_contracts.json").read_text(encoding="utf-8"))
    if len(contracts) < 12:
        fail("too few figure contracts")
    contract_files = {item["file"] for item in contracts}
    for expected in ("fig_year_distribution", "fig_market_distribution", "fig_system_ui_overview", "fig_system_ui_evidence"):
        if expected not in contract_files:
            fail(f"missing required figure contract: {expected}")
    if "fig_market_year_distribution" in contract_files:
        fail("mixed year/market figure must not be present")
    for item in contracts:
        base = item["file"]
        if not (ROOT / "figures" / f"{base}.svg").exists():
            fail(f"missing SVG for {base}")
        if not (ROOT / "figures" / f"{base}.png").exists():
            fail(f"missing PNG for {base}")
        if f"{base}" not in text:
            fail(f"figure {base} is not referenced in MathModel.tex")

    stats = json.loads((ROOT / "tables/stats.json").read_text(encoding="utf-8"))
    if stats["dataset"]["pdf_count"] != 200:
        fail("unexpected PDF count")
    if stats["indicators"]["count"] != 65:
        fail("unexpected indicator count")
    if stats["results"]["row_count"] != 13000:
        fail("unexpected extraction row count")

    print("verification passed")


if __name__ == "__main__":
    main()
