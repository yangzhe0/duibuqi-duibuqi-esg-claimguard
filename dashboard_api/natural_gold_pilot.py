from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from dashboard_api.natural_gold import PROJECT_ROOT, disagreement_fields, load_manifest
from src.esg_demo.blocks import flatten_report, load_content_list


PILOT_VERSION = "natural-gold-v1-pilot30"
PILOT_SEED = "esg-claimguard-natural-gold-pilot30-20260809"
PILOT_DIR = PROJECT_ROOT / "data/evaluation/natural_gold/v1/pilot30"
PILOT_MANIFEST = PILOT_DIR / "manifest.csv"
PILOT_METADATA = PILOT_DIR / "pilot.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs/ai_contest/natural_gold_pilot30"
INDICATOR_POOL = PROJECT_ROOT / "outputs/formal_v2/indicator_pool_v2.csv"
PARSED_ROOT = PROJECT_ROOT / "data/parsed_reports_v1/reports"
DEFAULT_MODEL = "qwen3:30b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
SILVER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "disclosure": {"type": "string", "enum": ["found", "missing", "uncertain"]},
        "subject": {"type": "string"},
        "period": {"type": "string"},
        "scope": {"type": "string"},
        "value": {"type": "string"},
        "unit": {"type": "string"},
        "evidence_pages": {"type": "string"},
        "evidence_text": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "note": {"type": "string"},
    },
    "required": [
        "disclosure",
        "subject",
        "period",
        "scope",
        "value",
        "unit",
        "evidence_pages",
        "evidence_text",
        "confidence",
        "note",
    ],
    "additionalProperties": False,
}

PILOT_QUOTAS: dict[str, dict[str, int]] = {
    "E": {"quantitative": 8, "boolean": 1, "qualitative": 1},
    "S": {"quantitative": 5, "boolean": 2, "qualitative": 3},
    "G": {"quantitative": 3, "boolean": 3, "qualitative": 4},
}
PILOT_FIELDS = (
    "pilot_order",
    "pilot_id",
    "task_id",
    "dataset_version",
    "report_id",
    "indicator_id",
    "indicator_name",
    "dimension",
    "indicator_type",
    "stratum",
    "pdf_path",
)
DRAFT_FIELDS = (
    *PILOT_FIELDS,
    "draft_id",
    "retrieval_strategy",
    "model",
    "prompt_version",
    "disclosure",
    "subject",
    "period",
    "scope",
    "value",
    "unit",
    "evidence_pages",
    "evidence_text",
    "confidence",
    "note",
    "candidate_pages",
    "candidate_block_ids",
    "validation_status",
    "validation_errors",
    "raw_response_sha256",
    "elapsed_seconds",
)
DISAGREEMENT_FIELDS = (
    *PILOT_FIELDS,
    "manual_priority",
    "disagreement_fields",
    "disclosure_a",
    "disclosure_b",
    "value_a",
    "value_b",
    "unit_a",
    "unit_b",
    "evidence_pages_a",
    "evidence_pages_b",
    "evidence_text_a",
    "evidence_text_b",
    "confidence_a",
    "confidence_b",
    "note_a",
    "note_b",
)


