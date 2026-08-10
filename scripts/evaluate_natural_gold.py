#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_api.natural_gold import natural_gold_evaluation, natural_gold_summary
from dashboard_api.reviews import ReviewStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/ai_contest/natural_gold_evaluation.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the frozen model only after Natural-Gold v1 is complete.")
    parser.add_argument("--db", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    store = ReviewStore(Path(args.db)) if args.db else ReviewStore()
    annotations = store.natural_gold_annotations()
    payload = {
        "summary": natural_gold_summary(annotations),
        "evaluation": natural_gold_evaluation(annotations),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
