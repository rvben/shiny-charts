"""Reproducible comparison of the same dashboard with fresh/warm browser caches.

Run the dashboard on localhost, then: uv run python bench/run.py --rounds 5
Results measure this dashboard and machine, not general library superiority.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.metadata
import json
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path

import plotly
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parents[1]
IDS = ["trend", "workloads", "latency", "distribution"]

INSTRUMENT = """(() => {
  const ids = ['trend','workloads','latency','distribution'];
  window.__bench = { counts:{}, durations:[], firstReady:null };
  function record(id, duration) {
    if (!ids.includes(id)) return;
    __bench.counts[id] = (__bench.counts[id] || 0) + 1;
    if (duration != null) __bench.durations.push({id,duration});
    if (__bench.firstReady == null && ids.every(id => __bench.counts[id])) {
      requestAnimationFrame(() => { if (__bench.firstReady == null) __bench.firstReady=performance.now(); });
    }
  }
  document.addEventListener('shiny-charts:rendered', e => record(e.target.id, +e.target.dataset.renderMs));
  let plotly;
  Object.defineProperty(window, 'Plotly', {
    configurable:true, get:()=>plotly, set:value => {
      plotly=value;
      for (const method of ['newPlot','react']) {
        const original=value[method];
        value[method]=function(el,...args) {
          const start=performance.now();
          const result=original.call(value,el,...args);
          return Promise.resolve(result).then(result => {
            const node=typeof el==='string'?document.getElementById(el):el;
            const output=node?.closest('.shiny-plotly-output');
            if(output) record(output.id,performance.now()-start);
            return result;
          });
        };
      }
    }
  });
})();"""


def one_visit(browser, base: str, engine: str, updates: int = 8) -> dict:
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.add_init_script(INSTRUMENT)
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    transfer = []
    frames = []
    requests = {}
    cached = set()
    cdp.on(
        "Network.requestWillBeSent",
        lambda event: requests.update({event["requestId"]: event["request"]["url"]}),
    )
    cdp.on("Network.requestServedFromCache", lambda event: cached.add(event["requestId"]))
    cdp.on(
        "Network.loadingFinished",
        lambda event: transfer.append(
            {
                "url": requests.get(event["requestId"], ""),
                "bytes": event["encodedDataLength"],
                "cached": event["requestId"] in cached,
            }
        ),
    )
    cdp.on(
        "Network.webSocketFrameReceived",
        lambda event: frames.append(len(event["response"]["payloadData"].encode())),
    )
    samples = []
    try:
        for visit in ("cold", "warm"):
            transfer.clear()
            frames.clear()
            cached.clear()
            page.goto(f"{base}/{engine}/")
            page.wait_for_function("__bench.firstReady != null", polling="raf")
            page.wait_for_function("document.fonts.status === 'loaded'")
            first_ready = page.evaluate("__bench.firstReady")
            http = sum(item["bytes"] for item in transfer)
            websocket = sum(frames)
            asset = [
                item
                for item in transfer
                if ("shiny-charts.js" in item["url"] or "plotly.min.js" in item["url"])
            ]
            update_samples = []
            for _i in range(updates):
                frames.clear()
                before = page.evaluate("({...__bench.counts})")
                start = page.evaluate("performance.now()")
                page.locator("#refresh").click()
                page.wait_for_function(
                    "before => Object.keys(before).every(id => __bench.counts[id]>before[id])",
                    arg=before,
                    polling="raf",
                )
                end = page.evaluate(
                    "new Promise(resolve => requestAnimationFrame(() => resolve(performance.now())))"
                )
                update_samples.append({"ms": end - start, "websocket_bytes": sum(frames)})
            samples.append(
                {
                    "visit": visit,
                    "first_dashboard_ms": first_ready,
                    "http_bytes": http,
                    "websocket_bytes": websocket,
                    "engine_assets": asset,
                    "updates": update_samples,
                }
            )
    finally:
        context.close()
    return {"engine": engine, "visits": samples}


def summarize(runs: list[dict]) -> dict:
    summary = {}
    for engine in ("charts", "plotly"):
        selected = [run for run in runs if run["engine"] == engine]
        result = {}
        for visit in ("cold", "warm"):
            samples = [v for run in selected for v in run["visits"] if v["visit"] == visit]
            updates = [u for v in samples for u in v["updates"]]
            result[visit] = {
                "first_dashboard_ms_median": round(
                    statistics.median(s["first_dashboard_ms"] for s in samples), 1
                ),
                "http_bytes_median": statistics.median(s["http_bytes"] for s in samples),
                "websocket_bytes_median": statistics.median(s["websocket_bytes"] for s in samples),
                "update_ms_median": round(statistics.median(s["ms"] for s in updates), 1),
                "update_websocket_bytes_median": statistics.median(
                    s["websocket_bytes"] for s in updates
                ),
                "samples": len(samples),
            }
        summary[engine] = result
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8055")
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    runs = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            # Activate shiny-plotly's compressed asset route before cold-cache measurements.
            one_visit(browser, args.url, "plotly", updates=1)
            for i in range(args.rounds):
                order = ("charts", "plotly") if i % 2 == 0 else ("plotly", "charts")
                for engine in order:
                    print(f"Round {i + 1}/{args.rounds}: {engine}", flush=True)
                    runs.append(one_visit(browser, args.url, engine))
            browser_version = browser.version
        finally:
            browser.close()
    charts_js = (ROOT / "src/shiny_charts/www/shiny-charts.js").read_bytes()
    plotly_js = (Path(plotly.__file__).parent / "package_data/plotly.min.js").read_bytes()
    result = {
        "date": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "chromium": browser_version,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("shiny", "shiny-charts", "shiny-plotly", "plotly")
        },
        "method": "Same 2,400-request SVG dashboard, 4 charts, matched data/colors, styled Plotly, fresh context per engine/round then same-context warm revisit, alternating order. No network/CPU throttling. HTTP encodedDataLength includes headers; websocket is received UTF-8 payload bytes. Update timing includes Playwright click and the next animation frame.",
        "bundle_bytes": {
            "charts": {"raw": len(charts_js), "gzip": len(gzip.compress(charts_js))},
            "plotly": {"raw": len(plotly_js), "gzip": len(gzip.compress(plotly_js))},
        },
        "summary": summarize(runs),
        "runs": runs,
    }
    path = ROOT / "bench/results.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    print(f"Raw measurements: {path}")


if __name__ == "__main__":
    main()
