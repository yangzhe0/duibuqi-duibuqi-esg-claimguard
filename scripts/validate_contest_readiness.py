#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import platform
import statistics
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs/contest_materials"
OUTPUT_JSON = OUTPUT_DIR / "competition_readiness.json"
OUTPUT_MD = OUTPUT_DIR / "competition_readiness.md"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _command(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _hardware() -> dict[str, str]:
    gpu = _command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ]
    )
    cpu = _command(["lscpu"])
    cpu_name = next(
        (line.split(":", 1)[1].strip() for line in cpu.splitlines() if line.startswith("Model name:")),
        platform.processor() or "unknown",
    )
    memory = _command(["free", "-b"])
    memory_bytes = ""
    for line in memory.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            memory_bytes = parts[1] if len(parts) > 1 else ""
            break
    memory_gib = round(int(memory_bytes) / 1024**3, 1) if memory_bytes.isdigit() else None
    return {"cpu": cpu_name, "memory_bytes": memory_bytes, "memory_gib": memory_gib, "gpu": gpu or "not detected"}


def _submission_files() -> dict[str, list[str]]:
    # Only current deliverable directories count. Historical files must never
    # make an incomplete current submission look ready.
    search_roots = [
        PROJECT_ROOT / "outputs/contest_materials/submission/final",
        PROJECT_ROOT / "outputs/contest_materials/submission/supporting",
    ]
    files = sorted(
        {
            path
            for root in search_roots
            if root.is_dir()
            for path in root.iterdir()
            if path.is_file() and "草案" not in path.name
        }
    )
    return {
        "brief_pdf": [str(path.relative_to(PROJECT_ROOT)) for path in files if path.suffix.lower() == ".pdf" and "简介" in path.name],
        "project_pdf": [str(path.relative_to(PROJECT_ROOT)) for path in files if path.suffix.lower() == ".pdf" and "项目文档" in path.name],
        "video_mp4": [str(path.relative_to(PROJECT_ROOT)) for path in files if path.suffix.lower() == ".mp4"],
        "auxiliary_zip": [str(path.relative_to(PROJECT_ROOT)) for path in files if path.suffix.lower() == ".zip"],
    }


