# Finance-card recipes

Run `make gallery`, then open <http://127.0.0.1:8060/>. Alternatively:

```sh
uv run uvicorn examples.gallery_app:app --host 127.0.0.1 --port 8060
```

The [example](../examples/gallery_app.py) demonstrates three compositions using
the public `chart`, `output_chart` and `render_chart` API. It uses native Shiny
controls and the existing locally hosted demo font; no external service or new
dependency is needed. Its [host stylesheet](../examples/www/gallery.css) extends
the existing demo theme without changing library defaults.

## Spending: metric, chart, selected-period detail

The headline and comparison use the same records as the bars. Seven-day windows
show days; four-week windows show seven-day totals. The comparison always uses
the immediately preceding window of the same length.

`.select()` and a unique `key` connect both chart clicks and keyboard selection
in View data to the detail below the chart. `.annotate(y="top", ...)` identifies
the selected bar without relying on color. Selection is app-owned; changing the
reporting period clears it, and events from another view revision are ignored.
Clear selection removes the annotation and restores the highest-spending summary.

## Cash balance: trend with a reconciliation

The continuous ledger carries a starting balance through 56 days. Both reporting
windows end on the same date, so the closing balance stays the same while the
opening balance, incoming payments and outgoing payments change. The figures
below the line chart reconcile as opening + incoming − outgoing = closing.

The line chart uses the library's data-extent scale, rather than zero, to make
changes in balance readable. Currency ticks and the accessible data table expose
the actual scale. The host overrides one chart palette token for this card;
the renderer still inherits its text, font, surface and grid from the theme.

## Budget: percentage chart with exact amounts

Each category's budget is its daily allowance multiplied by the selected number
of days. Horizontal bars show actual / budget, with a reference rule at 100%.
Values above budget remain visible beyond that rule. The adjacent table shows
actual amounts, budgets and remaining amounts; an overrun is explicitly labeled
“over” as well as colored. The overall remainder can be positive while one
category exceeds its allowance.

## Adapting the recipes

Replace `LEDGER` with your own dated records and category totals; keep the
headline, chart and supporting detail derived from the same reactive calculation.
The current example has fixed, nonempty synthetic windows. A production data
source should handle missing dates, unavailable comparisons and zero budgets
explicitly before computing ratios.

The composition takes inspiration from the
[Mebius chart gallery](https://www.mebius.design/freebies/charts): contextual
metrics, compact period controls and supporting detail around a chart. All
implementation code and synthetic data here are authored for this example;
no Mebius code, Figma files or assets are included.
