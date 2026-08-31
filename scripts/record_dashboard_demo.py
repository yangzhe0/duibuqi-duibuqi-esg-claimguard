#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs/ai_contest/submission/drafts/dashboard_demo.webm"


def pause(page: Page, seconds: float) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def nav(page: Page, label: str) -> None:
    page.locator("nav button", has_text=label).click()
    pause(page, 2.5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a read-only ESG ClaimGuard Dashboard walkthrough.")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(args.output.parent),
            record_video_size={"width": 1920, "height": 1080},
            locale="zh-CN",
            color_scheme="light",
        )
        page = context.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.locator(".metric-grid").wait_for()
        pause(page, 7)
        page.mouse.move(440, 400, steps=20)
        page.mouse.wheel(0, 570)
        pause(page, 6)
        page.mouse.wheel(0, -570)
        pause(page, 2)

        nav(page, "披露预审")
        page.locator(".preaudit-kpis").wait_for()
        pause(page, 7)
        page.mouse.wheel(0, 520)
        pause(page, 5)
        issue = page.locator(".issue-queue button").first
        if issue.count():
            issue.click()
            pause(page, 5)
        open_evidence = page.locator(".evidence-comparison button").first
        if open_evidence.count():
            open_evidence.click()
            page.locator(".workbench-page").wait_for(timeout=15000)
            pause(page, 15)
        else:
            nav(page, "证据复核")
            page.locator(".workbench-page").wait_for(timeout=15000)
            pause(page, 15)

        page.locator(".result-column").hover()
        page.mouse.wheel(0, 620)
        pause(page, 6)
        nav(page, "质量评测")
        pause(page, 9)
        page.mouse.wheel(0, 440)
        pause(page, 4)
        nav(page, "金标准")
        pause(page, 10)
        nav(page, "接入报告")
        pause(page, 8)
        nav(page, "系统总览")
        pause(page, 5)

        video = page.video
        context.close()
        if video is None:
            raise RuntimeError("Playwright did not create a video")
        video.save_as(args.output)
        browser.close()

    print(args.output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
