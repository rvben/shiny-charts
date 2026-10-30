# Migrating a dashboard card

Keep Shiny controls, reactive calculations, and business logic. Change the chart
output, builder, formatting, and event handler for one card at a time. There is no
automatic `go.Figure` conversion.

## Before: shiny-plotly

```python
from shiny import reactive
from shiny_plotly import output_plotly, render_plotly
import plotly.graph_objects as go

# Inside the UI: output_plotly("latency")
# Inside server():
@render_plotly(events="click")
def latency():
    rows = filtered()
    fig = go.Figure(go.Scatter(
        x=[r["latency"] for r in rows],
        y=[r["cost"] for r in rows],
        customdata=[r["id"] for r in rows],
        mode="markers",
    ))
    fig.update_layout(uirevision="latency-v1", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(tickprefix="$", tickformat=".3f")
    return fig

@reactive.effect
@reactive.event(input.latency_click)
def clicked():
    selected_request.set(input.latency_click()["points"][0]["customdata"])
```

## After: shiny-charts

```python
from shiny_charts import chart, output_chart, render_chart

# Inside the UI: output_chart("latency")
# Inside server():
@render_chart
def latency():
    rows = filtered()
    return (
        chart.scatter(rows, x="latency", y="cost", color="workload", key="id")
        .format(y="currency:USD:3")
        .labels(x="Latency (ms)", y="Cost / request")
        .view("latency-v1")
        .select(brush=True)
        .renderer("canvas")  # Keep the renderer stable across filters.
    )

@reactive.effect
@reactive.event(input.latency_selection)
def selected():
    event = input.latency_selection()
    if event["kind"] == "records":
        selected_request.set(event["keys"][0])
    elif event["kind"] == "clear":
        selected_request.set(None)
```

The host's CSS supplies font and theme values; repeated layout templates are not
needed for the native chart. `.band(lower=,upper=)` replaces helper traces for an
interval and `.rule(y=,label=)` adds a reference line. Keep Plotly for features
outside the beta's supported scope.

For small batches on a large retained window, add a [data proxy](incremental-updates.md)
after the initial render. Keep full renders for changes to chart definitions.

## Runnable examples

- `make native`: the four-card FinOps application at localhost:8056. It imports
  only Shiny and shiny-charts and preserves workload/period filters, stable
  request inspection, histogram ranges, brush counts, theme changes and exports.
- `make operations`: service observations, long category names, missing measurements,
  live appends, replacement data, and rolling-window selection at localhost:8057.
- `make demo`: both engines in a controlled comparison at localhost:8055.
- `uv run shiny run examples/express_app.py`: minimal Express chart.

`examples/finops.py` shares dashboard UI and calculations between routes; only
the Plotly route imports Plotly. The native app and wheel are also smoke-tested
in an environment where neither Plotly package is installed.

At a request-count setting of 10,000+ the FinOps example explicitly uses Canvas,
keeping the renderer consistent when workload/period filters change.
The library retains SVG by default. Changing renderer recreates the engine and
resets view state; keep a consistent renderer when zoom continuity matters.

Check event handling, data-table/CSV output, hidden series, zoom preservation,
theme changes, and representative data sizes before adopting another card.
Treat the 100,000-record case as a stress profile, not a guarantee of instant
interaction; full chart specs still travel over Shiny's websocket.
