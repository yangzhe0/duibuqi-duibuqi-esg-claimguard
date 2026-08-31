#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "dashboard_web/package-lock.json"
OUTPUT = ROOT / "outputs/ai_contest/frontend_dependency_licenses.md"


def main() -> int:
    payload = json.loads(LOCK.read_text(encoding="utf-8"))
    rows = []
    for key, item in payload.get("packages", {}).items():
        if not key.startswith("node_modules/"):
            continue
        rows.append((key.removeprefix("node_modules/"), item.get("version", ""), item.get("license", "UNKNOWN")))
    rows.sort(key=lambda row: row[0].lower())
    counts = Counter(row[2] for row in rows)
    summary = "、".join(f"{license_id} {count}" for license_id, count in sorted(counts.items()))
    table = "\n".join(f"| `{name}` | `{version}` | `{license_id}` |" for name, version, license_id in rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "# 前端依赖许可清单\n\n"
        "> 来源：`dashboard_web/package-lock.json`；生成日期：2026-08-22。"
        "包元数据用于提交披露，具体义务仍以上游许可证正文为准。\n\n"
        f"- 依赖包数：{len(rows)}\n- 许可分布：{summary}\n\n"
        "| 包 | 版本 | package-lock 许可标识 |\n|---|---:|---|\n"
        + table
        + "\n",
        encoding="utf-8",
    )
    print(OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
