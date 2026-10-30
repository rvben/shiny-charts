"""Capture the supported dashboard viewports in one bounded visual-QA pass."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8055")
parser.add_argument("--out", default=".impeccable/review")
parser.add_argument("--native", action="store_true", help="Capture the standalone native app")
parser.add_argument("--operations", action="store_true", help="Capture service operations")
args = parser.parse_args()
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        views = (
            (("native", 1440), ("native", 390))
            if args.native
            else (("operations", 1440), ("operations", 390))
            if args.operations
            else (("charts", 1440), ("charts", 390), ("plotly", 1440))
        )
        for engine, width in views:
            page = browser.new_page(
                viewport={"width": width, "height": 1000 if width > 400 else 844}
            )
            page.goto(
                args.url + "/" if engine in ("native", "operations") else f"{args.url}/{engine}/"
            )
            chart_id = "observations" if engine == "operations" else "latency"
            if engine != "plotly":
                page.wait_for_function(
                    "id => window.shinyCharts?.get(id)?.spec.rows.length === 2400", arg=chart_id
                )
            else:
                page.wait_for_function(
                    "document.querySelector('#latency .js-plotly-plot')?._fullLayout"
                )
            page.wait_for_function("document.fonts.status === 'loaded'")
            for mode in ("light", "dark"):
                page.evaluate(
                    "mode => document.documentElement.setAttribute('data-bs-theme', mode)", mode
                )
                if engine != "plotly":
                    color = "#243044" if mode == "light" else "#e7edf5"
                    page.wait_for_function(
                        "([id, color]) => document.getElementById(id).dataset.themeColor === color",
                        arg=[chart_id, color],
                    )
                else:
                    page.wait_for_function(
                        "mode => document.querySelector('#latency .js-plotly-plot')._fullLayout.font.color === (mode === 'dark' ? '#e7edf5' : '#243044')",
                        arg=mode,
                    )
                page.evaluate(
                    "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
                )
                page.screenshot(
                    path=str(out / f"{engine}-{width}-{mode}.png"),
                    full_page=True,
                    animations="disabled",
                )
            page.close()
    finally:
        browser.close()
print(out.resolve())
