"""Synthetic full-migration coverage and short-card regressions. No client data."""

from datetime import date, timedelta

from shiny import App, reactive, ui

from shiny_charts import chart, output_chart, render_chart

STATUSES = ["Made prediction", "Declined prediction", "Timed out", "Failed"]
COUNTS = [300000, 12000, 30000, 15000]


def server(input, output, session):
    @render_chart
    def rotation():
        return (
            chart.bar({"status": STATUSES, "n": COUNTS}, x="status", y="n")
            .format(y="number:0")
            .ticks(x_rotation=float(input.angle()))
            .renderer(input.engine())
        )

    @render_chart
    def slices():
        rows = [
            {
                "status": name,
                "n": 0 if input.zero_pie() else value,
                "share": value / sum(COUNTS),
                "key": f"slice-{i}",
            }
            for i, (name, value) in enumerate(zip(STATUSES, COUNTS, strict=True))
        ]
        rows.append({"status": "Missing value", "n": None, "share": None, "key": "missing"})
        return (
            chart.pie(rows, names="status", values="n", key="key", tooltip=["share"])
            .format(y="number:0")
            .palette({name: i + 1 for i, name in enumerate(STATUSES)})
            .hover(template="{status}: {n:number:0} ({share:percent:1})")
            .legend(order=list(reversed(STATUSES)), layout="scroll", placement="bottom")
            .labels(title="Prediction outcomes")
            .select()
            .view(input.revision(), zoom=False)
            .renderer(input.engine())
        )

    @reactive.effect
    @reactive.event(input.replace_pie, ignore_init=True)
    async def replace_pie():
        await slices.proxy().replace_data(
            [{"status": "Updated", "n": 7, "share": 1.0, "key": "updated"}]
        )

    @render_chart
    def annotated():
        rows = [
            {"day": date(2026, 1, i), "n": n, "share": 0.1 * i, "key": f"day-{i}"}
            for i, n in enumerate([5, 12, 8], 1)
        ]
        return (
            chart.line(rows, x="day", y="n", key="key", tooltip=["share"])
            .hover(template="{n:number:0} observations ({share:percent:1})")
            .rule(x=date(2026, 1, 2), label="Cutoff")
            .rule(y=10, label="Target")
            .annotate(x=date(2026, 1, 2), y=12, text="Peak <literal>", position="right")
            .domain(y=(0, 12))
            .select()
            .view(input.revision(), zoom=False)
            .renderer(input.engine())
        )

    @render_chart
    def horizontal():
        return (
            chart.bar(
                {"status": STATUSES, "n": COUNTS}, x="status", y="n", orientation="horizontal"
            )
            .rule(x="Timed out", label="Status")
            .rule(y=150000, label="Threshold")
            .annotate(x="Made prediction", y=150000, text="Halfway", position="inside")
            .renderer(input.engine())
        )

    @render_chart
    def shares():
        return (
            chart.bar(
                [
                    {"day": f"2026-01-0{d}", "who": w, "share": v}
                    for d in range(1, 9)
                    for w, v in (("A", 0.58), ("B", 0.42))
                ],
                x="day",
                y="share",
                color="who",
                stacked=True,
            )
            .format(y="percent:0")
            .renderer(input.engine())
        )

    @render_chart
    def dates_bar():
        return chart.bar(
            {
                "day": [date(2026, 1, 1) + timedelta(days=i) for i in range(14)],
                "y": list(range(14)),
            },
            x="day",
            y="y",
        ).renderer(input.engine())

    @render_chart
    def divider():
        return (
            chart.bar({"month": ["Feb", "Mar", "Apr", "May"], "n": [5, 12, 9, 8]}, x="month", y="n")
            .domain(y=(0, 12))
            .rule(x_between=("Mar", "Apr"), label="")
            .annotate(x="Mar", y="top", text="Actuals")
            .annotate(x="Apr", y="top", text="Forecast")
            .annotate(x="Mar", y=12, text="Peak", position="right")
            .renderer(input.engine())
        )

    @render_chart
    def forecast():
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        if input.forecast_filter():
            months.remove("Mar")
        rows = [
            {"m": m, "y": n + i, "g": g, "key": f"{m}|{g}"}
            for i, m in enumerate(months)
            for g, n in (("A", 4), ("B", 6))
        ]
        totals = [
            {"m": m, "total": n}
            for m, n in [
                ("Jun", 21),
                ("Feb", 13),
                ("Jan", 12),
                ("Mar", 16),
                ("Apr", 17),
                ("May", None),
            ]
        ]
        return (
            chart.bar(rows, x="m", y="y", color="g", key="key", stacked=True)
            .line(totals, y="total", label="Total forecast")
            .format(y="number:2")
            .palette({"A": 1, "B": 2, "Total forecast": 3})
            .legend(order=["Total forecast", "A", "B"], layout="scroll", placement="bottom")
            .rule(x_between=("Mar", "Apr"), label="Forecast starts")
            .annotate(x="Mar", y="top", text="Actuals", position="left")
            .annotate(x="Apr", y="top", text="Forecast (plan)", position="right")
            .labels(title="Values and forecast")
            .view(input.revision(), zoom=False)
            .select()
            .renderer(input.engine())
        )

    @reactive.effect
    @reactive.event(input.replace_forecast, ignore_init=True)
    async def replace_forecast():
        await forecast.proxy().replace_data(
            [
                {"m": m, "y": 3, "g": g, "key": f"updated-{m}|{g}"}
                for m in ["Jan", "Apr", "Jun"]
                for g in ("A", "B")
            ]
        )

    @render_chart
    def compact():
        return (
            chart.bar(
                [{"x": "a", "y": 1600000, "g": name} for name in STATUSES],
                x="x",
                y="y",
                color="g",
                stacked=True,
            )
            .format(y="number:0")
            .labels(y="Observations")
            .legend(layout="scroll")
            .select()
            .renderer(input.engine())
        )


app = App(
    ui.page_fluid(
        ui.h2("Adoption API pilot"),
        ui.p("Synthetic data only."),
        ui.input_dark_mode(),
        ui.input_select("engine", "Renderer", ["svg", "canvas"]),
        ui.input_select("angle", "Rotation", {"45": "45°", "-45": "−45°", "90": "90°"}),
        ui.input_action_button("revision", "Change revision"),
        ui.input_checkbox("zero_pie", "Zero pie values"),
        ui.input_action_button("replace_pie", "Replace pie data"),
        ui.div(output_chart("rotation"), style="width:min(100%,460px)", class_="rotation-width"),
        ui.div(output_chart("slices", height="360px"), style="width:min(100%,360px)"),
        ui.div(output_chart("annotated", height="340px"), style="width:min(100%,460px)"),
        ui.div(output_chart("horizontal", height="360px"), style="width:min(100%,460px)"),
        ui.div(output_chart("compact", height="340px"), style="width:min(100%,320px)"),
        ui.div(output_chart("shares"), style="width:min(100%,440px)", class_="shares-width"),
        ui.div(output_chart("dates_bar"), style="width:min(100%,300px)"),
        ui.div(output_chart("divider"), style="width:min(100%,460px)"),
        ui.input_checkbox("forecast_filter", "Filter out March"),
        ui.input_action_button("replace_forecast", "Replace forecast bars"),
        ui.div(output_chart("forecast"), style="width:min(100%,300px)", class_="forecast-width"),
        title="Adoption API pilot",
        lang="en",
    ),
    server,
)
