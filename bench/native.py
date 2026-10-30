"""Fresh-process CPU/RSS comparison; input construction excluded from timing."""

import gc
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable


def rss():
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())])) / 1024


def worker(backend, n, kind):
    import polars as pl

    from shiny_charts._wire import pack

    if backend == "rust":
        from shiny_charts.native import chart
    else:
        from shiny_charts import chart
    df = pl.DataFrame(
        {
            "x": pl.int_range(0, n, eager=True),
            "y": pl.int_range(0, n, eager=True).cast(pl.Float64) / 7,
        }
    )
    df = df.with_columns((pl.col("x") % 8).cast(pl.String).alias("group"))
    if kind == "line":
        df = df.with_columns(*[(pl.col("y") + i).alias(f"unused_{i}") for i in range(8)])
    baseline = rss()
    timings = []
    retained = None
    for round in range(4):
        gc.collect()
        start = time.process_time()
        c = (
            getattr(chart, kind)(df, x="x", y="y", color="group")
            .labels(title="Benchmark")
            .view("one", zoom=False)
        )
        built = time.process_time()
        if backend == "rust":
            inner = c.native_json()
            message = {
                "values": {
                    "chart": {
                        "spec_json": inner,
                        "height": None,
                        "stream": {"token": "benchmark", "sequence": 0},
                    }
                }
            }
        else:
            inner = pack(c)
            message = {
                "values": {
                    "chart": {
                        "spec": inner,
                        "height": None,
                        "stream": {"token": "benchmark", "sequence": 0},
                    }
                }
            }
        wired = time.process_time()
        encoded = json.dumps(message)
        final = time.process_time()
        if round:
            timings.append(
                [
                    (built - start) * 1000,
                    (wired - built) * 1000,
                    (final - wired) * 1000,
                    (final - start) * 1000,
                ]
            )
        retained = rss()
        size = len(encoded.encode())
        del c, inner, message, encoded
    return dict(
        backend=backend,
        rows=n,
        kind=kind,
        build_ms=statistics.median(t[0] for t in timings),
        wire_ms=statistics.median(t[1] for t in timings),
        envelope_ms=statistics.median(t[2] for t in timings),
        total_cpu_ms=statistics.median(t[3] for t in timings),
        baseline_rss_mib=baseline,
        retained_rss_mib=retained,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        / (1024**2 if sys.platform == "darwin" else 1024),
        bytes=size,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(worker(sys.argv[1], int(sys.argv[2]), sys.argv[3])))
    else:
        results = []
        for kind in ("scatter", "line"):
            for n in (100_000, 500_000):
                for backend in ("python", "rust"):
                    env = {**os.environ, "PYTHONPATH": str(HERE)}
                    result = json.loads(
                        subprocess.check_output([PYTHON, __file__, backend, str(n), kind], env=env)
                    )
                    results.append(result)
                    print(json.dumps(result), flush=True)
        (HERE / "results-native.json").write_text(json.dumps(results, indent=2) + "\n")
