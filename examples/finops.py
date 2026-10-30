"""Shared FinOps UI and state; Plotly imports belong only to the comparison route."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from shiny import App, reactive, render, ui

from examples.data import WORKLOADS, color_for, requests, spend, trends
from shiny_charts import chart, output_chart, render_chart

if TYPE_CHECKING:
    import plotly.graph_objects as go

HERE = Path(__file__).parent


def make_app(engine: str = "charts", *, comparison: bool = True) -> App:
    native = engine == "charts"
    if not native:
        import plotly.graph_objects as go
        from shiny_plotly import output_plotly, render_plotly
    output = output_chart if native else output_plotly
    app_ui = ui.page_fluid(
        ui.tags.head(ui.tags.link(rel="stylesheet", href="styles.css")),
        ui.tags.a("Skip to charts", href="#charts", class_="skip-link"),
        ui.tags.header(
            ui.tags.div(
                ui.tags.strong("LLM Unit Economics"),
                ui.tags.span("Synthetic data · Python Shiny", class_="app-context"),
            ),
            ui.tags.nav(
                ui.tags.a("shiny-charts", href="/charts/", aria_current="page" if native else None),
                ui.tags.a(
                    "Styled Plotly", href="/plotly/", aria_current=None if native else "page"
                ),
                aria_label="Rendering engine comparison",
            )
            if comparison
            else None,
            ui.input_dark_mode(id="color_mode", mode="light"),
            class_="app-header",
        ),
        ui.tags.main(
            ui.tags.div(
                ui.tags.div(
                    ui.h1("Where does model spend go?"),
                    ui.p("Compare workloads, inspect latency, and trace individual requests."),
                ),
                ui.tags.div(
                    ui.tags.span("Chart engine"),
                    ui.tags.strong("shiny-charts" if native else "shiny-plotly"),
                    class_="engine-name",
                )
                if comparison
                else None,
                class_="page-heading",
            ),
            ui.tags.div(
                ui.input_select(
                    "workload",
                    "Workload",
                    {"All": "All workloads", **{v: v for v in WORKLOADS}},
                ),
                ui.input_select(
                    "period",
                    "Period",
                    {"30": "Last 30 days", "14": "Last 14 days", "7": "Last 7 days"},
                ),
                ui.input_select(
                    "n",
                    "Request count",
                    {"500": "500", "2400": "2,400", "10000": "10,000", "100000": "100,000"},
                    selected="2400",
                ),
                ui.input_action_button("refresh", "Simulate data update"),
                ui.input_action_button("clear", "Clear filters"),
                class_="controls",
            ),
            ui.tags.div(
                ui.output_text("status"),
                class_="selection-status",
                role="status",
                aria_live="polite",
            ),
            ui.tags.section(
                ui.tags.div(
                    ui.card(
                        ui.card_header(
                            ui.tags.div(
                                ui.h2("Cost per request"),
                                ui.p("Daily mean and 95% interval. Ctrl + scroll to zoom."),
                            )
                        ),
                        output("trend"),
                        full_screen=True,
                        class_="trend-card",
                    ),
                    ui.card(
                        ui.card_header(
                            ui.tags.div(
                                ui.h2("Spend by workload"),
                                ui.p("Click a workload to filter the dashboard."),
                            )
                        ),
                        output("workloads"),
                        full_screen=True,
                    ),
                    class_="charts-top",
                ),
                ui.tags.div(
                    ui.card(
                        ui.card_header(
                            ui.tags.div(
                                ui.h2("Latency and cost"),
                                ui.p(
                                    "Click a request to inspect it. "
                                    "Select a region to count matching records."
                                ),
                            )
                        ),
                        output("latency"),
                        full_screen=True,
                    ),
                    ui.card(
                        ui.card_header(
                            ui.tags.div(
                                ui.h2("Request cost distribution"),
                                ui.p("Click a bin to inspect its interval and request count."),
                            )
                        ),
                        output("distribution"),
                        full_screen=True,
                    ),
                    class_="charts-bottom",
                ),
                id="charts",
                aria_label="Cost and performance charts",
            ),
            ui.tags.section(
                ui.h2("Selection detail"), ui.output_text("detail"), class_="detail-panel"
            ),
            ui.tags.footer(
                "Synthetic data for evaluating chart behavior. "
                + (
                    "Both engines use the same data, filters, and workload colors."
                    if comparison
                    else "Chart selections preserve stable request identifiers."
                )
            ),
        ),
        title=f"FinOps · {'shiny-charts' if native else 'Styled Plotly'}",
        lang="en",
    )

    def server(input, output, session):
        selected = reactive.Value(None)

        @reactive.calc
        def all_data():
            return requests(int(input.n()), input.refresh())

        @reactive.calc
        def period_data():
            minimum = 30 - int(input.period())
            return [r for r in all_data() if (r["date"].day - 1) >= minimum]

        @reactive.calc
        def filtered():
            return [
                r
                for r in period_data()
                if input.workload() == "All" or r["workload"] == input.workload()
            ]

        @render.text
        def status():
            scope = "All workloads" if input.workload() == "All" else input.workload()
            return f"{scope} · {len(filtered()):,} requests · update {input.refresh()}"

        @reactive.effect
        @reactive.event(input.clear)
        def _clear():
            ui.update_select("workload", selected="All")
            selected.set(None)

        @reactive.effect
        def _select_workload():
            event = input.workloads_click()
            value = event.get("x") if native else event.get("points", [{}])[0].get("x")
            if value in WORKLOADS:
                ui.update_select("workload", selected=value)

        @reactive.effect
        def _latency_selection():
            event = input.latency_selection() if native else input.latency_selected()
            if native:
                selected.set(event)
            else:
                points = event.get("points", [])
                selected.set(
                    {
                        "kind": "records",
                        "keys": [p.get("customdata", [None])[0] for p in points],
                        "count": len(points),
                    }
                )

        if not native:

            @reactive.effect
            def _latency_click():
                event = input.latency_click()
                point = event.get("points", [{}])[0]
                selected.set({"kind": "records", "keys": [point.get("customdata", [None])[0]]})

        @reactive.effect
        def _distribution_click():
            event = input.distribution_click()
            if native:
                selected.set(event)
            else:
                point = event.get("points", [{}])[0]
                bounds = point.get("customdata")
                if bounds:
                    selected.set(
                        {
                            "kind": "bin",
                            "range": {
                                "min": bounds[0],
                                "max": bounds[1],
                                "upper_inclusive": bounds[2],
                            },
                            "count": point.get("y"),
                        }
                    )

        @render.text
        def detail():
            event = selected()
            if not event or event.get("kind") == "clear":
                return "Choose a request, draw a selection, or click a distribution bin."
            if event.get("kind") == "bin":
                bounds = event["range"]
                edge = "included" if bounds["upper_inclusive"] else "excluded"
                return (
                    f"Cost interval ${bounds['min']:.3f}–${bounds['max']:.3f}: "
                    f"{event['count']:,} requests. The upper edge is {edge}."
                )
            keys = event.get("keys", [])
            if len(keys) == 1:
                record = next((r for r in all_data() if r["id"] == keys[0]), None)
                if record:
                    outcome = "Successful" if record["success"] else "Failed"
                    return (
                        f"{record['id']} · {record['workload']} · {record['latency']:,.1f} ms · "
                        f"${record['cost']:.5f} · {outcome}"
                    )
            return (
                f"{event.get('count', len(keys)):,} requests selected. "
                "Stable record IDs are available to the server."
            )

        if native:

            @render_chart
            def trend():
                return (
                    chart.line(trends(filtered()), x="date", y="cost", color="workload")
                    .band(lower="low", upper="high")
                    .format(y="currency:USD:3")
                    .labels(
                        x="September 2026 (UTC)", y="Cost / request", title="Daily request cost"
                    )
                    .rule(y=0.05, label="Budget $0.050")
                )

            @render_chart
            def workloads():
                return (
                    chart.bar(spend(period_data()), x="workload", y="spend", color="workload")
                    .format(y="currency:USD")
                    .labels(x="Workload", y="Total spend")
                    .select()
                )

            @render_chart
            def latency():
                rows = filtered()
                return (
                    chart.scatter(
                        rows,
                        x="latency",
                        y="cost",
                        color="workload",
                        key="id",
                        tooltip=["success"],
                    )
                    .format(y="currency:USD:3")
                    .labels(x="Latency (ms)", y="Cost / request")
                    .select(brush=True)
                    .renderer("canvas" if int(input.n()) >= 10000 else "svg")
                )

            @render_chart
            def distribution():
                return (
                    chart.histogram(filtered(), x="cost", bins=18, range=(0, 0.09))
                    .format(x="currency:USD:3")
                    .labels(x="Cost / request", y="Requests")
                    .select()
                )

        else:

            @render_plotly(
                theme=(plotly_theme(False), plotly_theme(True)),
                config={"displaylogo": False},
                events="relayout",
            )
            def trend():
                rows = trends(filtered())
                fig = go.Figure()
                for name in WORKLOADS:
                    items = [r for r in rows if r["workload"] == name]
                    if not items:
                        continue
                    x = [r["date"] for r in items]
                    fig.add_trace(
                        go.Scatter(
                            x=x,
                            y=[r["low"] for r in items],
                            mode="lines",
                            line={"width": 0},
                            showlegend=False,
                            hoverinfo="skip",
                            legendgroup=name,
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=x,
                            y=[r["high"] for r in items],
                            mode="lines",
                            line={"width": 0},
                            fill="tonexty",
                            fillcolor=rgba(color_for(name), 0.12),
                            showlegend=False,
                            hoverinfo="skip",
                            legendgroup=name,
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=x,
                            y=[r["cost"] for r in items],
                            name=name,
                            mode="lines",
                            line={"color": color_for(name), "width": 2},
                            legendgroup=name,
                            hovertemplate=(
                                "%{x|%b %d}<br>%{fullData.name}: $%{y:.3f}<extra></extra>"
                            ),
                        )
                    )
                fig.add_hline(
                    y=0.05,
                    line_dash="dash",
                    line_color="#727e90",
                    annotation_text="Budget $0.050",
                    annotation_position="top right",
                )
                return finish(fig, "September 2026 (UTC)", "Cost / request", currency=True)

            @render_plotly(
                theme=(plotly_theme(False), plotly_theme(True)),
                config={"displaylogo": False},
                events="click",
            )
            def workloads():
                rows = spend(period_data())
                fig = go.Figure(
                    go.Bar(
                        x=[r["workload"] for r in rows],
                        y=[r["spend"] for r in rows],
                        marker_color=[color_for(r["workload"]) for r in rows],
                        hovertemplate="%{x}<br>$%{y:.2f}<extra></extra>",
                    )
                )
                return finish(fig, "Workload", "Total spend", currency=True, digits=2)

            @render_plotly(
                theme=(plotly_theme(False), plotly_theme(True)),
                config={"displaylogo": False},
                events=("click", "selected"),
            )
            def latency():
                fig = go.Figure()
                for name in WORKLOADS:
                    items = [r for r in filtered() if r["workload"] == name]
                    if not items:
                        continue
                    fig.add_trace(
                        go.Scatter(
                            x=[r["latency"] for r in items],
                            y=[r["cost"] for r in items],
                            customdata=[[r["id"], r["success"]] for r in items],
                            name=name,
                            mode="markers",
                            marker={"color": color_for(name), "size": 7},
                            hovertemplate=(
                                "%{x:.1f} ms<br>$%{y:.3f}<br>Success: %{customdata[1]}"
                                "<extra>%{fullData.name}</extra>"
                            ),
                        )
                    )
                return finish(fig, "Latency (ms)", "Cost / request", currency=True)

            @render_plotly(
                theme=(plotly_theme(False), plotly_theme(True)),
                config={"displaylogo": False},
                events="click",
            )
            def distribution():
                spec = chart.histogram(filtered(), x="cost", bins=18, range=(0, 0.09)).to_spec()
                fig = go.Figure(
                    go.Bar(
                        x=[r[0] for r in spec["rows"]],
                        y=[r[1] for r in spec["rows"]],
                        customdata=[
                            [a, b, i == len(spec["intervals"]) - 1]
                            for i, (a, b) in enumerate(spec["intervals"])
                        ],
                        width=0.0048,
                        marker_color=color_for("Requests"),
                    )
                )
                fig = finish(fig, "Cost / request", "Requests")
                fig.update_xaxes(tickprefix="$", tickformat=".3f")
                return fig

    return App(app_ui, server, static_assets=HERE / "www")


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def plotly_theme(dark: bool) -> dict:
    return {
        "layout": {
            "font": {
                "family": "Manrope, sans-serif",
                "size": 12,
                "color": "#e7edf5" if dark else "#243044",
            },
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "xaxis": {"showgrid": False, "zeroline": False, "showline": False},
            "yaxis": {"gridcolor": "#364254" if dark else "#e0e6ee", "zeroline": False},
            "hoverlabel": {
                "bgcolor": "#172231" if dark else "#ffffff",
                "font": {"family": "Manrope, sans-serif"},
            },
            "colorway": [color_for(name) for name in WORKLOADS],
        }
    }


def finish(fig: go.Figure, x: str, y: str, currency: bool = False, digits: int = 3) -> go.Figure:
    fig.update_layout(
        template=None,
        margin={"l": 58, "r": 20, "t": 28, "b": 70},
        xaxis_title=x,
        yaxis_title=y,
        uirevision="default",
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="closest",
        dragmode="zoom",
    )
    if currency:
        fig.update_yaxes(tickprefix="$", tickformat=f".{digits}f")
    return fig
