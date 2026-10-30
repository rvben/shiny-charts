import asyncio
import os
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from shiny import App, module, reactive, ui
from shiny.express import wrap_express_app
from starlette.routing import Mount

from shiny_charts import chart, output_chart, render_chart


@module.ui
def module_ui():
    return ui.div(
        output_chart("plot", height="260px"),
        ui.input_action_button("append", "Append module record"),
    )


@module.server
def module_server(input, output, session):
    @render_chart
    def plot():
        return chart.scatter(
            [{"x": 1, "y": 2, "key": "module-record"}], x="x", y="y", key="key"
        ).select()

    @reactive.effect
    @reactive.event(input.append)
    async def append_record():
        n = input.append()
        await plot.proxy().append([{"x": n + 1, "y": n + 2, "key": f"module-record-{n}"}])


def fixture_app():
    def server(input, output, session):
        module_server("scope")

        @render_chart
        async def example():
            state = input.state()
            if state == "slow":
                await asyncio.sleep(0.6)
            if state == "missing-pairs":
                return chart.scatter({"x": [None, 1], "y": [2, None]}, x="x", y="y")
            if state == "none":
                return None
            if state == "error":
                raise ValueError("Try another example")
            rows = [
                {"x": 1, "y": -0.2, "lo": -1, "hi": 1, "key": "one"},
                {"x": 2, "y": 0.3, "lo": -0.5, "hi": 1.5, "key": "two"},
            ]
            if state == "empty":
                rows = []
            return (
                chart.line(rows, x="x", y="y", key="key")
                .band(lower="lo", upper="hi")
                .view(input.revision())
                .renderer(input.renderer())
                .select()
            )

        @reactive.effect
        @reactive.event(input.bad_update)
        async def bad_update():
            # Exercise the production custom-message handler, not a testing hook.
            proxy = example.proxy()
            mode = input.bad_update_mode()
            await session.send_custom_message(
                "shiny-charts:update",
                {
                    "id": "example",
                    "token": "superseded" if mode == "generation" else proxy._token,
                    "base": -1 if mode == "sequence" else proxy._sequence,
                    "sequence": proxy._sequence + 1,
                    "operation": "append",
                    "max_rows": None,
                    "data": {
                        "columns": ["x", "y", "key"],
                        "rows": [[3, "invalid" if mode == "numeric" else 1, "three"]],
                        "bounds": [[-1, 2]],
                    },
                },
            )

        @reactive.effect
        @reactive.event(input.append_example)
        async def append_example():
            await example.proxy().append([{"x": 3, "y": 1, "lo": 0, "hi": 2, "key": "three"}])

        @render_chart
        def scoped():
            return chart.bar({"x": ["A", "B"], "y": [2, 5]}, x="x", y="y")

        @render_chart
        def stacked():
            return chart.bar(
                [
                    {"x": "A", "y": 2, "g": "One"},
                    {"x": "B", "y": 3, "g": "One"},
                    {"x": "A", "y": 4, "g": "Two"},
                ],
                x="x",
                y="y",
                color="g",
                stacked=True,
            )

        @render_chart
        def area():
            return chart.area({"x": [1, 2, 3], "y": [1, None, 3]}, x="x", y="y")

    return App(
        ui.page_fluid(
            ui.input_select(
                "state", "State", ["data", "empty", "none", "error", "slow", "missing-pairs"]
            ),
            ui.input_select("revision", "Revision", ["one", "two"]),
            ui.input_select("bad_update_mode", "Bad update", ["generation", "sequence", "numeric"]),
            ui.input_action_button("bad_update", "Send rejected update"),
            ui.input_action_button("append_example", "Append band record"),
            ui.input_select("renderer", "Renderer", ["svg", "canvas"]),
            ui.card(output_chart("example"), full_screen=True, height="360px"),
            ui.div(
                output_chart("scoped", height="260px"),
                data_bs_theme="dark",
                style="--chart-fg: #fedcba; --chart-font: Georgia;",
            ),
            output_chart("stacked", height="260px"),
            output_chart("area", height="260px"),
            module_ui("scope"),
        ),
        server,
    )


@pytest.fixture(scope="session")
def server_url():
    from examples.adoption_app import app as adoption
    from examples.app import app
    from examples.finops import make_app
    from examples.operations_app import app as operations
    from examples.pilot_app import app as pilot

    app.routes.insert(0, Mount("/pilot", pilot))
    app.routes.insert(0, Mount("/adoption", adoption))
    app.routes.insert(0, Mount("/operations", operations))

    app.routes.insert(0, Mount("/native", make_app(comparison=False)))
    app.routes.insert(0, Mount("/fixture", fixture_app()))
    app.routes.insert(
        0,
        Mount("/express", wrap_express_app(Path(__file__).parents[1] / "examples/express_app.py")),
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Test server did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


# Close Playwright's synchronous event loop before async tests in other modules.
@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        engine = getattr(playwright, os.getenv("SHINY_CHARTS_BROWSER", "chromium"))
        browser = engine.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    page.close()
    assert not errors, errors
