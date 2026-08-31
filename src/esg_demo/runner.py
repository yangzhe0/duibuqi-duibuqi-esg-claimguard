import argparse
import csv
import json
import time
from pathlib import Path

from .blocks import flatten_report, load_content_list
from .extract import build_prompt, candidate_result, empty_result, normalize_llm_result, select_candidate_blocks
from .indicators import DEMO_INDICATORS, FORMAL_INDICATORS, Indicator
from .ollama import OllamaClient


DEFAULT_REPORT_FILTERS = ["06810", "002692", "605377", "688618"]
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "qwen3:30b"
DEFAULT_FORMAL_REPORT_LIMIT = 100
DISALLOWED_MODELS = {"qwen2.5:7b-instruct"}


def run_demo(
    project_root: Path,
    report_filters: list[str],
    out_dir: Path,
    model: str,
    ollama_url: str,
    max_blocks_per_indicator: int,
    use_llm: bool,
) -> dict:
    _validate_model(model)
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_paths = _find_report_jsons(project_root, report_filters)
    summary = _run_extraction(
        started=started,
        report_paths=report_paths,
        out_dir=out_dir,
        model=model,
        ollama_url=ollama_url,
        max_blocks_per_indicator=max_blocks_per_indicator,
        use_llm=use_llm,
        indicators=DEMO_INDICATORS,
        indicator_set="demo",
        write_formal_artifacts=False,
    )
    return summary


def run_formal(
    project_root: Path,
    report_filters: list[str],
    report_limit: int | None,
    out_dir: Path,
    model: str,
    ollama_url: str,
    max_blocks_per_indicator: int,
    use_llm: bool,
) -> dict:
    _validate_model(model)
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_paths = _find_report_jsons(project_root, report_filters)
    if report_limit is not None:
        report_paths = report_paths[:report_limit]
    return _run_extraction(
        started=started,
        report_paths=report_paths,
        out_dir=out_dir,
        model=model,
        ollama_url=ollama_url,
        max_blocks_per_indicator=max_blocks_per_indicator,
        use_llm=use_llm,
        indicators=FORMAL_INDICATORS,
        indicator_set="formal_current",
        write_formal_artifacts=True,
        report_limit=report_limit,
    )


