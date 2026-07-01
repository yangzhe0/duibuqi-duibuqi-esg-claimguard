from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"


def main() -> None:
    contracts_path = ROOT / "tables/figure_contracts.json"
    contracts = json.loads(contracts_path.read_text(encoding="utf-8")) if contracts_path.exists() else []
    cards = []
    for item in contracts:
        base = item["file"]
        png = f"figures/{base}.png"
        svg = f"figures/{base}.svg"
        cards.append(
            f"""
            <section class="card">
              <h2>图 {item['number']}：{item['title']}</h2>
              <img src="{png}" alt="{item['title']}">
              <p><strong>核心结论：</strong>{item['core_claim']}</p>
              <p><strong>数据来源：</strong>{item['data_source']}</p>
              <p><strong>正文位置：</strong>{item['text_location']}</p>
              <p><strong>评审风险：</strong>{item['review_risk']}</p>
              <p><a href="{svg}">SVG</a> · <a href="{png}">PNG</a></p>
            </section>
            """
        )
    html = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>Figure Gallery</title>
<style>
body {{ margin: 0; font-family: system-ui, -apple-system, "Noto Sans CJK SC", sans-serif; color: #1a202c; background: #f7fafc; }}
header {{ padding: 28px 42px; background: #fff; border-bottom: 1px solid #e2e8f0; }}
main {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 18px; padding: 22px; }}
.card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; }}
h1 {{ margin: 0; font-size: 28px; }}
h2 {{ font-size: 20px; margin: 0 0 12px; }}
img {{ width: 100%; border: 1px solid #edf2f7; }}
p {{ line-height: 1.55; }}
a {{ color: #2b6cb0; }}
</style>
<header><h1>ESG 结构化抽取论文图表面板</h1><p>由 latex/scripts/build_gallery.py 生成，用于统一检查图表与 Figure Contract。</p></header>
<main>
{''.join(cards)}
</main>
</html>
"""
    (ROOT / "figure_gallery.html").write_text(html, encoding="utf-8")
    print("wrote latex/figure_gallery.html")


if __name__ == "__main__":
    main()
