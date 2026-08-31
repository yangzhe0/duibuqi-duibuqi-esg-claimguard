#!/usr/bin/env python3
import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.esg_demo.blocks import flatten_report, load_content_list
from src.esg_demo.extract import _parse_json_object, select_candidate_blocks
from src.esg_demo.indicators import Indicator
from src.esg_demo.ollama import build_llm_client
from src.esg_demo.runner import DEFAULT_MODEL, DEFAULT_OLLAMA_URL, _find_report_jsons, _validate_model


DEFAULT_POOL = Path("outputs/formal_v3_mineru25_qwen36/indicator_pool.csv")
DEFAULT_OUT_DIR = Path("outputs/formal_v3_mineru25_qwen36/new_reports")
ALLOWED_STATUS = {"found", "missing", "error"}
ZERO_EVENT_UNITS = {
    "s_work_injury": "起",
    "s_customer_complaints": "件",
    "e_environmental_penalty": "次",
}
ZERO_EVENT_PATTERNS = (
    "未发生",
    "没有发生",
    "零事故",
    "无工伤",
    "无伤亡",
    "无重大安全事故",
    "0起",
    "0 起",
    "未收到",
)
LLM_ERROR_FIELDS = [
    "report_id",
    "indicator_id",
    "indicator_name",
    "status",
    "llm_reason",
    "raw_response",
    "source_candidate_count",
    "elapsed_seconds",
]
HIGH_RISK_REVIEW_INDICATORS = {
    "s_work_injury",
    "s_customer_complaints",
    "e_environmental_penalty",
    "e_ghg_total",
    "e_cod",
    "e_ammonia_nitrogen",
}


class LLMOutputCircuitBreaker(RuntimeError):
    pass