def _run_extraction(
    started: float,
    report_paths: list[Path],
    out_dir: Path,
    model: str,
    ollama_url: str,
    max_blocks_per_indicator: int,
    use_llm: bool,
    indicators: list[Indicator],
    indicator_set: str,
    write_formal_artifacts: bool,
    report_limit: int | None = None,
) -> dict:
    all_blocks = []
    blocks_by_report = {}
    for path in report_paths:
        report_id = path.parent.name
        blocks = flatten_report(report_id, path, load_content_list(path))
        blocks_by_report[report_id] = blocks
        all_blocks.extend(blocks)

    client = OllamaClient(model=model, url=ollama_url) if use_llm else None
    results = []
    coverage_rows = []
    llm_errors = []
    for report_id, blocks in blocks_by_report.items():
        for indicator in indicators:
            candidates = select_candidate_blocks(blocks, indicator, max_blocks_per_indicator)
            coverage_rows.append(_coverage_row(report_id, indicator, candidates))
            if not candidates:
                results.append(empty_result(report_id, indicator, "missing"))
                continue
            if not client:
                results.append(candidate_result(report_id, indicator, candidates))
                continue
            try:
                raw = client.generate(build_prompt(report_id, indicator, candidates))
                results.append(normalize_llm_result(report_id, indicator, raw))
            except Exception as exc:
                llm_errors.append(str(exc))
                results.append(empty_result(report_id, indicator, "error", str(exc)))

    if write_formal_artifacts:
        indicator_rows = [_indicator_row(indicator) for indicator in indicators]
        _write_json(out_dir / "indicator_pool.json", indicator_rows)
        _write_csv(out_dir / "indicator_pool.csv", indicator_rows)
        _write_csv(out_dir / "candidate_coverage.csv", coverage_rows)
        _write_csv(out_dir / "quality_review_sample.csv", _quality_review_rows(results))
    _write_csv(out_dir / "block_table_sample.csv", all_blocks)
    _write_json(out_dir / "extraction_results.json", results)
    _write_csv(out_dir / "extraction_results.csv", results)
    summary = {
        "indicator_set": indicator_set,
        "reports": len(report_paths),
        "report_ids": [path.parent.name for path in report_paths],
        "report_limit": report_limit,
        "blocks": len(all_blocks),
        "indicators": len(indicators),
        "results": len(results),
        "llm_enabled": use_llm,
        "model": model,
        "ollama_url": ollama_url,
        "llm_error_count": len(llm_errors),
        "llm_errors": llm_errors[:5],
        "elapsed_seconds": round(time.time() - started, 3),
    }
    _write_json(out_dir / "run_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ESG MinerU JSON extraction demo.")
    parser.add_argument("--reports", nargs="*", default=DEFAULT_REPORT_FILTERS, help="Report code/prefix filters.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--out-dir", default="outputs/demo")
    parser.add_argument("--max-blocks-per-indicator", type=int, default=5)
    parser.add_argument("--no-llm", action="store_true", help="Generate candidate evidence without calling Ollama.")
    args = parser.parse_args(argv)
    try:
        _validate_model(args.model)
    except ValueError as exc:
        parser.error(str(exc))

    summary = run_demo(
        project_root=Path("."),
        report_filters=args.reports,
        out_dir=Path(args.out_dir),
        model=args.model,
        ollama_url=args.ollama_url,
        max_blocks_per_indicator=args.max_blocks_per_indicator,
        use_llm=not args.no_llm,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def formal_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the formal ESG extraction workflow.")
    parser.add_argument("--reports", nargs="*", default=[], help="Report code/prefix filters. Empty means all parsed reports.")
    parser.add_argument("--report-limit", type=int, default=DEFAULT_FORMAL_REPORT_LIMIT)
    parser.add_argument("--indicator-set", choices=["formal_current"], default="formal_current")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--out-dir", default="outputs/formal_v3_mineru25_qwen36/new_reports")
    parser.add_argument("--max-blocks-per-indicator", type=int, default=5)
    parser.add_argument("--no-llm", action="store_true", help="Generate candidate evidence and coverage without calling Ollama.")
    args = parser.parse_args(argv)
    try:
        _validate_model(args.model)
    except ValueError as exc:
        parser.error(str(exc))

    summary = run_formal(
        project_root=Path("."),
        report_filters=args.reports,
        report_limit=args.report_limit,
        out_dir=Path(args.out_dir),
        model=args.model,
        ollama_url=args.ollama_url,
        max_blocks_per_indicator=args.max_blocks_per_indicator,
        use_llm=not args.no_llm,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _validate_model(model: str) -> None:
    if model in DISALLOWED_MODELS:
        raise ValueError(f"model {model} is not allowed for this demo; use {DEFAULT_MODEL}")


def _indicator_row(indicator: Indicator) -> dict:
    return {
        "indicator_id": indicator.indicator_id,
        "indicator_name": indicator.name,
        "dimension": indicator.dimension,
        "indicator_type": indicator.indicator_type,
        "keywords": "|".join(indicator.keywords),
        "common_units": "|".join(indicator.common_units),
        "is_core": indicator.is_core,
    }


def _coverage_row(report_id: str, indicator: Indicator, candidates: list[dict]) -> dict:
    first = candidates[0] if candidates else {}
    return {
        "report_id": report_id,
        "indicator_id": indicator.indicator_id,
        "indicator_name": indicator.name,
        "dimension": indicator.dimension,
        "indicator_type": indicator.indicator_type,
        "status": "candidate" if candidates else "missing",
        "candidate_count": len(candidates),
        "top_page_no": first.get("page_no", ""),
        "top_block_id": first.get("block_id", ""),
        "top_block_type": first.get("block_type", ""),
        "top_evidence_quote": first.get("text", "")[:500] if first else "",
    }


def _quality_review_rows(results: list[dict], max_rows: int = 200) -> list[dict]:
    review_rows = []
    for row in results:
        if row.get("status") not in {"candidate", "found"}:
            continue
        if not str(row.get("evidence_quote", "")).strip():
            continue
        review_rows.append(
            {
                "report_id": row.get("report_id", ""),
                "indicator_id": row.get("indicator_id", ""),
                "indicator_name": row.get("indicator_name", ""),
                "dimension": row.get("dimension", ""),
                "indicator_type": row.get("indicator_type", ""),
                "status": row.get("status", ""),
                "value": row.get("value", ""),
                "unit": row.get("unit", ""),
                "qualitative_text": row.get("qualitative_text", ""),
                "page_no": row.get("page_no", ""),
                "block_id": row.get("block_id", ""),
                "block_type": row.get("block_type", ""),
                "evidence_quote": row.get("evidence_quote", ""),
                "manual_label": "",
                "manual_notes": "",
            }
        )
        if len(review_rows) >= max_rows:
            break
    return review_rows


def _find_report_jsons(project_root: Path, report_filters: list[str]) -> list[Path]:
    reports_root = project_root / "outputs/formal_v3_mineru25_qwen36/parsed"
    paths = []
    for report_dir in sorted(path for path in reports_root.iterdir() if path.is_dir()):
        if report_filters and not any(report_dir.name.startswith(value) or value in report_dir.name for value in report_filters):
            continue
        json_path = report_dir / f"{report_dir.name}_content_list_v2.json"
        if json_path.is_file():
            paths.append(json_path)
    if not paths:
        raise FileNotFoundError(f"no reports matched filters: {report_filters}")
    return paths


def _write_json(path: Path, rows) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_sanitize_csv_row(row) for row in rows)


def _sanitize_csv_row(row: dict) -> dict:
    return {key: _sanitize_csv_value(value) for key, value in row.items()}


def _sanitize_csv_value(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
