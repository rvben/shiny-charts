# Incremental data updates

In 0.3.0a1, obtain a session-local `ChartProxy` from an existing `render_chart`
instance. `await proxy.append(records, max_rows=...)` transports only incoming
records. `await proxy.replace_data(records)` sends replacement records while
keeping the current chart definition. Both support line, area, bar, and scatter,
including aligned line/area interval bounds. Histograms require a full render to
recompute bins. This is incremental transport: the browser redraws the retained
rows with the existing engine rather than applying point-level engine patches.

```python
from shiny import App, reactive, ui
from shiny_charts import chart, output_chart, render_chart

app_ui = ui.page_fluid(
    ui.input_action_button("add", "Append observation"),
    output_chart("requests", height="320px"),
)

def server(input, output, session):
    initial = [{"x": 0, "y": 2, "id": "initial"}]

    @render_chart
    def requests():
        return chart.scatter(initial, x="x", y="y", key="id").view("requests-v1").select()

    proxy = requests.proxy()

    @reactive.effect
    @reactive.event(input.add)
    async def add():
        if not proxy.ready:
            return  # Wait for the initial chart render.
        n = input.add()
        await proxy.append([{"x": n, "y": n + 2, "id": f"observation-{n}"}], max_rows=2000)

app = App(app_ui, server)
```

The same pattern works in Express and Core modules. The renderer resolves its
output ID through its session namespace. Create the controller inside the server;
never share a renderer or controller across sessions. It retains a server-side
snapshot so incoming values/keys can be validated before sending. `ready` means a
successful full render has established that snapshot; it is not a browser receipt.
`row_count` is the number of records in the latest server-side snapshot.

## Data, windows and state

- Supply the same encoded fields, key, tooltip fields, and any band bounds as the
  original chart. Extra unused fields stay on the server. Formatting, orientation,
  axes, selection settings, and view revision come from the rendered definition.
- `max_rows` is a positive JavaScript-safe integer; it keeps newest rows in arrival
  order across all groups. Lines may sort x values for display afterward. An empty
  append is a no-op unless its row limit shrinks the current window.
- Keys must be unique across the current records and new batch, even when older
  records will roll off. Integer keys must fit the JavaScript safe range; use
  strings for larger identifiers. Replacement records may reuse previous keys.
- Zoom and hidden groups remain local. Use stable keys for app selection identity;
  the app decides what to do when a selected record leaves its window. Data updates
  close an open table preview and restore focus, avoiding selection from stale rows.
  CSV and image exports reflect the current dataset.
- Changing encodings, labels, rendering mode, view revision, or histogram bins uses
  a normal full render. That render supersedes queued messages from the old data
  generation. A renderer returning `None` or raising an error invalidates its proxy
  until a successful full render establishes another generation.

## Ordering and acknowledgements

Each full render creates a generation token and sequence zero. A controller
serializes concurrent calls; updates contain the previous and next sequence.
The browser validates a message before changing data and reports:

- `<id>_update`: `{status: "applied", token, sequence, rows, revision}` after a valid
  update is installed. This does not mean progressive Canvas painting has finished.
- `{status: "ignored", reason, token, sequence, revision}` for a stale, out-of-order,
  or malformed update. An unbound output reports `reason: "unbound"` and has no
  current revision to report.

A successful Python send is not a browser acknowledgement. On desynchronization,
perform a full render from the app's authoritative data; no automatic reconnect
replay or retry is provided. Do not rely on chart-generated input events to keep
an authoritative dataset. Keep it in your application's data/reactive state.
If that state is read directly by the chart renderer, changing it also triggers a
full render: use `reactive.isolate()` for reads intended to be delivered by proxy,
and an explicit generation dependency for deliberate full resets. See the runnable
[service operations app](../examples/operations_app.py) for this pattern, four
synchronized cards, filters, live batches, measurement revisions and empty recovery.
Its inspection panel preserves an individual record while it remains in scope;
region counts reset explicitly when data or queue changes.

Use full renders for infrequent changes when their simplicity fits. Proxy append
is most useful when a small new batch would otherwise resend a large window.
Run `uv run python bench/updates.py` for the controlled full/proxy comparison. Its
local report separates received websocket bytes from completed browser paint time.
