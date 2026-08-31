#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
import re
import subprocess
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEAM = "队不起队不起"
DEFAULT_COMPETITION_GROUP = "开放赛题-生成式大语言模型与智能体"
DEFAULT_DASHBOARD_CLIP = ROOT / "outputs/ai_contest/submission/drafts/dashboard_demo.webm"
DEFAULT_CAPTIONS = ROOT / "outputs/ai_contest/submission/supporting/ESG_ClaimGuard_项目视频字幕.srt"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

SLIDES = [
    (20, "ESG ClaimGuard", "可持续披露一致性预审系统", [f"{DEFAULT_TEAM}｜{DEFAULT_COMPETITION_GROUP}", "合成语音、屏幕文字与真实工作台录屏"]),
    (28, "为什么需要预审", "长报告中的问题不只是“找一个数”", ["声明分散在正文、跨页表格、图表与附注", "主体、期间、单位和范围必须同时核对", "目标：把逐页搜索转化为可回原文的候选"]),
    (30, "证据约束流水线", "版面感知 + 结构化推理 + 确定性验证", ["PDF → MinerU2.5-Pro：OCR / 版面 / 表格 / 页码", "Qwen3.6-27B：指标理解与受约束 JSON", "原文精确匹配 → 人工处置 → 可追溯底稿"]),
    (34, "冻结正式数据", "完整运行不等于准确率", ["200 份报告｜10,528 页｜65 项指标", "13,000 条唯一结果：found 7,688｜missing 5,312", "10,015 次生成｜调用错误 0｜结果 error 0"]),
    (38, "实机工作台", "从总览进入披露预审与证据复核", ["按报告、指标和维度查看候选", "回到页码、规范区块和原始引文", "质量评测、金标准与报告接入统一管理"]),
    (32, "定量结果可复算", "直接值、推导值和单位来源分离", ["3,214 条定量结果字段完整", "直接读取 3,089｜明确推导 125", "单位归一或推断 109｜表达式与输入留痕"]),
    (32, "证据合同", "模型不能脱离原文自由作答", ["7,688 条 found 均为原始区块精确子串", "页码、区块、引文与结构化值同步校验", "合同失败 0；证据不足保守输出 missing"]),
    (32, "工程验收", "单卡顺序部署与全链路校验", ["总墙钟约 7.76 小时｜中位 2.765 秒/任务", "P95 3.683 秒/任务｜SHA-256 全部通过", "Python 68/68｜生产 smoke 18/18｜前端构建通过"]),
    (22, "创新与边界", "主张可审计，不提前宣称更准确", ["比关键词多语义｜比自由问答多证据门", "比普通 RAG 多定量来源和缺失合同", "209 条为 Agent 工程复核，不是人工金标准"]),
    (12, "可回原文 · 可人工处置 · 可导出", "让有限复核时间集中在有证据的问题上", ["不作企业评分｜不替代人工审阅或法定鉴证", "Natural-Gold 0/300｜不报告 Precision / Recall / F1", f"ESG ClaimGuard｜{DEFAULT_TEAM}"]),
]

NARRATIONS = [
    f"大家好，我们是{DEFAULT_TEAM}。本视频使用合成语音配合字幕，介绍 ESG ClaimGuard，可持续披露一致性预审系统。",
    "一份可持续发展报告往往有上百页，关键声明分散在正文、表格、图表和附注中。复核人员不仅要找到数字，还要同时核对主体、期间、单位和范围。我们的目标，是把人工逐页搜索转化为有证据、可处置的候选问题。",
    "系统采用证据约束流水线。MinerU2.5-Pro 先处理 OCR、版面、表格和页码，Qwen3.6 二十七 B 再进行指标理解并输出受约束结构。最后由确定性规则核对原文、区块和字段，交给人工处置。",
    "冻结正式数据覆盖二百份报告、一万零五百二十八页和六十五项指标，形成一万三千条唯一结果。其中有证据披露七千六百八十八条，缺失候选五千三百一十二条，错误为零。一万零十五次生成调用也没有模型调用错误。这些只证明规模与完整性。",
    "现在展示真实工作台。用户先在总览查看报告、指标和状态，再进入披露预审定位候选问题。证据复核页保留报告页码、规范区块和原始引文；质量评测、金标准和报告接入也在同一界面中管理。",
    "定量结果必须可以复算。三千二百一十四条定量记录字段完整，其中三千零八十九条来自直接读取，一百二十五条记录明确推导过程；一百零九条涉及单位归一或推断。推导表达式、输入和单位来源都单独留痕。",
    "证据合同限制模型自由作答。七千六百八十八条 found 的引文全部是原始解析区块的精确子串，并同时校验页码、区块和结构化字段。合同失败为零；证据不足时系统保守输出 missing，但 missing 不等于企业事实上的未披露。",
    "正式推理总墙钟约七点七六小时，任务中位耗时二点七六五秒，P 九十五为三点六八三秒。冻结文件校验和全部通过，六十八项 Python 测试、十八项生产 smoke 和前端构建均通过。",
    "项目的创新是可审计：比关键词多语义理解，比自由问答多确定性证据门，比普通 RAG 多定量来源与缺失合同。二百零九条记录由 Codex Agent 模拟人工完成工程复核，不是真实人工金标准，也不用于准确率声明。",
    "ESG ClaimGuard 的价值，是让问题可回原文、可由人工处置、可导出底稿。系统不作企业评分，不替代人工审阅或法定鉴证。Natural-Gold 目前仍为零比三百，因此我们不报告 Precision、Recall 或 F1。谢谢观看。",
]


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(round(seconds * 1000), 0)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def caption_chunks(text: str, max_chars: int = 26) -> list[str]:
    """Split narration into readable sentence-level captions without changing text."""
    clauses = [item.strip() for item in re.split(r"(?<=[。！？；])", text) if item.strip()]
    chunks: list[str] = []
    for clause in clauses:
        while len(clause) > max_chars:
            split_at = max((clause.rfind(mark, 0, max_chars + 1) for mark in "，、："), default=-1)
            if split_at < max_chars // 2:
                split_at = max_chars
                # Never break an ASCII product/model name between cues.
                if split_at < len(clause) and clause[split_at - 1].isascii() and clause[split_at].isascii():
                    whitespace = clause.rfind(" ", 0, split_at)
                    if whitespace >= max_chars // 2:
                        split_at = whitespace
            else:
                split_at += 1
            chunks.append(clause[:split_at].strip())
            clause = clause[split_at:].strip()
        if clause:
            chunks.append(clause)
    return chunks