def build_pilot(
    source_rows: list[dict[str, str]] | None = None,
    output_dir: Path = PILOT_DIR,
    seed: str = PILOT_SEED,
) -> dict[str, Any]:
    """Select 30 unique indicators from the frozen manifest with fixed strata."""
    source_rows = source_rows if source_rows is not None else load_manifest()
    selected: list[dict[str, str]] = []
    used_indicators: set[str] = set()
    for dimension, type_quotas in PILOT_QUOTAS.items():
        for indicator_type, quota in type_quotas.items():
            candidates = [
                row
                for row in source_rows
                if row.get("dimension") == dimension and row.get("indicator_type") == indicator_type
            ]
            candidates.sort(key=lambda row: _digest(seed, dimension, indicator_type, row["task_id"]))
            chosen = []
            for row in candidates:
                if row["indicator_id"] in used_indicators:
                    continue
                chosen.append(row)
                used_indicators.add(row["indicator_id"])
                if len(chosen) == quota:
                    break
            if len(chosen) != quota:
                raise ValueError(f"cannot fill pilot stratum {dimension}/{indicator_type}: {len(chosen)} of {quota}")
            selected.extend(chosen)
    selected.sort(key=lambda row: _digest(seed, "order", row["task_id"]))
    pilot_rows = []
    for index, row in enumerate(selected, start=1):
        pilot_rows.append(
            {
                "pilot_order": str(index),
                "pilot_id": f"pilot30-{index:02d}",
                **{field: row.get(field, "") for field in PILOT_FIELDS if field not in {"pilot_order", "pilot_id"}},
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = _csv_bytes(pilot_rows, PILOT_FIELDS)
    (output_dir / "manifest.csv").write_bytes(manifest_bytes)
    source_manifest = PROJECT_ROOT / "data/evaluation/natural_gold/v1/manifest.csv"
    metadata = {
        "pilot_version": PILOT_VERSION,
        "state": "frozen",
        "source_dataset": "natural-gold-v1",
        "source_manifest_sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        "pilot_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "sampling_seed": seed,
        "sample_size": len(pilot_rows),
        "unique_indicators": len({row["indicator_id"] for row in pilot_rows}),
        "dimension_counts": dict(Counter(row["dimension"] for row in pilot_rows)),
        "stratum_counts": dict(Counter(row["stratum"] for row in pilot_rows)),
        "silver_only": True,
        "promotion_policy": "Machine drafts never enter Natural-Gold without independent human confirmation.",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (output_dir / "pilot.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"rows": pilot_rows, "metadata": metadata}


def load_pilot(path: Path = PILOT_MANIFEST) -> list[dict[str, str]]:
    return _read_csv(path)


def generate_silver_drafts(
    draft_id: str,
    pilot_rows: list[dict[str, str]] | None = None,
    output_dir: Path = OUTPUT_DIR,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    resume: bool = True,
) -> list[dict[str, str]]:
    if draft_id not in {"silver_a", "silver_b"}:
        raise ValueError("draft_id must be silver_a or silver_b")
    pilot_rows = pilot_rows if pilot_rows is not None else load_pilot()
    if not pilot_rows:
        raise ValueError("Pilot-30 manifest is empty; run build_pilot first")
    indicators = {row["indicator_id"]: row for row in _read_csv(INDICATOR_POOL)}
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{draft_id}.csv"
    existing = {row["task_id"]: row for row in _read_csv(target)} if resume else {}
    output = [existing[row["task_id"]] for row in pilot_rows if row["task_id"] in existing]
    completed = set(existing)

    for index, task in enumerate(pilot_rows, start=1):
        if task["task_id"] in completed:
            continue
        indicator = indicators.get(task["indicator_id"])
        if not indicator:
            raise ValueError(f"indicator not found: {task['indicator_id']}")
        blocks = _load_blocks(task["report_id"])
        if draft_id == "silver_a":
            candidates = retrieve_silver_a(blocks, indicator)
            prompt = _prompt_silver_a(task, indicator, candidates)
            temperature = 0.0
            strategy = "exact_block_rank_v1"
            prompt_version = "silver-a-v1"
        else:
            candidates = retrieve_silver_b(blocks, indicator)
            prompt = _prompt_silver_b(task, indicator, candidates)
            temperature = 0.25
            strategy = "page_context_rank_v1"
            prompt_version = "silver-b-v1"
        started = time.monotonic()
        if not candidates:
            raw = ""
            annotation = _empty_uncertain("关键词检索未召回候选，不能据此认定未披露，需人工全文检查。")
            errors = ["no_candidate_retrieval"]
        else:
            try:
                raw = _ollama_generate(prompt, model, ollama_url, temperature)
                annotation, errors = _normalize_draft(raw, task, candidates)
            except Exception as exc:
                raw = ""
                annotation = _empty_uncertain(f"generation_error: {exc}")
                errors = ["generation_error"]
        row = {
            **task,
            "draft_id": draft_id,
            "retrieval_strategy": strategy,
            "model": model,
            "prompt_version": prompt_version,
            **annotation,
            "candidate_pages": ",".join(str(page) for page in sorted({int(item["page_no"]) for item in candidates})),
            "candidate_block_ids": "|".join(str(item.get("block_id", "")) for item in candidates),
            "validation_status": "valid" if not errors else "needs_human",
            "validation_errors": "|".join(errors),
            "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else "",
            "elapsed_seconds": f"{time.monotonic() - started:.3f}",
        }
        existing[task["task_id"]] = {field: str(row.get(field, "")) for field in DRAFT_FIELDS}
        output = [existing[item["task_id"]] for item in pilot_rows if item["task_id"] in existing]
        _write_csv_atomic(target, output, DRAFT_FIELDS)
        print(
            f"[{draft_id}] {index}/{len(pilot_rows)} {task['pilot_id']} {task['indicator_name']} "
            f"-> {row['disclosure']} ({row['validation_status']})",
            flush=True,
        )
    return output


def retrieve_silver_a(blocks: list[dict[str, Any]], indicator: dict[str, str], limit: int = 8) -> list[dict[str, Any]]:
    """Narrow block-level exact keyword retrieval."""
    keywords = _split_terms(indicator.get("keywords", ""))
    units = _split_terms(indicator.get("common_units", ""))
    scored = []
    for block in blocks:
        text = str(block.get("text", ""))
        hits = [term for term in keywords if term and term.casefold() in text.casefold()]
        if not hits:
            continue
        score = 20 * len(hits)
        score += 6 if indicator["indicator_name"] in text else 0
        score += 3 if block.get("block_type") == "table" else 1
        score += 2 * sum(unit.casefold() in text.casefold() for unit in units)
        if indicator["indicator_type"] == "quantitative" and re.search(r"\d", text):
            score += 4
        scored.append((score, block))
    scored.sort(key=lambda item: (-item[0], int(item[1]["page_no"]), int(item[1]["block_index"])))
    return [block for _, block in scored[:limit]]


def retrieve_silver_b(blocks: list[dict[str, Any]], indicator: dict[str, str], page_limit: int = 4) -> list[dict[str, Any]]:
    """Broader page-context retrieval using original terms and neighboring blocks."""
    terms = _split_terms(indicator.get("original_keywords", "")) + _split_terms(indicator.get("keywords", ""))
    terms = list(dict.fromkeys([indicator["indicator_name"], *terms]))
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        by_page[int(block["page_no"])].append(block)
    ranked_pages = []
    for page, page_blocks in by_page.items():
        text = "\n".join(str(block.get("text", "")) for block in page_blocks)
        hits = {term for term in terms if term and term.casefold() in text.casefold()}
        if not hits:
            continue
        score = 12 * len(hits) + min(sum(text.casefold().count(term.casefold()) for term in hits), 8)
        if indicator["indicator_type"] == "quantitative" and re.search(r"\d", text):
            score += 4
        ranked_pages.append((score, page))
    ranked_pages.sort(key=lambda item: (-item[0], item[1]))
    candidates: list[dict[str, Any]] = []
    for _, page in ranked_pages[:page_limit]:
        page_blocks = by_page[page]
        hit_indices = [
            index
            for index, block in enumerate(page_blocks)
            if any(term and term.casefold() in str(block.get("text", "")).casefold() for term in terms)
        ]
        wanted = set()
        for index in hit_indices:
            wanted.update({index - 1, index, index + 1})
        page_candidates = [block for index, block in enumerate(page_blocks) if index in wanted and str(block.get("text", "")).strip()]
        page_candidates.sort(key=lambda block: int(block["block_index"]))
        candidates.extend(page_candidates[:6])
    return candidates[:16]


def compare_silver_drafts(
    pilot_rows: list[dict[str, str]] | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    pilot_rows = pilot_rows if pilot_rows is not None else load_pilot()
    a_rows = {row["task_id"]: row for row in _read_csv(output_dir / "silver_a.csv")}
    b_rows = {row["task_id"]: row for row in _read_csv(output_dir / "silver_b.csv")}
    comparison = []
    field_counts: Counter[str] = Counter()
    status_pairs: Counter[str] = Counter()
    dimension_totals: Counter[str] = Counter()
    dimension_disagreements: Counter[str] = Counter()
    for task in pilot_rows:
        a, b = a_rows.get(task["task_id"]), b_rows.get(task["task_id"])
        if not a or not b:
            continue
        fields = disagreement_fields(a, b)
        field_counts.update(fields)
        status_pairs[f"{a['disclosure']}|{b['disclosure']}"] += 1
        dimension_totals[task["dimension"]] += 1
        if fields:
            dimension_disagreements[task["dimension"]] += 1
        priority = "high" if "disclosure" in fields or any(field in fields for field in ("value", "unit")) else "medium" if fields else "spot_check"
        comparison.append(
            {
                **task,
                "manual_priority": priority,
                "disagreement_fields": "|".join(fields),
                "disclosure_a": a["disclosure"],
                "disclosure_b": b["disclosure"],
                "value_a": a["value"],
                "value_b": b["value"],
                "unit_a": a["unit"],
                "unit_b": b["unit"],
                "evidence_pages_a": a["evidence_pages"],
                "evidence_pages_b": b["evidence_pages"],
                "evidence_text_a": a["evidence_text"],
                "evidence_text_b": b["evidence_text"],
                "confidence_a": a["confidence"],
                "confidence_b": b["confidence"],
                "note_a": a["note"],
                "note_b": b["note"],
            }
        )
    comparison.sort(key=lambda row: ({"high": 0, "medium": 1, "spot_check": 2}[row["manual_priority"]], int(row["pilot_order"])))
    _write_csv_atomic(output_dir / "disagreements.csv", comparison, DISAGREEMENT_FIELDS)
    completed = len(comparison)
    disagreement_count = sum(bool(row["disagreement_fields"]) for row in comparison)
    spot_check_target = min(max(round((completed - disagreement_count) * 0.2), 3), completed - disagreement_count) if completed > disagreement_count else 0
    disagreement_rows = [row for row in comparison if row["disagreement_fields"]]
    agreement_rows = [row for row in comparison if not row["disagreement_fields"]]
    spot_checks: list[dict[str, str]] = []
    for dimension in "ESG":
        candidates = [row for row in agreement_rows if row["dimension"] == dimension]
        if candidates and len(spot_checks) < spot_check_target:
            spot_checks.append(min(candidates, key=lambda row: _digest(PILOT_SEED, "spot-check", row["task_id"])))
    remaining = [row for row in agreement_rows if row not in spot_checks]
    remaining.sort(key=lambda row: _digest(PILOT_SEED, "spot-check", row["task_id"]))
    spot_checks.extend(remaining[: max(spot_check_target - len(spot_checks), 0)])
    human_queue = [*disagreement_rows, *spot_checks]
    human_queue.sort(key=lambda row: ({"high": 0, "medium": 1, "spot_check": 2}[row["manual_priority"]], int(row["pilot_order"])))
    _write_csv_atomic(output_dir / "human_review_queue.csv", human_queue, DISAGREEMENT_FIELDS)
    summary = {
        "pilot_version": PILOT_VERSION,
        "silver_only": True,
        "total_tasks": len(pilot_rows),
        "silver_a_completed": len(a_rows),
        "silver_b_completed": len(b_rows),
        "paired_tasks": completed,
        "exact_agreements": completed - disagreement_count,
        "tasks_with_disagreement": disagreement_count,
        "exact_agreement_rate": round((completed - disagreement_count) / completed, 4) if completed else None,
        "disclosure_agreement_rate": round(sum(row["disclosure_a"] == row["disclosure_b"] for row in comparison) / completed, 4) if completed else None,
        "field_disagreement_counts": dict(field_counts),
        "status_pairs": dict(status_pairs),
        "dimension_disagreement": {
            dimension: {
                "count": dimension_disagreements[dimension],
                "total": dimension_totals[dimension],
                "rate": round(dimension_disagreements[dimension] / dimension_totals[dimension], 4) if dimension_totals[dimension] else None,
            }
            for dimension in "ESG"
        },
        "validation": {
            "silver_a_needs_human": sum(row.get("validation_status") != "valid" for row in a_rows.values()),
            "silver_b_needs_human": sum(row.get("validation_status") != "valid" for row in b_rows.values()),
        },
        "human_next": {
            "priority_arbitration": disagreement_count,
            "agreement_spot_check": len(spot_checks),
            "total_review_queue": len(human_queue),
            "review_queue": "human_review_queue.csv",
            "promotion_to_gold": 0,
        },
        "boundary": "Silver-A/B are machine-generated candidate labels. They are not independent human annotations and must not enter Natural-Gold without human confirmation.",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    return summary


def _load_blocks(report_id: str) -> list[dict[str, Any]]:
    path = PARSED_ROOT / report_id / f"{report_id}_content_list_v2.json"
    if not path.is_file():
        raise ValueError(f"parsed report not found: {report_id}")
    return flatten_report(report_id, path, load_content_list(path))


def _prompt_silver_a(task: dict[str, str], indicator: dict[str, str], candidates: list[dict[str, Any]]) -> str:
    return _prompt_common(
        task,
        indicator,
        candidates,
        "你执行严格的直接证据标注。只有候选块逐字、明确披露目标指标时才标 found；关键词标题、目录或相邻概念不能算披露。",
    )


def _prompt_silver_b(task: dict[str, str], indicator: dict[str, str], candidates: list[dict[str, Any]]) -> str:
    return _prompt_common(
        task,
        indicator,
        candidates,
        "你执行审慎的上下文核验。综合同页相邻块判断表格标题、脚注和正文是否共同支持目标指标；口径不清或候选窗口不足时标 uncertain，不要猜测。",
    )


def _prompt_common(
    task: dict[str, str],
    indicator: dict[str, str],
    candidates: list[dict[str, Any]],
    role_instruction: str,
) -> str:
    evidence = [
        {
            "page_no": block.get("page_no", ""),
            "block_id": block.get("block_id", ""),
            "block_type": block.get("block_type", ""),
            "text": _shorten(str(block.get("text", "")), 1000),
        }
        for block in candidates
    ]
    return (
        "/no_think\n"
        f"{role_instruction}\n"
        "这是机器生成的 Silver Draft，不是人工金标准。只能根据给定候选证据回答，不使用外部知识，不读取其他模型答案。\n"
        "disclosure 只能是 found、missing、uncertain。当前候选不是全文：只有候选明确支持时才用 found；候选无关、不足或没有候选时用 uncertain，不得据此推断 missing。\n"
        "found 时 evidence_pages、evidence_text 必填；evidence_text 必须逐字复制最小连续证据。定量指标 found 时 value 必填，unit 使用原文单位，不自行换算。\n"
        "subject、period、scope 只在原文明示时填写；不明示就留空。confidence 只能是 high、medium、low。uncertain 时 note 必填。\n"
        "只返回 JSON 对象，字段固定为 disclosure,subject,period,scope,value,unit,evidence_pages,evidence_text,confidence,note。evidence_pages 使用逗号分隔页码字符串。\n"
        f"报告：{task['report_id']}\n"
        f"指标：{task['indicator_name']}（{task['indicator_id']}）\n"
        f"类型：{task['indicator_type']}\n"
        f"关键词定义：{indicator.get('keywords', '')}\n"
        f"常见单位提示（不能替代原文）：{indicator.get('common_units', '')}\n"
        f"候选证据：{json.dumps(evidence, ensure_ascii=False)}"
    )


def _ollama_generate(prompt: str, model: str, url: str, temperature: float) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": SILVER_RESPONSE_SCHEMA,
        "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": 1024, "seed": 41 if temperature == 0 else 97},
    }
    opener = request.build_opener(request.ProxyHandler({}))
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener.open(req, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"cannot connect to Ollama: {exc.reason}") from exc
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    if "response" not in result:
        raise RuntimeError("Ollama response field is missing")
    return str(result["response"])


def _normalize_draft(raw: str, task: dict[str, str], candidates: list[dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    try:
        payload = _parse_json(raw)
    except (ValueError, json.JSONDecodeError):
        return _empty_uncertain("invalid_json"), ["invalid_json"]
    disclosure = str(payload.get("disclosure", "")).strip().lower()
    if disclosure not in {"found", "missing", "uncertain"}:
        errors.append("invalid_disclosure")
        disclosure = "uncertain"
    confidence, confidence_valid = _normalize_confidence(payload.get("confidence", "medium"))
    if not confidence_valid:
        errors.append("invalid_confidence")
    pages = _parse_pages(payload.get("evidence_pages", ""))
    candidate_pages = {int(item["page_no"]) for item in candidates}
    if pages and not set(pages).issubset(candidate_pages):
        errors.append("evidence_page_outside_candidates")
    evidence_text = re.sub(r"\s+", " ", str(payload.get("evidence_text", ""))).strip()
    candidate_text = "\n".join(str(item.get("text", "")) for item in candidates)
    if evidence_text and _normal_quote(evidence_text) not in _normal_quote(candidate_text):
        errors.append("evidence_text_not_verbatim")
    value = str(payload.get("value", "")).strip()
    if disclosure == "found":
        if not pages:
            errors.append("found_without_page")
        if not evidence_text:
            errors.append("found_without_evidence")
        if task["indicator_type"] == "quantitative" and not re.search(r"\d", value):
            errors.append("quantitative_found_without_value")
    note = str(payload.get("note", "")).strip()
    if disclosure == "uncertain" and not note:
        errors.append("uncertain_without_note")
        note = "候选证据不足，需人工检查原文。"
    if errors and any(item.startswith("found_without") or item.startswith("quantitative_found") for item in errors):
        disclosure = "uncertain"
        confidence = "low"
        note = (note + "；结构化字段不完整，需人工检查。").strip("；")
    return (
        {
            "disclosure": disclosure,
            "subject": str(payload.get("subject", "")).strip(),
            "period": str(payload.get("period", "")).strip(),
            "scope": str(payload.get("scope", "")).strip(),
            "value": value,
            "unit": str(payload.get("unit", "")).strip(),
            "evidence_pages": ",".join(str(page) for page in pages),
            "evidence_text": evidence_text,
            "confidence": confidence,
            "note": note,
        },
        errors,
    )


def _empty_uncertain(note: str) -> dict[str, str]:
    return {
        "disclosure": "uncertain",
        "subject": "",
        "period": "",
        "scope": "",
        "value": "",
        "unit": "",
        "evidence_pages": "",
        "evidence_text": "",
        "confidence": "low",
        "note": note,
    }


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("JSON response is not an object")
    return value


def _parse_pages(value: Any) -> list[int]:
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[,，;；\s]+", str(value or ""))
    pages = []
    for part in parts:
        text = str(part).strip()
        if text.isdigit() and int(text) > 0:
            pages.append(int(text))
    return sorted(set(pages))


def _normalize_confidence(value: Any) -> tuple[str, bool]:
    aliases = {
        "high": "high",
        "高": "high",
        "较高": "high",
        "medium": "medium",
        "中": "medium",
        "中等": "medium",
        "low": "low",
        "低": "low",
        "较低": "low",
    }
    text = str(value).strip().lower()
    if text in aliases:
        return aliases[text], True
    try:
        numeric = float(text)
    except ValueError:
        return "low", False
    if not 0 <= numeric <= 1:
        return "low", False
    if numeric >= 0.8:
        return "high", True
    if numeric >= 0.5:
        return "medium", True
    return "low", True


def _summary_markdown(summary: dict[str, Any]) -> str:
    dimensions = summary["dimension_disagreement"]
    labels = {
        "disclosure": "披露状态",
        "subject": "主体",
        "period": "期间",
        "scope": "范围",
        "value": "数值",
        "unit": "单位",
        "evidence_pages": "证据页",
        "evidence_text": "证据原文",
    }
    field_counts = "、".join(
        f"{labels.get(field, field)} {count}"
        for field, count in sorted(summary["field_disagreement_counts"].items(), key=lambda item: (-item[1], item[0]))
    )
    return f"""# Natural-Gold Pilot-30 Silver Draft 汇总

> Silver-A 与 Silver-B 均由机器生成，只用于缩小人工核查范围，不是两名独立人工标注，也没有写入 Natural-Gold 正式库。

## 完成情况

- Pilot 任务：{summary['total_tasks']}
- Silver-A：{summary['silver_a_completed']}
- Silver-B：{summary['silver_b_completed']}
- 成对完成：{summary['paired_tasks']}
- 严格完全一致：{summary['exact_agreements']}
- 至少一个字段分歧：{summary['tasks_with_disagreement']}
- Disclosure 一致率：{_percent(summary['disclosure_agreement_rate'])}
- 全字段严格一致率：{_percent(summary['exact_agreement_rate'])}

## 分歧结构

- 字段分歧计数：{field_counts}
- E 维度：{dimensions['E']['count']} / {dimensions['E']['total']}
- S 维度：{dimensions['S']['count']} / {dimensions['S']['total']}
- G 维度：{dimensions['G']['count']} / {dimensions['G']['total']}
- A 结构校验需人工：{summary['validation']['silver_a_needs_human']}
- B 结构校验需人工：{summary['validation']['silver_b_needs_human']}

## 下一步人工工作量

- 优先核查分歧任务：{summary['human_next']['priority_arbitration']}
- 一致任务建议抽查：{summary['human_next']['agreement_spot_check']}
- 本轮人工队列合计：{summary['human_next']['total_review_queue']}
- 可执行队列：`{summary['human_next']['review_queue']}`
- 自动晋级 Natural-Gold：0

只有经人工确认的记录才能录入“金标准”页面。Silver 一致不代表事实正确。
"""


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or not path.stat().st_size:
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_csv_bytes(rows, fields))
    temporary.replace(path)


def _csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _split_terms(value: str) -> list[str]:
    return [term.strip() for term in str(value or "").split("|") if term.strip()]


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _normal_quote(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"
