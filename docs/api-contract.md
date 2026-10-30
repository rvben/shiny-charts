# API contract

**Experimental project: pilot-only and not production-validated.** This contract
describes compatibility expectations, not a claim of production maturity.

This document defines the supported surface of published 0.4.0. Changes to documented builders, defaults,
view behavior and selection fields require release notes and a version change. While the
package remains 0.x, an incompatible public API change increments the minor version;
patch releases preserve this contract. Rendering-engine options and wire internals remain
private.

## Python surface

Public exports: `Chart`, `chart`, `output_chart`, `render_chart`, `Selection`, `ChartProxy`,
and `__version__`. Builders and fluent operations are documented in the README.
`shiny_charts.events` defines the selection TypedDicts for type checkers; consumers still
receive ordinary dictionaries through Shiny inputs.

Builders accept record iterables, column mappings, and pandas/polars DataFrames without
requiring either dataframe library at runtime. Builders snapshot encoded values; changing
the caller's records afterward does not change the chart. Fluent methods return another
chart. `to_spec()` returns an independent snapshot: changing its nested containers does not
modify a chart. Internal `_spec`, `_source`, `_wire`, renderer adapter, and ECharts options
are not public API. Wire dictionaries are a transport detail, not a public data format.

Each builder transports only its encoded columns, requested tooltip fields, and explicitly
selected band bounds. Missing numeric observations use JSON null. Keys must be non-null
unique strings/numbers; booleans are rejected. Integer keys are limited to the JavaScript
safe range; use strings for larger IDs. Datetimes normalize to UTC and naive datetimes are
interpreted as UTC. Time axes display UTC.

## Rendering and state

`output_chart(id)` fills its Shiny container; `height=` creates a fixed-height output. IDs
resolve through the active Core module namespace. Express creates an output automatically. A
renderer returning `None` disposes the chart, shows a no-data message, and clears
click/selection/legend/view inputs to `None`. Errors also clear those inputs and use Shiny's
error rendering and the next successful value recovers the output.

SVG is the library default; `.renderer("canvas")` explicitly chooses Canvas. The FinOps
example chooses Canvas for a scatter with a request-count setting of at least 10,000. That
choice belongs to the example, not to the library's default API.

The same `.view(revision)` preserves x-axis zoom bounds and hidden group names across full
reactive updates. Changing revision resets both and selection state. The binding emits
`clear` selection, an empty legend, and a reset view with the new revision, and sets the
click input to `None`. Renderer changes emit the same resets and recreate the engine and
reset local state. Colors for named groups remain stable under filtering/reordering; palette
hash collisions are possible. `.palette({name: slot})` pins groups to one-based inherited
slots 1–12 (unmapped names retain the original six-slot hash) without hard-coding light/dark
colors. The view does not promise preservation of brush rectangles or an open data-table
snapshot.

`.view(revision)` retains its documented `zoom=True` default; pass `zoom=False` to change
only revision/view identity. Zoom uses Ctrl + wheel. Point/category/bin selection requires
`.select()`. Rectangle brushing requires scatter and `.select(brush=True)`.

## Data proxies

`renderer.proxy()` returns its session-local `ChartProxy`. Public async operations:
`replace_data(data)` and `append(data, max_rows=None)`; public read-only properties: `ready`
and `row_count`. The current rendered definition, formats, bounds encoding, and view are
retained. Line/area/bar/scatter and b5 pie support these operations; histograms require a full render.
Concurrent calls are serialized. Full renders start another generation and supersede earlier
updates. Empty/failed renders invalidate the proxy. See [incremental
updates](incremental-updates.md) for validation, arrival-order row limits, band alignment,
acknowledgements, and recovery responsibilities.

Horizontal bars use `orientation="horizontal"` while retaining semantic x=category, y=value
encodings and event fields. Long category tick labels may be abbreviated; full names remain
in tooltips, tables and CSV. Escape exits region-selection mode.

## Events

