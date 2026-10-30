"""Compare full versus proxy transport for identical rolling Canvas scatters."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright
from shiny import App, reactive, ui
from starlette.applications import Starlette
from starlette.routing import Mount

from shiny_charts import __version__, chart, output_chart, render_chart

ROOT = Path(__file__).parents[1]


def records(start, count):
    return [
        {
            "x": 100 + i * 37 % 1800,
            "y": (10 + i * 13 % 80) / 1000,
            "group": ["One", "Two", "Three"][i % 3],
            "id": f"row-{i:07d}",
        }
        for i in range(start, start + count)
    ]


def make_app(size, mode, batch_size):
    def server(input, output, session):
        data = reactive.Value(records(0, size))
        cursor = size

        @render_chart
        def points():
            if mode == "proxy":
                with reactive.isolate():
                    rows = data.get()
            else:
                rows = data.get()
            return (
                chart.scatter(rows, x="x", y="y", color="group", key="id")
                .renderer("canvas")
                .view("rolling")
                .select(brush=True)
            )

        @reactive.effect
        @reactive.event(input.update)
        async def update():
            nonlocal cursor
            batch = records(cursor, batch_size)
            cursor += batch_size
            current = [*data.get(), *batch][-size:]
            if mode == "proxy":
                await points.proxy().append(batch, max_rows=size)
            data.set(current)

    return App(
        ui.page_fluid(
            ui.input_action_button("update", "Append batch"),
            output_chart("points", height="420px"),
            lang="en",
        ),
        server,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[10000, 100000])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--batch", type=int, default=100)
    parser.add_argument("--out", default="bench/results-updates.json")
    args = parser.parse_args()
    app = Starlette(
        routes=[
            Mount(f"/{size}/{mode}", make_app(size, mode, args.batch))
            for size in args.sizes
            for mode in ("full", "proxy")
        ]
    )
    runner = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not runner.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Benchmark server did not start")
        time.sleep(0.02)
    results = []
    try:
        port = runner.servers[0].sockets[0].getsockname()[1]
        with sync_playwright() as p:
            browser = p.chromium.launch()
            version = browser.version
            try:
                for size in args.sizes:
                    for mode in ("full", "proxy"):
                        page = browser.new_page(viewport={"width": 1440, "height": 1000})
                        page.set_default_timeout(60000)
                        frames = []
                        errors = []
                        page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))

                        def received(payload, frames=frames):
                            frames.append(
                                len(payload.encode("utf8"))
                                if isinstance(payload, str)
                                else len(payload)
                            )

                        page.on(
                            "websocket",
                            lambda ws, received=received: ws.on("framereceived", received),
                        )
                        page.add_init_script("""window.renders=[];document.addEventListener('shiny-charts:rendered',e=>{
                          const s=shinyCharts.get(e.target.id);renders.push(+e.target.dataset.renderMs);
                          if(!s.measuring){s.measuring=true;s.engine.on('finished',()=>{
                            const datum=s.engine.getModel().getSeriesByIndex(0).getData().getRawDataItem(0);
                            window.completed={time:performance.now(),x:datum?.value[0],y:datum?.value[1]};
                          });}
                        });""")
                        page.goto(f"http://127.0.0.1:{port}/{size}/{mode}/")
                        page.wait_for_function(
                            "window.shinyCharts?.get('points')?.spec.rows.length>0 && !shinyCharts.get('points').engine._scheduler.unfinished"
                        )
                        samples = []
                        for round in range(args.rounds):
                            frames.clear()
                            before = page.evaluate(
                                "({time:performance.now(),count:renders.length,key:shinyCharts.get('points').spec.rows.at(-1)[3]})"
                            )
                            page.click("#update")
                            page.wait_for_function(
                                "before=>{const s=shinyCharts.get('points');return renders.length>before.count&&s.spec.rows.at(-1)[3]!==before.key&&completed?.time>before.time&&completed.x===s.spec.rows[0][0]&&completed.y===s.spec.rows[0][1]&&!s.engine._scheduler.unfinished}",
                                arg=before,
                            )
                            end = page.evaluate(
                                "new Promise(resolve=>requestAnimationFrame(()=>resolve(performance.now())))"
                            )
                            state = page.evaluate(
                                """()=>{const s=shinyCharts.get('points');let painted=0;s.engine.getModel().eachSeries(series=>series.getData().eachItemGraphicEl(()=>painted++));return{first:s.spec.rows[0][3],last:s.spec.rows.at(-1)[3],rows:s.spec.rows.length,painted};}"""
                            )
                            assert state["rows"] == size and state["painted"] == size, state
                            assert state["first"] == f"row-{(round + 1) * args.batch:07d}"
                            assert state["last"] == f"row-{size + (round + 1) * args.batch - 1:07d}"
                            samples.append(
                                {
                                    "update_ms": round_float(end - before["time"]),
                                    "sync_render_ms": page.evaluate("renders.at(-1)"),
                                    "websocket_bytes": sum(frames),
                                    "painted": state["painted"],
                                }
                            )
                        assert not errors, errors
                        result = {
                            "n": size,
                            "mode": mode,
                            "samples": samples,
                            "median": {
                                key: round_float(statistics.median(s[key] for s in samples))
                                for key in ("update_ms", "sync_render_ms", "websocket_bytes")
                            },
                        }
                        results.append(result)
                        print(result, flush=True)
                        page.close()
            finally:
                browser.close()
    finally:
        runner.should_exit = True
        thread.join(timeout=5)
    result = {
        "date": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "version": __version__,
        "chromium": version,
        "batch_size": args.batch,
        "rounds": args.rounds,
        "results": results,
    }
    (ROOT / args.out).write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Incremental transport comparison",
        "",
        "Both paths retain the same rolling window of keyed Canvas scatter points, append the same deterministic batch, use the same renderer and chart definition, and verify the exact first/last IDs and painted point count after every completed update. The full path rebuilds/sends the complete chart; the proxy path sends only new records and a row limit. The browser still redraws the retained dataset in both cases.",
        "",
        "| Retained rows | Update path | Received websocket bytes | Completed update | Render setup |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for r in results:
        m = r["median"]
        lines.append(
            f"| {r['n']:,} | {r['mode']} | {m['websocket_bytes']:,.0f} | {m['update_ms']:.1f} ms | {m['sync_render_ms']:.1f} ms |"
        )
    lines += [
        "",
        f"Measured {result['date']} with shiny-charts {__version__}, Python {result['python']}, Chromium {version}, {result['platform']}. {args.rounds} samples per path, batch size {args.batch}, 1440 × 1000, no CPU/network throttling. Each path starts in a new browser page; only updates are timed. Bytes are all received UTF-8 websocket payload bytes during an update, without compression or TCP headers. Timings include Shiny/Python/transport, Playwright click overhead, progressive drawing completion and the next animation frame. These are local workload measurements, not a Plotly/WebGL comparison or general throughput guarantee.",
        "",
        "Proxy messages are ordered by full-render generation and sequence. Stale or malformed messages are ignored and reported through the update input; a successful Python send is not a browser acknowledgement. No server sampling, binary transport, point-level engine update, or automatic reconnect replay is claimed.",
        "",
        "Reproduce with `uv run python bench/updates.py`. This report and raw samples are local artifacts excluded from commits.",
        "",
    ]
    (ROOT / "bench/report-updates.md").write_text("\n".join(lines))


def round_float(value):
    return round(value, 1)


if __name__ == "__main__":
    main()
