import json
import re
from typing import Any

from .indicators import Indicator


def select_candidate_blocks(blocks: list[dict], indicator: Indicator, max_blocks: int) -> list[dict]:
    scored = []
    for row in blocks:
        text = row.get("text", "")
        score = sum(1 for keyword in indicator.keywords if keyword and keyword in text)
        if score:
            type_bonus = {"table": 3, "list": 3, "paragraph": 2, "chart": 1, "image": 1}.get(row.get("block_type"), 0)
            scored.append((score * 10 + type_bonus, row))
    scored.sort(key=lambda item: (-item[0], item[1].get("page_no", 0), item[1].get("block_index", 0)))
    return [row for _, row in scored[:max_blocks]]


def candidate_result(report_id: str, indicator: Indicator, candidates: list[dict], status: str = "candidate") -> dict:
    if not candidates:
        return empty_result(report_id, indicator, "missing")
    first = candidates[0]
    return {
        "report_id": report_id,
        "indicator_id": indicator.indicator_id,
        "indicator_name": indicator.name,
        "dimension": indicator.dimension,
        "indicator_type": indicator.indicator_type,
        "status": status,
        "value": "",
        "unit": "",
        "qualitative_text": "",
        "evidence_quote": _shorten(first.get("text", ""), 500),
        "page_no": first.get("page_no", ""),
        "block_id": first.get("block_id", ""),
        "block_type": first.get("block_type", ""),
        "confidence": 0.0,
        "notes": "candidate evidence only; LLM disabled",
    }


def empty_result(report_id: str, indicator: Indicator, status: str = "missing", notes: str = "") -> dict:
    return {
        "report_id": report_id,
        "indicator_id": indicator.indicator_id,
        "indicator_name": indicator.name,
        "dimension": indicator.dimension,
        "indicator_type": indicator.indicator_type,
        "status": status,
        "value": "",
        "unit": "",
        "qualitative_text": "",
        "evidence_quote": "",
        "page_no": "",
        "block_id": "",
        "block_type": "",
        "confidence": 0.0,
        "notes": notes,
    }


def build_prompt(report_id: str, indicator: Indicator, candidates: list[dict]) -> str:
    evidence = []
    for row in candidates:
        evidence.append(
            {
                "block_id": row.get("block_id"),
                "page_no": row.get("page_no"),
                "block_type": row.get("block_type"),
                "text": _shorten(row.get("text", ""), 1200),
            }
        )
    return (
        "/no_think\n"
        "你是ESG报告指标抽取器。只能使用给定证据，不得使用外部知识，不得猜测。\n"
        "如果证据中没有该指标，status 必须为 missing，其他值留空。\n"
        "定量指标提取 value 和 unit；定性指标提取 qualitative_text 原文摘要，qualitative_text 控制在 120 个汉字以内。\n"
        "evidence_quote 必须逐字摘自证据，evidence_quote 控制在 160 个汉字以内。\n"
        "只返回一个 JSON 对象，不要 Markdown，不要解释。\n"
        "JSON 字段固定为：status,value,unit,qualitative_text,evidence_quote,page_no,block_id,block_type,confidence,notes。\n"
        f"报告：{report_id}\n"
        f"指标：{indicator.name}\n"
        f"指标类型：{indicator.indicator_type}\n"
        f"证据：{json.dumps(evidence, ensure_ascii=False)}"
    )


def normalize_llm_result(report_id: str, indicator: Indicator, raw_text: str) -> dict:
    try:
        payload = _parse_json_object(raw_text)
    except ValueError as exc:
        return empty_result(report_id, indicator, "error", f"invalid llm json: {exc}")
    result = empty_result(report_id, indicator, str(payload.get("status", "error") or "error"))
    for key in ("value", "unit", "qualitative_text", "evidence_quote", "page_no", "block_id", "block_type", "notes"):
        result[key] = payload.get(key, "")
    try:
        result["confidence"] = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    if result["status"] not in {"found", "missing", "error"}:
        has_content = any(str(result.get(key, "")).strip() for key in ("value", "qualitative_text", "evidence_quote"))
        result["status"] = "found" if has_content else "missing"
        result["notes"] = (str(result.get("notes", "")) + " normalized invalid status").strip()
    return result


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no json object found")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("json is not an object")
    return value


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."
