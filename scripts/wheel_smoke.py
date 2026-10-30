"""Executed outside the checkout, using an isolated wheel installation."""

import importlib.metadata
import importlib.util
import sys
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright
from shiny import App, ui
from starlette.applications import Starlette
from starlette.routing import Mount

import shiny_charts
from examples.adoption_app import app as adoption
from examples.finops_app import app as finops
from examples.operations_app import app as operations
from shiny_charts import chart, output_chart, render_chart

assert Path(shiny_charts.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert shiny_charts.__version__ == importlib.metadata.version("shiny-charts")
assert importlib.util.find_spec("plotly") is None
assert importlib.util.find_spec("shiny_plotly") is None


def server(input, output, session):
    @render_chart
    def points():
        return chart.bar(
            {"x": ["A", "B"], "y": [2, 5], "id": ["a", "b"]}, x="x", y="y", key="id"
        ).select()


widget = App(ui.page_fluid(output_chart("points", height="280px")), server)
app = Starlette(
    routes=[
        Mount("/widget", widget),
        Mount("/finops", finops),
        Mount("/operations", operations),
        Mount("/adoption", adoption),
    ]
)
runner = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
thread = threading.Thread(target=runner.run, daemon=True)
thread.start()
deadline = time.monotonic() + 15
while not runner.started:
    if time.monotonic() > deadline:
        raise RuntimeError("Smoke server did not start")
    time.sleep(0.02)
try:
    port = runner.servers[0].sockets[0].getsockname()[1]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/widget/")
            page.wait_for_function("shinyCharts?.get('points')?.spec.rows.length===2")
            expect(page.locator("#points .sc-plot svg")).to_be_visible()
            page.get_by_role("button", name="View data").click()
            page.get_by_role("dialog").get_by_role(
                "button", name="Select", exact=True
            ).first.click()
            page.wait_for_function("Shiny.shinyapp.$inputValues.points_selection?.keys[0]==='a'")
            page.goto(f"http://127.0.0.1:{port}/finops/")
            page.wait_for_function("shinyCharts?.get('latency')?.spec.rows.length===2400")
            assert page.locator(".js-plotly-plot").count() == 0
            assert page.get_by_role("navigation", name="Rendering engine comparison").count() == 0
            page.select_option("#n", "10000")
            page.wait_for_function(
                "shinyCharts.get('latency').spec.renderer==='canvas'&&shinyCharts.get('latency').spec.rows.length===10000"
            )
            page.goto(f"http://127.0.0.1:{port}/operations/")
            page.wait_for_function("shinyCharts?.get('observations')?.spec.rows.length===2400")
            page.click("#append")
            page.wait_for_function("shinyCharts.get('observations').stream.sequence===1")
            assert page.evaluate("shinyCharts.get('observations').spec.rows[0][3]") == "obs-0000100"
            assert (
                page.evaluate("Shiny.shinyapp.$inputValues.observations_update.status") == "applied"
            )
            page.click("#revise")
            page.wait_for_function("shinyCharts.get('observations').stream.sequence===2")
            page.goto(f"http://127.0.0.1:{port}/adoption/")
            page.wait_for_function("shinyCharts?.get('annotated')?.spec.rows.length===3")
            assert (
                page.evaluate("shinyCharts.get('slices').engine.getOption().series[0].type")
                == "pie"
            )
            assert (
                page.evaluate("shinyCharts.get('annotated').engine.getOption().series.at(-1).id")
                == "annotations"
            )
            page.evaluate(
                "shinyCharts.get('slices').engine.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:0})"
            )
            expect(page.locator("#slices")).to_contain_text("Failed: 15,000 (4.2%)")
            page.wait_for_function("shinyCharts?.get('divider')?.spec.rows.length===4")
            labels = page.evaluate("""() =>
              shinyCharts.get('shares').engine.getZr().storage.getDisplayList()
              .filter(el=>el.type==='tspan').map(el=>el.style.text)""")
            assert "100%" in labels
            labels = page.evaluate("""() =>
              shinyCharts.get('divider').engine.getZr().storage.getDisplayList()
              .filter(el=>el.type==='tspan').map(el=>el.style.text)""")
            assert "Actuals" in labels and "Forecast" in labels
            page.wait_for_function("shinyCharts?.get('forecast')?.spec.rows.length===12")
            assert page.evaluate(
                "shinyCharts.get('forecast').engine.getOption().series.find(s=>s.id==='line-overlay').type"
            ) == "line"
            expect(page.locator("#forecast")).to_contain_text("Actuals")
            expect(page.locator("#slices .sc-summary")).to_contain_text("4 displayed records")
            assert not errors, errors
        finally:
            browser.close()
finally:
    runner.should_exit = True
    thread.join(timeout=5)
