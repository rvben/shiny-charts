# Server capacity and migration coverage

These are local synthetic measurements, not a prediction of dashboard capacity.
The browser engine does layout and rendering; the Python builder validates scalar
columns and creates a semantic spec. This avoids constructing a rendering-engine
figure on the server, but conversion, validation, wire packing, and JSON encoding
still cost CPU and allocate memory. Server aggregation often dominates them.

## Import footprint

`shiny-charts` depends at runtime on Shiny and htmltools. Importing it does not import
Plotly, pandas, NumPy, or polars; DataFrames are accepted through their conversion
methods without importing their libraries. Shiny itself has a process footprint,
so compare additional chart-library memory after the same Shiny baseline.

Measured with Python 3.13.5, Shiny 1.8.0, local shiny-charts 0.4.0b4 and Plotly 7.1.0
on macOS arm64. Seven fresh interpreter processes per case; medians of current RSS
from `ps` after garbage collection. Both libraries were installed in the same
environment, but only the requested library was imported in each process.

| Process contents | RSS (MiB) | Additional RSS over Shiny |
| --- | ---: | ---: |
| Python benchmark harness | 20.39 | — |
| Shiny | 61.25 | — |
| Shiny + `import shiny_charts` | 61.72 | 0.47 |
| Shiny + `import plotly.graph_objects` | 61.56 | 0.31 |
| Shiny + Plotly + first two-point bar figure | 81.11 | 19.86 |

Plotly's lazy import is small in this case too. Its first figure loads more code,
so an import-only comparison misses that initialization. These numbers do not
establish a universal tens-of-MB advantage: RSS depends on OS, Python, allocator,
Plotly version and what the app already imports. Measure separate real app
processes after imports and after the first rendered chart on the deployment host.
RSS is not private memory/PSS, peak render memory, or per-session memory.

## Warm spec construction CPU (local macOS results)

Seven rounds after a warm-up, alternating library order, using `process_time()`.
Synthetic data generation, aggregation and group partitioning are outside the timer.
Shiny-charts gets prepared records; Plotly gets prepared per-series x/y lists.
Both produce a basic stacked bar or grouped scatter figure with the same values.
This compares the native builders, not Plotly Express, UI integration, browser
paint, sessions, aggregation or a complete dashboard. It includes validation in
both native builders. Plotly's first-figure initialization is excluded here.

| Chart / rows / groups | shiny-charts build CPU (ms) | Plotly build CPU (ms) | shiny-charts wire CPU (ms) | Plotly wire CPU (ms) |
| --- | ---: | ---: | ---: | ---: |
| Stacked bars / 800 / 8 | 0.55 | 1.78 | 0.37 | 0.90 |
| Stacked bars / 6,400 / 64 | 4.16 | 11.33 | 2.76 | 3.93 |
| Scatter / 10,000 / 1 | 8.19 | 13.66 | 4.30 | 5.34 |
| Scatter / 100,000 / 1 | 86.73 | 131.55 | 64.81 | 48.98 |

Wire CPU includes packing plus UTF-8 JSON encoding for shiny-charts and `to_json()`
plus UTF-8 encoding for Plotly. Wire output differs structurally. The native builder
was faster in these local macOS cases; the reported Linux results below do not
reproduce that advantage for larger/many-series charts. No general 2–3× speedup
is claimed. Also, packing/encoding was slower at 100,000 scatter rows.
Payloads were not uniformly smaller either: 100,000-row scatter was 1,279,994 bytes
versus 886,208 for Plotly. Send aggregated bars/lines where the product permits;
do not treat these results as a reason to ship raw dashboard datasets.

Reproduce from the repository with:

```sh
uv run python bench/adoption.py --rounds 7 --out /tmp/shiny-charts-adoption.json
```

The JSON records individual samples, medians, imported optional modules and package
versions. Rerun on Linux with the application's installed packages before using
these figures to size replicas. Pre-filtered input is not copied from any client app.

## Reported Linux pilot results

The b4 pilot supplied the following results; they were not rerun by the maintainers.
The referenced synthetic feedback folder was not available in the workspace when
this documentation was updated. These are reported measurements, not an independent
benchmark replication. Environment: Linux, Python 3.14.4, Shiny 1.8.0, shiny-charts
0.4.0b4, Plotly 7.1.0, polars 1.44.2. Raw samples and host details are needed to compare
variance and explain differences; these results are sufficient to narrow the claims.

Seven fresh-process rounds of `bench/adoption.py`, median RSS:

| Process contents | Reported RSS (MiB) |
| --- | ---: |
| Shiny | 63.7 |
| Shiny + shiny-charts import | 63.5 |
| Shiny + Plotly graph-objects import | 63.6 |
| Shiny + first Plotly figure | 74.6 |

