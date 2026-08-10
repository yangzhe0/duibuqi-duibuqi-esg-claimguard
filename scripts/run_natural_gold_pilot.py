#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_api.natural_gold_pilot import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    OUTPUT_DIR,
    PILOT_DIR,
    build_pilot,
    compare_silver_drafts,
    generate_silver_drafts,
    load_pilot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and run model-generated Silver-A/B drafts for Natural-Gold Pilot-30.")
    parser.add_argument("--stage", choices=("build", "silver_a", "silver_b", "compare", "all"), default="all")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    if args.stage in {"build", "all"}:
        payload = build_pilot(output_dir=PILOT_DIR)
        print(json.dumps(payload["metadata"], ensure_ascii=False, indent=2), flush=True)
    pilot = load_pilot()
    if args.stage in {"silver_a", "all"}:
        generate_silver_drafts("silver_a", pilot, output_dir, args.model, args.ollama_url, not args.no_resume)
    if args.stage in {"silver_b", "all"}:
        generate_silver_drafts("silver_b", pilot, output_dir, args.model, args.ollama_url, not args.no_resume)
    if args.stage in {"compare", "all"}:
        summary = compare_silver_drafts(pilot, output_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
