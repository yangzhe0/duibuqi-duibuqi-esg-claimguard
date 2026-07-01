#!/usr/bin/env python3
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_esg_formal_v2 import DEFAULT_POOL, run_sample
from src.esg_demo.runner import DEFAULT_MODEL, DEFAULT_OLLAMA_URL


def main() -> int:
    summary = run_sample(
        project_root=Path("."),
        indicator_pool_path=DEFAULT_POOL,
        out_dir=Path("outputs/formal_v2/llm_100"),
        report_limit=100,
        model=DEFAULT_MODEL,
        ollama_url=DEFAULT_OLLAMA_URL,
        max_blocks_per_indicator=5,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
