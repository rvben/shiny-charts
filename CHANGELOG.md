# Changelog

## 0.5.0b1 — experimental native beta

- Add an optional Rust Arrow-to-wire backend for Polars bar, line, area and scatter
  charts. Install the `native` extra and import `chart` from `shiny_charts.native`.
- Retain column buffers across fluent copies, validate/pack in Rust and serialize
  without creating per-cell Python objects on the normal native render path.
- Keep the Python backend as the default and for unsupported types and inputs.
  `shiny_charts.native.is_native(value)` exposes which path a chart uses.
- Add an inner-JSON renderer transport; normal outputs retain their existing path.
- Proxy updates remain on Python; expensive synchronous work is not offloaded.
  Date/timestamp, Float32, categorical, untyped Null and decimal inputs fall back.


## 0.4.0 — stable

- Publish the first stable release of the documented Core/Express API after external
  beta re-tests. No new Python runtime dependencies.
- Add one shared-axis `Chart.line(...)` overlay on vertical category bars, with gaps,
  shared formatting/palette/legend, image export and a separate data table/CSV.
  Bar selections keep their keys; bar proxies retain the overlay snapshot.
- Honor directional plot-edge annotation positions against category dividers; measure
  available text space, truncate long labels and omit later overlapping edge labels.
  Fit between-category rule labels inside the plot, including narrow cards.
- Count visible nonzero pie slices in the accessible summary, excluding missing and
  hidden groups while retaining all supplied rows in tables/CSV.


## 0.4.0b6 — beta

- Fix truncated `100%` ticks by including stack totals and semantic percentage
  endpoints when reserving numeric axis space.
- Format temporal category bar axes with short UTC dates, preserving identities.
- Keep annotation text at domain edges visible, while respecting explicit domains.
- Make explicit `number:N`/`percent:N` precision fixed (including trailing zeros);
  bare formats retain compact up-to-two-digit precision. CSV keeps raw values.
- Omit missing-value pie groups from the legend.
- Add category midpoint `.rule(x_between=(...,...), label=...)` and plot-edge
  `.annotate(x=..., y="top"/"bottom", text=...)` on vertical charts.
  Filtered/nonadjacent divider categories are omitted; annotations remain literal.

## 0.4.0b5 — beta

- Bound rotated tick labels using actual chart height to preserve plotting space
  and move the axis title close to them. Reserve space for wide numeric ticks and
  the y-axis title in narrow cards.
- Add `.legend(layout="scroll", placement="bottom")` and single-row narrow-card
  toolbar icons with full accessible names.
- Add `chart.pie`, data-coordinate `.annotate`, semantic `.rule(x=...)`, and escaped
  `.hover(template=..., formats=...)` for full-app migration pilots. Include synthetic
  SVG/Canvas interaction, export and update regressions with no new Python dependencies.
- Scope performance claims to their measured platform/workload. Add reported Linux
  import, warm-build and real-view CPU/RSS results; many-series bars and scatter have
  no general construction, wire-CPU or payload advantage.


## 0.4.0b4 — beta

- Keep compact fixed percent domains evenly spaced, including both endpoints.
- Register the modular ECharts label-layout feature. Hide zero-height and undersized
  stacked segment labels using actual text/bar dimensions, leaving stack totals
  and tooltip/table values available; retain overlap handling for other value labels.
- Automatically wrap a few long category names at word boundaries; explicit
  rotation retains all categories. Add `.ticks(x_labels="all" | "wrap" | "auto")`.
- Add synthetic H–L browser regressions in SVG and Canvas, and an isolated import-RSS
  and warm construction-CPU benchmark with documented scope and migration coverage.


## 0.4.0b3 — beta

- Place the visible chart title above the keyboard legend and plot; preserve titles
  and the current chart snapshot in SVG/PNG exports without re-rendering the chart.
- Serialize live SVG DOM safely so quoted host font families produce valid exports.
- Add `output_chart(..., empty_message="...")` for Core and
  `@render_chart(empty_message="...")` for Express automatic output UI. The message
  applies to None, zero-row and non-plottable results and survives recovery.