Inputs are `<id>_click`, `<id>_selection`, `<id>_view`, `<id>_legend`, and `<id>_update`
(including the module namespace). Events have `priority="event"` and the chart's `revision`,
except an update status for an unbound output, which has no current revision. Changing data
at the same revision does not automatically emit a selection; applications reconcile
selected keys with their filtered scope. Revision/renderer resets emit the current revision
as described above. When a chart is removed by a None result or renderer error, interaction
inputs become `None`. A point/category/bin click emits both a click and selection; a brush
or clear emits selection only.

| `kind` | Required fields besides `revision` |
| --- | --- |
| `records` | `keys`, `x`, `y`, `group`, `row` |
| `category` | `keys` (empty), `x`, `y`, `group`, `row` |
| `bin` | `range: {min,max,upper_inclusive}`, `count` |
| `range` | `range: {x:[min,max],y:[min,max]}`, `count`, `keys`, `truncated` |
| `clear` | `keys` (empty) |

`row` indexes the current displayed dataset, not the caller's original dataframe after
another filter. Use `key=` for identity across filters. A point without a key produces a
`category` event even on a numeric axis. `group` is null when there is no color encoding.
Missing points are not selectable scatter records.

Brush bounds are inclusive. Counts cover visible series only; keys retain displayed record
order and stop at 10,000 entries. `truncated` is true when keyed results exceed that bound.
Without keys, the count/range is available and `truncated` is false. Histogram bounds
include the lower edge; only the final bin includes the upper edge. Histogram events never
masquerade as raw request IDs.

View events contain `{startValue,endValue}` or `{reset:true}`. Legend events contain
`{hidden:[group names]}`. Consumers should ignore unknown extra fields so additive event
metadata can be introduced without breaking handlers.

## Themes, exports, and accessibility

Computed host typography and Bootstrap theme tokens are inherited. Chart-specific CSS
variables override them. Ancestor theme/class/style changes repaint locally. The library
does not ship the demo's font, page layout, or host palette.

CSV exports every displayed record and encoded column; histograms export bins. SVG outputs
save SVG and Canvas outputs save PNG. A table preview contains at most 250 displayed records
and provides keyboard selection. Chart descriptions, controls, focus restoration, and table
access are supported; complete keyboard exploration of graphical points and full
screen-reader parity are not claimed.

## Supported scope

Python >=3.10, Shiny >=1.5, htmltools >=0.6. CI targets Python 3.10–3.14, the exact
dependency floor, and Chromium/Firefox/WebKit. See CONTRIBUTING.md for the commands. A
prepared workflow is not evidence that its remote jobs have run. R, Shinylive, 3D/maps,
lasso, point-level engine updates, and server resampling remain outside this release's
supported scope.

 ## Beta integration details

Line, area, bar and scatter accept explicit `tooltip=` field lists. Histogram exports and
tooltips describe generated bins rather than source records. Encoded x/y cells in View data
use their axis formats; other fields retain literal text. Numeric formats currently use
`en-US`. UTC time axes have abbreviated ticks; table and tooltip timestamps include the full
date and time to seconds. CSV keeps raw encoded values (including UTC strings), with missing
values as empty cells.

An unbound output initially says “Loading chart…”. Shiny recalculation sets `aria-busy` and
shows “Updating chart…” while keeping the previous chart visible. Errors have an alert
message; a successful render replaces them. A scatter with no complete x/y pairs shows the
empty-data state. Null rows remain available in the data table and CSV.

Host overrides apply to chart controls and dialogs as well as the plot: `--chart-fg`,
`--chart-muted`, `--chart-grid`, `--chart-border`, `--chart-surface`, `--chart-font`,
`--chart-color-1` through `--chart-color-12`, `--chart-hover` and `--chart-focus`. Supply
accessible contrast for the host's theme.

The Portfolio pulse adoption keeps four registered bookmark inputs. Chart events are
transient and are not added to those URLs. Applications own persistent selection and
bookmark policy; the library does not silently register them.

 ## Optional b2 presentation controls

- `.domain(x=(min, max), y=(min, max))` sets numeric bounds. Either bound may be
  `None` for automatic scaling; finite bounds must be strictly ordered. The x domain
  requires `x_type="value"`. These are semantic axes: a horizontal bar's y domain
  controls its physical horizontal value axis. Explicit bounds can intentionally
  clip data; domains are not normalization or filtering.