def run_sample(
    project_root: Path,
    indicator_pool_path: Path,
    out_dir: Path,
    report_limit: int,
    model: str,
    ollama_url: str,
    max_blocks_per_indicator: int,
    client=None,
    report_filters: list[str] | None = None,
    report_paths: list[Path] | None = None,
    resume: bool = False,
    llm_api: str = "ollama",
) -> dict:
    _validate_model(model)
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    indicators = _load_indicators(indicator_pool_path)
    if report_paths is None:
        report_paths = _find_report_jsons(project_root, report_filters or [])
    report_paths = [Path(path) for path in report_paths][:report_limit]
    llm = client or build_llm_client(model=model, url=ollama_url, api=llm_api)
    loaded_results = _load_existing_results(out_dir / "extraction_results.csv") if resume else []
    expected_keys = {(path.parent.name, indicator.indicator_id) for path in report_paths for indicator in indicators}
    loaded_keys = [(row.get("report_id", ""), row.get("indicator_id", "")) for row in loaded_results]
    if len(loaded_keys) != len(set(loaded_keys)):
        raise ValueError("Resume checkpoint contains duplicate report-indicator keys")
    unknown_keys = sorted(set(loaded_keys) - expected_keys)
    if unknown_keys:
        raise ValueError(f"Resume checkpoint contains {len(unknown_keys)} keys outside the frozen run grid")
    # Error rows are deliberately retried on resume. Treating them as completed
    # can make an interrupted batch look healthy while silently preserving a
    # transient inference failure.
    results = [row for row in loaded_results if _valid_resume_row(row)]
    previous_error_rows = len(loaded_results) - len(results)
    completed = {(row["report_id"], row["indicator_id"]) for row in results}
    errors = []
    skipped_results = 0
    executed_calls = 0
    generation_calls = 0
    retry_generation_calls = 0
    consecutive_transport_errors = 0
    consecutive_model_output_errors = 0

    for path in report_paths:
        report_id = path.parent.name
        blocks = flatten_report(report_id, path, load_content_list(path))
        for indicator in indicators:
            if (report_id, indicator.indicator_id) in completed:
                skipped_results += 1
                continue
            row_started = time.time()
            candidates = select_candidate_blocks(blocks, indicator, max_blocks_per_indicator)
            if not candidates:
                results.append(_missing_row(report_id, indicator, 0, round(time.time() - row_started, 3)))
                continue
            executed_calls += 1
            try:
                prompt = _build_v2_prompt(report_id, indicator, candidates)
                generation_calls += 1
                raw = llm.generate(prompt)
                consecutive_transport_errors = 0
                result = _normalize_v2_result(
                    report_id=report_id,
                    indicator=indicator,
                    raw_text=raw,
                    candidate_count=len(candidates),
                    elapsed_seconds=round(time.time() - row_started, 3),
                    candidates=candidates,
                )
                if result["status"] == "error" and "invalid llm json" in result["llm_reason"]:
                    generation_calls += 1
                    retry_generation_calls += 1
                    retry_raw = llm.generate(_build_v2_retry_prompt(prompt))
                    retry_result = _normalize_v2_result(
                        report_id=report_id,
                        indicator=indicator,
                        raw_text=retry_raw,
                        candidate_count=len(candidates),
                        elapsed_seconds=round(time.time() - row_started, 3),
                        candidates=candidates,
                    )
                    if retry_result["status"] != "error":
                        retry_result["llm_reason"] = (retry_result["llm_reason"] + " retry_after_invalid_json").strip()
                        result = retry_result
                if result["status"] == "error":
                    errors.append(_error_row(result))
                    consecutive_model_output_errors += 1
                else:
                    consecutive_model_output_errors = 0
                results.append(result)
                if consecutive_model_output_errors >= 10:
                    _write_progress_checkpoint(out_dir, results, errors)
                    raise LLMOutputCircuitBreaker(
                        "LLM output circuit breaker opened after 10 consecutive invalid result rows"
                    )
            except LLMOutputCircuitBreaker:
                raise
            except Exception as exc:
                consecutive_transport_errors += 1
                result = _error_result(
                    report_id,
                    indicator,
                    str(exc),
                    len(candidates),
                    round(time.time() - row_started, 3),
                )
                errors.append(_error_row(result))
                results.append(result)
                if consecutive_transport_errors >= 3:
                    _write_progress_checkpoint(out_dir, results, errors)
                    raise RuntimeError("LLM transport circuit breaker opened after 3 consecutive request failures") from exc
        _write_progress_checkpoint(out_dir, results, errors)

    _write_json(out_dir / "extraction_results.json", results)
    _write_csv(out_dir / "extraction_results.csv", results)
    if errors:
        _write_csv(out_dir / "llm_errors.csv", errors)
    else:
        _write_csv_with_fields(out_dir / "llm_errors.csv", [], LLM_ERROR_FIELDS)
    error_analysis = _error_analysis_rows(results, errors)
    _write_csv(out_dir / "error_analysis.csv", error_analysis)
    _write_error_analysis_markdown(out_dir / "error_analysis.md", error_analysis)
    _write_csv(out_dir / "sample_review.csv", _sample_review_rows(results))
    summary = {
        "indicator_set": "formal",
        "reports": len(report_paths),
        "report_ids": [path.parent.name for path in report_paths],
        "indicators": len(indicators),
        "results": len(results),
        "total_calls": sum(1 for row in results if int(row["source_candidate_count"]) > 0),
        "executed_calls": executed_calls,
        "generation_calls": generation_calls,
        "retry_generation_calls": retry_generation_calls,
        "previous_results_loaded": len(loaded_results),
        "previous_error_rows_retried": previous_error_rows,
        "skipped_results": skipped_results,
        "resume_enabled": resume,
        "llm_enabled": True,
        "model": model,
        "ollama_url": ollama_url,
        "llm_api": llm_api,
        "llm_error_count": len(errors),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    _write_json(out_dir / "run_summary.json", summary)
    if out_dir.name == "llm_50":
        diagnostics_name = "llm_50_diagnostics.md"
    elif out_dir.name == "llm_100":
        diagnostics_name = "llm_100_diagnostics.md"
    elif out_dir.name == "llm_200":
        diagnostics_name = "llm_200_diagnostics.md"
    else:
        diagnostics_name = "llm_sample_diagnostics.md"
    _write_diagnostics(out_dir / diagnostics_name, summary, results)
    return summary


def _write_progress_checkpoint(out_dir: Path, results: list[dict], errors: list[dict]) -> None:
    _write_json(out_dir / "extraction_results.json", results)
    _write_csv(out_dir / "extraction_results.csv", results)
    if errors:
        _write_csv(out_dir / "llm_errors.csv", errors)
    else:
        _write_csv_with_fields(out_dir / "llm_errors.csv", [], LLM_ERROR_FIELDS)


def _load_indicators(path: Path) -> list[Indicator]:
    rows = _read_csv(path)
    return [
        Indicator(
            row["indicator_id"],
            row["indicator_name"],
            row["dimension"],
            row["indicator_type"],
            tuple(_split_pipe(row.get("keywords", ""))),
            tuple(_split_pipe(row.get("common_units", ""))),
            True,
        )
        for row in rows
    ]


def _load_existing_results(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return _read_csv(path)


def _valid_resume_row(row: dict) -> bool:
    status = row.get("status")
    if status not in {"found", "missing"}:
        return False
    evidence_fields = ("value", "unit", "qualitative_text", "evidence_quote", "page_no", "block_id", "block_type")
    if status == "missing":
        return not any(str(row.get(field, "")).strip() for field in evidence_fields)
    if not all(str(row.get(field, "")).strip() for field in ("evidence_quote", "page_no", "block_id")):
        return False
    if row.get("indicator_type") == "quantitative":
        return (
            bool(str(row.get("value", "")).strip())
            and bool(str(row.get("unit", "")).strip())
            and row.get("quantitative_incomplete") != "true"
        )
    return True


def _build_v2_prompt(report_id: str, indicator: Indicator, candidates: list[dict]) -> str:
    evidence = [
        {
            "block_id": row.get("block_id", ""),
            "page_no": row.get("page_no", ""),
            "block_type": row.get("block_type", ""),
            "text": _shorten(row.get("text", ""), 1200),
        }
        for row in candidates
    ]
    return (
        "/no_think\n"
        "你是 ESG 指标结构化抽取器。只能使用给定候选证据，不得读取整篇报告，不得使用外部知识，不得猜测。\n"
        "如果候选证据不能支持该指标，status 必须为 missing，value/unit/qualitative_text/evidence_quote/page_no/block_id/block_type 留空。\n"
        "定量 quantitative：只有证据明确给出数值时才能 found；value 必须含数字，unit 必须逐字来自证据。没有明确数值或单位时 status=missing，不要写描述性 value，不要自行计算。\n"
        "定性 qualitative：提取不超过 120 个汉字的 qualitative_text。布尔 boolean：只判断证据是否披露该机制/制度/措施，found 时 value 填 true，并给出简短 qualitative_text。\n"
        "found 结果必须有逐字摘自证据的 evidence_quote，且 evidence_quote 控制在 160 个汉字以内。\n"
        "llm_reason 控制在 40 个汉字以内，不能重复解释。\n"
        "只返回一个完整 JSON 对象，字段固定为：status,value,unit,qualitative_text,evidence_quote,page_no,block_id,block_type,llm_confidence,llm_reason。\n"
        f"报告：{report_id}\n"
        f"指标ID：{indicator.indicator_id}\n"
        f"指标名称：{indicator.name}\n"
        f"维度：{indicator.dimension}\n"
        f"指标类型：{indicator.indicator_type}\n"
        f"候选证据：{json.dumps(evidence, ensure_ascii=False)}"
    )


def _build_v2_retry_prompt(original_prompt: str) -> str:
    return (
        original_prompt
        + "\n上一次回答不是合法 JSON。现在只输出一个完整 JSON 对象，不要解释，不要重复推理。"
        + "llm_reason 不超过 20 个汉字。"
    )


def _normalize_v2_result(
    report_id: str,
    indicator: Indicator,
    raw_text: str,
    candidate_count: int,
    elapsed_seconds: float,
    candidates: list[dict] | None = None,
) -> dict:
    try:
        payload = _parse_llm_json(raw_text)
    except ValueError as exc:
        return _error_result(report_id, indicator, f"invalid llm json: {exc}", candidate_count, elapsed_seconds, raw_text)
    status = str(payload.get("status", "") or "").strip()
    if status not in ALLOWED_STATUS:
        has_content = any(str(payload.get(key, "")).strip() for key in ("value", "qualitative_text", "evidence_quote"))
        status = "found" if has_content else "missing"
    result = _base_row(report_id, indicator, status, candidate_count, elapsed_seconds)
    for key in ("value", "unit", "qualitative_text", "evidence_quote", "page_no", "block_id", "block_type"):
        result[key] = payload.get(key, "")
    result["llm_confidence"] = _float_string(payload.get("llm_confidence", payload.get("confidence", 0.0)))
    result["llm_reason"] = str(payload.get("llm_reason", payload.get("notes", "")) or "")
    if result["status"] == "missing":
        for key in ("value", "unit", "qualitative_text", "evidence_quote", "page_no", "block_id", "block_type"):
            result[key] = ""
        return result
    if result["status"] == "found" and not str(result["evidence_quote"]).strip():
        result["status"] = "error"
        result["llm_reason"] = (result["llm_reason"] + " found result missing evidence_quote").strip()
    if result["status"] == "found" and candidates is not None:
        _reconcile_candidate_lineage(result, candidates)
    _postprocess_quantitative_result(result)
    if result.get("quantitative_incomplete") == "true":
        _downgrade_quantitative_to_missing(
            result,
            "quantitative evidence lacks a complete numeric value and source unit",
        )
    return result


def _compact_evidence_text(value: object) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9.%％]+", "", str(value or ""))


def _exact_source_excerpt(source_text: object, quote_text: object) -> str:
    """Recover one contiguous, verbatim source excerpt from an LLM quote.

    Models sometimes join several otherwise-correct snippets with ellipses.  A
    joined quote is not a valid trace, so prefer the longest individually
    traceable segment and map it back to the original source characters.
    """
    source = str(source_text or "")
    compact_source_chars: list[str] = []
    source_positions: list[int] = []
    for index, char in enumerate(source):
        if re.match(r"[\u4e00-\u9fffA-Za-z0-9.%％]", char):
            compact_source_chars.append(char)
            source_positions.append(index)
    compact_source = "".join(compact_source_chars)
    if not compact_source:
        return ""

    raw_segments = [str(quote_text or "")]
    raw_segments.extend(re.split(r"(?:\.{3,}|…+|⋯+|[。；;!！?？]+)", str(quote_text or "")))
    candidates = []
    for segment in raw_segments:
        compact_segment = _compact_evidence_text(segment)
        if len(compact_segment) < 6:
            continue
        start = compact_source.find(compact_segment)
        if start >= 0:
            candidates.append((len(compact_segment), start, compact_segment))
    if not candidates:
        return ""
    _, start, compact_segment = max(candidates)
    raw_start = source_positions[start]
    raw_end = source_positions[start + len(compact_segment) - 1] + 1
    excerpt = source[raw_start:raw_end].strip()
    return excerpt if len(excerpt) <= 160 else ""


def _reconcile_candidate_lineage(result: dict, candidates: list[dict]) -> None:
    quote = _compact_evidence_text(result.get("evidence_quote", ""))
    if not quote:
        return
    by_id = {str(candidate.get("block_id", "")): candidate for candidate in candidates}
    selected = by_id.get(str(result.get("block_id", "")))
    if selected is not None and quote not in _compact_evidence_text(selected.get("text", "")):
        excerpt = _exact_source_excerpt(selected.get("text", ""), result.get("evidence_quote", ""))
        if excerpt:
            result["evidence_quote"] = excerpt
            quote = _compact_evidence_text(excerpt)
            result["postprocess_repaired"] = "true"
            result["repair_method"] = "exact_source_excerpt_reconciliation"
            result["repair_reason"] = "replaced a joined/paraphrased quote with the longest verbatim source segment"
    if selected is None or quote not in _compact_evidence_text(selected.get("text", "")):
        matches = [candidate for candidate in candidates if quote in _compact_evidence_text(candidate.get("text", ""))]
        if not matches:
            excerpt_matches = [
                (candidate, _exact_source_excerpt(candidate.get("text", ""), result.get("evidence_quote", "")))
                for candidate in candidates
            ]
            excerpt_matches = [(candidate, excerpt) for candidate, excerpt in excerpt_matches if excerpt]
            if len(excerpt_matches) == 1:
                selected, excerpt = excerpt_matches[0]
                result["evidence_quote"] = excerpt
                matches = [selected]
                result["postprocess_repaired"] = "true"
                result["repair_method"] = "exact_source_excerpt_reconciliation"
                result["repair_reason"] = "aligned a traceable quote segment to the unique source candidate"
        if len(matches) != 1:
            result["status"] = "error"
            result["llm_reason"] = (result["llm_reason"] + " evidence quote not uniquely traceable to candidates").strip()
            return
        selected = matches[0]
        result["postprocess_repaired"] = "true"
        result["repair_method"] = "candidate_lineage_reconciliation"
        result["repair_reason"] = "aligned model evidence fields to the unique source candidate"
    result["block_id"] = selected.get("block_id", "")
    result["page_no"] = selected.get("page_no", "")
    result["block_type"] = selected.get("block_type", "")


def _parse_llm_json(raw_text: str) -> dict:
    try:
        return _parse_json_object(raw_text)
    except ValueError:
        pass
    text = raw_text.strip()
    text = re.sub(r"```(?:json)?", "", text, flags=re.I).replace("```", "")
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no json object found")


def _postprocess_quantitative_result(row: dict) -> None:
    row["postprocess_repaired"] = row.get("postprocess_repaired", "false")
    row["quantitative_incomplete"] = row.get("quantitative_incomplete", "false")
    row["repair_method"] = row.get("repair_method", "none")
    row["repair_reason"] = row.get("repair_reason", "")
    if row["indicator_type"] != "quantitative" or row["status"] != "found":
        return
    evidence = str(row.get("evidence_quote", ""))
    if not evidence.strip():
        row["quantitative_incomplete"] = "true"
        row["repair_reason"] = "found quantitative result has empty evidence_quote"
        return
    if _apply_conservative_indicator_rules(row):
        return
    if str(row.get("value", "")).strip() and str(row.get("unit", "")).strip() and _looks_numeric_value(row.get("value", "")):
        return
    extracted_value, extracted_unit = _extract_value_unit(evidence)
    repaired_parts = []
    if not str(row.get("value", "")).strip() and extracted_value:
        row["value"] = extracted_value
        repaired_parts.append("value")
    if not str(row.get("unit", "")).strip() and extracted_unit:
        row["unit"] = extracted_unit
        repaired_parts.append("unit")
    if repaired_parts:
        row["postprocess_repaired"] = "true"
        row["repair_method"] = "regex_" + "_".join(repaired_parts) + "_from_evidence"
        row["repair_reason"] = "filled missing quantitative field from evidence_quote"
    if str(row.get("value", "")).strip() and str(row.get("unit", "")).strip() and _looks_numeric_value(row.get("value", "")):
        _apply_conservative_indicator_rules(row)
        return
    if _has_zero_event_evidence(evidence) or _known_zero_count_without_unit(row, evidence):
        unit = ZERO_EVENT_UNITS.get(row["indicator_id"])
        if unit:
            row["value"] = "0"
            row["unit"] = unit
            row["postprocess_repaired"] = "true"
            row["quantitative_incomplete"] = "false"
            row["repair_method"] = "zero_event_normalization"
            row["repair_reason"] = "normalized zero-event count from evidence_quote"
            return
        row["quantitative_incomplete"] = "true"
        row["repair_method"] = "none"
        row["repair_reason"] = "zero_event_but_unit_unknown"
        return
    if not str(row.get("value", "")).strip() or not str(row.get("unit", "")).strip() or not _looks_numeric_value(row.get("value", "")):
        row["quantitative_incomplete"] = "true"
        row["postprocess_repaired"] = "false"
        row["repair_method"] = "none"
        row["repair_reason"] = "quantitative found result lacks numeric value or unit in evidence_quote"
    _apply_conservative_indicator_rules(row)


def _apply_conservative_indicator_rules(row: dict) -> bool:
    indicator_id = row.get("indicator_id", "")
    evidence = str(row.get("evidence_quote", ""))
    compact = re.sub(r"\s+", "", evidence)
    if indicator_id == "s_customer_complaints":
        complaint_count = _extract_customer_complaint_count(evidence)
        if complaint_count:
            value, unit = complaint_count
            if row.get("value") != value or row.get("unit") != unit:
                row["value"] = value
                row["unit"] = unit
                row["postprocess_repaired"] = "true"
                row["quantitative_incomplete"] = "false"
                row["repair_method"] = "customer_complaint_count_override"
                row["repair_reason"] = "preferred explicit customer complaint count over adjacent zero-event text"
            return True
        if any(term in compact for term in ("投诉解决率", "投诉办结率", "投诉率", "满意度")):
            _downgrade_quantitative_to_missing(row, "customer complaint evidence is a rate/process metric, not complaint count")
            return True
    if indicator_id == "s_work_injury":
        if any(term in compact for term in ("工伤保险", "工伤率", "损失工作日", "因工损失", "死亡人数", "投入金额")):
            _downgrade_quantitative_to_missing(row, "work-injury evidence maps to insurance, lost workdays, or deaths rather than accident count")
            return True
        if "工伤" not in compact and not _has_zero_event_evidence(evidence):
            _downgrade_quantitative_to_missing(row, "work-injury count requires explicit work-injury evidence")
            return True
    if indicator_id == "s_customer_satisfaction":
        has_satisfaction_context = "满意度" in compact or "NPS" in evidence.upper()
        has_specific_number = bool(
            re.search(r"(满意度|NPS)[^，。；;|]{0,12}?(?:为|达|达到|得分|分数|=|：|:)?\s*\d+(?:\.\d+)?\s*(%|％|分)", evidence, flags=re.I)
            or re.search(r"NPS\s*(?:为|达|达到|=|：|:)\s*\d+(?:\.\d+)?(?!\s*年)", evidence, flags=re.I)
        )
        if not has_satisfaction_context or not has_specific_number:
            _downgrade_quantitative_to_missing(row, "customer satisfaction requires an explicit satisfaction/NPS numeric value")
            return True
    if indicator_id == "s_patents":
        patent_count = re.search(r"(?:发明)?专利\s*(\d+(?:,\d{3})*)", evidence)
        if patent_count and not str(row.get("unit", "")).strip():
            row["value"] = patent_count.group(1).replace(",", "")
            row["unit"] = "项"
            row["postprocess_repaired"] = "true"
            row["quantitative_incomplete"] = "false"
            row["repair_method"] = "patent_count_unit_from_evidence"
            row["repair_reason"] = "filled patent count unit from evidence_quote"
            return True
        if not _looks_numeric_value(row.get("value", "")):
            _downgrade_quantitative_to_missing(row, "patent count evidence lacks a specific numeric value")
            return True
    if indicator_id == "s_employee_gender":
        if "女性员工" in compact and _looks_numeric_value(row.get("value", "")) and not str(row.get("unit", "")).strip():
            row["unit"] = "人"
            row["postprocess_repaired"] = "true"
            row["quantitative_incomplete"] = "false"
            row["repair_method"] = "employee_gender_unit_from_evidence"
            row["repair_reason"] = "filled female employee count unit from evidence_quote"
            return True
    if indicator_id == "g_independent_director_ratio":
        if re.search(r"\d+\s*/\s*\d+", str(row.get("value", ""))) and not str(row.get("unit", "")).strip():
            row["unit"] = "比例"
            row["postprocess_repaired"] = "true"
            row["quantitative_incomplete"] = "false"
            row["repair_method"] = "ratio_unit_from_indicator_context"
            row["repair_reason"] = "filled ratio unit for fraction value supported by evidence_quote"
            return True
    if indicator_id == "g_board_diversity":
        if "独立董事占比" in compact and not any(term in compact for term in ("女性董事", "董事会多元", "性别", "多元化")):
            _downgrade_quantitative_to_missing(row, "board diversity evidence maps to independent director ratio")
            return True
    if indicator_id == "e_voc":
        if str(row.get("unit", "")).strip() in {"%", "％"} and any(term in compact for term in ("下降", "减少", "降低")):
            _downgrade_quantitative_to_missing(row, "VOC evidence is a percentage change rather than emission amount")
            return True
    if indicator_id == "e_air_pollutants":
        if re.search(r"GB\d", evidence, flags=re.I) and not any(unit in evidence for unit in ("吨", "千克", "公斤")):
            _downgrade_quantitative_to_missing(row, "air pollutant evidence maps to discharge standard rather than emission amount")
            return True
    if indicator_id in {"s_research_development", "s_community_investment"}:
        if not _looks_numeric_value(row.get("value", "")) or not str(row.get("unit", "")).strip():
            _downgrade_quantitative_to_missing(row, "investment indicator requires explicit numeric value and unit")
            return True
    return False


def _extract_customer_complaint_count(text: str) -> tuple[str, str] | None:
    patterns = (
        r"客户投诉[^，。；;|]{0,12}?(\d+(?:\.\d+)?)\s*(起|件|次)",
        r"投诉[^，。；;|]{0,8}?(\d+(?:\.\d+)?)\s*(起|件|次)",
        r"(\d+(?:\.\d+)?)\s*(起|件|次)[^，。；;|]{0,8}?客户投诉",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1), match.group(2)
    return None


def _known_zero_count_without_unit(row: dict, evidence: str) -> bool:
    if str(row.get("value", "")).strip() not in {"0", "0.0", "0.00"}:
        return False
    indicator_id = row.get("indicator_id", "")
    compact = re.sub(r"\s+", "", evidence)
    if indicator_id == "s_work_injury" and re.search(r"工伤[^0-9]{0,6}0", compact):
        return True
    if indicator_id == "s_customer_complaints" and ("未收到客户投诉" in compact or "无客户投诉" in compact):
        return True
    return False


def _downgrade_quantitative_to_missing(row: dict, reason: str) -> None:
    row["status"] = "missing"
    for key in ("value", "unit", "qualitative_text", "evidence_quote", "page_no", "block_id", "block_type"):
        row[key] = ""
    row["postprocess_repaired"] = "false"
    row["quantitative_incomplete"] = "false"
    row["repair_method"] = "conservative_missing"
    row["repair_reason"] = reason
    row["llm_reason"] = (str(row.get("llm_reason", "")) + " conservative_missing").strip()


def _extract_value_unit(text: str) -> tuple[str, str]:
    unit_pattern = r"(吨二氧化碳当量|吨标准煤|万吨标准煤|吨/百万营收|吨二氧化碳当量/百万营收|万元|元|名|人次|人|次|件|项|家|小时|千瓦时|万千瓦时|兆瓦时|MWh|kWh|万立方米|立方米|吨|千克|公斤|分|%|％)"
    match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(" + unit_pattern + r")", text, flags=re.I)
    if match:
        return match.group(1).replace(",", ""), match.group(2)
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*(%|％)", text)
    if percent_match:
        return percent_match.group(1), percent_match.group(2)
    number_match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", text)
    unit_match = re.search(r"(?<!事)" + unit_pattern, text, flags=re.I)
    return (number_match.group(1).replace(",", "") if number_match else "", unit_match.group(1) if unit_match else "")


def _looks_numeric_value(value) -> bool:
    return bool(re.search(r"\d", str(value or "")))


def _has_zero_event_evidence(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if any(pattern.replace(" ", "") in compact for pattern in ZERO_EVENT_PATTERNS):
        return True
    if re.search(r"无[^，。；;]{0,8}(事故|处罚|违规|投诉|伤亡|工伤)", compact):
        return True
    return False


def _missing_row(report_id: str, indicator: Indicator, candidate_count: int, elapsed_seconds: float) -> dict:
    return _base_row(report_id, indicator, "missing", candidate_count, elapsed_seconds)


def _error_result(report_id: str, indicator: Indicator, reason: str, candidate_count: int, elapsed_seconds: float, raw_response: str = "") -> dict:
    row = _base_row(report_id, indicator, "error", candidate_count, elapsed_seconds)
    row["llm_reason"] = reason
    row["raw_response"] = raw_response
    return row


def _base_row(report_id: str, indicator: Indicator, status: str, candidate_count: int, elapsed_seconds: float) -> dict:
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
        "llm_confidence": "0.0000",
        "llm_reason": "",
        "source_candidate_count": candidate_count,
        "elapsed_seconds": f"{elapsed_seconds:.3f}",
        "postprocess_repaired": "false",
        "quantitative_incomplete": "false",
        "repair_method": "none",
        "repair_reason": "",
        "raw_response": "",
    }


def _error_row(row: dict) -> dict:
    return {
        "report_id": row["report_id"],
        "indicator_id": row["indicator_id"],
        "indicator_name": row["indicator_name"],
        "status": row["status"],
        "llm_reason": row["llm_reason"],
        "raw_response": row.get("raw_response", ""),
        "source_candidate_count": row["source_candidate_count"],
        "elapsed_seconds": row["elapsed_seconds"],
    }


def _sample_review_rows(results: list[dict], max_rows: int = 200) -> list[dict]:
    candidates = [row for row in results if row["status"] != "missing"]
    candidates.sort(key=_sample_review_priority)
    rows = []
    for row in candidates[:max_rows]:
        review = dict(row)
        review["review_label"] = ""
        review["review_notes"] = ""
        review["manual_label"] = ""
        review["manual_notes"] = ""
        rows.append(review)
    return rows


def _sample_review_priority(row: dict) -> tuple:
    confidence = _safe_float(row.get("llm_confidence"), 1.0)
    return (
        0 if row.get("quantitative_incomplete") == "true" else 1,
        0 if row.get("postprocess_repaired") == "true" else 1,
        0 if confidence < 0.65 else 1,
        0 if row.get("indicator_id") in HIGH_RISK_REVIEW_INDICATORS else 1,
        row.get("dimension", ""),
        row.get("indicator_type", ""),
        row.get("report_id", ""),
        row.get("indicator_id", ""),
    )


def _error_analysis_rows(results: list[dict], errors: list[dict]) -> list[dict]:
    error_lookup = {(row["report_id"], row["indicator_id"]): row for row in errors}
    rows = []
    for row in results:
        is_error = row["status"] == "error"
        is_incomplete_quant = (
            row["status"] == "found"
            and row["indicator_type"] == "quantitative"
            and (not str(row["value"]).strip() or not str(row["unit"]).strip() or row.get("quantitative_incomplete") == "true")
        )
        if not is_error and not is_incomplete_quant:
            continue
        error_category, root_cause, fix_strategy = _classify_problem(row, error_lookup.get((row["report_id"], row["indicator_id"]), {}))
        rows.append(
            {
                "report_id": row["report_id"],
                "indicator_id": row["indicator_id"],
                "indicator_name": row["indicator_name"],
                "dimension": row["dimension"],
                "indicator_type": row["indicator_type"],
                "status": row["status"],
                "value": row["value"],
                "unit": row["unit"],
                "evidence_quote": row["evidence_quote"],
                "page_no": row["page_no"],
                "block_id": row["block_id"],
                "block_type": row["block_type"],
                "error_category": error_category,
                "root_cause": root_cause,
                "fix_strategy": fix_strategy,
                "raw_response": row.get("raw_response", ""),
            }
        )
    return rows


def _classify_problem(row: dict, error: dict) -> tuple[str, str, str]:
    if row["status"] == "error":
        reason = row.get("llm_reason", "")
        if "invalid llm json" in reason:
            return ("json_parse_error", "模型响应无法解析为合法 JSON。", "保留 raw_response，使用更稳健 JSON 提取；必要时对该样本重试。")
        return ("llm_error", reason or "LLM 调用或输出异常。", "检查 llm_errors.csv 中 raw_response 和候选证据。")
    if row.get("postprocess_repaired") == "true" and row.get("quantitative_incomplete") == "false":
        return ("postprocess_repaired", "模型漏填 value 或 unit，但 evidence_quote 中可正则提取。", "保留修复值，并在扩量时监控同类指标。")
    if row.get("quantitative_incomplete") == "true":
        if not _looks_numeric_value(row.get("value", "")):
            return ("quantitative_non_numeric", "模型把描述性文本或指标词填入 quantitative value。", "保持 found 但标记 quantitative_incomplete，不伪造数值；后续收紧 prompt。")
        return ("quantitative_unit_missing", "定量结果缺少单位，且 evidence_quote 无法可靠补齐。", "保持 found 并标记 quantitative_incomplete；后续补充单位词召回或人工复核。")
    return ("other", "未分类问题。", "人工复核。")


def _write_error_analysis_markdown(path: Path, rows: list[dict]) -> None:
    counts = Counter(row["error_category"] for row in rows)
    lines = [
        "# formal LLM Sample Error Analysis",
        "",
        "本报告分析 formal 小样本 LLM 抽取中的 JSON/error 与定量字段缺失问题，不是人工 gold 标注。",
        "",
        f"- 问题记录数：{len(rows)}",
        f"- error_category 分布：{dict(counts)}",
        "",
        "## Problem Rows",
        "",
    ]
    if not rows:
        lines.append("无。")
    else:
        for row in rows:
            lines.append(
                f"- `{row['indicator_id']}` / `{row['report_id']}` / {row['error_category']}：{row['root_cause']} 修复策略：{row['fix_strategy']}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_diagnostics(path: Path, summary: dict, results: list[dict]) -> None:
    status_counts = Counter(row["status"] for row in results)
    found = [row for row in results if row["status"] == "found"]
    found_by_dimension = Counter(row["dimension"] for row in found)
    found_by_type = Counter(row["indicator_type"] for row in found)
    elapsed_values = [float(row["elapsed_seconds"]) for row in results]
    call_elapsed_values = [
        float(row["elapsed_seconds"])
        for row in results
        if int(row.get("source_candidate_count") or 0) > 0
    ]
    evidence_empty_found = sum(1 for row in found if not str(row["evidence_quote"]).strip())
    quantitative_missing_value_unit = sum(
        1
        for row in found
        if row["indicator_type"] == "quantitative" and (not str(row["value"]).strip() or not str(row["unit"]).strip())
    )
    postprocess_repaired = sum(1 for row in results if row.get("postprocess_repaired") == "true")
    quantitative_incomplete = sum(1 for row in results if row.get("quantitative_incomplete") == "true")
    problem_rows = [
        row
        for row in results
        if row["status"] == "error" or row.get("quantitative_incomplete") == "true"
    ]
    error_rate = status_counts["error"] / len(results) if results else 0.0
    avg_elapsed = sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0.0
    avg_call_elapsed = sum(call_elapsed_values) / len(call_elapsed_values) if call_elapsed_values else 0.0
    slowest_rows = sorted(results, key=lambda row: float(row.get("elapsed_seconds") or 0), reverse=True)[:10]
    if path.name == "llm_100_diagnostics.md":
        recommendation = (
            "建议作为最终实验结果进入报告。"
            if error_rate <= 0.03 and evidence_empty_found == 0 and quantitative_missing_value_unit <= 15
            else "暂不建议作为最终实验结果；需先修复错误、证据缺失或定量字段缺失问题。"
        )
    elif path.name == "llm_200_diagnostics.md":
        recommendation = (
            "200 份全量实验可作为系统规模化能力支撑。"
            if error_rate <= 0.03 and evidence_empty_found == 0 and quantitative_missing_value_unit <= 30
            else "200 份全量实验仍有需复核问题；报告中应按限制说明。"
        )
    else:
        recommendation = (
            "建议进入下一阶段 100 份扩展抽取。"
            if error_rate <= 0.03 and evidence_empty_found == 0 and quantitative_missing_value_unit <= 10
            else "暂不建议扩展到 100 份；需先修复错误、证据缺失或定量字段缺失问题。"
        )
    lines = [
        _diagnostics_title(path),
        "",
        "- 本诊断基于 formal qwen3 证据约束抽取，不是 ESG 评分或排名。",
        f"- 报告数：{summary['reports']}",
        f"- 指标数：{summary['indicators']}",
        f"- 总结果数：{len(results)}",
        f"- qwen3 调用数（结果口径）：{summary['total_calls']}",
        f"- 本次运行新增 qwen3 调用数：{summary.get('executed_calls', summary['total_calls'])}",
        f"- 断点续跑跳过结果数：{summary.get('skipped_results', 0)}",
        f"- 总调用数：{summary['total_calls']}",
        f"- llm_error_count：{summary.get('llm_error_count', status_counts['error'])}",
        f"- found / missing / error 数量：{dict(status_counts)}",
        f"- E/S/G found 分布：{dict(found_by_dimension)}",
        f"- quantitative / qualitative / boolean found 分布：{dict(found_by_type)}",
        f"- 平均单次调用耗时：{avg_call_elapsed:.3f} 秒/调用",
        f"- 平均结果耗时：{avg_elapsed:.3f} 秒/结果",
        f"- 总耗时：{summary.get('elapsed_seconds', 0)} 秒",
        f"- 错误率：{error_rate:.4f}",
        f"- JSON/error 是否已消除：{'是' if status_counts['error'] == 0 else '否'}",
        f"- 证据为空的 found 数量：{evidence_empty_found}",
        f"- value/unit 缺失的定量 found 数量：{quantitative_missing_value_unit}",
        f"- quantitative found value/unit 缺失是否减少：当前为 {quantitative_missing_value_unit}，修复后通过 postprocess/标记机制显式处理。",
        f"- postprocess repaired 数量：{postprocess_repaired}",
        f"- quantitative_incomplete 数量：{quantitative_incomplete}",
        "- 仍有问题的 indicator_id 和原因："
        + (" 无" if not problem_rows else ""),
    ]
    for row in problem_rows[:20]:
        lines.append(f"  - `{row['indicator_id']}` / `{row['report_id']}`：{row.get('llm_reason') or row.get('repair_reason')}")
    lines.append("- 最慢的 10 个 report-indicator：")
    for row in slowest_rows:
        lines.append(
            f"  - `{row['report_id']}` / `{row['indicator_id']}`：{float(row.get('elapsed_seconds') or 0):.3f} 秒，status={row['status']}"
        )
    lines.extend([
        f"- 下一阶段建议：{recommendation}",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _diagnostics_title(path: Path) -> str:
    if path.name == "llm_50_diagnostics.md":
        return "# formal LLM 50 Diagnostics"
    if path.name == "llm_100_diagnostics.md":
        return "# formal LLM 100 Diagnostics"
    if path.name == "llm_200_diagnostics.md":
        return "# formal LLM 200 Diagnostics"
    return "# formal LLM Sample Diagnostics"


def _write_json(path: Path, rows) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    if not rows:
        temporary.write_text("", encoding="utf-8")
        temporary.replace(path)
        return
    with temporary.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(_sanitize_row(row) for row in rows)
    temporary.replace(path)


def _write_csv_with_fields(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_sanitize_row(row) for row in rows)
    temporary.replace(path)


def _sanitize_row(row: dict) -> dict:
    return {key: (value.replace("\x00", "") if isinstance(value, str) else value) for key, value in row.items()}


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def _shorten(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _float_string(value) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "0.0000"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the current ESG-65 evidence-constrained extraction.")
    parser.add_argument("--indicator-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report-limit", type=int, default=10)
    parser.add_argument("--reports", nargs="*", default=[])
    parser.add_argument("--input-json", nargs="*", default=[], help="Explicit MinerU content_list_v2.json paths for new reports.")
    parser.add_argument("--resume", action="store_true", help="Skip report-indicator rows already present in extraction_results.csv.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--llm-api", choices=["ollama", "openai"], default="ollama")
    parser.add_argument("--max-blocks-per-indicator", type=int, default=5)
    args = parser.parse_args()
    explicit_paths = [Path(path) for path in args.input_json]
    summary = run_sample(
        project_root=Path("."),
        indicator_pool_path=Path(args.indicator_pool),
        out_dir=Path(args.out_dir),
        report_limit=args.report_limit,
        model=args.model,
        ollama_url=args.ollama_url,
        max_blocks_per_indicator=args.max_blocks_per_indicator,
        report_filters=args.reports,
        report_paths=explicit_paths or None,
        resume=args.resume,
        llm_api=args.llm_api,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
