"""Minimal Express integration: uv run shiny run examples/express_app.py."""

from shiny import reactive
from shiny.express import input, ui

from shiny_charts import chart, render_chart

ui.page_opts(title="Dashboard-native charts", fillable=True, lang="en")
ui.input_slider("scale", "Scale", min=1, max=5, value=1)
ui.input_dark_mode()
ui.input_action_button("append", "Append month")
ui.input_checkbox("hide_revenue", "Hide revenue", False)

with ui.card(full_screen=True):
    ui.card_header("Revenue")

    @render_chart(empty_message="Revenue data has not arrived.")
    def revenue():
        if input.hide_revenue():
            return None
        return chart.bar(
            {"month": ["January", "February", "March"], "revenue": [12 * input.scale(), 18, 24]},
            x="month",
            y="revenue",
        ).format(y="currency:EUR")


@reactive.effect
@reactive.event(input.append)
async def append_month():
    if not revenue.proxy().ready:
        return
    await revenue.proxy().append([{"month": f"Additional month {input.append()}", "revenue": 30}])
