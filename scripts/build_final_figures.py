#!/usr/bin/env python3
"""Build publication figures from the self-contained formal dataset."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "outputs/final_results"
OUT = ROOT / "latex/figures"

PALETTE = {
    "blue": "#0F4D92",
    "blue2": "#3775BA",
    "green": "#42949E",
    "green2": "#8BCF8B",
    "red": "#B64342",
    "grey": "#767676",
    "light": "#CFCECE",
    "dark": "#272727",
}

CONTRACTS = [
    {"id": "fig_pipeline", "claim": "顺序部署把文档感知、语义抽取和确定性证据门分离，并保留人工处置出口。", "evidence": "系统组件及数据流", "type": "流程图"},
    {"id": "fig_scale_status", "claim": "正式链路完整覆盖 200×65 网格，结果只含 found/missing。", "evidence": "200 报告、10,528 页、13,000 行及状态计数", "type": "双面板柱状图"},
    {"id": "fig_dimension_coverage", "claim": "found 分布在 E/S/G 三个维度间存在差异，但这里只表示语料披露覆盖。", "evidence": "按维度的 found/missing 计数与 found 比例", "type": "堆叠柱状图"},
    {"id": "fig_report_distribution", "claim": "不同报告的 ESG-65 found 数量呈现明显离散分布。", "evidence": "200 份报告的 found 数直方图与分位数", "type": "直方图"},
    {"id": "fig_inference", "claim": "Qwen3.6 全量生成调用在单卡顺序链路中完成且 error=0；耗时直方图仅统计具有 elapsed_seconds 的结果行。", "evidence": "生成调用运行汇总与有耗时记录的结果行分布", "type": "直方图+运行级指标卡"},
    {"id": "fig_evidence_gate", "claim": "完成门分别呈现数值来源与单位来源，并把 found 结果绑定到严格原串证据。", "evidence": "validation.json 中的严格 quote、value origin、unit origin 与人工核验计数", "type": "三面板柱状图"},
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def setup() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.sans-serif": ["Noto Sans CJK SC", "Droid Sans Fallback", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
            "font.size": 8,
            "axes.labelsize": 9,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
        }
    )


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def label_panel(ax, letter: str) -> None:
    ax.text(-0.08, 1.08, letter, transform=ax.transAxes, fontsize=18, fontweight="bold", va="top")


def pipeline() -> None:
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.set_axis_off()
    items = [
        ("冻结 PDF", "200 份\n10,528 页", PALETTE["grey"]),
        ("MinerU2.5", "OCR / 版面\n表格 / bbox", PALETTE["blue2"]),
        ("候选召回", "ESG-65\n块级上下文", PALETTE["green"]),
        ("Qwen3.6", "固定 JSON\n温度 0", PALETTE["blue"]),
        ("确定性门", "原串证据\nlineage / 派生", PALETTE["red"]),
        ("人工处置", "确认 / 修正\n补材 / 排除", PALETTE["green2"]),
    ]
    xs = np.linspace(0.07, 0.93, len(items))
    for i, ((title, body, color), x) in enumerate(zip(items, xs)):
        ax.add_patch(plt.Rectangle((x - 0.07, 0.34), 0.14, 0.34, transform=ax.transAxes, facecolor=color, edgecolor="none", alpha=0.94))
        ax.text(x, 0.57, title, transform=ax.transAxes, ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        ax.text(x, 0.43, body, transform=ax.transAxes, ha="center", va="center", color="white", fontsize=8.5)
        if i < len(items) - 1:
            ax.annotate("", xy=(xs[i + 1] - 0.075, 0.51), xytext=(x + 0.075, 0.51), xycoords=ax.transAxes, arrowprops={"arrowstyle": "->", "color": PALETTE["dark"], "lw": 1.4})
    ax.text(0.5, 0.88, "ESG ClaimGuard 正式链路", transform=ax.transAxes, ha="center", fontsize=15, fontweight="bold", color=PALETTE["dark"])
    ax.text(0.5, 0.16, "MinerU 与 Qwen 顺序驻留；任何 found 必须回到同报告、同页、同 block 的 canonical 原文", transform=ax.transAxes, ha="center", color=PALETTE["grey"])
    save(fig, "fig_pipeline")


def main() -> int:
    setup()
    rows = read_csv(RUN / "extraction/extraction_results.csv")
    validation = json.loads((RUN / "validation.json").read_text())
    summary = json.loads((RUN / "extraction/run_summary.json").read_text())
    manual = read_csv(RUN / "extraction/manual_reconciliation.csv")
    pipeline()

    status = Counter(row["status"] for row in rows)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    axes[0].bar(["报告", "页", "指标", "结果网格"], [200, 10528, 65, 13000], color=[PALETTE["grey"], PALETTE["blue2"], PALETTE["green"], PALETTE["blue"]])
    axes[0].set_yscale("log"); axes[0].set_ylabel("规模（对数坐标）")
    for i, v in enumerate([200, 10528, 65, 13000]): axes[0].text(i, v * 1.12, f"{v:,}", ha="center", fontsize=8)
    axes[1].bar(["found", "missing", "error"], [status["found"], status["missing"], status["error"]], color=[PALETTE["blue"], PALETTE["light"], PALETTE["red"]])
    axes[1].set_ylabel("report × indicator 行数")
    for i, k in enumerate(["found", "missing", "error"]): axes[1].text(i, status[k] + 160, f"{status[k]:,}", ha="center", fontsize=8)
    label_panel(axes[0], "a"); label_panel(axes[1], "b"); fig.suptitle("正式数据规模与结果状态", fontsize=13, fontweight="bold")
    save(fig, "fig_scale_status")

    dims = ["E", "S", "G"]
    dc = {d: Counter(row["status"] for row in rows if row["dimension"] == d) for d in dims}
    found = np.array([dc[d]["found"] for d in dims]); missing = np.array([dc[d]["missing"] for d in dims])
    fig, ax = plt.subplots(figsize=(7.6, 4.6)); x = np.arange(3)
    ax.bar(x, found, color=PALETTE["blue"], label="found"); ax.bar(x, missing, bottom=found, color=PALETTE["light"], label="missing")
    ax.set_xticks(x, ["环境 E（25项）", "社会 S（20项）", "治理 G（20项）"]); ax.set_ylabel("结果行数"); ax.legend(loc="upper right")
    for i, (f, m) in enumerate(zip(found, missing)): ax.text(i, f / 2, f"{f:,}\n{f/(f+m):.1%}", ha="center", va="center", color="white", fontweight="bold")
    ax.set_title("三维度披露覆盖分布（非准确率）", fontsize=13, fontweight="bold"); save(fig, "fig_dimension_coverage")

    by_report = defaultdict(int)
    for row in rows:
        by_report[row["report_id"]] += row["status"] == "found"
    counts = np.array(list(by_report.values()))
    fig, ax = plt.subplots(figsize=(7.6, 4.6)); ax.hist(counts, bins=np.arange(counts.min() - .5, counts.max() + 1.5, 3), color=PALETTE["blue2"], edgecolor="white")
    ax.axvline(np.median(counts), color=PALETTE["red"], lw=1.5, label=f"中位数 {np.median(counts):.0f}")
    ax.set_xlabel("单报告 found 指标数（共 65 项）"); ax.set_ylabel("报告数"); ax.legend(); ax.set_title("200 份报告的 found 数量分布", fontsize=13, fontweight="bold")
    save(fig, "fig_report_distribution")

    elapsed = np.array([float(row["elapsed_seconds"]) for row in rows if float(row.get("elapsed_seconds") or 0) > 0])
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    axes[0].hist(elapsed, bins=45, color=PALETTE["blue"], edgecolor="white"); axes[0].axvline(np.median(elapsed), color=PALETTE["red"], label=f"中位数 {np.median(elapsed):.2f}s")
    axes[0].set_xlabel("有耗时记录的结果行：elapsed_seconds（秒）"); axes[0].set_ylabel("结果行数"); axes[0].legend(); label_panel(axes[0], "a")
    axes[1].set_axis_off(); cards = [("运行级生成调用", f"{summary['generation_calls']:,}"), ("有耗时记录的结果行", f"{len(elapsed):,}"), ("总墙钟", f"{summary['elapsed_seconds']/3600:.2f} h"), ("模型错误", str(summary['llm_error_count']))]
    for i, (k, v) in enumerate(cards):
        y = 0.82 - i * .2; axes[1].text(.1, y, k, transform=axes[1].transAxes, color=PALETTE["grey"], fontsize=9); axes[1].text(.92, y, v, transform=axes[1].transAxes, ha="right", fontsize=15, fontweight="bold", color=PALETTE["blue"])
    label_panel(axes[1], "b"); fig.suptitle("Qwen3.6 全量推理运行证据", fontsize=13, fontweight="bold"); save(fig, "fig_inference")

    q = validation["counts"]
    value_direct = q["quantitative_direct"]
    value_derived = q["quantitative_derived"]
    unit_normalized = q["quantitative_normalized_or_inferred_unit"]
    unit_direct = q["quantitative_found"] - unit_normalized
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.2))
    axes[0].bar(["严格原串 found", "人工核验", "证据失败"], [q["evidence_contract"]["valid_found_rows"], len(manual), q["evidence_contract"]["failure_count"]], color=[PALETTE["blue"], PALETTE["green"], PALETTE["red"]])
    axes[0].set_ylabel("行数"); label_panel(axes[0], "a")
    value_vals = [value_direct, value_derived]
    axes[1].bar(["直接读取", "显式派生"], value_vals, color=[PALETTE["blue"], PALETTE["green"]]); axes[1].set_title("value origin"); label_panel(axes[1], "b")
    unit_vals = [unit_direct, unit_normalized]
    axes[2].bar(["原文单位", "规范化/推断"], unit_vals, color=[PALETTE["blue2"], PALETTE["grey"]]); axes[2].set_title("unit origin"); label_panel(axes[2], "c")
    for ax, values in zip(axes, [[q["evidence_contract"]["valid_found_rows"], len(manual), q["evidence_contract"]["failure_count"]], value_vals, unit_vals]):
        for i, v in enumerate(values): ax.text(i, v + max(values) * .025, f"{v:,}", ha="center", fontsize=8)
    fig.suptitle("证据完成门与定量 lineage（来源分面）", fontsize=13, fontweight="bold"); save(fig, "fig_evidence_gate")

    stats = {
        "reports": len(by_report), "pages": 10528, "indicators": 65, "rows": len(rows), "statuses": status,
        "dimension": {d: dict(dc[d]) for d in dims}, "report_found": {"min": int(counts.min()), "median": float(np.median(counts)), "max": int(counts.max())},
        "inference": {"calls": summary["generation_calls"], "elapsed_seconds": summary["elapsed_seconds"], "median_row_seconds": float(np.median(elapsed)), "p95_row_seconds": float(np.quantile(elapsed, .95))},
        "evidence": q,
    }
    (OUT / "figure_contracts.json").write_text(json.dumps(CONTRACTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=dict) + "\n", encoding="utf-8")
    cards = "\n".join(f'<article><h2>{c["id"]}</h2><p>{c["claim"]}</p><img src="{c["id"]}.png" alt="{c["id"]}"></article>' for c in CONTRACTS)
    (OUT / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><title>ESG ClaimGuard 图表</title><style>body{{font-family:sans-serif;background:#eef4f1;margin:30px}}article{{background:white;padding:24px;margin:20px auto;max-width:1100px}}img{{width:100%;height:auto}}</style>{cards}', encoding="utf-8")
    print(json.dumps({"figures": len(CONTRACTS), "output": str(OUT.relative_to(ROOT)), "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
