#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_MANIFEST = PROJECT_ROOT / "data/evaluation/natural_gold/v1/pilot30/manifest.csv"
RESULT_DIR = PROJECT_ROOT / "outputs/ai_contest/natural_gold_pilot30"
FIGURE_DIR = RESULT_DIR / "figures"
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

COLORS = {
    "E": "#1F7A5A",
    "S": "#3973B7",
    "G": "#B98517",
    "silver_a": "#375A7F",
    "silver_b": "#D88136",
    "found": "#238B68",
    "missing": "#B94A48",
    "uncertain": "#9A7B2F",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def setup_style() -> None:
    if FONT_PATH.is_file():
        font_manager.fontManager.addfont(str(FONT_PATH))
        plt.rcParams["font.family"] = "Noto Sans CJK SC"
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "svg.fonttype": "none",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def clean_axes(axis) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(axis="both", length=0)
    axis.grid(False)


def label_bars(axis, bars, suffix: str = "") -> None:
    for bar in bars:
        value = bar.get_height()
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value + max(axis.get_ylim()[1] * 0.018, 0.08),
            f"{value:g}{suffix}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )


def save_figure(figure, stem: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_DIR / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    figure.savefig(FIGURE_DIR / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def plot_composition(pilot: list[dict[str, str]]) -> None:
    dimensions = Counter(row["dimension"] for row in pilot)
    indicator_types = Counter(row["indicator_type"] for row in pilot)
    figure, axes = plt.subplots(1, 2, figsize=(11.8, 4.4), gridspec_kw={"wspace": 0.28})
    figure.suptitle("Pilot-30：小样本但覆盖完整的分层设计", fontsize=15, fontweight="bold", y=1.03)

    dim_labels = ["环境 E", "社会 S", "治理 G"]
    dim_keys = ["E", "S", "G"]
    bars = axes[0].bar(dim_labels, [dimensions[key] for key in dim_keys], color=[COLORS[key] for key in dim_keys], width=0.58)
    axes[0].set_title("a  ESG 维度严格均衡")
    axes[0].set_ylabel("任务数")
    axes[0].set_ylim(0, 12)
    axes[0].set_yticks([0, 5, 10])
    label_bars(axes[0], bars)
    clean_axes(axes[0])

    type_keys = ["quantitative", "boolean", "qualitative"]
    type_labels = ["定量指标", "是非指标", "定性指标"]
    type_colors = ["#347C98", "#7E6BA8", "#6D8A45"]
    bars = axes[1].bar(type_labels, [indicator_types[key] for key in type_keys], color=type_colors, width=0.58)
    axes[1].set_title("b  三类指标均有覆盖")
    axes[1].set_ylabel("任务数")
    axes[1].set_ylim(0, 19)
    axes[1].set_yticks([0, 5, 10, 15])
    label_bars(axes[1], bars)
    clean_axes(axes[1])

    figure.text(0.5, -0.02, "30 个任务对应 30 个不同指标；机器草稿仅用于辅助人工核验。", ha="center", fontsize=9, color="#555555")
    save_figure(figure, "figure_1_pilot_composition")


def plot_disagreements(summary: dict) -> None:
    field_names = {
        "disclosure": "披露状态",
        "value": "数值",
        "unit": "单位",
        "period": "期间",
        "scope": "范围",
        "evidence_pages": "证据页",
        "evidence_text": "证据原文",
        "subject": "主体",
    }
    ordered_fields = sorted(summary["field_disagreement_counts"], key=lambda key: (-summary["field_disagreement_counts"][key], key))
    figure, axes = plt.subplots(1, 2, figsize=(12.4, 4.7), gridspec_kw={"wspace": 0.3})
    figure.suptitle("Silver 双路草稿：分歧将人工注意力集中到 11 个任务", fontsize=15, fontweight="bold", y=1.03)

    labels = [field_names.get(key, key) for key in ordered_fields]
    values = [summary["field_disagreement_counts"][key] for key in ordered_fields]
    bars = axes[0].bar(labels, values, color="#557A95", width=0.62)
    axes[0].set_title("a  分歧集中于证据与数值字段")
    axes[0].set_ylabel("发生分歧的任务数")
    axes[0].set_ylim(0, max(values, default=1) + 1.5)
    axes[0].tick_params(axis="x", rotation=22)
    label_bars(axes[0], bars)
    clean_axes(axes[0])

    dims = ["E", "S", "G"]
    rates = [summary["dimension_disagreement"][key]["rate"] * 100 for key in dims]
    bars = axes[1].bar(["环境 E", "社会 S", "治理 G"], rates, color=[COLORS[key] for key in dims], width=0.58)
    axes[1].set_title("b  治理类需优先人工复核")
    axes[1].set_ylabel("至少一个字段分歧（%）")
    axes[1].set_ylim(0, 72)
    axes[1].set_yticks([0, 20, 40, 60])
    label_bars(axes[1], bars, "%")
    clean_axes(axes[1])

    figure.text(0.5, -0.02, "注：这是机器草稿之间的差异，不代表人工一致性，也不代表模型准确率。", ha="center", fontsize=9, color="#555555")
    save_figure(figure, "figure_2_silver_disagreements")


def plot_diagnostics(a_rows: list[dict[str, str]], b_rows: list[dict[str, str]]) -> None:
    status_order = ["found", "missing", "uncertain"]
    status_labels = ["已找到", "未披露", "不确定"]
    confidence_order = ["high", "medium", "low"]
    confidence_labels = ["高", "中", "低"]
    a_status, b_status = Counter(row["disclosure"] for row in a_rows), Counter(row["disclosure"] for row in b_rows)
    a_conf, b_conf = Counter(row["confidence"] for row in a_rows), Counter(row["confidence"] for row in b_rows)
    a_needs = sum(row["validation_status"] != "valid" for row in a_rows)
    b_needs = sum(row["validation_status"] != "valid" for row in b_rows)

    figure, axes = plt.subplots(1, 2, figsize=(12.2, 4.7), gridspec_kw={"wspace": 0.3})
    figure.suptitle("Silver 输出诊断：不确定项不被强行包装为结论", fontsize=15, fontweight="bold", y=1.03)
    width = 0.34
    x = list(range(3))

    bars_a = axes[0].bar([value - width / 2 for value in x], [a_status[key] for key in status_order], width, label="Silver-A", color=COLORS["silver_a"])
    bars_b = axes[0].bar([value + width / 2 for value in x], [b_status[key] for key in status_order], width, label="Silver-B", color=COLORS["silver_b"])
    axes[0].set_title("a  披露状态分布")
    axes[0].set_ylabel("任务数")
    axes[0].set_xticks(x, status_labels)
    axes[0].set_ylim(0, 20)
    axes[0].legend(frameon=False, ncols=2, loc="upper center")
    label_bars(axes[0], bars_a)
    label_bars(axes[0], bars_b)
    clean_axes(axes[0])

    bars_a = axes[1].bar([value - width / 2 for value in x], [a_conf[key] for key in confidence_order], width, label="Silver-A", color=COLORS["silver_a"])
    bars_b = axes[1].bar([value + width / 2 for value in x], [b_conf[key] for key in confidence_order], width, label="Silver-B", color=COLORS["silver_b"])
    axes[1].set_title("b  自报置信度与结构校验")
    axes[1].set_ylabel("任务数")
    axes[1].set_xticks(x, confidence_labels)
    axes[1].set_ylim(0, 24)
    axes[1].legend(frameon=False, ncols=2, loc="upper center")
    axes[1].text(0.98, 0.72, f"需人工核验\nA：{a_needs} 条\nB：{b_needs} 条", transform=axes[1].transAxes, ha="right", va="top", fontsize=10, color="#8B3E2F")
    label_bars(axes[1], bars_a)
    label_bars(axes[1], bars_b)
    clean_axes(axes[1])

    figure.text(0.5, -0.02, "注：模型自报置信度未经 Natural-Gold 校准，不可解释为正确概率。", ha="center", fontsize=9, color="#555555")
    save_figure(figure, "figure_3_silver_diagnostics")


def write_preview() -> None:
    cards = [
        ("图 1：Pilot 分层覆盖", "figure_1_pilot_composition.svg"),
        ("图 2：Silver 双路分歧结构", "figure_2_silver_disagreements.svg"),
        ("图 3：Silver 输出可靠性诊断", "figure_3_silver_diagnostics.svg"),
    ]
    body = "\n".join(f'<section><h2>{title}</h2><img src="{filename}" alt="{title}"></section>' for title, filename in cards)
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Pilot-30 图表预览</title>
<style>body{{margin:0 auto;max-width:1240px;padding:32px;background:#f4f5f2;color:#1e2930;font-family:system-ui,sans-serif}}h1{{margin-bottom:28px}}section{{background:white;padding:20px 24px;margin:24px 0;border-radius:12px;box-shadow:0 4px 18px #00000012}}h2{{font-size:18px;margin:0 0 12px}}img{{display:block;width:100%;height:auto}}</style>
</head><body><h1>Natural-Gold Pilot-30 图表预览</h1>{body}</body></html>
"""
    (FIGURE_DIR / "index.html").write_text(html, encoding="utf-8")


def main() -> int:
    setup_style()
    pilot = read_csv(PILOT_MANIFEST)
    a_rows = read_csv(RESULT_DIR / "silver_a.csv")
    b_rows = read_csv(RESULT_DIR / "silver_b.csv")
    summary = json.loads((RESULT_DIR / "summary.json").read_text(encoding="utf-8"))
    if len(pilot) != 30 or len(a_rows) != 30 or len(b_rows) != 30:
        raise ValueError("Pilot-30 and both Silver drafts must each contain exactly 30 rows")
    plot_composition(pilot)
    plot_disagreements(summary)
    plot_diagnostics(a_rows, b_rows)
    write_preview()
    print(FIGURE_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
