"""Three finance-card recipes, composed entirely with the public chart API.

Run: uv run uvicorn examples.gallery_app:app --host 127.0.0.1 --port 8060
All figures are deterministic synthetic data, denominated in USD.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from shiny import App, reactive, render, ui

from shiny_charts import chart, output_chart, render_chart

HERE = Path(__file__).parent
END = date(2026, 10, 28)
CATEGORIES = ("People", "Infrastructure", "Software", "Workspace")
DAILY_BUDGET = dict(zip(CATEGORIES, (480, 340, 190, 140), strict=True))


def ledger():
    """A continuous ledger makes the ending balance consistent across windows."""
    balance = 38_000
    rows = []
    for i in range(56):
        day = END - timedelta(days=55 - i)
        expenses = {
            "People": 420 + (i * 17 % 95),
            "Infrastructure": 225 + (i * 29 % 170),
            "Software": 195 + (i * 11 % 55),
            "Workspace": 85 + (i * 7 % 50),
        }
        income = 1450 + (i * 43 % 550) if day.weekday() < 5 else 550
        spent = sum(expenses.values())
        balance += income - spent
        rows.append({"day": day, "income": income, "spent": spent, "balance": balance, **expenses})
    return rows


LEDGER = ledger()


def spending_buckets(rows):
    """Daily bars for a week; seven-day totals for a four-week window."""
    size = 1 if len(rows) == 7 else 7
    result = []
    for start in range(0, len(rows), size):
        bucket = rows[start : start + size]
        first, last = bucket[0]["day"], bucket[-1]["day"]
        label = first.strftime("%a") if size == 1 else f"{first.day}–{last.day} Oct"
        result.append(
            {
                "period": label,
                "spent": sum(r["spent"] for r in bucket),
                "key": first.isoformat(),
                "dates": f"{first:%d %b %Y}" if size == 1 else f"{first:%d %b}–{last:%d %b %Y}",
            }
        )
    return result


def money(value):
    return f"${value:,.0f}"


def metric(value, note):
    return ui.div(ui.p(value, class_="finance-value"), ui.p(note, class_="finance-note"))


def heading(title, description):
    return ui.div(ui.h2(title), ui.p(description), class_="finance-card-heading")


app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.link(rel="stylesheet", href="styles.css"),
        ui.tags.link(rel="stylesheet", href="gallery.css"),
    ),
    ui.tags.a("Skip to charts", href="#finance-charts", class_="skip-link"),
    ui.tags.header(
        ui.div(
            ui.tags.strong("Finance cards"),
            ui.span("shiny-charts · interactive examples", class_="app-context"),
        ),
        ui.input_dark_mode(id="color_mode", mode="light"),
        class_="app-header",
    ),
    ui.tags.main(
        ui.div(
            ui.div(
                ui.h1("Cash flow, at a glance."),
                ui.p("Explore spending, follow your balance, and see where the budget goes."),
            ),
            ui.div(
                ui.span("Synthetic data · USD", class_="finance-disclosure"),
                ui.output_text("date_range"),
                class_="finance-scope",
            ),
            class_="page-heading",
        ),
        ui.div(
            ui.input_radio_buttons(
                "period",
                "Reporting period",
                {"7": "Last 7 days", "28": "Last 4 weeks"},
                selected="7",
                inline=True,
            ),
            ui.p("Select a spending bar to inspect its total. All cards follow the period."),
            class_="finance-controls",
        ),
        ui.tags.section(
            ui.tags.article(
                heading("Spending", "Outgoing payments across all four categories."),
                ui.output_ui("spend_metric"),
                output_chart("spending", height="280px"),
                ui.div(
                    ui.output_text("spending_detail"),
                    class_="finance-selection",
                    role="status",
                    aria_live="polite",
                ),
                class_="finance-card finance-spending",
                aria_label="Spending",
            ),
            ui.tags.article(
                heading("Cash balance", "End-of-day balance after incoming and outgoing payments."),
                ui.output_ui("balance_metric"),
                output_chart("balance", height="280px"),
                ui.output_ui("cash_summary"),
                class_="finance-card finance-balance",
                aria_label="Cash balance",
            ),
            ui.tags.article(
                ui.div(
                    heading(
                        "Budget by category", "Actual spending as a share of the period budget."
                    ),
                    ui.output_ui("budget_metric"),
                    class_="finance-budget-header",
                ),
                ui.div(
                    output_chart("budget", height="290px"),
                    ui.output_ui("budget_table"),
                    class_="finance-budget-body",
                ),
                class_="finance-card finance-budget",
                aria_label="Budget by category",
            ),
            id="finance-charts",
            class_="finance-grid",
            aria_label="Finance charts",
        ),
        ui.tags.footer(
            ui.p(
                "Illustrative business finances, ending 28 October 2026. "
                "Budgets are daily allowances multiplied by the selected number of days."
            ),
            ui.p(
                "Use View data for keyboard selection and exact values, or download a CSV "
                "from any chart. Change the theme to see the charts follow the page."
            ),
        ),
        class_="finance-main",
    ),
    title="Finance cards · shiny-charts",
    lang="en",
)


def server(input, output, session):
    selected = reactive.Value(None)

    @reactive.calc
    def window():
        return LEDGER[-int(input.period()) :]

    @reactive.calc
    def buckets():
        return spending_buckets(window())

    @reactive.calc
    def categories():
        rows = window()
        return [
            {
                "category": name,
                "spent": sum(r[name] for r in rows),
                "budget": DAILY_BUDGET[name] * len(rows),
                "share": sum(r[name] for r in rows) / (DAILY_BUDGET[name] * len(rows)),
            }
            for name in CATEGORIES
        ]

    @reactive.effect
    @reactive.event(input.period)
    def reset_selection():
        selected.set(None)

    @reactive.effect
    @reactive.event(input.spending_selection)
    def choose_period():
        event = input.spending_selection()
        if not event or event.get("revision") != input.period():
            return
        keys = event.get("keys", [])
        selected.set(keys[0] if event["kind"] == "records" and keys else None)

    @render.text
    def date_range():
        return f"{window()[0]['day']:%d %b} – {END:%d %b %Y}"

    @render.ui
    def spend_metric():
        n = int(input.period())
        total = sum(r["spent"] for r in window())
        previous = sum(r["spent"] for r in LEDGER[-2 * n : -n])
        change = (total / previous - 1) * 100
        direction = "more" if change >= 0 else "less"
        return metric(money(total), f"{abs(change):.1f}% {direction} than the preceding {n} days")

    @render.ui
    def balance_metric():
        net = sum(r["income"] - r["spent"] for r in window())
        direction = "up" if net >= 0 else "down"
        return metric(
            money(window()[-1]["balance"]),
            f"Closing balance · {direction} {money(abs(net))} this period",
        )

    @render.ui
    def cash_summary():
        rows = window()
        incoming, outgoing = sum(r["income"] for r in rows), sum(r["spent"] for r in rows)
        opening = rows[0]["balance"] - rows[0]["income"] + rows[0]["spent"]
        return ui.tags.dl(
            *[
                ui.div(ui.tags.dt(label), ui.tags.dd(money(value)))
                for label, value in (
                    ("Opening", opening),
                    ("Incoming", incoming),
                    ("Outgoing", outgoing),
                )
            ],
            class_="finance-cash-summary",
        )

    @render.ui
    def budget_metric():
        remaining = sum(r["budget"] - r["spent"] for r in categories())
        return ui.p(
            ui.strong(money(abs(remaining))),
            " remaining overall" if remaining >= 0 else " over budget overall",
            class_="finance-budget-total",
        )

    @render_chart
    def spending():
        data = buckets()
        plot = (
            chart.bar(data, x="period", y="spent", key="key", tooltip=["dates"])
            .format(y="currency:USD:0")
            .labels(x="Period", y="Spent (USD)")
            .palette({"Spent (USD)": 3})
            .hover(template="{dates}\n{spent:currency:USD:0}")
            .value_labels()
            .select()
            .view(input.period(), zoom=False)
        )
        chosen = next((r for r in data if r["key"] == selected.get()), None)
        if chosen:
            plot = plot.annotate(x=chosen["period"], y="top", text="Selected")
        return plot

    @render.text
    def spending_detail():
        chosen = next((r for r in buckets() if r["key"] == selected.get()), None)
        if chosen:
            share = chosen["spent"] / sum(r["spent"] for r in buckets())
            return f"{chosen['dates']} · {money(chosen['spent'])} · {share:.1%} of period spending"
        largest = max(buckets(), key=lambda r: r["spent"])
        return (
            f"Highest spending: {largest['period']} · {money(largest['spent'])}. "
            "Select a bar for detail."
        )

    @render_chart
    def balance():
        return (
            chart.line(window(), x="day", y="balance")
            .format(y="currency:USD:0")
            .labels(x="Date", y="Balance (USD)")
            .palette({"Balance (USD)": 1})
            .view(input.period(), zoom=False)
        )

    @render_chart
    def budget():
        return (
            chart.bar(
                categories(),
                x="category",
                y="share",
                orientation="horizontal",
                tooltip=["spent", "budget"],
            )
            .format(y="percent:0")
            .labels(x="Category", y="Budget used")
            .palette({"Budget used": 6})
            .value_labels()
            .rule(y=1, label="Budget")
            .hover(
                template="{category}\nSpent: {spent:currency:USD:0}\n"
                "Budget: {budget:currency:USD:0}\nUsed: {share:percent:1}"
            )
        )

    @render.ui
    def budget_table():
        def row(item):
            remaining = item["budget"] - item["spent"]
            return ui.tags.tr(
                ui.tags.th(item["category"], scope="row"),
                ui.tags.td(money(item["spent"])),
                ui.tags.td(money(item["budget"])),
                ui.tags.td(
                    f"{money(abs(remaining))} {'left' if remaining >= 0 else 'over'}",
                    class_="finance-over" if remaining < 0 else "",
                ),
            )

        return ui.tags.table(
            ui.tags.caption("Period totals · USD"),
            ui.tags.thead(
                ui.tags.tr(
                    *[
                        ui.tags.th(label, scope="col")
                        for label in ("Category", "Spent", "Budget", "Remaining")
                    ]
                )
            ),
            ui.tags.tbody(*[row(item) for item in categories()]),
            class_="finance-table",
        )


app = App(app_ui, server, static_assets=HERE / "www")
