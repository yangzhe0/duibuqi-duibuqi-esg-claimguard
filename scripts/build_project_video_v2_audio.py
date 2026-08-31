#!/usr/bin/env python3
"""Build a separate, humanized Edge-TTS narration master for the V2 video."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "outputs/ai_contest/submission/drafts/video_v2_audio"
DEFAULT_OUTPUT = ROOT / "outputs/ai_contest/submission/final/队不起队不起_ESG ClaimGuard_项目配音.wav"
VOICE = "zh-CN-XiaoxiaoNeural"
TOTAL_SECONDS = 275.2

SCENES = [
    {
        "start": 0.0,
        "rate": "-3%",
        "pitch": "-2Hz",
        "text": "一份 ESG 报告，可能有上百页。真正困难的，不只是找到一个数字，而是确认它属于谁、对应哪一期、使用什么单位。大家好，我们是队不起队不起。我们带来的 ESG ClaimGuard，让披露结论能够回到原文。",
    },
    {
        "start": 21.4,
        "rate": "-2%",
        "pitch": "-1Hz",
        "text": "复核人员面对的，往往不是一道简单的检索题。同一个数字，必须同时核对主体、期间、单位和统计范围；它还可能藏在正文、跨页表格、图表，甚至附注里。人工搜索不仅耗时，也很难保证不同复核人员使用相同标准。我们希望把逐页翻找，变成一组有证据、可处置的候选问题。",
    },
    {
        "start": 50.8,
        "rate": "-2%",
        "pitch": "-2Hz",
        "text": "为此，系统采用证据优先的流水线。MinerU 二点五先处理 OCR、版面、表格和页码，再按 ESG 六十五项指标召回块级上下文。Qwen 三点六负责理解语义，并输出受约束的结构。最后，确定性规则逐项核对原文、单位和来源链，再把结果交给人工处置。模型负责理解，规则负责守门。",
    },
    {
        "start": 84.2,
        "rate": "-3%",
        "pitch": "-1Hz",
        "text": "现在看到的是项目的真实工作台。进入系统总览后，可以先查看报告规模、指标分布和处理状态。环境、社会与治理三个维度的覆盖情况，以及每份报告的 found 数量，都可以快速比较。再进入披露预审，按照报告、指标和风险维度筛选候选；候选队列、抽取值和处置状态会同步联动。点击一条记录，就能继续查看结构化结果和证据位置。整个过程不是让模型直接下结论，而是把值得复核的内容，连同出处一起送到使用者面前。质量评测、金标准管理和新报告接入，也在同一个界面中完成。",
    },
    {
        "start": 137.6,
        "rate": "-3%",
        "pitch": "-2Hz",
        "text": "证据复核页把报告页码、规范区块、原始引文和结构化值放在一起。用户可以直接回到报告页面，核对表格中的上下文，再选择确认、修正、补充材料或者排除。系统要求每一条 found 引文，都是原始解析区块中的精确子串；页码、区块和字段也必须同步通过校验。证据不足时，系统会保守输出 missing。这里的 missing 只是待复核候选，并不等于企业事实上没有披露。",
    },
    {
        "start": 179.0,
        "rate": "+3%",
        "pitch": "-1Hz",
        "text": "冻结正式数据覆盖二百份报告、一万零五百二十八页和六十五项指标，共形成一万三千条唯一结果。其中，七千六百八十八条为有原文证据的 found，五千三百一十二条为 missing，错误为零。三千二百一十四条定量记录还进一步区分直接读取、明确推导，以及单位归一来源。这些结果证明链路规模和完整性，但不代表模型准确率。",
    },
    {
        "start": 210.4,
        "rate": "-2%",
        "pitch": "-2Hz",
        "text": "完整推理在单卡顺序部署下完成，总墙钟约七点七六小时。一万零十五次生成调用没有模型调用错误；冻结文件的校验和全部通过，六十八项 Python 测试和十八项生产 smoke 也全部通过。换句话说，我们交付的不只是一次演示，而是一条可以重新运行、重新核对的工程链路。",
    },
    {
        "start": 237.8,
        "rate": "-1%",
        "pitch": "-1Hz",
        "text": "相比关键词检索，ClaimGuard 增加语义理解；相比自由问答，增加确定性证据门；相比普通 RAG，记录数值与单位来源。系统不作企业评分，也不替代人工审阅或法定鉴证。本作品不声明未经独立人工评测的准确率。",
    },
    {
        "start": 259.2,
        "rate": "-4%",
        "pitch": "-2Hz",
        "text": "ESG ClaimGuard，让问题可回原文、可由人工处置，也能导出复核底稿。把有限的时间，集中在真正有证据的问题上。谢谢观看。",
    },
]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


async def synthesize(work: Path) -> list[Path]:
    outputs: list[Path] = []
    for index, scene in enumerate(SCENES, start=1):
        mp3_path = work / f"scene-{index:02d}.mp3"
        wav_path = work / f"scene-{index:02d}.wav"
        await edge_tts.Communicate(
            scene["text"],
            voice=VOICE,
            rate=scene["rate"],
            pitch=scene["pitch"],
        ).save(str(mp3_path))
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp3_path),
            "-af", "highpass=f=65,lowpass=f=15500,acompressor=threshold=-20dB:ratio=2.2:attack=18:release=180:makeup=1.6",
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path),
        ])
        outputs.append(wav_path)
    return outputs


def build_master(segments: list[Path], output: Path) -> None:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-t", str(TOTAL_SECONDS), "-i", "anullsrc=r=48000:cl=mono"]
    for path in segments:
        command.extend(["-i", str(path)])
    filters: list[str] = []
    labels = ["[0:a]"]
    for index, scene in enumerate(SCENES, start=1):
        delay = round((scene["start"] + 0.7) * 1000)
        label = f"v{index}"
        filters.append(f"[{index}:a]adelay={delay}[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=7[out]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[out]", "-t", str(TOTAL_SECONDS), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    run(command)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    segments = asyncio.run(synthesize(args.work_dir))
    timings = []
    for index, (scene, path) in enumerate(zip(SCENES, segments, strict=True), start=1):
        timings.append({"scene": index, "start": scene["start"], "duration": round(duration(path), 3), "text": scene["text"]})
    (args.work_dir / "narration_timing.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.work_dir / "narration.txt").write_text("\n\n".join(item["text"] for item in SCENES) + "\n", encoding="utf-8")
    build_master(segments, args.output)
    print(json.dumps({"output": str(args.output.relative_to(ROOT)), "duration": duration(args.output), "segments": timings}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