- `.ticks(x_rotation=45)` rotates the semantic x ticks by a finite −90 to 90 degrees.
  In b4, explicit rotation retains every category, and `x_labels="all"` or
  `x_labels="wrap"` controls categorical tick display. The default `"auto"` wraps few
  long word-based names and thins dense axes; ISO dates remain whole strings.
- `.value_labels(show=True, totals=False)` is bar-only. `totals=True` requires stacked
  bars. Values use the y format; totals sum visible groups per category separately
  for positive and negative stacks. `show=False, totals=True` displays only totals.
  Overlapping labels may be omitted for readability. Totals use silent annotation
  series and never produce record-selection events.
- `.legend(order=["B", "A"])` puts listed groups first and retains data order for the
  remainder. Absent names are permitted for stable ordering across filters. Names
  must be unique strings. Ordering also sets series/stack order.
- `.data_table(hide=["key"])` hides encoded or requested tooltip columns in View data.
  It does not remove columns from browser transport, CSV, tooltips, or selection
  payloads. This is display configuration, not privacy redaction.
- `.labels(title=...)` draws a host-themed title and includes it in image exports.
  Very long visible titles truncate; the full title remains in the accessible summary
  and View data heading.

Normalized nonnegative stacked bar/area percentage shares use a 0–100% domain at all widths
when their category totals are at most 1 and their rules/bands stay within that range.
Explicit y domains take precedence; oversubscribed/negative data is not clamped. Tick
intervals respect the chosen numeric precision, avoiding repeated integer labels on all-zero
data. Zero-row outputs show a no-data message without axes or toolbar; records without
plottable pairs keep their data/CSV controls.

## b3 output presentation

Visible chart titles precede the legend and plot. SVG/PNG export adds the title to
the current rendered snapshot, without changing the chart's engine, zoom, brush,
legend state, or render count. Long headings truncate on screen and in the image;
the full title remains in the accessible summary and data-table heading. Omit the
chart title or use `.labels(title="")` when a host card header already provides it.

`output_chart(..., empty_message="...")` sets the Core output's no-data text.
`@render_chart(empty_message="...")` configures Express automatic output UI.
An explicit Core output uses its own configured message. Non-empty strings are
required and inserted as literal text. None, zero-row and non-plottable results use
the same configured message, retaining it across errors and recovery. The default
text remains “No data for this filter. Adjust the dashboard filters to show records.”


## b4 display hardening

Fixed percent domains with both bounds use intervals that divide the range exactly
and explicitly include endpoint labels. Tick spacing retains the displayed precision
where the range permits it. Automatic normalized share axes retain their prior behavior.

Stacked value labels are shown only if their actual text bounding box fits within the
laid-out bar segment with 4px padding per side. Zero/null segments have no in-bar text.
Totals remain separate and use overlap hiding at crowded widths. Hidden values remain
available through tooltips, View data, and CSV; shrinking type is not a fallback.

A few long categorical names wrap at whitespace by default. `.ticks(x_labels="wrap")`
requests word wrapping, `"all"` retains every tick, and `"auto"` retains adaptive behavior.
Explicit `x_rotation` keeps all categories; choose rotation or a wider chart if labels
cannot fit. Word wrapping applies to vertical categorical axes; horizontal categories retain
their gutter truncation and rotation controls.


## b5 migration coverage

- `chart.pie(data, names=, values=, key=None, tooltip=())`: nonnegative numeric values,
  scalar category names and existing records/column mappings/pandas/polars inputs.
  Each row is a slice with preserved row/key identity. Missing values have no slice;
  all-zero data shows the empty message while records remain available for table/CSV.
  Duplicate names share one legend entry. Pie has no Cartesian domain/tick/rule/
  annotation APIs, and no brush. Palette, hover, legend, export and proxy updates apply.
- `.rule(x=..., label=...)` complements `.rule(y=..., label=...)`; exactly one axis
  is required. Numeric, ISO/date/datetime and category x coordinates are supported.
  X rules map to semantic x even for horizontal bars. Unavailable categories are omitted.
