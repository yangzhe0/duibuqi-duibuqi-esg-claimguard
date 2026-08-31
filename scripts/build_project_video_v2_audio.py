#!/usr/bin/env python3
"""Build the naturalized male narration master for the final project video."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "outputs/ai_contest/submission/drafts/video_v2_audio"
DEFAULT_OUTPUT = DEFAULT_DIR / "队不起队不起_ESG ClaimGuard_项目配音_云扬V2.wav"
DEFAULT_VOICE = "zh-CN-YunyangNeural"
TOTAL_SECONDS = 275.2
START_OFFSET = 0.35


def part(text: str, rate: str, pitch: str, pause: float = 0.0) -> dict[str, object]:
    return {"text": text, "rate": rate, "pitch": pitch, "pause": pause}


SCENES = [
    {
        "start": 0.0,
        "parts": [
            part("一份 ESG 报告，可能有上百页。", "-3%", "-1Hz", 0.22),
            part("真正困难的，不只是找到一个数字。还要确认，它属于谁、对应哪一期，用的是什么单位。", "+1%", "+0Hz", 0.28),
            part("大家好，我们是队不起队不起。我们带来的 ESG ClaimGuard，让披露结论能够回到原文。", "+2%", "-1Hz"),
        ],
    },
    {
        "start": 21.4,
        "parts": [
            part("复核人员面对的，往往不是一道简单的检索题。", "-3%", "-1Hz", 0.20),
            part("同一个数字，必须同时核对主体、期间、单位和统计范围。它还可能藏在正文、跨页表格、图表，甚至附注里。", "+1%", "+0Hz", 0.28),
            part("人工搜索不仅耗时，也很难保证不同复核人员使用相同标准。", "-2%", "-1Hz", 0.22),
            part("我们希望把逐页翻找，变成一组有证据、可处置的候选问题。", "-1%", "-1Hz"),
        ],
    },
    {
        "start": 50.8,
        "parts": [
            part("为此，系统采用证据优先的流水线。", "-4%", "-1Hz", 0.22),
            part("MinerU 二点五先处理 OCR、版面、表格和页码，再按 ESG 六十五项指标召回块级上下文。", "+2%", "+0Hz", 0.20),
            part("Qwen 三点六负责理解语义，并输出受约束的结构。", "-1%", "-1Hz", 0.20),
            part("最后，确定性规则逐项核对原文、单位和来源链，再把结果交给人工处置。", "+1%", "+0Hz", 0.30),
            part("模型负责理解，规则负责守门。", "-5%", "-2Hz"),
        ],
    },
    {
        "start": 84.2,
        "parts": [
            part("现在看到的是项目的真实工作台。", "-4%", "-1Hz", 0.22),
            part("进入系统总览后，可以先查看报告规模、指标分布和处理状态。环境、社会与治理三个维度的覆盖情况，以及每份报告的 found 数量，都可以快速比较。", "+2%", "+0Hz", 0.26),
            part("再进入披露预审，按照报告、指标和风险维度筛选候选。候选队列、抽取值和处置状态，会同步联动。", "+1%", "-1Hz", 0.22),
            part("点击一条记录，就能继续查看结构化结果和证据位置。", "-2%", "+0Hz", 0.20),
            part("整个过程，不是让模型直接下结论。而是把值得复核的内容，连同出处，一起送到使用者面前。质量摘要和新报告接入，也在同一个界面中完成。", "+1%", "-1Hz"),
        ],
    },
    {
        "start": 137.6,
        "parts": [
            part("证据复核页，把报告页码、规范区块、原始引文和结构化值放在一起。", "-2%", "-1Hz", 0.22),
            part("用户可以直接回到报告页面，核对表格中的上下文，再选择确认、修正、补充材料或者排除。", "+1%", "+0Hz", 0.24),
            part("系统要求每一条 found 引文，都是原始解析区块中的精确子串。页码、区块和字段，也必须同步通过校验。", "+2%", "-1Hz", 0.24),
            part("证据不足时，系统会保守输出 missing。这里的 missing 只是待复核候选，并不等于企业事实上没有披露。", "-1%", "-1Hz"),
        ],
    },
    {
        "start": 179.0,
        "parts": [
            part("冻结正式数据覆盖二百份报告、一万零五百二十八页和六十五项指标，共形成一万三千条唯一结果。", "+3%", "+0Hz", 0.20),
            part("其中，七千六百八十八条为有原文证据的 found，五千三百一十二条为 missing，错误为零。", "+4%", "-1Hz", 0.20),
            part("三千二百一十四条定量记录，还进一步区分直接读取、明确推导，以及单位归一来源。", "+2%", "+0Hz", 0.22),
            part("这些结果证明链路规模和完整性，但不代表模型准确率。", "-4%", "-2Hz"),
        ],
    },
    {
        "start": 210.4,
        "parts": [
            part("完整推理在单卡顺序部署下完成，总墙钟约七点七六小时。", "+1%", "-1Hz", 0.20),
            part("一万零十五次生成调用，没有模型调用错误。冻结文件的校验和，也全部通过。", "+2%", "+0Hz", 0.20),
            part("六十三项 Python 测试和十六项生产 smoke，也全部通过。", "-1%", "-1Hz", 0.24),
            part("换句话说，我们交付的不只是一次演示，而是一条可以重新运行、重新核对的工程链路。", "+1%", "-2Hz"),
        ],
    },
    {
        "start": 237.8,
        "parts": [
            part("相比关键词检索，ClaimGuard 增加语义理解。相比自由问答，增加确定性证据门。相比普通 RAG，记录数值与单位来源。", "+3%", "+0Hz", 0.24),
            part("系统不作企业评分，也不替代人工审阅或法定鉴证。", "-1%", "-1Hz", 0.22),
            part("本作品不声明未经独立人工评测的准确率。", "-4%", "-2Hz"),
        ],
    },
    {
        "start": 259.2,
        "parts": [
            part("ESG ClaimGuard，让问题可回原文、可由人工处置，也能导出复核底稿。", "-1%", "-1Hz", 0.24),
            part("把有限的时间，集中在真正有证据的问题上。", "-4%", "-2Hz", 0.22),
            part("谢谢观看。", "-6%", "-2Hz"),
        ],
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


def concatenate_parts(paths: list[Path], parts: list[dict[str, object]], output: Path) -> None:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for path in paths:
        command.extend(["-i", str(path)])
    filters: list[str] = []
    labels: list[str] = []
    for index, item in enumerate(parts):
        label = f"p{index}"
        pause = float(item["pause"])
        if pause > 0:
            filters.append(f"[{index}:a]apad=pad_dur={pause:.3f}[{label}]")
        else:
            filters.append(f"[{index}:a]anull[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"concat=n={len(paths)}:v=0:a=1,highpass=f=55[out]")
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "48000", "-ac", "1",
        "-c:a", "pcm_s16le", str(output),
    ])
    run(command)


async def synthesize(work: Path, voice: str) -> tuple[list[Path], list[dict[str, object]]]:
    scene_outputs: list[Path] = []
    timings: list[dict[str, object]] = []
    for scene_index, scene in enumerate(SCENES, start=1):
        parts = scene["parts"]
        part_outputs: list[Path] = []
        part_timings: list[dict[str, object]] = []
        for part_index, item in enumerate(parts, start=1):
            stem = f"scene-{scene_index:02d}-part-{part_index:02d}"
            mp3_path = work / f"{stem}.mp3"
            wav_path = work / f"{stem}.wav"
            if not wav_path.exists():
                await edge_tts.Communicate(
                    str(item["text"]), voice=voice, rate=str(item["rate"]), pitch=str(item["pitch"]),
                ).save(str(mp3_path))
                run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp3_path),
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path),
                ])
            part_outputs.append(wav_path)
            part_timings.append({**item, "duration": round(duration(wav_path), 3)})

        scene_output = work / f"scene-{scene_index:02d}.wav"
        concatenate_parts(part_outputs, parts, scene_output)
        scene_duration = duration(scene_output)
        next_start = float(SCENES[scene_index]["start"]) if scene_index < len(SCENES) else TOTAL_SECONDS
        end = float(scene["start"]) + START_OFFSET + scene_duration
        if end > next_start:
            raise RuntimeError(
                f"Scene {scene_index} narration ends at {end:.3f}s, after its {next_start:.3f}s boundary"
            )
        scene_outputs.append(scene_output)
        timings.append({
            "scene": scene_index,
            "start": scene["start"],
            "offset": START_OFFSET,
            "duration": round(scene_duration, 3),
            "end": round(end, 3),
            "slack": round(next_start - end, 3),
            "text": "".join(str(item["text"]) for item in parts),
            "parts": part_timings,
        })
    return scene_outputs, timings


def build_master(segments: list[Path], output: Path) -> None:
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-t",
        str(TOTAL_SECONDS), "-i", "anullsrc=r=48000:cl=mono",
    ]
    for path in segments:
        command.extend(["-i", str(path)])
    filters: list[str] = []
    labels = ["[0:a]"]
    for index, scene in enumerate(SCENES, start=1):
        delay = round((float(scene["start"]) + START_OFFSET) * 1000)
        label = f"v{index}"
        filters.append(f"[{index}:a]adelay={delay}[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
        "acompressor=threshold=-18dB:ratio=1.45:attack=28:release=220,"
        "alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=9[out]"
    )
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[out]", "-t", str(TOTAL_SECONDS),
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ])
    run(command)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    segments, timings = asyncio.run(synthesize(args.work_dir, args.voice))
    (args.work_dir / "narration_timing.json").write_text(
        json.dumps(timings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.work_dir / "narration.txt").write_text(
        "\n\n".join(item["text"] for item in timings) + "\n", encoding="utf-8"
    )
    build_master(segments, args.output)
    print(json.dumps({
        "output": str(args.output.relative_to(ROOT)),
        "voice": args.voice,
        "duration": duration(args.output),
        "segments": timings,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
