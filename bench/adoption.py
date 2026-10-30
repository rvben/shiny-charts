"""Reproducible import-RSS and warm spec CPU measurements; no dashboard claims.

Run with uv run python bench/adoption.py --out /tmp/shiny-charts-adoption.json.
RSS is current resident memory from ps, not peak RSS or Python allocation size.
Each import sample uses a fresh interpreter with the same installed packages.
Synthetic chart inputs and group partitioning are prepared outside timed sections.
"""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path


def footprint(mode):
    script = r"""
import gc,json,os,subprocess,sys,time
start=time.perf_counter()
mode=sys.argv[1]
if mode!='python':
 import shiny
if mode=='shiny_charts':
 import shiny_charts
if mode in ('plotly_go','plotly_figure'):
 import plotly.graph_objects as go
if mode=='plotly_figure':
 figure=go.Figure(go.Bar(x=['a','b'],y=[1,2]))
gc.collect()
rss=int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True).strip())
print(json.dumps({'rss_mib':rss/1024,'elapsed_ms':(time.perf_counter()-start)*1000,
 'optional_imports':[name for name in ['plotly','pandas','numpy','polars'] if name in sys.modules]}))
"""
    return json.loads(subprocess.check_output([sys.executable, "-c", script, mode], text=True))


def preparation(kind, n, groups, rounds):
    import plotly.graph_objects as go

    from shiny_charts import chart
    from shiny_charts._wire import pack

    rows = [
        {"x": i // groups if kind == "bar" else i, "y": 1 + i % 97, "group": f"Group {i % groups}"}
        for i in range(n)
    ]
    columns = [
        (
            f"Group {g}",
            [row["x"] for row in rows if row["group"] == f"Group {g}"],
            [row["y"] for row in rows if row["group"] == f"Group {g}"],
        )
        for g in range(groups)
    ]

    def native():
        builder = chart.bar if kind == "bar" else chart.scatter
        options = {"stacked": True} if kind == "bar" else {}
        return builder(rows, x="x", y="y", color="group", **options)

    def plotly():
        cls = go.Bar if kind == "bar" else go.Scatter
        options = {} if kind == "bar" else {"mode": "markers"}
        return go.Figure(
            data=[cls(x=x, y=y, name=name, **options) for name, x, y in columns],
            layout={"barmode": "stack"} if kind == "bar" else {},
        )

    def wire_native(value):
        return json.dumps(pack(value), separators=(",", ":"), allow_nan=False).encode()

    samples = {"shiny_charts": [], "plotly": []}
    for _name, build, wire in [
        ("shiny_charts", native, wire_native),
        ("plotly", plotly, lambda v: v.to_json().encode()),
    ]:
        wire(build())  # Exclude imports and first-figure initialization from warm CPU.
    for i in range(rounds):
        methods = [
            ("shiny_charts", native, wire_native),
            ("plotly", plotly, lambda v: v.to_json().encode()),
        ]
        if i % 2:
            methods.reverse()
        for name, build, wire in methods:
            gc.collect()
            start = time.process_time()
            value = build()
            built = time.process_time()
            payload = wire(value)
            end = time.process_time()
            samples[name].append(
                {
                    "build_cpu_ms": (built - start) * 1000,
                    "wire_cpu_ms": (end - built) * 1000,
                    "wire_bytes": len(payload),
                }
            )
    return {
        "kind": kind,
        "rows": n,
        "groups": groups,
        "input": "pre-built records for shiny-charts; pre-partitioned x/y lists for Plotly",
        "samples": samples,
        "median": {
            name: {key: round(statistics.median(s[key] for s in values), 2) for key in values[0]}
            for name, values in samples.items()
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("/tmp/shiny-charts-adoption.json"))
    args = parser.parse_args()
    result = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "versions": {
            name: importlib.metadata.version(name) for name in ["shiny", "shiny-charts", "plotly"]
        },
        "rounds": args.rounds,
        "imports": {},
    }
    for mode in ["python", "shiny", "shiny_charts", "plotly_go", "plotly_figure"]:
        values = [footprint(mode) for _ in range(args.rounds)]
        result["imports"][mode] = {
            "samples": values,
            "median_rss_mib": round(statistics.median(s["rss_mib"] for s in values), 2),
        }
        print(mode, result["imports"][mode]["median_rss_mib"], flush=True)
    result["preparation"] = [
        preparation(kind, n, groups, args.rounds)
        for kind, n, groups in [
            ("bar", 800, 8),
            ("bar", 6400, 64),
            ("scatter", 10000, 1),
            ("scatter", 100000, 1),
        ]
    ]
    for item in result["preparation"]:
        print(item["kind"], item["rows"], item["groups"], item["median"], flush=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
