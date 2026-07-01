from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
URL = "http://localhost:8507"


SHOTS = [
    ("fig_system_ui_overview", "系统总览"),
    ("fig_system_ui_company", "公司视角"),
    ("fig_system_ui_indicator", "指标视角"),
    ("fig_system_ui_evidence", "证据核验"),
    ("fig_system_ui_risk", "高风险样本"),
]


def write_svg_wrapper(name: str, title: str, width: int = 1440, height: int = 1200) -> None:
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <image href="{name}.png" x="0" y="0" width="{width}" height="{height}" preserveAspectRatio="xMidYMin meet"/>
  <text x="36" y="{height-30}" font-family="Noto Sans CJK SC, sans-serif" font-size="22" fill="#4A5568">{title}真实 Streamlit 页面截图</text>
</svg>
'''
    (FIG / f"{name}.svg").write_text(svg, encoding="utf-8")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, device_scale_factor=1)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        for name, tab in SHOTS:
            if tab != "系统总览":
                page.get_by_role("tab", name=tab).click()
                page.wait_for_timeout(2500)
            page.screenshot(path=str(FIG / f"{name}.png"), full_page=False)
            write_svg_wrapper(name, tab)
            print(f"captured {name}")
        browser.close()


if __name__ == "__main__":
    main()