- `.annotate(x=..., y=..., text=..., position="top")` adds plain data-coordinate
  text to Cartesian charts. Positions: top/bottom/left/right/inside. Coordinates
  follow x type, y is finite; category annotations appear only when the category exists.
  Engine text is silent; SVG/PNG exports include it. In b6 its anchor must be within
  the plot domain, while text may draw outside the plot with reserved edge space. Annotations
  can extend automatic bounds; explicit domains retain precedence. No automatic
  annotation collision resolution, pixel placement or HTML formatting.
- `.hover(template=..., formats=...)`: templates compile server-side to literal/field
  tokens with optional number/percent/currency formats. Encoded/tooltip columns only.
  Values and literals are escaped; newlines become line breaks. Double braces are literal.
  No evaluation, conversions, nested formats or arbitrary HTML. Formatted columns must
  be numeric/missing, including on data updates. Per-column formats affect hover only.
- `.legend(order=None, placement=None, layout=None)`: named order plus top/bottom
  placement and wrap/scroll layout. Omitted arguments retain previous choices; default
  behavior remains top/wrap. Scroll legends retain keyboard buttons, pressed state and
  server input behavior. Toolbar icons preserve accessible names at narrow card widths.

Rotated ticks budget their depth from the actual plot height and truncate to protect
plotting space. Default/fixed-height outputs share this behavior. The axis name sits
just below the labels; choose a taller output if whole rotated labels are essential.


## b6 display and divider additions

Explicit `number:N` and `percent:N` show exactly N decimal digits (0–6), matching
currency precision. Bare number/percent remain compact, with at most two digits.
This applies wherever the format is used, including table y values; CSV stays raw.
Temporal category bar ticks use short UTC dates without changing transported x values.
Missing pie values have neither slice nor legend entry unless another valid row shares
that name. Valid zero-valued groups remain; all-zero pies retain the empty state.

`.rule(x_between=(first, second), label=...)` requires a category x axis and two
distinct scalar categories. It is mutually exclusive with x/y. Both categories must
be present and adjacent in displayed order to draw the midpoint divider. Missing or
nonadjacent pairs are silently omitted, including after proxy updates; horizontal
bars map the line across the semantic category axis.

`.annotate(x=..., y="top"/"bottom", text=...)` on vertical Cartesian charts anchors
x in data/category coordinates and y outside the corresponding plot edge. It reserves
space without extending the value domain. In 0.4.0, `position="left"`/`"right"` determines horizontal anchoring and alignment
against a matching category divider, otherwise the category. Other positions centre text. Horizontal bars retain
numeric data annotations. Explicit domains omit out-of-domain anchors; text attached
to an in-domain anchor can extend beyond the plot. Unknown category anchors are omitted.
No annotation collision handling or fractional/pixel x coordinates are provided.


## 0.4.0 shared-axis line overlay and layout fixes

`Chart.line(data, *, y, label, x=None, tooltip=())` is supported only on vertical
category bar charts, with at most one overlay. X defaults to the bar x column and
must contain unique non-null scalar categories. Labels are nonempty and cannot match
bar group names (including on later proxy updates). Values are numeric/missing.

The line shares the existing axes, format, domain, palette, legend, view revision and
exports. Categories follow bar order; absent/null line values form gaps. Extra line
categories are omitted until the bar data includes them. Numeric axes account for the
line's visible values; normalized percentage domains do not clamp a line above 100%.

Line points are non-selectable and never emit bar keys. Axis hover shows the line's
own label and shared y format, plus requested line tooltip values. Base hover templates
apply only to bars. View data includes a separate line table, without selection controls,
and its own raw CSV download. The main toolbar CSV retains only the bar dataset.
Bar proxy append/replace retains the line snapshot; change overlay data with a full
render. There is no secondary axis, horizontal overlay, multiple layers or line proxy.

Top/bottom edge labels are measured, bounded within plot width and later overlaps are
omitted. Left/right labels associated with opposite sides of a matching divider face
away from its midpoint. Rule labels fit inside available plot space or ellipsize.
Data-coordinate annotations have no general collision solver. Pie accessible summaries
count visible nonzero slices, omitting missing/zero values and hidden groups; table/CSV
retain all supplied rows.
