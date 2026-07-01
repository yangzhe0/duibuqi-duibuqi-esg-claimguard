from __future__ import annotations

import html
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from paper_data import OUT, collect_stats, write_json, write_tables


FIG = OUT / "figures"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


PALETTE = {
    "green": "#2F7D5A",
    "blue": "#2B6CB0",
    "gold": "#B7791F",
    "red": "#C2413B",
    "gray": "#4A5568",
    "light": "#F7FAFC",
    "line": "#CBD5E0",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def svg_text(x: int, y: int, text: str, size: int = 24, color: str = "#1A202C", weight: str = "400", anchor: str = "middle") -> str:
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Noto Serif CJK SC, SimSun, serif" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(text)}</text>'


def save_svg_png(name: str, svg: str, png_drawer=None, size: tuple[int, int] = (1400, 900)) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    svg_path = FIG / f"{name}.svg"
    png_path = FIG / f"{name}.png"
    svg_path.write_text(svg, encoding="utf-8")
    if png_drawer:
        image = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(image)
        png_drawer(draw)
    else:
        image = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(image)
        draw.text((40, 40), name, fill="#1A202C", font=font(38, True))
        draw.text((40, 100), "请查看同名 SVG 图。", fill="#4A5568", font=font(28))
    image.save(png_path, dpi=(320, 320))


def draw_bar_png(title: str, labels: list[str], values: list[int], colors: list[str], size=(1400, 900)):
    def drawer(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle([0, 0, size[0], size[1]], fill="white")
        draw.text((60, 45), title, fill="#1A202C", font=font(38, True))
        max_v = max(values) if values else 1
        left, top, width, gap = 260, 145, 900, 58
        for idx, (label, value) in enumerate(zip(labels, values)):
            y = top + idx * gap
            bar_w = int(width * value / max_v)
            draw.text((60, y + 5), label, fill="#1A202C", font=font(24))
            draw.rounded_rectangle([left, y, left + bar_w, y + 34], radius=4, fill=colors[idx % len(colors)])
            draw.text((left + bar_w + 16, y + 1), str(value), fill="#1A202C", font=font(24, True))
        draw.line([left, size[1] - 95, left + width, size[1] - 95], fill="#CBD5E0", width=2)
        draw.text((60, size[1] - 72), "数据来源：项目既有结构化输出统计生成", fill="#4A5568", font=font(20))
    return drawer


def bar_svg(name: str, title: str, labels: list[str], values: list[int], colors: list[str], w=1400, h=900) -> None:
    max_v = max(values) if values else 1
    left, top, width, gap = 300, 150, 920, 58
    elems = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">', '<rect width="100%" height="100%" fill="white"/>']
    elems.append(svg_text(60, 72, title, 38, "#1A202C", "700", "start"))
    for idx, (label, value) in enumerate(zip(labels, values)):
        y = top + idx * gap
        bar_w = int(width * value / max_v)
        elems.append(svg_text(60, y + 26, label, 24, "#1A202C", "400", "start"))
        elems.append(f'<rect x="{left}" y="{y}" width="{bar_w}" height="34" rx="4" fill="{colors[idx % len(colors)]}"/>')
        elems.append(svg_text(left + bar_w + 16, y + 27, str(value), 24, "#1A202C", "700", "start"))
    elems.append(f'<line x1="{left}" y1="{h-95}" x2="{left+width}" y2="{h-95}" stroke="#CBD5E0" stroke-width="2"/>')
    elems.append(svg_text(60, h - 55, "数据来源：项目既有结构化输出统计生成", 20, "#4A5568", "400", "start"))
    elems.append("</svg>")
    save_svg_png(name, "\n".join(elems), draw_bar_png(title, labels, values, colors, (w, h)), (w, h))


def pie_svg(name: str, title: str, data: dict[str, int], colors: list[str]) -> None:
    labels = list(data.keys())
    values = list(data.values())
    total = sum(values) or 1
    w, h = 1200, 850
    cx, cy, r = 380, 430, 230
    start = -90
    elems = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">', '<rect width="100%" height="100%" fill="white"/>']
    elems.append(svg_text(60, 72, title, 38, "#1A202C", "700", "start"))
    for i, value in enumerate(values):
        angle = 360 * value / total
        end = start + angle
        large = 1 if angle > 180 else 0
        x1 = cx + r * math.cos(math.radians(start))
        y1 = cy + r * math.sin(math.radians(start))
        x2 = cx + r * math.cos(math.radians(end))
        y2 = cy + r * math.sin(math.radians(end))
        elems.append(f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} Z" fill="{colors[i % len(colors)]}" stroke="white" stroke-width="3"/>')
        start = end
    for i, (label, value) in enumerate(zip(labels, values)):
        y = 250 + i * 70
        elems.append(f'<rect x="720" y="{y-26}" width="34" height="34" rx="4" fill="{colors[i % len(colors)]}"/>')
        elems.append(svg_text(775, y, f"{label}：{value}（{value/total:.1%}）", 28, "#1A202C", "400", "start"))
    elems.append(svg_text(60, h - 55, "数据来源：报告标识元数据统计", 20, "#4A5568", "400", "start"))
    elems.append("</svg>")

    def drawer(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle([0, 0, w, h], fill="white")
        draw.text((60, 45), title, fill="#1A202C", font=font(38, True))
        start_ang = -90
        for i, value in enumerate(values):
            ang = 360 * value / total
            draw.pieslice([cx - r, cy - r, cx + r, cy + r], start_ang, start_ang + ang, fill=colors[i % len(colors)], outline="white", width=3)
            start_ang += ang
        for i, (label, value) in enumerate(zip(labels, values)):
            y = 224 + i * 70
            draw.rounded_rectangle([720, y, 754, y + 34], radius=4, fill=colors[i % len(colors)])
            draw.text((775, y - 5), f"{label}：{value}（{value/total:.1%}）", fill="#1A202C", font=font(28))
        draw.text((60, h - 72), "数据来源：报告标识元数据统计", fill="#4A5568", font=font(20))

    save_svg_png(name, "\n".join(elems), drawer, (w, h))


def flow_svg(name: str, title: str, nodes: list[str], subtitle: str) -> None:
    w, h = 1600, 820
    elems = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">', '<rect width="100%" height="100%" fill="white"/>']
    elems.append(svg_text(60, 72, title, 38, "#1A202C", "700", "start"))
    x0, y0, bw, bh, gap = 80, 190, 250, 90, 48
    for i, node in enumerate(nodes):
        x = x0 + (i % 5) * (bw + gap)
        y = y0 + (i // 5) * 190
        color = [PALETTE["green"], PALETTE["blue"], PALETTE["gold"], PALETTE["gray"], PALETTE["red"]][i % 5]
        elems.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="#FFFFFF" stroke="{color}" stroke-width="3"/>')
        parts = node.split("\\n")
        for j, part in enumerate(parts):
            elems.append(svg_text(x + bw // 2, y + 37 + j * 30, part, 24, "#1A202C", "700" if j == 0 else "400"))
        if i < len(nodes) - 1:
            nx = x0 + ((i + 1) % 5) * (bw + gap)
            ny = y0 + ((i + 1) // 5) * 190
            if (i + 1) % 5:
                elems.append(f'<path d="M {x+bw} {y+bh/2} L {nx-18} {ny+bh/2}" stroke="#718096" stroke-width="3" fill="none" marker-end="url(#arrow)"/>')
            else:
                elems.append(f'<path d="M {x+bw/2} {y+bh} C {x+bw/2} {y+150}, {nx+bw/2} {ny-80}, {nx+bw/2} {ny-18}" stroke="#718096" stroke-width="3" fill="none" marker-end="url(#arrow)"/>')
    elems.insert(2, '<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M2,2 L10,6 L2,10 Z" fill="#718096"/></marker></defs>')
    elems.append(svg_text(80, h - 70, subtitle, 22, "#4A5568", "400", "start"))
    elems.append("</svg>")

    def drawer(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle([0, 0, w, h], fill="white")
        draw.text((60, 43), title, fill="#1A202C", font=font(38, True))
        for i, node in enumerate(nodes):
            x = x0 + (i % 5) * (bw + gap)
            y = y0 + (i // 5) * 190
            color = [PALETTE["green"], PALETTE["blue"], PALETTE["gold"], PALETTE["gray"], PALETTE["red"]][i % 5]
            draw.rounded_rectangle([x, y, x + bw, y + bh], radius=8, outline=color, width=3, fill="white")
            for j, part in enumerate(node.split("\\n")):
                bbox = draw.textbbox((0, 0), part, font=font(23, j == 0))
                draw.text((x + bw / 2 - (bbox[2]-bbox[0]) / 2, y + 17 + j * 32), part, fill="#1A202C", font=font(23, j == 0))
            if i < len(nodes) - 1 and (i + 1) % 5:
                draw.line([x + bw, y + bh / 2, x + bw + gap - 18, y + bh / 2], fill="#718096", width=3)
        draw.text((80, h - 88), subtitle, fill="#4A5568", font=font(22))

    save_svg_png(name, "\n".join(elems), drawer, (w, h))


def build_all() -> None:
    stats = collect_stats()
    write_json(OUT / "tables/stats.json", stats)
    write_tables(stats)

    for stale in ("fig_market_year_distribution.png", "fig_market_year_distribution.svg"):
        stale_path = FIG / stale
        if stale_path.exists():
            stale_path.unlink()

    pie_svg("fig_dataset_composition", "样本报告类型构成", stats["dataset"]["report_type_counts"], [PALETTE["green"], PALETTE["blue"], PALETTE["gold"], PALETTE["red"]])
    bar_svg("fig_year_distribution", "报告年份分布", [f"{k}年" for k in stats["dataset"]["year_counts"].keys()], list(stats["dataset"]["year_counts"].values()), [PALETTE["green"], PALETTE["gold"]], 1100, 620)
    bar_svg("fig_market_distribution", "市场代码类型分布", list(stats["dataset"]["market_counts"].keys()), list(stats["dataset"]["market_counts"].values()), [PALETTE["blue"], PALETTE["green"]], 1200, 620)
    bar_svg("fig_parse_scale", "MinerU 解析产物规模", ["页数", "Markdown字符/1000", "表格标记", "图片引用", "标题行"], [int(stats["parsed"]["pages"]["sum"]), int(stats["parsed"]["chars"]["sum"] / 1000), int(stats["parsed"]["table_markers"]["sum"]), int(stats["parsed"]["image_refs"]["sum"]), int(stats["parsed"]["headings"]["sum"])], [PALETTE["green"], PALETTE["blue"], PALETTE["gold"]])
    block_counts = dict(list(stats["parsed"]["block_type_counts"].items())[:10])
    bar_svg("fig_block_type_distribution", "内容块类型分布（前十类）", list(block_counts.keys()), list(block_counts.values()), [PALETTE["blue"], PALETTE["green"], PALETTE["gold"], PALETTE["gray"]], 1500, 920)
    bar_svg("fig_indicator_system", "ESG-65 指标体系结构", list(stats["indicators"]["by_dimension"].keys()) + list(stats["indicators"]["by_type"].keys()), list(stats["indicators"]["by_dimension"].values()) + list(stats["indicators"]["by_type"].values()), [PALETTE["green"], PALETTE["blue"], PALETTE["gold"], PALETTE["red"], PALETTE["gray"]], 1300, 760)
    bar_svg("fig_result_status", "13,000 个 report-indicator 任务结果分布", list(stats["results"]["status_counts"].keys()), list(stats["results"]["status_counts"].values()), [PALETTE["green"], PALETTE["gray"], PALETTE["red"]], 1200, 700)
    dim_labels = [f"{k}-total" for k in stats["results"]["by_dimension_total"]] + [f"{k}-found" for k in stats["results"]["by_dimension_found"]]
    dim_values = list(stats["results"]["by_dimension_total"].values()) + list(stats["results"]["by_dimension_found"].values())
    bar_svg("fig_dimension_result", "E/S/G 维度任务与 found 分布", dim_labels, dim_values, [PALETTE["gray"], PALETTE["green"], PALETTE["blue"]], 1300, 800)
    type_labels = [f"{k}-total" for k in stats["results"]["by_type_total"]] + [f"{k}-found" for k in stats["results"]["by_type_found"]]
    type_values = list(stats["results"]["by_type_total"].values()) + list(stats["results"]["by_type_found"].values())
    bar_svg("fig_type_result", "指标类型任务与 found 分布", type_labels, type_values, [PALETTE["gray"], PALETTE["gold"], PALETTE["blue"]], 1400, 820)
    bar_svg("fig_candidate_funnel", "候选证据召回与抽取链路漏斗", ["总任务", "候选为空", "进入模型", "found", "missing"], [stats["results"]["row_count"], stats["results"]["candidate_empty"], stats["results"]["candidate_positive"], stats["results"]["status_counts"].get("found", 0), stats["results"]["status_counts"].get("missing", 0)], [PALETTE["gray"], PALETTE["red"], PALETTE["blue"], PALETTE["green"], PALETTE["gold"]], 1300, 780)
    bar_svg("fig_risk_distribution", "质量诊断风险类型分布", list(stats["risk"]["by_issue"].keys()), list(stats["risk"]["by_issue"].values()), [PALETTE["red"], PALETTE["gold"], PALETTE["blue"], PALETTE["green"], PALETTE["gray"]], 1500, 900)
    bar_svg("fig_risk_level", "风险等级与复核样本结构", list(stats["risk"]["by_level"].keys()) + ["复核样本", "需人工关注"], list(stats["risk"]["by_level"].values()) + [stats["review_summary"].get("total_review_samples", 0), stats["review_summary"].get("needs_manual_check_count", 0)], [PALETTE["red"], PALETTE["gold"], PALETTE["green"], PALETTE["blue"]], 1300, 760)
    flow_svg("fig_overall_pipeline", "证据约束型 ESG 长文档结构化抽取技术路线", ["原始 PDF\\n200份报告", "MinerU解析\\nJSON/Markdown", "内容块建模\\n页码与块号", "ESG-65指标\\n三类字段", "report-indicator\\n13000任务", "候选证据召回\\nTop-k证据", "约束抽取\\nJSON Schema", "后处理\\n字段修复", "质量诊断\\n风险样本", "Streamlit复核\\n闭环展示"], "流程图遵循 Figure Contract：每个节点对应可追溯的数据文件或输出表。")
    flow_svg("fig_block_model", "PDF 到内容块的结构化表示模型", ["PDF页面", "文本/标题", "表格块", "图片资源", "page_no", "block_id", "block_type", "text", "证据空间", "候选集合"], "内容块是后续召回、抽取和复核定位的最小证据单元。")
    flow_svg("fig_extraction_schema", "候选证据约束抽取与 JSON 输出", ["任务(i,j)", "候选证据Eij", "证据不足\\nmissing", "qwen3语义抽取", "value/unit", "qualitative_text", "boolean evidence", "evidence_quote", "page/block", "risk_tag"], "模型只在候选证据范围内抽取，输出字段用于可追溯复核。")
    flow_svg("fig_quality_loop", "后处理、质量诊断与交互式复核闭环", ["JSON解析", "字段完整性", "单位修复", "零事件归一", "风险规则", "抽样复核", "公司视角", "指标视角", "证据核验", "CSV下载"], "风险样本用于组织复核优先级，不替代完整人工真值集。")
    flow_svg("fig_streamlit_architecture", "Streamlit 可追溯复核系统功能架构", ["系统总览", "公司视角", "指标视角", "证据核验", "高风险样本", "新报告接入", "evidence_quote", "page_no", "block_id", "risk_tag"], "系统页面直接绑定结构化字段，形成结果查看、定位和下载闭环。")

    contracts = []
    for idx, path in enumerate(sorted(FIG.glob("*.svg")), start=1):
        base = path.stem
        contracts.append({
            "number": idx,
            "file": base,
            "title": base.replace("fig_", "").replace("_", " "),
            "core_claim": "支撑正文对数据、模型链路、结果分布或复核闭环的论证。",
            "data_source": "仓库既有 CSV/JSON/Markdown 统计或根据模型结构绘制。",
            "script": "latex/scripts/build_figures.py",
            "text_location": "MathModel.tex 对应章节",
            "review_risk": "检查是否将运行结果分布误写为人工标注评价结论。",
            "real_statistic": base not in {"fig_overall_pipeline", "fig_block_model", "fig_extraction_schema", "fig_quality_loop", "fig_streamlit_architecture"},
            "has_svg": True,
            "has_png": (FIG / f"{base}.png").exists(),
        })
    write_json(OUT / "tables/figure_contracts.json", contracts)
    print(f"generated {len(contracts)} figure contracts")


if __name__ == "__main__":
    build_all()