- Document the b2 title migration: omit `.labels(title=...)`, or use
  `.labels(title="")`, when the host card header already supplies the visible title.

## 0.4.0b2 — beta

- Synchronize selection, legend, view and click inputs when revision or renderer
  changes; clear stale interaction inputs on None/error results. Keep same-revision
  view preservation and the documented `view(..., zoom=True)` default.
- Show a no-data state for None and zero-row results, hide zero-row axes/tools,
  and show chart-level recalculation feedback with recovery.
- Draw chart titles, including in SVG/PNG exports. Migration: apps with an existing
  card-header title can omit `.labels(title=...)` or use `.labels(title="")` to avoid
  displaying it twice. Keep normalized percentage
  stacks at 0–100% in compact layouts without clipping oversubscribed data.
- Support polars DataFrames through `to_dicts()` without a runtime dependency.
- Thin dense date categories without mid-string wrapping; avoid duplicate integer
  ticks on zero data. Match legend swatches to bar/scatter/line families.
- Add optional numeric domains, tick rotation, bar values and signed stack totals,
  legend/stack ordering, hidden data-table columns, and twelve explicit palette slots.
  Preserve the existing default six-colour hash and selection/CSV key transport.
- Add a synthetic pilot app and browser/compiler/Python regressions based on client
  feedback, without including client data or machine-dependent performance claims.

## 0.4.0b1 — beta

- Package the first public beta for pinned development and staging pilots, with
  bundled browser assets and an explicit supported API contract.

- Migrate the existing Portfolio pulse app locally, retaining calculations, filters
  and selective URL restoration; keep its illustrative data explicitly labeled.
- Add tooltip fields to bar and area builders.
- Honor custom host colors in tools, focus indicators and data dialogs.
- Format table cells consistently with tooltips; keep raw CSV values. Show full UTC
  timestamps in data previews and tooltips.
- Add loading, recalculation and error semantics; detect scatter empty states from
  complete x/y pairs.
- Define the beta contract and exercise desktop/mobile dashboard updates.

## 0.3.0a1 — local alpha

- Add renderer-bound ChartProxy with async replacement and append, rolling row
  limits, aligned interval bounds, ordered generations/sequences and browser status.
- Add service-operations adoption with queue filters, gaps/missing measurements,
  compact cards, live batches, revisions, stable selected record identity and
  region feedback that resets when data or scope changes.
- Add named inherited palette slots to resolve common group color collisions.
- Add horizontal bars, long-label handling, adaptive numeric gutters, Escape to
  exit brushing, and automatic closing of stale table previews after data changes.
- Verify Core/Express/module proxies, session isolation, failed transport,
  concurrent calls, stale/malformed messages, current exports and empty recovery.
- Add a controlled completed-render and websocket full/proxy comparison.
- Validation change: integer keys outside JavaScript's safe range are rejected;
  use string identifiers to retain exact record identity.

## 0.2.0a1 — local alpha

- Extract a native FinOps app that runs without Plotly; retain a separate styled
  comparison. Support 100,000 requests and opt the dense scatter into Canvas.
- Remove redundant scatter/bar source copies and copy scalar row containers
  directly when creating public/wire snapshots, preserving mutation isolation.
- Resize the renderer only when dimensions change. Disable progressive SVG
  patches; keep progressive Canvas painting with individual point identity.
- Define the alpha API/event contract and public selection TypedDicts.
- Add Python/dependency-floor/browser CI, isolated wheel/native-app checks,
  repeatable 10k/100k preparation/paint profiling, and migration examples.

## 0.1.0a1 — prototype

- Five dashboard chart families, native Shiny Core/Express output binding,
  host-theme integration, intervals/rules, normalized click/brush events,
  preserved view state, and CSV/SVG/PNG/table access.

These alphas have not been published. Measurements and review artifacts stay local.
