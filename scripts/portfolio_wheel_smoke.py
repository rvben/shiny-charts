"""Run the adoption outside the checkout, with the built wheel and optional SDK."""

import importlib.util
import threading
import time

import uvicorn
from playwright.sync_api import expect, sync_playwright

from examples.portfolio_app import app

assert importlib.util.find_spec("plotly") is None
runner = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
thread = threading.Thread(target=runner.run, daemon=True)
thread.start()
deadline = time.monotonic() + 15
while not runner.started:
    if time.monotonic() > deadline:
        raise RuntimeError("Portfolio wheel server did not start")
    time.sleep(0.02)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{runner.servers[0].sockets[0].getsockname()[1]}/")
            page.wait_for_function("shinyCharts?.get('trend')?.spec.rows.length===8")
            page.select_option("#region", "Americas")
            page.wait_for_function("()=>location.search.includes('Americas')")
            page.reload()
            expect(page.locator("#region")).to_have_value("Americas")
            page.wait_for_function(
                "shinyCharts?.get('trend')?.spec.rows[0][2]==='Americas · All products'"
            )
            page.get_by_role("button", name="View data").click()
            expect(page.get_by_role("dialog").locator("tbody tr").first).to_contain_text("42%")
            assert not errors, errors
        finally:
            browser.close()
finally:
    runner.should_exit = True
    thread.join(timeout=5)