The differences between import-only rows are noise, not evidence of negative
import overhead. The first-figure increase is about 11 MiB on this Linux host,
compared with about 20 MiB in the local macOS test. Neither import alone accounts
for that initialization cost.

Reported warm build/wire CPU medians from the same script:

| Case | shiny-charts build / wire (ms) | Plotly build / wire (ms) |
| --- | ---: | ---: |
| Bar / 800 / 8 series | 0.71 / 0.41 | 1.97 / 0.91 |
| Bar / 6,400 / 64 series | 16.8 / 2.9 | 14.6 / 4.0 |
| Scatter / 10,000 / 1 series | 21.4 / 4.3 | 13.4 / 4.2 |
| Scatter / 100,000 / 1 series | 128.6 / 66.9 | 131.3 / 35.3 |

The small-bar advantage holds here. The many-series bar construction is slightly
slower, and scatter construction plus wire encoding is slower overall. The
6,400-row payload is larger too (69 KB versus 47 KB). Choosing a pilot based on
small aggregated bars/lines is justified; assuming gains for large scatter or
many-series workloads is not.

The pilot also ran separate fresh app processes, with Plotly absent from the native
route and jemalloc decay set to zero. Three runs of the real six-chart view with
20,000 filtered rows reported:

| Metric | shiny-charts only | Plotly renderer |
| --- | --- | --- |
| Process RSS after first render | 153–158 MiB | 174–177 MiB |
| Server CPU for six charts | 60–68 ms | 153–162 ms |
| Build + serialization portion | approximately 0–5 ms | approximately 100 ms |
| Serialized six-chart bytes | 15.5 KB | 15.2 KB |

The native route used pack plus JSON. The Plotly route used figure-to-dict, removed
the template, then used `pio.to_json`. This workload supports an approximately
20 MiB process-memory and 100 ms CPU benefit after removing Plotly from the app;
it does not support a chart-payload benefit. At 500,000 rows, aggregation took about
one second and dominated render CPU, while the memory difference stayed similar.

The supplied simplified synthetic app reported smaller gaps: 133–137 versus
140–145 MiB and 18–20 versus 27–32 ms at 20,000 rows; 173–176 versus 185–191 MiB
and about 150–200 versus 155–165 ms at 500,000 rows. Its Plotly figures had fewer
traces and formatting options. These measurements concern whole views, not the
native builder benchmark above, so they should not be combined into one speed ratio.

## Migration coverage

| Requirement | Current support |
| --- | --- |
| Stacked/grouped vertical bars | `chart.bar(..., color=..., stacked=True/False)` |
| Horizontal bars | `chart.bar(..., orientation="horizontal")` |
| Lines and time series | `chart.line(...)`; numeric/category/time x axes, gaps and groups |
| Area, scatter, histogram | Supported; histograms are built server-side |
| Horizontal reference line | `.rule(y=..., label=...)` |
| Interval band | `.band(lower=..., upper=..., label=...)` on line/area |
| Custom hover data | `tooltip=["field", ...]` adds escaped literal column values |
| Formatted hover templates | Beta b5: `.hover(template="{n:number:0} ({share:percent:1})")`; literal escaped text only, no HTML/evaluation |
| Pie/donut | Beta b5: `chart.pie(..., names=..., values=...)`; donut not included |
| Plot text annotations | Beta b5: `.annotate(x=..., y=..., text=..., position=...)` in data coordinates |
| Vertical reference line | Beta b5: `.rule(x=..., label=...)` for numeric, date/time or category x |
| Category divider / plot-edge text | Beta b6: `rule(x_between=(...,...))` and `annotate(y="top", ...)` on vertical charts |
| Stacked bars + shared-axis line | Stable 0.4.0: `.line(totals, y="total", label="Forecast")` on vertical category bars |
| Stable production package | Stable 0.4.0 available on PyPI |

The published b5 adds pie,
data-coordinate text annotations, vertical rules and formatted hover templates,
with no new Python runtime dependencies. Per-column hover formats are also available
through `.hover(formats={"share": "percent:1"})`. Columns must already be encoded or
listed in the builder's `tooltip=[...]`; unrelated source columns never travel.

The documented API was published as stable **0.4.0** after package/browser
validation. The next adoption check is a representative full app migration,
including hover text and annotations. Confirm selection, exports, theming and
short-card layouts, and repeat separate-process CPU/RSS measures. This remains
pilot validation, not evidence of production adoption. The optional native backend
in **0.5.0b1** is a separate experiment; do not relabel that beta as stable to
satisfy an internal mirror policy.

## Empty messages (already published in b3)

Core apps configure the output:

```python
output_chart("daily_shares", empty_message="No observations available yet.")
```

Express automatic output configures the renderer:

```python
@render_chart(empty_message="No observations available yet.")
def daily_shares():
    return None
```

With an explicit Core output, put the message on `output_chart`; the renderer option
configures only automatic output creation. The default dashboard-oriented text
remains unchanged.