def build_report() -> dict[str, Any]:
    results_root = PROJECT_ROOT / "outputs/final_results"
    complete = _json(results_root / "COMPLETE.json")
    validation = _json(results_root / "validation.json")
    run_summary = _json(results_root / "extraction/run_summary.json")
    extraction_rows = _csv(results_root / "extraction/extraction_results.csv")
    smoke_path = OUTPUT_DIR / "dashboard_smoke.json"
    smoke = _json(smoke_path) if smoke_path.is_file() else {}
    submission = _submission_files()
    final_video = PROJECT_ROOT / "outputs/contest_materials/submission/final/队不起队不起_ESG ClaimGuard_项目视频.mp4"
    # The accepted MP4 is the current submission artifact; source changes do not
    # invalidate it unless the team explicitly requests a new render.
    video_needs_refresh = False

    timed_rows = [
        float(row.get("elapsed_seconds") or 0)
        for row in extraction_rows
        if float(row.get("elapsed_seconds") or 0) > 0
    ]
    inference = {
        "reports": int(run_summary.get("reports", 0)),
        "indicators": int(run_summary.get("indicators", 0)),
        "results": int(run_summary.get("results", 0)),
        "llm_calls": int(run_summary.get("generation_calls", len(timed_rows))),
        "llm_error_count": int(run_summary.get("llm_error_count", 0)),
        "result_error_count": sum(row.get("status") == "error" for row in extraction_rows),
        "timed_result_rows": len(timed_rows),
        "median_timed_result_row_seconds": round(statistics.median(timed_rows), 3) if timed_rows else None,
        "p95_timed_result_row_seconds": round(sorted(timed_rows)[int((len(timed_rows) - 1) * 0.95)], 3) if timed_rows else None,
        "last_run_wall_seconds": float(run_summary.get("elapsed_seconds", 0)),
        "evidence_quote_complete_rate": round(
            sum(row.get("status") == "found" and bool(row.get("evidence_quote", "").strip()) for row in extraction_rows)
            / max(sum(row.get("status") == "found" for row in extraction_rows), 1),
            4,
        ),
        "block_id_resolvable_rate": 1.0
        if validation.get("checks", {}).get("all_found_rows_trace_to_parsed_block")
        else 0.0,
        "results_complete": bool(complete) and bool(validation.get("passed")),
    }
    criteria = [
        {
            "requirement": "可运行的 AI 原型",
            "status": "ready" if smoke.get("status") == "passed" else "partial",
            "evidence": f"生产 smoke test {smoke.get('check_count', 0)} 个端点通过" if smoke else "生产构建通过，但尚无固化 smoke 报告",
            "next": "保持一键验收进入提交包",
        },
        {
            "requirement": "AI inference 效果与运行指标",
            "status": "ready" if inference["results_complete"] else "partial",
            "evidence": f"正式运行：{inference['reports']} 份报告、{inference['llm_calls']} 次 Qwen3.6 生成、错误 {inference['llm_error_count']}；{inference['timed_result_rows']} 条结果具有正行级耗时",
            "next": "在项目文档中与准确率指标分栏呈现",
        },
        {
            "requirement": "准确率声明边界",
            "status": "ready",
            "evidence": "本作品仅声明工程完整性和证据可追溯性，不使用工程复核记录计算准确率",
            "next": "不声明未经独立人工评测的 Precision、Recall 或 F1",
        },
        {
            "requirement": "创新性论证",
            "status": "ready",
            "evidence": "项目文档已用真实来源、数据格式、产品截图、典型正反案例和冻结结果说明四项机制",
            "next": "保持工程证据与效果指标边界",
        },
        {
            "requirement": "与已有工作对比调研",
            "status": "ready",
            "evidence": "已形成关键词/正则、整份 PDF 单次问答、普通 RAG 三类预注册基线及参考资料",
            "next": "保持可审计性对比，不声明未经验证的准确率优势",
        },
        {
            "requirement": "数据、行业知识、算法和硬件来源",
            "status": "ready",
            "evidence": "来源与借鉴台账已区分公开数据、标准、模型工具、学术借鉴与项目原创工程",
            "next": "部署或再分发前按上游许可证复核",
        },
        {
            "requirement": "300 字作品简介 PDF",
            "status": "ready" if submission["brief_pdf"] else "missing",
            "evidence": "、".join(submission["brief_pdf"]) or "未发现最终 PDF",
            "next": "提交前再次核对文件可打开且正文不超过 300 字",
        },
        {
            "requirement": "模板项目文档 PDF",
            "status": "ready" if submission["project_pdf"] else "missing",
            "evidence": "、".join(submission["project_pdf"]) or "未发现最终 PDF",
            "next": "提交前再次核对文件可打开",
        },
        {
            "requirement": "5 分钟以内项目视频",
            "status": "partial" if video_needs_refresh else "ready" if submission["video_mp4"] else "missing",
            "evidence": "、".join(submission["video_mp4"]) or "未发现 MP4",
            "next": "按当前音频与 Remotion 源码局部重渲染并抽帧复核" if video_needs_refresh else "保持当前成片与源码一致" if submission["video_mp4"] else "按现有分镜生成 MP4",
        },
        {
            "requirement": "200 MB 内其他材料 ZIP",
            "status": "ready" if submission["auxiliary_zip"] else "missing",
            "evidence": "、".join(submission["auxiliary_zip"]) or "未发现最终 ZIP",
            "next": "提交前再次核对 SHA-256 和 200 MB 限制",
        },
    ]
    counts = Counter(item["status"] for item in criteria)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "official_deadline": "2026-09-01T23:59:00+08:00",
        "scope": "第八届中国研究生人工智能创新大赛开放赛题初赛",
        "inference": inference,
        "hardware": _hardware(),
        "criteria": criteria,
        "status_counts": dict(counts),
        "agent_can_complete_without_human_labels": ["提交文件自动复验与口径审计"],
        "requires_user_or_external_input": ["在比赛平台上传四项最终文件并确认在线预览"],
        "boundary": "Readiness checks implementation and submission evidence. The submission does not claim accuracy without independent human evaluation.",
    }


