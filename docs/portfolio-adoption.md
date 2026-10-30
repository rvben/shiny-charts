# Portfolio pulse adoption

This is a local migration of ShinyHub's existing `examples/bookmarking-demo/app.py`,
not a new chart showcase or production-data validation. `tests/fixtures/portfolio_original.py`
is the unchanged baseline. `examples/portfolio_app.py` is the migrated app. Neither
the deployed original nor its deployment requirements were edited.

Run `uv sync --locked`, `npm ci`, `npm run build`, then `make portfolio`.
The optional development `adoption` group includes the published bookmarking SDK
0.5.2 (Shiny >=1.8). The library runtime needs only Shiny >=1.5 and htmltools >=0.6.

## Preserved behavior

Region/product factors, reporting year, forecast multiplier, metric rounding and
all eight relative trend values retain the original semantics. Excluding forecast
removes the last two trend values, as before. The series has no annual revenue
amounts, so it is labeled as an illustrative relative index. Financial cards still
show the original modeled revenue, margin and customer calculations.

The same four fields use the existing bookmark registration, defaults and aliases.
Old `territory` links restore Region; `Legacy planning` restores Planning. Removed
and unknown inputs are handled by the SDK. Chart selection is transient.

## Integration pattern

The original builds handcrafted bar tags inside `render.ui`. The migrated output
is declared once beside the reactive metric fragment:

```python
output_chart("trend", height="280px")

@render_chart
def trend():
    return (chart.bar(trend_rows(), x="year", y="index", key="year",
                      tooltip=["scope"])
            .format(y="percent:0")
            .labels(x="Year", y="Trend index")
            .palette({"Trend index": 1})
            .view("portfolio-v1", zoom=False)
            .select())
```

Putting the chart outside the metric `render.ui` avoids recreating its engine on
filter changes. Years are stable string keys; detail text resolves them against
current rows and explains when a selected year is outside the filtered view.
The host maps its existing dark colors to chart CSS variables, including dialog,
hover and focus states. No library-specific page layout is required.

Tests compare actual original and migrated Shiny sessions, metric values and bar
values under filter changes, engine retention, bookmark round trips, outdated links,
transient selection, formatted table/raw CSV, mobile layout and automated a11y.
These checks do not validate the financial model against business data or replace
manual assistive-technology testing.
