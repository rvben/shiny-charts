"""Synthetic client-pilot regressions and optional beta APIs; no client data."""

import asyncio
import json
from datetime import date, timedelta

from shiny import App, reactive, render, ui

from shiny_charts import chart, output_chart, render_chart

DATES = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(30)]


def server(input, output, session):
    @render_chart
    def stale():
        start = input.shift() * 5
        rows = [
            {"d": d, "y": 1 + i % 3 + input.refresh(), "w": w, "k": f"{d}|{w}"}
            for i, d in enumerate(DATES[start : start + 5])
            for w in ("A", "B")
        ]
        return (
            chart.bar(rows, x="d", y="y", color="w", key="k", stacked=True)
            .select()
            .view(str(input.shift()), zoom=False)
            .renderer(input.pilot_renderer())
        )

    @render.code
    def pilot_state():
        state = {"revision": str(input.shift())}
        for suffix in ("selection", "legend", "view", "click"):
            name = f"stale_{suffix}"
            state[suffix] = input[name]() if name in input else None
        return json.dumps(state)

    @render_chart
    async def empty():
        mode = input.empty_mode()
        if mode == "none":
            return None
        if mode == "slow":
            await asyncio.sleep(0.8)
        if mode == "error":
            raise ValueError("Synthetic renderer failure; choose data to recover")
        rows = [] if mode == "zero" else [{"x": "a", "y": 1, "k": "internal-a"}]
        return chart.bar(rows, x="x", y="y", key="k").select()

    @render_chart
    def shares():
        rows = [
            {"x": d, "share": s, "who": w, "key": f"{d}|{w}"}
            for d in DATES[:5]
            for w, s in (("A", 0.4), ("B", 0.6))
        ]
        return (
            chart.bar(rows, x="x", y="share", color="who", key="key", stacked=True)
            .format(y="percent:0")
            .labels(title="Daily percentage shares")
            .renderer(input.pilot_renderer())
            .value_labels(totals=True)
            .legend(order=["B", "A"])
            .data_table(hide=["key"])
            .select()
        )

    @reactive.effect
    @reactive.event(input.append_shares, ignore_init=True)
    async def append_shares():
        day = (date(2026, 1, 5) + timedelta(days=input.append_shares())).isoformat()
        await shares.proxy().append(
            [
                {"x": day, "share": value, "who": group, "key": f"{day}|{group}"}
                for group, value in (("A", 0.4), ("B", 0.6))
            ]
        )

    @render_chart
    def dates():
        return chart.bar([{"x": d, "y": 1} for d in DATES], x="x", y="y")

    @render_chart
    def zeros():
        return chart.bar({"x": ["a", "b"], "y": [0, 0]}, x="x", y="y").format(y="number:0")

    @render_chart
    def groups():
        rows = [{"x": "a", "y": i + 1, "g": f"Group {i + 1}"} for i in range(8)]
        return (
            chart.bar(rows, x="x", y="y", color="g", stacked=True)
            .palette({f"Group {i + 1}": i + 1 for i in range(8)})
            .legend(order=[f"Group {i}" for i in range(8, 0, -1)])
            .domain(y=(0, 40))
            .value_labels(totals=True)
        )

    @render_chart
    def fixed_shares():
        return (
            chart.bar(
                [
                    {"x": str(i), "y": value, "g": group}
                    for i in range(8)
                    for group, value in (("A", 0.42), ("B", 0.58))
                ],
                x="x",
                y="y",
                color="g",
                stacked=True,
            )
            .format(y="percent:0")
            .domain(y=(0, 1))
            .value_labels(totals=True)
            .renderer(input.pilot_renderer())
        )

    @render_chart
    def small_segments():
        values = [705_062, 183_140, 1_620_405, 21_812]
        if input.zero_segments():
            values = [0] * 4
        return (
            chart.bar(
                [
                    {"x": x, "y": y, "g": g}
                    for x, y, g in zip(
                        ["left", "left", "right", "right"],
                        values,
                        ["big", "small"] * 2,
                        strict=True,
                    )
                ],
                x="x",
                y="y",
                color="g",
                stacked=True,
            )
            .format(y="number:0")
            .value_labels(totals=True)
            .renderer(input.pilot_renderer())
        )

    @render_chart
    def word_categories():
        return (
            chart.bar(
                {
                    "x": ["Made prediction", "Declined prediction", "Timed out", "Failed"],
                    "y": [5, 4, 3, 2],
                },
                x="x",
                y="y",
            )
            .ticks(x_rotation=45 if input.rotate_words() else 0)
            .renderer(input.pilot_renderer())
        )

    @render_chart
    def rotated():
        return (
            chart.bar([{"x": d, "y": i} for i, d in enumerate(DATES[:5])], x="x", y="y")
            .domain(y=(0, 10))
            .ticks(x_rotation=45)
            .value_labels()
        )


app = App(
    ui.page_fluid(
        ui.h2("shiny-charts beta pilot"),
        ui.p("Synthetic data only. Reproduces client feedback without client records."),
        ui.input_dark_mode(),
        ui.input_action_button("shift", "Shift data window"),
        ui.input_action_button("refresh", "Refresh at same revision"),
        ui.input_select("pilot_renderer", "Renderer", ["svg", "canvas"]),
        ui.input_action_button("append_shares", "Append share records"),
        ui.card(
            ui.card_header("Revision and server inputs"), output_chart("stale", height="340px")
        ),
        ui.output_code("pilot_state"),
        ui.input_select("empty_mode", "Empty state", ["none", "data", "zero", "slow", "error"]),
        ui.card(
            ui.card_header("Empty and loading states"),
            output_chart("empty", height="280px", empty_message="No observations available yet."),
        ),
        ui.div(
            ui.card(output_chart("shares", height="380px")),
            class_="pilot-width",
            style="width:min(100%,440px)",
        ),
        ui.div(output_chart("dates", height="300px"), style="width:min(100%,900px)"),
        output_chart("zeros", height="260px"),
        output_chart("groups", height="360px"),
        output_chart("rotated", height="340px"),
        ui.div(
            output_chart("fixed_shares", height="360px"),
            class_="feedback-shares",
            style="width:440px;max-width:100%",
        ),
        ui.input_checkbox("zero_segments", "All-zero segments"),
        ui.div(output_chart("small_segments", height="360px"), style="width:460px;max-width:100%"),
        ui.input_checkbox("rotate_words", "Rotate category words"),
        ui.div(output_chart("word_categories", height="360px"), style="width:460px;max-width:100%"),
    ),
    server,
)
