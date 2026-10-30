"""Second adoption app: rolling service data and renderer-bound proxy updates."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shiny import App, reactive, render, ui

from examples.operations_data import QUEUES, daily, queue_totals
from examples.operations_data import observations as make_observations
from shiny_charts import chart, output_chart, render_chart

HERE = Path(__file__).parent
CHANNEL_PALETTE = {"Email": 1, "Chat": 2, "Phone": 4}


def card(id, title, description, **kwargs):
    return ui.card(
        ui.card_header(ui.tags.div(ui.h2(title), ui.p(description))),
        output_chart(id),
        full_screen=True,
        **kwargs,
    )


app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.link(rel="stylesheet", href="styles.css"),
        ui.tags.link(rel="stylesheet", href="operations.css"),
    ),
    ui.tags.a("Skip to charts", href="#charts", class_="skip-link"),
    ui.tags.header(
        ui.tags.div(
            ui.tags.strong("Service operations"),
            ui.tags.span("Synthetic observations · Python Shiny", class_="app-context"),
        ),
        ui.input_dark_mode(id="color_mode", mode="light"),
        class_="app-header",
    ),
    ui.tags.main(
        ui.tags.div(
            ui.tags.div(
                ui.h1("How is the service desk keeping up?"),
                ui.p("Compare queues and inspect response times as new observations arrive."),
            ),
            class_="page-heading",
        ),
        ui.tags.div(
            ui.input_select("queue", "Queue", {"All": "All queues", **{q: q for q in QUEUES}}),
            ui.input_select(
                "n",
                "Rolling window",
                {
                    "500": "500 observations",
                    "2400": "2,400 observations",
                    "10000": "10,000 observations",
                },
                selected="2400",
            ),
            ui.input_select(
                "quality",
                "Measurements",
                {
                    "gaps": "Some missing",
                    "complete": "Complete",
                    "empty": "No observations",
                },
            ),
            class_="controls operations-controls",
        ),
        ui.tags.div(
            ui.input_action_button("append", "Append 100 observations"),
            ui.input_action_button("revise", "Revise measurements"),
            ui.input_switch("live", "Live updates every 3 seconds", value=False),
            class_="controls update-controls",
        ),
        ui.tags.div(
            ui.output_text("status"), class_="selection-status", role="status", aria_live="polite"
        ),
        ui.tags.section(
            ui.tags.div(
                card(
                    "response",
                    "Response time by day",
                    "Missing measurements stay as gaps. Ctrl + scroll to zoom.",
                    class_="trend-card",
                ),
                card(
                    "queues",
                    "Handled requests by queue",
                    "Select a queue; full names are available in the tooltip and data table.",
                ),
                class_="charts-top",
            ),
            ui.tags.div(
                card(
                    "throughput",
                    "Daily throughput",
                    "Requests handled across the selected queues.",
                    class_="compact-card",
                ),
                card(
                    "observations",
                    "Response and resolution",
                    "Inspect an observation or select a region. "
                    "Missing pairs are excluded from the plot.",
                ),
                class_="charts-bottom",
            ),
            id="charts",
            aria_label="Service performance charts",
        ),
        ui.tags.section(
            ui.h2("Observation detail"),
            ui.output_text("detail"),
            class_="detail-panel",
            aria_live="polite",
        ),
        ui.tags.footer(
            "Synthetic data for evaluating chart behavior. "
            "The window retains the newest observations; charts share the selected queue."
        ),
    ),
    title="Service operations · shiny-charts",
    lang="en",
)


def server(input, output, session):
    rows = reactive.Value([])
    generation = reactive.Value(0)
    selected = reactive.Value(None)
    region = reactive.Value(None)
    updates = reactive.Value(0)
    cursor = 0
    lock = asyncio.Lock()

    @reactive.effect
    def reset():
        nonlocal cursor
        count = int(input.n())
        cursor = count
        rows.set(
            []
            if input.quality() == "empty"
            else make_observations(0, count, gaps=input.quality() == "gaps")
        )
        with reactive.isolate():
            generation.set(generation.get() + 1)
        selected.set(None)
        region.set(None)
        updates.set(0)

    def filtered():
        queue = input.queue()
        # Data changes are delivered by proxies. Scope/generation changes still
        # use normal Shiny renders, which supersede the previous data generation.
        with reactive.isolate():
            data = rows.get()
        return [r for r in data if queue == "All" or r["queue"] == queue]

    @render_chart
    def response():
        generation.get()
        return (
            chart.line(daily(filtered()), x="day", y="response", color="channel", x_type="time")
            .palette(CHANNEL_PALETTE)
            .labels(x="Day (UTC)", y="Response (minutes)")
            .format(y="number:1")
            .view("response-v1")
        )

    @render_chart
    def queues():
        generation.get()
        return (
            chart.bar(queue_totals(filtered()), x="queue", y="handled", orientation="horizontal")
            .labels(x="Queue", y="Handled requests")
            .select()
        )

    @render_chart
    def throughput():
        generation.get()
        return (
            chart.area(daily(filtered(), by_channel=False), x="day", y="handled", x_type="time")
            .labels(x="Day (UTC)", y="Handled requests")
            .view("throughput-v1")
        )

    @render_chart
    def observations():
        generation.get()
        return (
            chart.scatter(
                filtered(),
                x="response",
                y="resolution",
                color="channel",
                key="id",
                tooltip=["queue", "time"],
            )
            .palette(CHANNEL_PALETTE)
            .labels(x="Response (minutes)", y="Resolution (minutes)", title="Service observations")
            .format(x="number:1", y="number:1")
            .select(brush=True)
            .view("observations-v1")
            .renderer("canvas" if int(input.n()) >= 10000 else "svg")
        )

    response_proxy, queues_proxy, throughput_proxy, points_proxy = (
        renderer.proxy() for renderer in (response, queues, throughput, observations)
    )

    async def deliver(append: bool):
        nonlocal cursor
        async with lock:
            if not all(
                p.ready for p in (response_proxy, queues_proxy, throughput_proxy, points_proxy)
            ):
                return
            old = rows.get()
            batch = (
                make_observations(cursor, 100, gaps=input.quality() != "complete") if append else []
            )
            if append:
                cursor += 100
                data = [*old, *batch][-int(input.n()) :]
            else:
                data = [
                    {
                        **r,
                        "response": round(r["response"] * 1.01, 2)
                        if r["response"] is not None
                        else None,
                    }
                    for r in old
                ]
            queue = input.queue()
            visible = [r for r in data if queue == "All" or r["queue"] == queue]
            incoming = [r for r in batch if queue == "All" or r["queue"] == queue]
            if append and visible:
                await points_proxy.append(incoming, max_rows=len(visible))
            else:
                await points_proxy.replace_data(visible)
            await response_proxy.replace_data(daily(visible))
            await queues_proxy.replace_data(queue_totals(visible))
            await throughput_proxy.replace_data(daily(visible, by_channel=False))
            rows.set(data)
            if region.get():
                region.set({"kind": "clear", "reason": "updated"})
            updates.set(updates.get() + 1)
            # Selection identity belongs to the app, not the position of a row.
            if selected.get() and not any(r["id"] == selected.get() for r in data):
                selected.set(None)

    @reactive.effect
    @reactive.event(input.append)
    async def append_batch():
        await deliver(True)

    @reactive.effect
    @reactive.event(input.revise)
    async def revise():
        await deliver(False)

    @reactive.effect
    async def live_updates():
        if input.live():
            reactive.invalidate_later(3)
            with reactive.isolate():
                await deliver(True)

    @reactive.effect
    @reactive.event(input.queues_selection)
    def select_queue():
        event = input.queues_selection()
        if event["kind"] in ("category", "records"):
            ui.update_select("queue", selected=event["x"])
        elif event["kind"] == "clear":
            ui.update_select("queue", selected="All")

    @reactive.effect
    @reactive.event(input.queue)
    def reconcile_scope():
        queue = input.queue()
        key = selected.get()
        if key and not any(
            r["id"] == key and (queue == "All" or r["queue"] == queue) for r in rows.get()
        ):
            selected.set(None)
        if region.get():
            region.set({"kind": "clear", "reason": "scope"})

    @reactive.effect
    @reactive.event(input.observations_selection)
    def select_observation():
        event = input.observations_selection()
        if event["kind"] == "records":
            region.set(None)
            selected.set(event["keys"][0])
        elif event["kind"] == "range":
            selected.set(None)
            region.set(event)
        elif event["kind"] == "clear":
            selected.set(None)
            region.set(None)

    @render.text
    def status():
        data = rows.get()
        queue = input.queue()
        visible = [r for r in data if queue == "All" or r["queue"] == queue]
        missing = sum(r["response"] is None or r["resolution"] is None for r in visible)
        return (
            f"{len(visible):,} observations · {missing:,} missing measurements "
            f"· update {updates.get()}"
        )

    @render.text
    def detail():
        area = region.get()
        if area:
            if area["kind"] == "clear":
                change = "Queue changed" if area["reason"] == "scope" else "Data updated"
                return f"{change}; select a region again or inspect an observation."
            xmin, xmax = area["range"]["x"]
            ymin, ymax = area["range"]["y"]
            return (
                f"{area['count']:,} observations selected · response {xmin:.1f}–{xmax:.1f} minutes "
                f"· resolution {ymin:.1f}–{ymax:.1f} minutes. "
                "Region counts reset when data or queue changes."
            )
        key = selected.get()
        if not key:
            return "Choose an observation in the plot or select a record in View data."
        record = next((r for r in rows.get() if r["id"] == key), None)
        if record is None:
            return "The selected observation has left the rolling window. Choose another record."
        value = "Missing" if record["response"] is None else f"{record['response']:.1f} minutes"
        return f"{key} · {record['queue']} · {record['channel']} · response {value}"


app = App(app_ui, server, static_assets=HERE / "www")
