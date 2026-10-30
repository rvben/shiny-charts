"""Completed warm updates in real adoption apps, with no competing benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright
from starlette.applications import Starlette
from starlette.routing import Mount

from shiny_charts import __version__

ROOT = Path(__file__).parents[1]


def run(rounds):
    sys.path.insert(0, str(ROOT))
    from examples.operations_app import app as operations
    from examples.portfolio_app import app as portfolio

    host = Starlette(routes=[Mount("/portfolio", portfolio), Mount("/operations", operations)])
    runner = uvicorn.Server(uvicorn.Config(host, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not runner.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Dashboard server did not start")
        time.sleep(0.02)
    results = []
    try:
        url = f"http://127.0.0.1:{runner.servers[0].sockets[0].getsockname()[1]}"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            version = browser.version
            try:
                for width, height in [(1440, 1000), (390, 844)]:
                    for app, size, ids in [
                        ("portfolio", 8, ["trend"]),
                        *[
                            ("operations", n, ["response", "queues", "throughput", "observations"])
                            for n in (500, 2400, 10000)
                        ],
                    ]:
                        page = browser.new_page(viewport={"width": width, "height": height})
                        page.set_default_timeout(60000)
                        frames = []
                        errors = []
                        page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                        page.on(
                            "websocket",
                            lambda ws, frames=frames: ws.on(
                                "framereceived",
                                lambda frame, frames=frames: frames.append(
                                    len(frame.encode("utf8"))
                                    if isinstance(frame, str)
                                    else len(frame)
                                ),
                            ),
                        )
                        page.add_init_script("""window.chartFinished={};document.addEventListener('shiny-charts:rendered',e=>{
                          const s=shinyCharts.get(e.target.id);
                          if(!s.measuring){s.measuring=true;s.engine.on('finished',()=>{chartFinished[e.target.id]=performance.now()})}
                        });""")
                        page.goto(f"{url}/{app}/")
                        page.wait_for_function(
                            "ids=>ids.every(id=>shinyCharts?.get(id)?.spec.rows.length>0)", arg=ids
                        )
                        if app == "operations":
                            page.select_option("#quality", "complete")
                            page.select_option("#n", str(size))
                            page.wait_for_function(
                                "n=>shinyCharts.get('observations').spec.rows.length===n", arg=size
                            )
                        page.wait_for_function(
                            "ids=>ids.every(id=>!shinyCharts.get(id).engine._scheduler.unfinished)",
                            arg=ids,
                        )
                        samples = []
                        for i in range(rounds):
                            if i:
                                page.wait_for_timeout(1000)
                            frames.clear()
                            before = page.evaluate(
                                "ids=>({time:performance.now(),counts:Object.fromEntries(ids.map(id=>[id,+document.getElementById(id).dataset.renderCount]))})",
                                ids,
                            )
                            if app == "portfolio":
                                region = "Americas" if i % 2 == 0 else "Europe"
                                page.select_option("#region", region)
                                page.wait_for_function(
                                    "region=>shinyCharts.get('trend').spec.rows[0][2]===region+' · All products'",
                                    arg=region,
                                )
                            else:
                                # DOM click keeps all four cards in their original viewport positions.
                                page.locator("#append").evaluate("button=>button.click()")
                                page.wait_for_function(
                                    "sequence=>['response','queues','throughput','observations'].every(id=>shinyCharts.get(id).stream.sequence===sequence)",
                                    arg=i + 1,
                                )
                            page.wait_for_function(
                                "args=>args.ids.every(id=>+document.getElementById(id).dataset.renderCount>args.before.counts[id]&&chartFinished[id]>args.before.time&&!shinyCharts.get(id).engine._scheduler.unfinished)",
                                arg={"ids": ids, "before": before},
                            )
                            end = page.evaluate(
                                "new Promise(resolve=>requestAnimationFrame(()=>resolve(performance.now())))"
                            )
                            rows = page.evaluate(
                                "ids=>Object.fromEntries(ids.map(id=>[id,shinyCharts.get(id).spec.rows.length]))",
                                ids,
                            )
                            if app == "operations":
                                painted = page.evaluate(
                                    "()=>{let count=0;shinyCharts.get('observations').engine.getModel().eachSeries(s=>s.getData().eachItemGraphicEl(()=>count++));return count}"
                                )
                                assert painted == size, (painted, size)
                                assert (
                                    page.evaluate("shinyCharts.get('observations').spec.rows[0][3]")
                                    == f"obs-{(i + 1) * 100:07d}"
                                )
                            else:
                                painted = 8
                                assert rows == {"trend": 8}
                            samples.append(
                                {
                                    "completed_ms": round(end - before["time"], 2),
                                    "received_websocket_bytes": sum(frames),
                                    "rows": rows,
                                    "painted_observations": painted,
                                }
                            )
                        assert not errors, errors
                        timings = sorted(sample["completed_ms"] for sample in samples)
                        result = {
                            "app": app,
                            "viewport": [width, height],
                            "n": size,
                            "samples": samples,
                            "median_ms": round(statistics.median(timings), 2),
                            "max_ms": max(timings),
                            "median_received_bytes": statistics.median(
                                sample["received_websocket_bytes"] for sample in samples
                            ),
                        }
                        results.append(result)
                        print(
                            json.dumps({k: v for k, v in result.items() if k != "samples"}),
                            flush=True,
                        )
                        page.close()
            finally:
                browser.close()
    finally:
        runner.should_exit = True
        thread.join(timeout=5)
    payload = {
        "version": __version__,
        "utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "browser": version,
        "rounds": rounds,
        "results": results,
    }
    (ROOT / "bench/results-dashboard.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# Local dashboard update measurement",
        f"\nshiny-charts {__version__} · Chromium {version} · {platform.platform()}",
        f"\n{rounds} warm updates per case, about one second idle between completed updates. Synthetic app data.",
        "\n| App | Width | Rows | Median completed ms | Slowest ms | Median received WS bytes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['app']} | {result['viewport'][0]} | {result['n']} | {result['median_ms']} | {result['max_ms']} | {result['median_received_bytes']} |"
        )
    lines.append(
        "\nPortfolio changes Region and waits for its chart and the next animation frame. Operations appends 100 records and waits for all four charts, engine finished signals and the next animation frame. Complete scatter measurements verify every point painted and the rolling first key. SVG below 10,000 rows, Canvas at 10,000. Each app runs in a fresh page, one benchmark at a time. Desktop/mobile refers to viewport size on this machine, not different device hardware. Received WebSocket bytes include all app messages; Portfolio bookmark autosync may occur after chart completion, so this is not total bookmark-cycle traffic. Timing includes Python, transport, browser rendering and Playwright polling. No Plotly comparison, cold-start claim, percentile estimate, sustained-throughput guarantee or production-data validation. Appends still redraw retained points. Reproduce: `make profile-dashboard`. Reports and samples are local working material."
    )
    (ROOT / "bench/report-dashboard.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    run(args.rounds)
