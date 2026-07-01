#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_esg_formal_v2 import DEFAULT_POOL, run_sample
from src.esg_demo.runner import DEFAULT_MODEL, DEFAULT_OLLAMA_URL


PRESET_LIMITS = {
    "sample": 10,
    "50": 50,
    "100": 100,
    "200": 200,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end ESG extraction system entrypoint for MinerU content_list_v2.json reports."
    )
    parser.add_argument("--mode", choices=sorted(PRESET_LIMITS), default="sample")
    parser.add_argument("--input-json", nargs="*", default=[], help="Explicit content_list_v2.json paths for new reports.")
    parser.add_argument("--reports", nargs="*", default=[], help="Report code/name filters when using parsed report library.")
    parser.add_argument("--out-dir", default="", help="Output directory. Defaults to outputs/formal_v2/llm_<mode>.")
    parser.add_argument("--indicator-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--max-blocks-per-indicator", type=int, default=5)
    parser.add_argument("--resume", action="store_true", help="Skip already completed report-indicator pairs.")
    args = parser.parse_args()

    input_paths = [Path(path) for path in args.input_json]
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"outputs/formal_v2/llm_{args.mode}")
    if input_paths and not args.out_dir:
        out_dir = Path("outputs/formal_v2/new_reports")

    summary = run_sample(
        project_root=Path("."),
        indicator_pool_path=Path(args.indicator_pool),
        out_dir=out_dir,
        report_limit=len(input_paths) if input_paths else PRESET_LIMITS[args.mode],
        model=args.model,
        ollama_url=args.ollama_url,
        max_blocks_per_indicator=args.max_blocks_per_indicator,
        report_filters=args.reports,
        report_paths=input_paths or None,
        resume=args.resume,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
