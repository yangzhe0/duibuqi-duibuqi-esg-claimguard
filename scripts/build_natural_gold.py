#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_api.natural_gold import DEFAULT_DATASET_DIR, DEFAULT_SAMPLE_SIZE, SAMPLING_SEED, build_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the frozen, model-blind Natural-Gold v1 sample manifest.")
    parser.add_argument("--output-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", default=SAMPLING_SEED)
    args = parser.parse_args()
    payload = build_manifest(Path(args.output_dir), args.sample_size, args.seed)
    rows = payload["rows"]
    print(
        json.dumps(
            {
                "manifest": payload["manifest_path"],
                "sha256": payload["metadata"]["manifest_sha256"],
                "sample_size": len(rows),
                "dimensions": Counter(row["dimension"] for row in rows),
                "indicator_types": Counter(row["indicator_type"] for row in rows),
                "unique_reports": len({row["report_id"] for row in rows}),
                "unique_indicators": len({row["indicator_id"] for row in rows}),
                "model_output_in_manifest": payload["metadata"]["model_output_in_manifest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
