#!/usr/bin/env python3
"""Capture factual source and product screenshots used by the project document."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/ai_contest/assets"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=1,
            locale="zh-CN",
            color_scheme="light",
        )

        dashboard = context.new_page()
        dashboard.goto(args.dashboard_url, wait_until="networkidle")
        dashboard.locator(".metric-grid").wait_for(timeout=30_000)
        dashboard.screenshot(path=args.output / "product_overview.png", full_page=False)

        dashboard.locator("nav button", has_text="披露预审").click()
        dashboard.locator(".preaudit-kpis").wait_for(timeout=30_000)
        dashboard.locator(".issue-queue button").first.wait_for(timeout=30_000)
        dashboard.screenshot(path=args.output / "product_preaudit.png", full_page=False)

        dashboard.locator("nav button", has_text="证据复核").click()
        dashboard.locator(".workbench-page").wait_for(timeout=30_000)
        dashboard.locator(".indicator-list button").first.wait_for(timeout=30_000)
        dashboard.wait_for_timeout(5_000)
        dashboard.screenshot(path=args.output / "product_evidence.png", full_page=False)

        source = context.new_page()
        source.goto(
            "https://www.cninfo.com.cn/new/fulltextSearch?notautosubmit=&keyWord=ESG%E6%8A%A5%E5%91%8A",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        source.wait_for_timeout(8_000)
        source.screenshot(path=args.output / "cninfo_search.png", full_page=False)

        browser.close()

    for path in sorted(args.output.glob("*.png")):
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