def build_srt() -> str:
    cues: list[str] = []
    cue_index = 1
    segment_start = 0.0
    for (duration, *_), narration in zip(SLIDES, NARRATIONS, strict=True):
        chunks = caption_chunks(narration)
        weights = [max(len(re.sub(r"\s+", "", chunk)), 1) for chunk in chunks]
        total_weight = sum(weights)
        cursor = segment_start
        for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True)):
            end = segment_start + duration if index == len(chunks) - 1 else cursor + duration * weight / total_weight
            cues.extend(
                [
                    str(cue_index),
                    f"{srt_timestamp(cursor)} --> {srt_timestamp(end)}",
                    chunk,
                    "",
                ]
            )
            cue_index += 1
            cursor = end
        segment_start += duration
    return "\n".join(cues)


def subtitle_filter(path: Path) -> str:
    escaped = str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    style = (
        "FontName=Noto Sans CJK SC,FontSize=25,PrimaryColour=&H00FFFFFF," 
        "OutlineColour=&H00101010,BackColour=&H90000000,BorderStyle=3," 
        "Outline=1,Shadow=0,Alignment=2,MarginV=72"
    )
    return f"subtitles='{escaped}':force_style='{style}'"


def svg(title: str, subtitle: str, bullets: list[str], index: int, team: str, competition_group: str) -> str:
    bullet_nodes = "".join(
        f'<circle cx="154" cy="{462 + i * 112}" r="8" fill="#38b07a"/>'
        f'<text x="184" y="{476 + i * 112}" class="bullet">{html.escape(line)}</text>'
        for i, line in enumerate(bullets)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">
<rect width="1920" height="1080" fill="#f4f8f6"/>
<rect width="1920" height="22" fill="#176447"/><rect x="0" y="1010" width="1920" height="70" fill="#123d30"/>
<circle cx="1680" cy="180" r="230" fill="#dcece5"/><circle cx="1760" cy="130" r="115" fill="#b8d8ca" opacity=".65"/>
<style>
.eyebrow{{font-family:'Noto Sans CJK SC';font-size:24px;font-weight:600;fill:#398267;letter-spacing:3px}}
.title{{font-family:'Noto Sans CJK SC';font-size:68px;font-weight:700;fill:#133e31}}
.subtitle{{font-family:'Noto Sans CJK SC';font-size:38px;font-weight:500;fill:#2d6e56}}
.bullet{{font-family:'Noto Sans CJK SC';font-size:32px;font-weight:400;fill:#213a31}}
.footer{{font-family:'Noto Sans CJK SC';font-size:22px;font-weight:400;fill:#d8e8e1}}
</style>
<text x="110" y="125" class="eyebrow">ESG CLAIMGUARD · 字幕演示</text>
<text x="110" y="250" class="title">{html.escape(title)}</text>
<text x="110" y="330" class="subtitle">{html.escape(subtitle)}</text>
<line x1="110" y1="380" x2="1420" y2="380" stroke="#78ae98" stroke-width="3"/>
{bullet_nodes}
<text x="110" y="1054" class="footer">{html.escape(team)}｜{html.escape(competition_group)}｜运行证据不等于模型准确率</text>
<text x="1790" y="1054" class="footer">{index:02d}/10</text>
</svg>'''


async def synthesize_narration(work: Path) -> Path:
    segments = []
    for index, ((duration, *_), text) in enumerate(zip(SLIDES, NARRATIONS, strict=True), start=1):
        mp3_path = work / f"voice-{index:02d}.mp3"
        wav_path = work / f"voice-{index:02d}.wav"
        await edge_tts.Communicate(text, voice="zh-CN-XiaoxiaoNeural", rate="+8%").save(str(mp3_path))
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp3_path),
                "-af", "apad", "-t", str(duration), "-ar", "48000", "-ac", "2", str(wav_path),
            ],
            check=True,
        )
        segments.append(wav_path)
    concat = work / "audio.txt"
    concat.write_text("\n".join(f"file '{path}'" for path in segments) + "\n", encoding="utf-8")
    output = work / "narration.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", str(output)],
        check=True,
    )
    return output


def configure_identity(team: str, competition_group: str) -> None:
    """Apply confirmed registration identity to visible slides and narration."""
    first = SLIDES[0]
    SLIDES[0] = (first[0], first[1], first[2], [f"{team}｜{competition_group}", first[3][1]])
    last = SLIDES[-1]
    SLIDES[-1] = (last[0], last[1], last[2], [last[3][0], last[3][1], f"ESG ClaimGuard｜{team}"])
    NARRATIONS[0] = f"大家好，我们是{team}。本视频使用合成语音配合字幕，介绍 ESG ClaimGuard，可持续披露一致性预审系统。"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a captioned, submission-ready ESG ClaimGuard MP4.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--competition-group", default=DEFAULT_COMPETITION_GROUP)
    parser.add_argument("--dashboard-clip", type=Path, default=DEFAULT_DASHBOARD_CLIP)
    parser.add_argument("--captions-output", type=Path, default=DEFAULT_CAPTIONS)
    parser.add_argument(
        "--caption-existing",
        type=Path,
        help="Burn the audited captions into an existing composite video without regenerating narration.",
    )
    args = parser.parse_args()
    if any(marker in value for value in (args.team, args.competition_group) for marker in ("待定", "待确认", "YYYY")):
        parser.error("video build requires confirmed --team and --competition-group values")
    if any(character in args.team for character in "/\\"):
        parser.error("--team cannot contain path separators")
    if args.caption_existing and (args.team != DEFAULT_TEAM or args.competition_group != DEFAULT_COMPETITION_GROUP):
        parser.error("--caption-existing cannot replace identity already embedded in video; perform a full regeneration")
    configure_identity(args.team, args.competition_group)
    if args.output is None:
        args.output = ROOT / f"outputs/ai_contest/submission/final/{args.team}_ESG ClaimGuard_项目视频.mp4"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.captions_output.parent.mkdir(parents=True, exist_ok=True)
    captions = build_srt()
    args.captions_output.write_text(captions, encoding="utf-8")

    if args.caption_existing:
        if not args.caption_existing.is_file():
            raise FileNotFoundError(args.caption_existing)
        temporary_output = args.output.with_name(f".{args.output.stem}.captioned{args.output.suffix}")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(args.caption_existing), "-vf", subtitle_filter(args.captions_output),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "copy", "-movflags", "+faststart", str(temporary_output),
            ],
            check=True,
        )
        temporary_output.replace(args.output)
        print(args.output.relative_to(ROOT))
        print(args.captions_output.relative_to(ROOT))
        return 0

    with tempfile.TemporaryDirectory(prefix="claimguard-video-") as temporary:
        work = Path(temporary)
        concat_lines = []
        for index, (duration, title, subtitle, bullets) in enumerate(SLIDES, start=1):
            svg_path = work / f"slide-{index:02d}.svg"
            png_path = work / f"slide-{index:02d}.png"
            svg_path.write_text(svg(title, subtitle, bullets, index, args.team, args.competition_group), encoding="utf-8")
            subprocess.run(["convert", "-font", FONT, str(svg_path), str(png_path)], check=True)
            concat_lines.extend([f"file '{png_path}'", f"duration {duration}"])
        concat_lines.append(f"file '{work / 'slide-10.png'}'")
        concat_path = work / "slides.txt"
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        total = sum(item[0] for item in SLIDES)
        narration = asyncio.run(synthesize_narration(work))
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-i", str(narration),
        ]
        if args.dashboard_clip.is_file():
            command.extend(
                [
                    "-i", str(args.dashboard_clip),
                    "-filter_complex",
                    "[0:v]fps=30,format=yuv420p[base];"
                    "[2:v]fps=30,scale=1920:1080,setpts=PTS-STARTPTS+82/TB[demo];"
                    f"[base][demo]overlay=eof_action=pass:shortest=0[composite];"
                    f"[composite]{subtitle_filter(args.captions_output)}[outv]",
                    "-map", "[outv]", "-map", "1:a:0",
                ]
            )
        else:
            command.extend(
                [
                    "-filter_complex",
                    f"[0:v]fps=30,format=yuv420p,{subtitle_filter(args.captions_output)}[outv]",
                    "-map", "[outv]", "-map", "1:a:0",
                ]
            )
        command.extend(
            [
                "-t", str(total), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-shortest", str(args.output),
            ]
        )
        subprocess.run(command, check=True)
    print(args.output.relative_to(ROOT))
    print(args.captions_output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
