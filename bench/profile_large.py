"""Measure chart preparation and actual SVG/Canvas paint at 10k/100k records.

Uses one scatter output to isolate the large-data path; this is not the four-card
dashboard cold-start benchmark. Each sample waits for ECharts' finished event.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import platform
import pstats
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright
from shiny import App, render, ui

from shiny_charts import chart, output_chart, render_chart
from shiny_charts._wire import pack

ROOT = Path(__file__).parents[1]


def records(n, update=0):
    return [
        {
            "latency": 100 + (i * 37 % 1800),
            "cost": (10 + i * 13 % 80 + update) / 1000,
            "workload": ["Customer experience", "Knowledge platform", "Engineering copilot"][i % 3],
            "id": f"req-{i:06d}",
            "success": i % 11 != 0,
        }
        for i in range(n)
    ]


def make_chart(rows, renderer="svg"):
    return (
        chart.scatter(rows, x="latency", y="cost", color="workload", key="id", tooltip=["success"])
        .format(y="currency:USD:3")
        .select(brush=True)
        .renderer(renderer)
    )


def preparation(n, rounds):
    rows = records(n)
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        value = make_chart(rows)
        built = time.perf_counter()
        spec = pack(value)
        packed = time.perf_counter()
        wire = json.dumps(spec, separators=(",", ":"), allow_nan=False).encode()
        end = time.perf_counter()
        samples.append(
            {
                "build_ms": (built - start) * 1000,
                "pack_ms": (packed - built) * 1000,
                "json_ms": (end - packed) * 1000,
                "wire_bytes": len(wire),
            }
        )
    profiler = cProfile.Profile()
    profiler.runcall(lambda: pack(make_chart(rows)))
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(12)
    return {
        "samples": samples,
        "median": {k: round(statistics.median(s[k] for s in samples), 2) for k in samples[0]},
        "cprofile": stream.getvalue(),
    }


def browser_samples(sizes, rounds):
    def server(input, output, session):
        @render_chart
        def points():
            return make_chart(records(int(input.n()), input.refresh()), input.renderer())

        @render.text
        def status():
            return f"{input.n()}:{input.renderer()}:{input.refresh()}"

    app = App(
        ui.page_fluid(
            ui.input_select("n", "Records", {str(n): f"{n:,}" for n in sizes}),
            ui.input_select("renderer", "Renderer", ["svg", "canvas"]),
            ui.input_action_button("refresh", "Update"),
            ui.output_text("status"),
            output_chart("points", height="420px"),
            lang="en",
        ),
        server,
    )
    runner = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not runner.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Profile server did not start")
        time.sleep(0.02)
    result = []
    try:
        port = runner.servers[0].sockets[0].getsockname()[1]
        with sync_playwright() as p:
            browser = p.chromium.launch()
            chromium = browser.version
            try:
                for size in sizes:
                    for renderer in ("svg", "canvas"):
                        page = browser.new_page(viewport={"width": 1440, "height": 1000})
                        page.set_default_timeout(60000)
                        errors = []
                        page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                        page.add_init_script("""window.samples=[]; document.addEventListener('shiny-charts:rendered', e => {
                          const s=shinyCharts.get(e.target.id); if(!s) return;
                          samples.push({sync:+e.target.dataset.renderMs, rows:s.spec.rows.length});
                          if (!s.profileAttached) {
                            s.profileAttached=true;
                            s.engine.on('finished',()=>{window.lastFinished={time:performance.now(),y:s.engine.getModel().getSeriesByIndex(0).getData().getRawDataItem(0)?.value[1]};});
                          }
                        });""")
                        page.goto(f"http://127.0.0.1:{port}")
                        page.wait_for_function("window.shinyCharts?.get('points')")
                        page.select_option("#renderer", renderer)
                        page.select_option("#n", str(size))
                        page.wait_for_function(
                            "args=>{const s=shinyCharts.get('points');return s.spec.rows.length===args[0]&&s.spec.renderer===args[1]&&!s.engine._scheduler.unfinished}",
                            arg=[size, renderer],
                        )
                        samples = []
                        for _ in range(rounds):
                            before = page.evaluate(
                                "({count:samples.length,time:performance.now(),y:shinyCharts.get('points').spec.rows[0][1]})"
                            )
                            page.locator("#refresh").click()
                            page.wait_for_function(
                                "before=>{const s=shinyCharts.get('points');return samples.length>before.count&&s.spec.rows[0][1]>before.y&&window.lastFinished?.time>before.time&&lastFinished.y===s.spec.rows[0][1]&&!s.engine._scheduler.unfinished}",
                                arg=before,
                            )
                            end = page.evaluate(
                                "new Promise(r=>requestAnimationFrame(()=>r(performance.now())))"
                            )
                            samples.append(
                                {
                                    "update_ms": end - before["time"],
                                    "sync_render_ms": page.evaluate("samples.at(-1).sync"),
                                }
                            )
                        dom = page.locator("#points *").count()
                        points = page.evaluate("""() => {let count=0;const s=shinyCharts.get('points');
                          s.engine.getModel().eachSeries(series=>series.getData().eachItemGraphicEl(()=>count++));return count;}""")
                        assert points == size, f"Only {points}/{size} points painted"
                        cdp = page.context.new_cdp_session(page)
                        cdp.send("HeapProfiler.collectGarbage")
                        heap = cdp.send("Runtime.getHeapUsage")["usedSize"]
                        assert not errors, errors
                        result.append(
                            {
                                "n": size,
                                "renderer": renderer,
                                "samples": samples,
                                "update_ms": round(
                                    statistics.median(s["update_ms"] for s in samples), 1
                                ),
                                "sync_render_ms": round(
                                    statistics.median(s["sync_render_ms"] for s in samples), 1
                                ),
                                "dom_nodes": dom,
                                "painted_points": points,
                                "heap_bytes": heap,
                            }
                        )
                        print(result[-1], flush=True)
                        page.close()
            finally:
                browser.close()
    finally:
        runner.should_exit = True
        thread.join(timeout=5)
    return result, chromium


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[10000, 100000])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--out", default="bench/results-profile-after.json")
    parser.add_argument("--python-only", action="store_true")
    args = parser.parse_args()
    result = {
        "date": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "rounds": args.rounds,
        "chart_module": chart.__file__,
        "preparation": {str(n): preparation(n, args.rounds) for n in args.sizes},
    }
    for n, item in result["preparation"].items():
        print(n, item["median"], flush=True)
    if not args.python_only:
        result["browser"], result["chromium"] = browser_samples(args.sizes, args.rounds)
    (ROOT / args.out).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
