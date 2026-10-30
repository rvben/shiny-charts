"""Write a local report from completed, point-count-verified profile samples."""

import json
from pathlib import Path

root = Path(__file__).parents[1]
data = json.loads((root / "bench/results-profile-after.json").read_text())
lines = [
    "# Large scatter profile",
    "",
    "The alpha removes redundant Python dataset/snapshot copies, resizes only when dimensions change, "
    "and disables progressive SVG patches. Canvas retains progressive drawing and individual "
    "point identity. The native FinOps app explicitly chooses Canvas when the request-count setting is at least 10,000.",
    "",
    "## Python preparation",
    "",
    "| Records | Builder | Wire packing | JSON | Chart spec bytes |",
    "| ---: | ---: | ---: | ---: | ---: |",
]
for n, item in data["preparation"].items():
    m = item["median"]
    lines.append(
        f"| {int(n):,} | {m['build_ms']} ms | {m['pack_ms']} ms | {m['json_ms']} ms | {m['wire_bytes']:,} |"
    )
before_path = root / "bench/results-profile-baseline-python.json"
if before_path.exists():
    before = json.loads(before_path.read_text())
    lines += [
        "",
        "Preparation measured against the original 0.1.0a1 installed wheel:",
        "",
        "| Records | Original build + pack | Alpha build + pack |",
        "| ---: | ---: | ---: |",
    ]
    for n, item in data["preparation"].items():
        m, old = item["median"], before["preparation"][n]["median"]
        lines.append(
            f"| {int(n):,} | {old['build_ms'] + old['pack_ms']:.1f} ms | {m['build_ms'] + m['pack_ms']:.1f} ms |"
        )
lines += [
    "",
    "## Completed browser updates",
    "",
    "| Records | Renderer | End-to-end update | Synchronous render setup | Painted points | DOM nodes | JS heap after GC |",
    "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
]
for m in data["browser"]:
    assert m["painted_points"] == m["n"]
    lines.append(
        f"| {m['n']:,} | {m['renderer']} | {m['update_ms']} ms | {m['sync_render_ms']} ms | {m['painted_points']:,} | {m['dom_nodes']:,} | {m['heap_bytes'] / 1e6:.1f} MB |"
    )
lines += [
    "",
    "## Method and limits",
    "",
    f"Measured {data['date']} on {data['platform']}, Python {data['python']}. "
    f"{data.get('rounds', 3)} samples per case, headless Chromium {data.get('chromium', 'not recorded')} at 1440 × 1000, no network/CPU throttling. "
    "One keyed scatter chart isolates the large-data path; this is separate from the "
    "four-card cold-start comparison. Records have fixed deterministic latency/cost/groups/IDs/success metadata.",
    "",
    "End-to-end update includes data generation, chart preparation, Shiny transport, "
    "Playwright click overhead, ECharts' finished event and the next animation frame. "
    "Synchronous render setup excludes later progressive Canvas paint. Every final sample "
    "checks the number of actual point graphic elements against the dataset. Heap is "
    "Chromium Runtime.getHeapUsage after HeapProfiler.collectGarbage, excludes native "
    "graphics memory and is not total browser memory. DOM counts cover the chart only.",
    "",
    "The initial 100k SVG prototype profile had only 12,000 SVG elements; its timings "
    "are not a valid completed-render comparison. Corrected SVG samples contain all "
    "100,000 points. Large-data results are not a Plotly benchmark or a claim that the "
    "alpha is faster than Plotly/WebGL. Full 100k chart specs still contain about 3.25 MB "
    "of uncompressed chart JSON. Python, transport, DOM and per-point graphics memory "
    "remain costs; Canvas is not server-side aggregation or resampling.",
    "",
    "Reproduce with `uv run python bench/profile_large.py --out bench/results-profile-after.json` "
    "and `uv run python bench/write_profile_report.py`. Raw result/report files are local "
    "working material excluded from commits.",
    "",
]
(root / "bench/report-profile.md").write_text("\n".join(lines))
print(root / "bench/report-profile.md")
