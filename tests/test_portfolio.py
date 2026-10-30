"""Exercise the existing app and its local migration through real Shiny sessions."""

import importlib.util
import json
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import uvicorn
from playwright.sync_api import expect
from starlette.applications import Starlette
from starlette.routing import Mount

pytest.importorskip("shinyhub_bookmarks")

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def portfolio_url():
    from examples.portfolio_app import app

    spec = importlib.util.spec_from_file_location(
        "portfolio_baseline", ROOT / "tests/fixtures/portfolio_original.py"
    )
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    host = Starlette(routes=[Mount("/original", original.app), Mount("/migrated", app)])
    runner = uvicorn.Server(uvicorn.Config(host, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not runner.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Portfolio server did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{runner.servers[0].sockets[0].getsockname()[1]}"
    runner.should_exit = True
    thread.join(timeout=5)


def ready(page, url):
    page.goto(url)
    if "/migrated/" in url:
        page.wait_for_function("window.shinyCharts?.get('trend')?.spec.rows.length>0")
    expect(page.locator(".metric-value")).to_have_count(3, timeout=30000)


def year(page, value):
    page.evaluate(
        "value=>{jQuery('#year').data('ionRangeSlider').update({from:value});jQuery('#year').trigger('change')}",
        value,
    )


def test_preserves_calculations_growth_and_engine_across_filters(page, browser, portfolio_url):
    baseline = browser.new_page()
    try:
        ready(baseline, portfolio_url + "/original/")
        ready(page, portfolio_url + "/migrated/")
        page.evaluate("window.retainedEngine=shinyCharts.get('trend').engine")
        for region, product, reporting_year, forecast in [
            ("Europe", "All products", 2026, True),
            ("Americas", "Planning", 2023, False),
            ("Asia Pacific", "Analytics", 2025, True),
        ]:
            for target in [baseline, page]:
                target.select_option("#region", region)
                target.select_option("#product", product)
                year(target, reporting_year)
                target.locator("#forecast").set_checked(forecast)
                expect(target.locator(".demo-result-head")).to_contain_text(f"{region} · {product}")
                target.wait_for_function(
                    "args=>Shiny.shinyapp.$inputValues.year===args[0]&&Shiny.shinyapp.$inputValues.forecast===args[1]",
                    arg=[reporting_year, forecast],
                )
            growth = [0.42, 0.57, 0.49, 0.70, 0.65, 0.81, 0.77, 0.92][: 8 if forecast else 6]
            expected = [
                [str(reporting_year - len(growth) + 1 + i), v, f"{region} · {product}"]
                for i, v in enumerate(growth)
            ]
            page.wait_for_function(
                "rows=>JSON.stringify(shinyCharts.get('trend').spec.rows)===JSON.stringify(rows)",
                arg=expected,
            )
            # Let Shiny's dashboard output complete too, using actual original values.
            scale = {"Europe": 1, "Americas": 1.22, "Asia Pacific": 1.36}[region] * {
                "All products": 1,
                "Planning": 0.82,
                "Analytics": 1.18,
            }[product]
            factor = 1 + (reporting_year - 2022) * 0.075
            metrics = [
                f"€{round(4250000 * scale * factor * (1.09 if forecast else 1)) / 1000000:.2f}M",
                f"{0.214 + (scale - 1) * 0.025:.1%}",
                f"{round(780 * scale * factor):,}",
            ]
            expect(page.locator(".metric-value")).to_have_text(metrics)
            expect(baseline.locator(".metric-value")).to_have_text(metrics)
            assert (
                baseline.locator(".trend-bar").evaluate_all(
                    "nodes=>nodes.map(n=>parseFloat(n.style.height)/100)"
                )
                == growth
            )
            assert page.evaluate(
                "shinyCharts.get('trend').engine===retainedEngine&&!retainedEngine.isDisposed()"
            )
    finally:
        baseline.close()


def test_bookmark_roundtrip_and_selection_excluded(page, portfolio_url):
    ready(page, portfolio_url + "/migrated/")
    page.select_option("#region", "Asia Pacific")
    page.select_option("#product", "Planning")
    year(page, 2024)
    page.locator("#forecast").uncheck()
    page.wait_for_function(
        "()=>location.search.includes('year=2024')&&location.search.includes('forecast=false')"
    )
    before = page.url
    page.locator("#trend").get_by_role("button", name="View data").click()
    page.get_by_role("dialog").get_by_role("button", name="Select", exact=True).first.click()
    expect(page.locator("#trend_detail")).to_contain_text(
        "2019 · trend index 42% · Asia Pacific · Planning"
    )
    page.wait_for_timeout(500)
    assert page.url == before
    fields = parse_qs(urlparse(before).query, keep_blank_values=True)
    assert set(fields) == {"_inputs_", "region", "product", "year", "forecast"}
    assert json.loads(fields["year"][0]) == 2024
    page.reload()
    expect(page.locator("#region")).to_have_value("Asia Pacific")
    expect(page.locator("#product")).to_have_value("Planning")
    expect(page.locator("#forecast")).not_to_be_checked()
    page.wait_for_function("window.shinyCharts?.get('trend')?.spec.rows.at(-1)[0]==='2024'")
    expect(page.locator("#trend_detail")).to_contain_text("Select a year")


def test_legacy_bookmark_restores_registered_aliases(page, portfolio_url):
    ready(page, portfolio_url + "/migrated/")
    page.get_by_role("link", name="Open a deliberately outdated bookmark").click()
    # Legacy values are recovered by the SDK after the new Shiny session connects.
    page.wait_for_function(
        "window.shinyCharts?.get('trend')?.spec.rows[0][2]==='Americas · Planning'", timeout=60000
    )
    expect(page.locator("#region")).to_have_value("Americas")
    expect(page.locator("#product")).to_have_value("Planning")
    page.wait_for_function(
        "window.shinyCharts?.get('trend')?.spec.rows[0][2]==='Americas · Planning'"
    )
    expect(page.locator(".metric-value").first).to_have_text("€6.02M")
    assert "Untrusted value" not in page.locator("body").inner_text()


def test_themed_table_percentages_raw_csv_and_stale_selection(page, portfolio_url):
    ready(page, portfolio_url + "/migrated/")
    page.locator("#trend").get_by_role("button", name="View data").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.locator("tbody tr").first).to_contain_text("42%")
    assert dialog.evaluate("n=>getComputedStyle(n).backgroundColor") == "rgb(14, 20, 38)"
    assert dialog.evaluate("n=>getComputedStyle(n).color") == "rgb(232, 238, 255)"
    close = dialog.get_by_role("button", name="Close", exact=True)
    close.hover()
    assert close.evaluate("n=>getComputedStyle(n).backgroundColor") == "rgb(27, 36, 68)"
    dialog.get_by_role("button", name="Select", exact=True).first.click()
    expect(page.locator("#trend_detail")).to_contain_text("2019 · trend index 42%")
    page.locator("#forecast").uncheck()
    expect(page.locator("#trend_detail")).to_contain_text("outside this view")
    with page.expect_download() as download:
        page.locator("#trend").get_by_role("button", name="Download CSV").click()
    text = Path(download.value.path()).read_text()
    assert '"0.42"' in text and "42%" not in text
    assert len(text.splitlines()) == 7


def test_mobile_host_layout_and_chart_accessibility(page, portfolio_url):
    page.set_viewport_size({"width": 390, "height": 844})
    ready(page, portfolio_url + "/migrated/")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.locator("#trend").get_by_role("button", name="View data").click()
    page.add_script_tag(path=str(ROOT / "node_modules/axe-core/axe.min.js"))
    result = page.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa']}})")
    assert not result["violations"], [(v["id"], len(v["nodes"])) for v in result["violations"]]
    assert page.get_by_role("dialog").bounding_box()["width"] <= 390