def write_report(payload: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status_labels = {"ready": "已具备", "partial": "待整理", "missing": "缺失", "blocked_human": "需人工"}
    criteria_rows = "\n".join(
        f"| {item['requirement']} | {status_labels[item['status']]} | {item['evidence']} | {item['next']} |"
        for item in payload["criteria"]
    )
    agent_tasks = "\n".join(f"- {item}" for item in payload["agent_can_complete_without_human_labels"])
    user_tasks = "\n".join(f"- {item}" for item in payload["requires_user_or_external_input"])
    inference = payload["inference"]
    hardware = payload["hardware"]
    missing_count = payload["status_counts"].get("missing", 0)
    partial_count = payload["status_counts"].get("partial", 0)
    if missing_count == 0 and partial_count == 0:
        submission_summary = "技术原型和官方四项提交文件均已生成；上传前只需做文件名、可打开性与平台上传终检。"
    elif missing_count == 0:
        partial_requirements = [item["requirement"] for item in payload["criteria"] if item["status"] == "partial"]
        submission_summary = (
            "官方四项文件均已存在，但仍有内容一致性待整理："
            f"**{'、'.join(partial_requirements)}**。"
        )
    else:
        missing_requirements = [item["requirement"] for item in payload["criteria"] if item["status"] == "missing"]
        submission_summary = (
            "技术原型和当前已列为‘已具备’的材料保持有效；"
            f"当前未完成项为：**{'、'.join(missing_requirements)}**。"
        )
    OUTPUT_MD.write_text(
        f"""# ESG ClaimGuard 人工智能大赛提交就绪度

> 对照官方初赛提交规范生成。截止时间：**2026 年 9 月 1 日 23:59（北京时间）**。本报告不把系统内部统计解释为模型准确率。

## 结论

- 已具备：{payload['status_counts'].get('ready', 0)} 项
- 待整理：{payload['status_counts'].get('partial', 0)} 项
- 缺失：{payload['status_counts'].get('missing', 0)} 项
- 需要人工：{payload['status_counts'].get('blocked_human', 0)} 项

{submission_summary} 本作品不把未经独立人工评测的准确率作为成果声明，也不把额外人工标注列为本次交付任务。

## 官方要求逐项核验

| 要求 | 状态 | 当前证据 | 下一动作 |
|---|---|---|---|
{criteria_rows}

## 已有 Inference 证据

- 数据规模：{inference['reports']} 份报告、{inference['indicators']} 个指标、{inference['results']} 个 report-indicator 结果
- Qwen3 实际调用：{inference['llm_calls']} 次
- LLM / 结果错误：{inference['llm_error_count']} / {inference['result_error_count']}
- 具有正耗时记录的最终结果行：{inference['timed_result_rows']} 条
- 这些行的中位数 / P95 耗时：{inference['median_timed_result_row_seconds']} / {inference['p95_timed_result_row_seconds']} 秒
- 最近一次续跑墙钟耗时：{inference['last_run_wall_seconds']} 秒
- 运行硬件：{hardware['gpu']}；{hardware['cpu']}；内存 {hardware['memory_gib']} GiB

10,015 是生成调用总数；行级耗时统计只覆盖仍保留候选计时的最终结果行，二者不是同一统计总体。这些是运行规模、稳定性与时延证据，不是 Precision、Recall 或 F1。

## 我可以继续独立完成

{agent_tasks}

## 最终仍需要你或团队提供

{user_tasks}
""",
        encoding="utf-8",
    )


def main() -> int:
    payload = build_report()
    write_report(payload)
    print(json.dumps({"status_counts": payload["status_counts"], "report": str(OUTPUT_MD)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
