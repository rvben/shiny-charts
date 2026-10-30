# shiny-charts

Interactive charts for everyday **Shiny for Python dashboards**, currently evaluated
in pilots. It has its own small semantic API and uses a bundled, modular
Apache ECharts runtime. Plotly is not a runtime dependency.

The switching case is native theme integration, fewer repeated layout decisions,
consistent interaction events, and a smaller browser bundle. The controlled FinOps
comparison (recorded for 0.2.0a1) measured faster cold starts and reactive updates on this machine after
profiling; the initial prototype had updates near parity. That comparison showed **no websocket-size advantage for full reactive renders**;
proxy transport is measured separately, and performance depends on the workload. The package supports common
dashboard charts; Plotly's broader feature catalogue remains outside its scope.

## Project status

**0.4.0 is the published stable API; this repository is at 0.5.0b1**, which adds an
opt-in experimental native backend. Stable API status does not establish production
adoption: use is currently pilot-only. The immediate focus is validating the existing
chart families in representative applications. Broader chart coverage and further
native optimization should follow demonstrated pilot needs.

[Source and issues](https://github.com/rvben/shiny-charts) ·
[Stable package](https://pypi.org/project/shiny-charts/0.4.0/) ·
[Experimental beta](https://pypi.org/project/shiny-charts/0.5.0b1/)

## Install

The published stable release is **0.4.0**, with migration coverage, display fixes,
divider APIs and a shared-axis bar/line overlay described below.

```sh
python -m pip install "shiny-charts==0.4.0"
```

Requires Python >=3.10, Shiny >=1.5, and htmltools >=0.6. The wheel includes the
browser runtime; Node is not required to use it. Pandas and polars are optional.

Pin the exact version for reproducible deployments. The documented Core/Express API
is stable; validate workflows, accessibility and performance with representative data.
Supported chart families are line, area, bar, scatter, histogram and pie. R Shiny and
Shinylive are outside this release's supported scope. See the scope and API notes below.

## Run the native FinOps app

```sh
uv sync --locked
uv run uvicorn examples.finops_app:app --host 127.0.0.1 --port 8056
```

Open [native FinOps](http://127.0.0.1:8056/). It runs with Shiny and shiny-charts alone;
Plotly is imported only by the separate comparison route. The four cards preserve
workload/period filtering, request inspection, brush counts, histogram intervals,
light/dark themes, persistent views, and exports. Dense scatterplots explicitly
choose Canvas when the request-count setting is at least 10,000; smaller ones use SVG.

See the [migration example](docs/migration.md) and [API contract](docs/api-contract.md).
The current API contract applies to 0.4.0.

## Explore the finance-card recipes

```sh
make gallery
```

Open [Finance cards](http://127.0.0.1:8060/): three composed examples for spending,
cash balance and budget usage. A shared 7-day/4-week selector updates the charts,
metrics and breakdowns; selecting a spending bar (or a row in View data) adds a
plot annotation and a detail summary. Light/dark mode, data tables and chart
exports use the existing public API. All figures are deterministic synthetic USD
amounts ending 28 October 2026.

See [the recipe guide](docs/finance-cards.md) and
[the runnable example](examples/gallery_app.py). These examples require no new
runtime dependencies.

## Run the second adoption app

```sh
uv run uvicorn examples.operations_app:app --host 127.0.0.1 --port 8057
```

Open [service operations](http://127.0.0.1:8057/). This synthetic dashboard exercises
long queue names, daily gaps, missing response/resolution pairs, a compact area card,
queue filtering, selected record identity and a rolling observation window. Append
100 observations, revise measurements, or enable live batches every three seconds.
It uses proxies for data updates and full renders for deliberate scope/dataset changes.

See [incremental updates](docs/incremental-updates.md). Obtain a controller with
`proxy = renderer.proxy()`; use `await proxy.append(records, max_rows=...)` or
`await proxy.replace_data(records)`. Appends send only new rows; the browser still
redraws retained data. Full renders supersede old messages, and the update input
reports application or rejection. Histograms use full renders to recompute bins.

## Try the comparison

From this directory:

```sh
uv sync
uv run python -m uvicorn examples.app:app --host 127.0.0.1 --port 8055
```

Open [shiny-charts](http://127.0.0.1:8055/charts/) and
[styled shiny-plotly](http://127.0.0.1:8055/plotly/). Both routes use the same synthetic
FinOps data, Shiny controls, chart families, workload colors, request identifiers,
success metadata, and filters. Plotly is deliberately styled to fit the dashboard.
Try workload bar clicks, request inspection, rectangle selection, a theme change,
zooming, hiding a series, and a simulated reactive update. The demo also supports
500, 2,400, 10,000, and 100,000 requests; the cold-start comparison uses 2,400
with SVG in both engines. At larger sizes the native scatter uses Canvas and
Plotly still uses SVG, so those dashboard timings do not compare identical renderers.

Install the package in another environment with `pip install /path/to/shiny-charts`.
The checked-in browser bundle makes Node unnecessary for Python users. To change the
frontend, run `npm ci && npm run build` first.

## Minimal Core app

```python
from shiny import App, ui
from shiny_charts import chart, output_chart, render_chart

app_ui = ui.page_fluid(
    ui.input_dark_mode(),
    ui.card(
        ui.card_header("Monthly revenue"),
        output_chart("revenue", height="320px"),
        full_screen=True,
    ),
)

def server(input, output, session):
    @render_chart
    def revenue():
        return (
            chart.bar(
                {"month": ["Jan", "Feb", "Mar"], "revenue": [12, 18, 24]},
                x="month", y="revenue",
            )
            .format(y="currency:EUR")
            .labels(y="Revenue")
        )

app = App(app_ui, server)
```

Outputs without an explicit height fill their Shiny card; fixed-height outputs work
outside fillable layouts. Core modules resolve output IDs through Shiny's namespace.
In **Express**, use `@render_chart` directly inside `with ui.card():`; an output is
created automatically. See [examples/express_app.py](examples/express_app.py), runnable
with `uv run shiny run examples/express_app.py`.

## Chart API

Builders accept a pandas or polars DataFrame, an iterable of record dictionaries, or a mapping
of column names to equally sized lists. Pandas and polars are optional. Only the encoded fields,
keys, requested tooltip fields, and band bounds are sent to the browser.

| Builder | Encodings / options |
| --- | --- |
| `chart.line(data, x=, y=)` | `color`, `key`, `tooltip`, `x_type` |
| `chart.area(data, x=, y=)` | `color`, `key`, `tooltip`, `stacked`, `x_type` |
| `chart.bar(data, x=, y=)` | `color`, `key`, `tooltip`, `stacked`, `orientation="horizontal"`; categorical x |
| `chart.scatter(data, x=, y=)` | `color`, `key`, `tooltip`; numeric x/y |
| `chart.histogram(data, x=)` | `bins=20`, optional `range=(min, max)`; server binning |
| `chart.pie(data, names=, values=)` (b5) | Nonnegative slice values; optional `key`, `tooltip` |

Use `color="workload"` for grouped series. Category-to-color hashing keeps assignments
stable when groups are filtered or reordered. Hash collisions are possible; use
`.palette({"Email": 1, "Chat": 2})` for distinct named roles in the host palette. Numeric and missing y values are accepted;
missing observations produce line/band gaps. Date and datetime x columns infer a time
axis; string dates need `x_type="time"`. Datetimes normalize to UTC, naive datetimes
are treated as UTC, and axis dates display in UTC. Explicit time strings should use
ISO 8601 with an offset. Numeric x values infer a value axis for lines and areas.

The fluent operations return a new chart:

```python
plot = (
    chart.line(daily, x="day", y="cost", color="workload")
    .format(y="currency:USD:3")
    .labels(x="Day", y="Cost / request", title="Daily request cost")
    .band(lower="low", upper="high", label="95% interval")
    .rule(y=0.045, label="Budget")
    .view("cost-v1")
)
```

| Operation | Behavior |
| --- | --- |
| `.format(x=, y=)` | `number[:digits]`, `percent[:digits]`, `currency:USD[:digits]`; 0–6 digits |
| `.palette({"Email": 1, "Chat": 2})` | Named groups use one-based inherited palette slots 1–12; others retain the original six-colour hash |
| `.labels(x=, y=, title=)` | Axis labels, visible chart title (also exported), and accessible chart/table description |
| `.band(lower=, upper=, label=)` | Line/area interval using source columns, including intervals crossing zero |
| `.rule(y=, label=)` | Horizontal reference line |
| `.domain(y=(0, 1), x=(None, 100))` | Numeric min/max bounds; `None` retains an automatic bound; x requires a numeric value axis |
| `.ticks(x_rotation=45, x_labels="auto")` | Rotate semantic x ticks; b4 adds `auto`, `all`, or `wrap` category label modes |
| `.value_labels(show=True, totals=False)` | Formatted bar values (b4 hides zero/undersized stacked segments); optional positive/negative totals for stacked bars, recalculated for visible groups |
| `.legend(order=["B", "A"])` | Named groups first, then remaining groups in data order; also controls stack/series order |
| `.data_table(hide=["internal_key"])` | Hide encoded/tooltip columns in View data; CSV, tooltips, transport and selection keys are unchanged |
| `.view(revision="default", zoom=True)` | Preserve zoom/hidden series while revision stays the same; change it to reset client state and server selection/legend/view inputs. Zoom defaults to `True`; use `zoom=False` explicitly |
| `.select(brush=False)` | Enable point/category/bin clicks; rectangle brush is scatter-only |
| `.renderer("svg")` | SVG default; opt into `"canvas"` explicitly |

Percent formats expect fractions (0.25 displays as 25%). Nonnegative stacked bar/area
shares whose category totals are at most 1 use a 0–100% axis at every width, unless
an explicit y domain, an out-of-range rule, or an out-of-range interval requires
another scale. Values exceeding 100% are not clamped. Numeric tick spacing respects
the displayed precision. b4 also divides fixed percent domains evenly, wraps few long
category names at word boundaries, and preserves every category when rotation is requested.
Dense date axes still thin rather than breaking date strings. Bar/histogram axes include
zero; lines and scatterplots use data extents. Zoom uses **Ctrl + mouse wheel** so a
dashboard remains scrollable. SVG export follows the SVG renderer; Canvas exports PNG.
Charts with records include CSV export and a keyboard-accessible table preview of its first
250 displayed records. CSV includes all displayed records. Histogram CSV contains bins,
not the unaggregated requests.

## Shiny interaction

```python
from shiny import reactive

# In server():
@reactive.effect
@reactive.event(input.requests_selection)
def selected():
    event = input.requests_selection()
    if event["kind"] == "records":
        selected_request.set(event["keys"][0])
```

For `output_chart("requests")`, available inputs are `requests_click`,
`requests_selection`, `requests_view`, and `requests_legend`. Point clicks also emit
a selection. Payloads carry the chart's view `revision`. A revision or renderer
change emits selection `clear`, legend `{hidden: []}`, and view `{reset: true}`
with the new revision, and clears the click input to `None`. Returning `None` or
rendering an error clears all four interaction inputs to `None`. Same-revision data
updates do not emit a selection automatically; applications still own reconciliation
of selected keys after filtering at the same revision.

| Selection kind | Payload |
| --- | --- |
| `records` | `keys`, `x`, `y`, `group`, original displayed `row` index |
| `category` | `x`, `y`, `group`, `row`, empty `keys` |
| `bin` | `range: {min, max, upper_inclusive}`, aggregated `count` |
| `range` | `range: {x: [min,max], y: [min,max]}`, `count`, `keys`, `truncated` |
| `clear` | Empty `keys` |

Pass a non-null unique `key` column for record identity across filtering. Brush counts
include only visible series and non-missing points. At most 10,000 record keys are sent;
`count` remains exact and `truncated` reports the limit. Bins include their lower edge
and exclude their upper edge, except the final bin includes the upper edge. View events
report x-axis bounds or `{reset: true}`; legend events report hidden group names.

## Theme integration

The chart reads computed styles from its actual output element. It inherits the font,
Bootstrap body/secondary text, background, and border colors; transparent chart surfaces
fit their containing card. Ancestor theme/class/style changes redraw in the browser.
Dark mode and themes scoped to individual cards are supported.

Optional overrides live on any ancestor:

```css
.my-dashboard {
  --chart-font: Georgia, serif;
  --chart-fg: #243044;
  --chart-muted: #596779;
  --chart-grid: #dce4ed;
  --chart-border: #dce4ed;
  --chart-surface: #ffffff;
  --chart-color-1: #087eac;
  /* --chart-color-2 through --chart-color-12 */
}
```

The library does not inject the demo's Manrope font or app palette. Those belong to
the host dashboard. `[data-bs-theme]` selects theme mode; system preference supplies
the fallback when there is no explicit theme.

## Migrating from shiny-plotly

Replace `output_plotly`/`render_plotly` with `output_chart`/`render_chart`, then rebuild
the figure using the semantic builders. Replace `customdata` IDs and nested Plotly click
payloads with `key=` and the normalized event inputs. Put dashboard theme values in CSS,
and use `.view()` where you previously used `uirevision`; pass `zoom=False` if the chart should not zoom.

There is **no automatic conversion** of `go.Figure` or Plotly Express figures and no
Plotly compatibility layer. Start with one ordinary chart card and retain shiny-plotly
for specialized charts. ECharts options are kept inside the frontend adapter; an
arbitrary engine-options escape hatch is not part of this prototype's public API.

## Verification and evidence

```sh
uv sync
npm ci
npm run build
npm test
uv run pytest -q
uv run ruff check src examples tests bench scripts
uv build
uv run python scripts/check_wheel.py
uv run python scripts/check_floor.py --python 3.10
```

Browser tests need Chromium (`uv run playwright install chromium`). Tests cover real
Shiny Core/Express rendering, scoped themes, modules, click/brush identity, persistent
views, table selection, CSV/image export, resizing, empty/error/None recovery, mobile
overflow, and automated accessibility checks. Automated checks are not a claim of full
screen-reader chart accessibility.

With the comparison server running, reproduce the local measurement:

```sh
uv run python bench/run.py --rounds 5
uv run python bench/write_report.py
```

The generated [decision report](bench/report.md) records medians, environment,
methodology, code-size comparison, and limits. Raw samples are in `bench/results.json`.
These reports and review screenshots are local working material and excluded from commits.

Profile the large scatter path independently:

```sh
uv run python bench/profile_large.py
uv run python bench/write_profile_report.py
```

This profile separates Python builder/packing/JSON costs from actual SVG/Canvas
completion for 10,000 and 100,000 points. It checks painted point counts and reports
post-GC heap/DOM size. It is separate from the four-card cold-start benchmark.
See the generated [large-data report](bench/report-profile.md). Full updates still
send complete chart specs; a smaller renderer bundle does not imply smaller event
traffic or instant updates with large data.

Compare full versus proxy updates independently:

```sh
uv run python bench/updates.py
```

The generated [incremental transport report](bench/report-updates.md) measures received
websocket bytes and completed Canvas updates for identical rolling keyed scatters.
This compares two shiny-charts update paths, separately from Plotly timings.

## Scope and next investment

Implemented: line, area, grouped/stacked bars, scatter, histogram, interval bands,
horizontal rules, SVG/Canvas, linked filtering, theme inheritance, and exports.
Beta b5 adds pie, x rules, data-coordinate annotations and formatted
hover templates; see the migration APIs below.
Missing: 3D, maps, facets, arbitrary mixed axes/layers (apart from the shared-axis bar line overlay below), lasso, server resampling,
point-level engine updates, automatic figure migration, and mature localization.
R and Shinylive have not been validated. Normal reactive renders send complete specs;
proxy appends send only new records while retaining the rendered definition. Long category labels and extreme numeric scales need broader layout testing.

The beta includes native FinOps and service-operations adoption apps, an explicit
API/event contract, ordered data proxies, migration examples, dependency-floor and
browser checks, and compatibility CI. The next external validation is a dashboard with actual user data and manual
accessibility testing before production adoption. A custom Plotly partial bundle could
narrow the cold-start advantage. See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks.

MIT package; bundled ECharts/zrender retain their licenses and notices. See
[THIRD_PARTY.md](THIRD_PARTY.md).

## Adopt in Portfolio pulse

```sh
make portfolio
```

Open [Portfolio pulse](http://127.0.0.1:8058/). This local migration of an existing
Python Shiny app retains its financial calculations, four filters and registered
URL bookmarks. Its data is illustrative. The deployed original remains unchanged.
The `adoption` development group installs `shinyhub-bookmarks==0.5.2`, which needs
Shiny >=1.8; the chart library still supports Shiny >=1.5 and does not depend on
that SDK. See the [adoption notes](docs/portfolio-adoption.md).

Bar and area builders now accept `tooltip=["field"]`, like line and scatter.
Data tables use the encoded axis formats; CSV keeps raw values. Custom hosts can
set `--chart-hover` and `--chart-focus` alongside the existing chart color tokens.

```sh
make profile-dashboard
```

This measures completed warm updates in Portfolio pulse and the four-card service
operations app at desktop/mobile widths. It is a local workload measurement,
not a Plotly comparison or a production throughput guarantee. Generated
`bench/report-dashboard.md` and `bench/results-dashboard.json` stay local.


## Synthetic client-pilot regressions

```sh
uv run uvicorn examples.pilot_app:app --host 127.0.0.1 --port 8059
```

This synthetic app exercises revision resets, server input state, percent shares,
value/stack-total labels, optional table-column hiding, twelve explicit palette slots,
dense dates, zero ticks, numeric domains, rotation, and None/empty/loading/error
recovery. `tests/test_pilot.py` checks the same interactions in a real Shiny session.
A zero-row chart clears axes and hides its toolbar. A renderer returning `None`
shows a no-data message and disposes the previous chart. Missing-pair charts with
records keep data/CSV access even when there is nothing to plot. Updating charts
show a chart-level status message while keeping existing data visible.

The default hashed palette remains the original six colours for b1 compatibility.
For eight distinct named groups, use `.palette({name: i + 1 for i, name in enumerate(names)})`.
Slots 1–12 inherit `--chart-color-1` through `--chart-color-12` from the host; colour
alone should not carry record identity. Table-column hiding is a presentation option,
not data redaction: keys still reach the browser, selection events, and CSV exports.


## Chart headings and empty messages (b3)

A visible `.labels(title=...)` heading appears above the legend and plot and is
included in SVG/PNG exports. Apps whose card header already supplies the title can
omit the chart title, or clear it with `.labels(title="")`, to avoid showing it twice.
The full title stays in the accessible summary and View data heading; long visible
headings truncate. Image export preserves the current rendered view.

For a chart that is not filter-driven, customize its no-data message in Core:

```python
output_chart("observations", empty_message="No observations available yet.")
```

Or configure the automatic output in Express:

```python
@render_chart(empty_message="No observations available yet.")
def observations():
    return None
```

The message must be a non-empty string and is rendered as literal text. It applies
to None, zero-row data, and records without plottable values. Core uses the message
on its explicit `output_chart`; the renderer option configures automatic output UI.
The existing default message remains unchanged.


## Adoption and server capacity

See [server footprint and construction measurements](docs/adoption.md) for a
reproducible fresh-process RSS benchmark, warm spec CPU timings, chart coverage,
and the remaining migration gaps. These measurements exclude dashboard aggregation
and do not predict session capacity on another host.


## Full-migration APIs (b5)

```python
chart.pie(rows, names="status", values="n", key="id", tooltip=["share"]).hover(
    template="{status}: {n:number:0} ({share:percent:1})"
)

chart.line(daily, x="day", y="n", tooltip=["share"]).rule(
    x=date(2026, 1, 2), label="Cutoff"
).annotate(x=date(2026, 1, 2), y=12, text="Peak", position="bottom").hover(
    formats={"share": "percent:1"}
)
```

Import `date` from `datetime` for the date example. Pie values are nonnegative;
missing values are omitted from slices, and an all-zero pie shows the empty message
while retaining its data table and CSV. Slice events retain original row keys.
Repeated names form separate slices controlled by one legend group; aggregate first
if one slice per category is intended. Pie accepts palette/legend/hover/selection
controls; axis domains, ticks, reference rules and plot annotations require Cartesian
charts. Donuts are not included.

`.rule` accepts exactly one of semantic `x` or `y`; x rules follow dates/categories
and map correctly on horizontal bars. `.annotate` uses data coordinates and plain
text, with `top`, `bottom`, `left`, `right` or `inside` placement. Unknown category
coordinates are omitted until the category appears; explicit domains retain precedence.
Annotations are silent, export with the chart, and may extend automatic axis bounds.
Position them to avoid obscuring important marks; annotation collision resolution
is not automatic.

Hover template fields are actual column names already encoded or explicitly requested
via `tooltip=[...]`. `{field}` uses its default display; `{field:percent:1}`, number
and currency formats override it. Double braces produce literal braces; newlines
produce line breaks. HTML and data are escaped, and expressions, attribute access,
conversions and nested formats are not evaluated. Per-column `.hover(formats=...)`
affects hover only, leaving table/CSV values and axis formatting unchanged.

`.legend(layout="scroll", placement="bottom")` creates a keyboard-accessible single
scrolling row below the plot. The defaults remain wrapping and top placement. Order,
placement and layout can be configured in separate calls. Narrow-card toolbars show
icons with complete accessible action names and native title tooltips, retaining a
single row; very short widths can scroll horizontally.

Rotated tick width is bounded by the actual output height, preserving plotting space
and keeping the axis title close to the labels. Long ticks truncate in short outputs;
use a taller output for complete rotated labels. Wide numeric ticks reserve room for
the y-axis name, with truncation only where the card cannot accommodate the values.

Run the synthetic coverage app with `uv run uvicorn examples.adoption_app:app --port 8059`.
The benchmark guide now separates macOS measurements from reported Linux results:
small aggregated bars can benefit, while many-series bars and large scatter charts
have no general CPU or payload advantage.


## b6: ticks, dates and dividers

Stacked numeric axis gutters include stack totals and percentage endpoints, so `100%`
is retained at compact and wide widths. Date/datetime values on categorical bar axes
use short UTC date labels; category order, timestamp identities and CSV stay unchanged.
Missing pie values also disappear from the legend (a group with any valid value stays).

Explicit `number:N` and `percent:N` now mean exactly N decimal places in axes,
tooltips, labels and formatted table values: `percent:1` renders `84.0%`. Bare
`number`/`percent` retain up to two decimal places. CSV exports retain raw values.
This changes the presentation of explicitly formatted whole values from b5.

```python
chart.bar(rows, x="month", y="n").rule(
    x_between=("Mar", "Apr"), label=""
).annotate(x="Mar", y="top", text="Actuals").annotate(
    x="Apr", y="top", text="Forecast"
)
```

`x_between` requires a categorical x axis and two distinct scalar categories; the
line appears halfway between their centres only while both are present and adjacent
in displayed order. Filtering them out or separating them omits the line. It also
maps correctly on horizontal bars. Exactly one of `x`, `y` or `x_between` is required.

Data-coordinate annotations can draw outside the plot when their anchor is within
its domain; this keeps text at the maximum readable without changing the data scale.
Plot-edge `y="top"`/`"bottom"` annotations on vertical charts use semantic data x
and place text outside the plot, reserving space without extending the value domain.
Their text remains literal, silent, theme-aware and included in SVG/PNG exports.
Unknown category annotations are omitted. Pixel coordinates, fractional paper x and
automatic collision handling remain outside the API.


## Shared-axis forecast overlay (0.4.0)

```python
chart.bar(df, x="period", y="value", color="group", stacked=True).line(
    totals, y="total", label="Total forecast"
)
```

`.line(data, y=, label=, x=None, tooltip=())` adds one line over vertical categorical
bars, sharing the category x axis and y axis. `x` defaults to the bar x column. One
row per category is required; duplicates raise an error rather than aggregate.
Points follow bar category order; missing/null values form gaps, and categories absent
from the bars are omitted. A line alone never introduces a new category.

The line label must differ from bar group names. Its palette slot, legend order,
hide/show state and revision reset use the same APIs as bars. Shared `.format(y=...)`
and `.domain(y=...)` apply to both; the overlay can extend automatic y bounds and
participates in SVG/PNG export. The overlay is silent for selections: bar keys and
row identities stay unchanged. Hover displays its own label and shared y format plus
requested line tooltip columns; the bar's hover template applies to bar rows only.
View data includes a separate line table and a **Download line CSV** button with all
supplied overlay rows; the existing toolbar CSV remains the bar dataset. No secondary
axis, horizontal overlay, multiple overlays, line value labels or separate line proxy
is included. Bar proxy updates retain the supplied line snapshot and omit line
categories filtered out of the bars; change both datasets with a full render.

Plot-edge annotation `position="left"`/`"right"` now anchors and aligns text on the
corresponding side of a matching between-category divider. Without a divider it uses
the category anchor. Labels are bounded to the available plot width, truncate with an
ellipsis when necessary, and later plot-edge labels that overlap an earlier one are
omitted. Other positions remain centred. Rule labels choose space inside the plot
rather than clipping at the edge. These rules apply at both top and bottom edges;
annotations in data coordinates still have no general collision solver.

Pie summaries count visible nonzero slices, excluding missing values and hidden
groups. Data tables and CSV still include the supplied missing/zero rows.

Version 0.4.0 promotes the documented Core/Express API to a stable release. Public
API removals or incompatible defaults require a minor-version change while the
package remains 0.x; patch releases preserve the contract. Engine options, `_spec`
and wire internals remain private. The stable PyPI release is 0.4.0.


## Experimental native beta (0.5.0b1)

```sh
python -m pip install "shiny-charts[native]==0.5.0b1"
```

Opt in by changing only the builder import:

```python
from shiny_charts.native import chart, is_native
from shiny_charts import output_chart, render_chart

spec = chart.bar(df, x="period", y="value", color="group", stacked=True)
assert is_native(spec)  # inspect during the pilot; unsupported inputs fall back
```

The default `from shiny_charts import chart` stays on Python. The optional
`shiny-charts-native==0.1.0b1` package supplies the Rust extension; internal mirrors
must carry both beta packages. The native path handles Polars integer, Float64,
boolean, string and null columns for bar, scatter, line and area. Dates/timestamps,
Float32, untyped Null, categorical/dictionary, decimal and other unsupported types fall back,
as do other input types and pie/histogram. `to_spec()` still returns an independent
Python snapshot, materializing rows when requested. Bands and overlays work,
but row-inspecting operations can materialize a cache; proxy updates use Python.

Local synthetic 500k-row benchmarks on macOS arm64 / CPython 3.13 measured roughly
13× lower server CPU for scatter and 45× for a line frame retaining eight unused
columns. These include build, packing and Shiny-shaped envelope encoding, exclude
aggregation and browser rendering, and compare against the Python backend—not
Plotly. They are not projected dashboard speedups. The transport includes another
browser JSON parse. Serialization releases the GIL, but synchronous work still
runs on Shiny's event-loop thread; no bounded worker offload is implemented.

Wheels use CPython's 3.10+ stable ABI; free-threaded Python is not covered. Unsupported
platforms can build the optional extension from source with a recent Rust compiler.
For rollback, restore the standard builder import and install `shiny-charts==0.4.0`.

The source distribution includes `bench/native.py` for fresh-process CPU/RSS
comparisons at 100k and 500k rows. Run it with the pilot environment’s Python.
