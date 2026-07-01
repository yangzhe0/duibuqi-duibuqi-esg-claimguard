from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    contracts_path = ROOT / "tables/figure_contracts.json"
    contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
    lines = ["# Figure Contracts", ""]
    for item in contracts:
        lines.extend([
            f"## 图 {item['number']} {item['title']}",
            "",
            f"- 图文件：`figures/{item['file']}.svg`，`figures/{item['file']}.png`",
            f"- 核心结论：{item['core_claim']}",
            f"- 数据来源：{item['data_source']}",
            f"- 生成脚本：`{item['script']}`",
            f"- 正文引用位置：{item['text_location']}",
            f"- 评审可能质疑点：{item['review_risk']}",
            f"- 图表是否基于真实统计：{'是' if item['real_statistic'] else '否，属于模型/流程结构图'}",
            f"- 是否生成 SVG：{'是' if item['has_svg'] else '否'}",
            f"- 是否生成 PNG：{'是' if item['has_png'] else '否'}",
            "",
        ])
    (ROOT / "figure_contracts.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote latex/figure_contracts.md")


if __name__ == "__main__":
    main()
