from pathlib import Path

from playwright.sync_api import expect


def ready(page, url):
    page.goto(url)
    page.wait_for_function("window.shinyCharts?.get('latency')?.spec.rows.length > 0")


def chart_click(page, id, series=0, item=0, bar=False):
    page.locator(f"#{id} .sc-plot").scroll_into_view_if_needed()
    point = page.evaluate(
        """([id, series, item, bar]) => {
      const s = shinyCharts.get(id), datum = s.engine.getOption().series[series].data[item];
      const layout = bar ? s.engine.getModel().getSeriesByIndex(series).getData().getItemLayout(item) : null;
      const p = bar ? [layout.x + layout.width/2, layout.y + layout.height/2] : s.engine.convertToPixel({ gridIndex: 0 }, datum.value);
      const box = s.plot.getBoundingClientRect(); return [box.x + p[0], box.y + p[1]];
    }""",
        [id, series, item, bar],
    )
    page.mouse.click(*point)


def test_linked_workload_filter_and_real_record_click(page, server_url):
    ready(page, server_url + "/charts/")
    chart_click(page, "workloads", bar=True)
    expect(page.locator("#workload")).to_have_value("Customer experience")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length === 800")
    chart_click(page, "latency", item=0)
    expect(page.locator("#detail")).to_contain_text("req-")
    expect(page.locator("#detail")).to_contain_text("Customer experience")


def test_histogram_click_reports_range_count_not_keys(page, server_url):
    ready(page, server_url + "/charts/")
    chart_click(page, "distribution", item=7, bar=True)
    expect(page.locator("#detail")).to_contain_text("Cost interval")
    expect(page.locator("#detail")).to_contain_text("upper edge")


def test_theme_inherits_host_tokens_and_changes_without_server_render(page, server_url):
    ready(page, server_url + "/charts/")
    before = page.evaluate("shinyCharts.get('latency').spec.rows")
    page.evaluate("document.documentElement.setAttribute('data-bs-theme', 'dark')")
    page.wait_for_function("document.getElementById('latency').dataset.themeColor === '#e7edf5'")
    assert page.evaluate("shinyCharts.get('latency').spec.rows") == before
    page.evaluate("document.querySelector('main').style.setProperty('--chart-font', 'Georgia')")
    page.wait_for_function("document.getElementById('latency').dataset.font === 'Georgia'")


def test_zoom_and_legend_survive_updates_and_workload_filter(page, server_url):
    ready(page, server_url + "/charts/")
    page.evaluate(
        "shinyCharts.get('latency').engine.dispatchAction({type:'dataZoom', startValue:400, endValue:800})"
    )
    view = page.evaluate("shinyCharts.get('latency').zoom")
    page.locator("#latency .sc-legend-item").filter(has_text="Knowledge platform").click()
    page.locator("#refresh").click()
    expect(page.locator("#status")).to_contain_text("update 1")
    page.wait_for_function("shinyCharts.get('latency').spec.rows[0][1] > 0")
    assert page.evaluate("shinyCharts.get('latency').zoom") == view
    assert page.evaluate("[...shinyCharts.get('latency').hidden]") == ["Knowledge platform"]
    page.select_option("#workload", "Engineering copilot")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length === 800")
    assert page.evaluate("shinyCharts.get('latency').zoom") == view
    page.locator("#latency").get_by_role("button", name="Reset view").click()
    assert page.evaluate("shinyCharts.get('latency').zoom") is None


def test_rectangle_brush_returns_exact_keys_and_count(page, server_url):
    ready(page, server_url + "/charts/")
    page.locator("#latency").get_by_role("button", name="Select region").click()
    coords = page.evaluate("""() => {
      const s=shinyCharts.get('latency'), box=s.plot.getBoundingClientRect();
      return [[350,.027],[650,.042]].map(v => { const p=s.engine.convertToPixel({gridIndex:0},v); return [box.x+p[0],box.y+p[1]]; });
    }""")
    page.mouse.move(*coords[0])
    page.mouse.down()
    page.mouse.move(*coords[1], steps=12)
    page.mouse.up()
    expect(page.locator("#detail")).to_contain_text("requests selected")
    event = page.evaluate("Shiny.shinyapp.$inputValues.latency_selection")
    assert event["kind"] == "range"
    assert event["count"] > 0
    assert len(event["keys"]) == event["count"]
    expected = page.evaluate(
        """event => {
      const s=shinyCharts.get('latency'), [xmin,xmax]=event.range.x, [ymin,ymax]=event.range.y;
      return s.spec.rows.filter(r=>r[0]>=xmin && r[0]<=xmax && r[1]>=ymin && r[1]<=ymax).map(r=>r[3]);
    }""",
        event,
    )
    assert event["keys"] == expected


def test_keyboard_data_table_and_csv_download(page, server_url):
    ready(page, server_url + "/charts/")
    page.locator("#latency").get_by_role("button", name="View data").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.get_by_role("dialog")).to_contain_text("Showing 250 of 2400")
    page.get_by_role("dialog").get_by_role("button", name="Select", exact=True).first.press("Enter")
    expect(page.locator("#detail")).to_contain_text("req-000000")
    expect(page.locator("#latency").get_by_role("button", name="View data")).to_be_focused()
    with page.expect_download() as info:
        page.locator("#latency").get_by_role("button", name="Download CSV").click()
    text = Path(info.value.path()).read_text()
    assert len(text.splitlines()) == 2401
    assert '"req-000000"' in text


def test_svg_image_export_and_fullscreen_resizes(page, server_url):
    ready(page, server_url + "/charts/")
    with page.expect_download() as info:
        page.locator("#trend").get_by_role("button", name="Save image").click()
    assert info.value.suggested_filename == "trend.svg"
    assert "<svg" in Path(info.value.path()).read_text()
    before = page.locator("#trend .sc-plot").bounding_box()
    page.locator(".trend-card .bslib-full-screen-enter").click()
    page.wait_for_function("shinyCharts.get('trend').plot.clientWidth > 900")
    assert page.locator("#trend .sc-plot").bounding_box()["width"] > before["width"]


def test_fixture_scoped_theme_canvas_errors_none_empty_and_revision(page, server_url):
    page.goto(server_url + "/fixture/")
    page.wait_for_function("shinyCharts?.get('example')?.spec.rows.length === 2")
    expect(page.locator("#scoped")).to_have_attribute("data-theme-color", "#fedcba")
    expect(page.locator("#scoped")).to_have_attribute("data-font", "Georgia")
    page.evaluate(
        "shinyCharts.get('example').engine.dispatchAction({type:'dataZoom',start:20,end:80})"
    )
    page.select_option("#revision", "two")
    page.wait_for_function("shinyCharts.get('example').spec.view.revision === 'two'")
    assert page.evaluate("shinyCharts.get('example').zoom") is None
    page.select_option("#renderer", "canvas")
    expect(page.locator("#example canvas")).to_be_visible()
    page.select_option("#state", "empty")
    expect(page.locator("#example .sc-empty")).to_be_visible()
    page.select_option("#state", "none")
    page.wait_for_function("!shinyCharts.get('example')")
    expect(page.locator("#example .sc-empty")).to_be_visible()
    page.select_option("#state", "error")
    expect(page.locator("#example")).to_contain_text("Try another example")
    page.select_option("#state", "data")
    expect(page.locator("#example canvas")).to_be_visible()


def test_module_ids_and_disposal(page, server_url):
    page.goto(server_url + "/fixture/")
    page.wait_for_function("shinyCharts?.get('scope-plot')?.spec.rows.length === 1")
    chart_click(page, "scope-plot")
    page.wait_for_function(
        "Shiny.shinyapp.$inputValues['scope-plot_click']?.keys[0] === 'module-record'"
    )
    page.evaluate(
        "window.removedChart=shinyCharts.get('scope-plot').engine; document.getElementById('scope-plot').remove()"
    )
    page.wait_for_function("!shinyCharts.get('scope-plot') && removedChart.isDisposed()")


def test_mobile_layout_and_accessibility(page, server_url):
    page.set_viewport_size({"width": 390, "height": 844})
    ready(page, server_url + "/charts/")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    assert page.locator("#latency .sc-plot").bounding_box()["width"] <= 390
    axe = Path(__file__).parents[1] / "node_modules/axe-core/axe.min.js"
    page.add_script_tag(path=str(axe))
    result = page.evaluate("axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa']}})")
    assert not result["violations"], [(v["id"], len(v["nodes"])) for v in result["violations"]]


def test_styled_plotly_comparison_runs_and_links_filters(page, server_url):
    page.goto(server_url + "/plotly/")
    page.wait_for_function("document.querySelector('#latency .js-plotly-plot')?._fullLayout")
    assert not page.locator(".shiny-output-error").count()
    page.select_option("#workload", "Customer experience")
    expect(page.locator("#status")).to_contain_text("800 requests")
    page.wait_for_function("document.querySelector('#latency .js-plotly-plot').data.length === 1")
    assert (
        page.evaluate("document.querySelector('#latency .js-plotly-plot').data[0].customdata[0][0]")
        == "req-000000"
    )


def test_express_auto_output_and_reactive_updates(page, server_url):
    page.goto(server_url + "/express/")
    page.wait_for_function("shinyCharts?.get('revenue')?.spec.rows.length === 3")
    track = page.locator(".irs-line").bounding_box()
    page.mouse.click(track["x"] + track["width"] / 2, track["y"] + track["height"] / 2)
    page.wait_for_function("shinyCharts.get('revenue').spec.rows[0][1] === 36")


def test_native_finops_100k_canvas_and_bounded_actual_brush(page, server_url):
    ready(page, server_url + "/native/")
    assert not page.get_by_role("navigation", name="Rendering engine comparison").count()
    assert not page.locator(".js-plotly-plot").count()
    page.select_option("#n", "100000")
    page.wait_for_function(
        "shinyCharts.get('latency').spec.rows.length===100000 && !shinyCharts.get('latency').engine._scheduler.unfinished"
    )
    expect(page.locator("#latency canvas").first).to_be_visible()
    painted = page.evaluate(
        """() => {let count=0;shinyCharts.get('latency').engine.getModel().eachSeries(s=>s.getData().eachItemGraphicEl(()=>count++));return count;}"""
    )
    assert painted == 100000
    page.evaluate(
        "shinyCharts.get('latency').engine.dispatchAction({type:'dataZoom',startValue:400,endValue:800})"
    )
    view = page.evaluate("shinyCharts.get('latency').zoom")
    page.locator("#latency .sc-legend-item").filter(has_text="Knowledge platform").click()
    page.select_option("#workload", "Customer experience")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length===33334")
    assert page.evaluate("shinyCharts.get('latency').zoom") == view
    assert page.evaluate("[...shinyCharts.get('latency').hidden]") == ["Knowledge platform"]
    assert page.evaluate("shinyCharts.get('latency').spec.renderer") == "canvas"
    page.locator("#latency .sc-plot").scroll_into_view_if_needed()
    page.locator("#latency").get_by_role("button", name="Select region").click()
    corners = page.evaluate("""() => { const s=shinyCharts.get('latency'), box=s.plot.getBoundingClientRect();
      const r=s.engine.getModel().getComponent('grid').coordinateSystem.getRect();
      return [[box.x+r.x+1,box.y+r.y+r.height-1],[box.x+r.x+r.width-1,box.y+r.y+1]]; }""")
    page.mouse.move(*corners[0])
    page.mouse.down()
    page.mouse.move(*corners[1], steps=12)
    page.mouse.up()
    page.wait_for_function("Shiny.shinyapp.$inputValues.latency_selection?.kind==='range'")
    event = page.evaluate("Shiny.shinyapp.$inputValues.latency_selection")
    assert event["count"] > 10000
    assert len(event["keys"]) == 10000
    assert event["truncated"] is True
    page.locator("#refresh").click()
    expect(page.locator("#status")).to_contain_text("update 1", timeout=30000)
    page.locator("#clear").click()
    page.select_option("#n", "500")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length===500")
    expect(page.locator("#latency .sc-plot svg")).to_be_visible()


def test_native_canvas_view_survives_filters_below_renderer_threshold(page, server_url):
    ready(page, server_url + "/native/")
    page.select_option("#n", "10000")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length===10000")
    page.evaluate(
        "shinyCharts.get('latency').engine.dispatchAction({type:'dataZoom',startValue:400,endValue:800})"
    )
    view = page.evaluate("shinyCharts.get('latency').zoom")
    page.locator("#latency .sc-legend-item").filter(has_text="Knowledge platform").click()
    page.select_option("#workload", "Customer experience")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length===3334")
    assert page.evaluate("shinyCharts.get('latency').spec.renderer") == "canvas"
    assert page.evaluate("shinyCharts.get('latency').zoom") == view
    assert page.evaluate("[...shinyCharts.get('latency').hidden]") == ["Knowledge platform"]
    page.select_option("#period", "7")
    page.wait_for_function("shinyCharts.get('latency').spec.rows.length<1000")
    assert page.evaluate("shinyCharts.get('latency').spec.renderer") == "canvas"
    assert page.evaluate("shinyCharts.get('latency').zoom") == view


def operations_ready(page, server_url):
    page.goto(server_url + "/operations/")
    page.wait_for_function("window.shinyCharts?.get('observations')?.spec.rows.length===2400")


def test_operations_proxy_preserves_view_engine_and_selected_identity(page, server_url):
    operations_ready(page, server_url)
    page.locator("#observations").get_by_role("button", name="View data").click()
    page.get_by_role("dialog").get_by_role("button", name="Select", exact=True).nth(200).press(
        "Enter"
    )
    expect(page.locator("#detail")).to_contain_text("obs-0000200")
    page.evaluate(
        "window.retainedEngine=shinyCharts.get('observations').engine; shinyCharts.get('observations').engine.dispatchAction({type:'dataZoom', startValue:10,endValue:30})"
    )
    view = page.evaluate("shinyCharts.get('observations').zoom")
    page.locator("#observations .sc-legend-item").filter(has_text="Email").click()
    initial = page.evaluate("shinyCharts.get('observations').stream.token")
    page.click("#append")
    page.wait_for_function("shinyCharts.get('observations').stream.sequence===1")
    expect(page.locator("#status")).to_contain_text("update 1")
    assert page.evaluate("shinyCharts.get('observations').engine===retainedEngine")
    assert page.evaluate("shinyCharts.get('observations').stream.token") == initial
    assert page.evaluate("shinyCharts.get('observations').zoom") == view
    assert page.evaluate("[...shinyCharts.get('observations').hidden]") == ["Email"]
    expect(page.locator("#detail")).to_contain_text("obs-0000200")
    assert page.evaluate("shinyCharts.get('observations').spec.rows[0][3]") == "obs-0000100"
    assert page.evaluate("shinyCharts.get('observations').spec.rows.at(-1)[3]") == "obs-0002499"
    assert page.evaluate("Shiny.shinyapp.$inputValues.observations_update.status") == "applied"
    page.click("#revise")
    page.wait_for_function("shinyCharts.get('observations').stream.sequence===2")
    assert page.evaluate("shinyCharts.get('observations').zoom") == view
    expect(page.locator("#detail")).to_contain_text("obs-0000200")
    page.select_option("#queue", "API integrations and developer support")
    page.wait_for_function(
        "shinyCharts.get('observations').stream.sequence===0 && shinyCharts.get('observations').spec.rows.length<500"
    )
    assert page.evaluate("shinyCharts.get('observations').zoom") == view
    page.click("#append")
    page.wait_for_function("shinyCharts.get('observations').stream.sequence===1")
    expect(page.locator("#status")).to_contain_text("update 3")
    assert not page.locator(".shiny-output-error").count()


def test_operations_missing_empty_recovery_live_updates_and_current_exports(page, server_url):
    operations_ready(page, server_url)
    assert page.evaluate("shinyCharts.get('observations').spec.rows.some(r=>r[0]===null)")
    page.select_option("#quality", "empty")
    page.wait_for_function("shinyCharts.get('observations').spec.rows.length===0")
    expect(page.locator("#observations .sc-empty")).to_be_visible()
    page.click("#append")
    page.wait_for_function("shinyCharts.get('observations').spec.rows.length===100")
    expect(page.locator("#observations .sc-empty")).to_be_hidden()
    assert page.evaluate("shinyCharts.get('response').spec.x_type") == "time"
    with page.expect_download() as info:
        page.locator("#observations").get_by_role("button", name="Download CSV").click()
    text = Path(info.value.path()).read_text()
    assert len(text.splitlines()) == 101 and "obs-0002400" in text and "obs-0002499" in text
    page.locator("#live").check()
    page.wait_for_function("shinyCharts.get('observations').stream.sequence>=2")
    page.locator("#live").uncheck()
    page.locator("#observations").get_by_role("button", name="View data").click()
    expect(page.get_by_role("dialog")).to_contain_text("Service observations")
    page.get_by_role("dialog").get_by_role("button", name="Close", exact=True).press("Escape")
    expect(page.locator("#observations").get_by_role("button", name="View data")).to_be_focused()


def test_operations_mobile_horizontal_bars_full_labels_and_accessibility(page, server_url):
    page.set_viewport_size({"width": 390, "height": 844})
    operations_ready(page, server_url)
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    assert page.evaluate("shinyCharts.get('queues').engine.getOption().yAxis[0].type") == "category"
    assert page.evaluate("shinyCharts.get('queues').engine.getOption().xAxis[0].type") == "value"
    page.locator("#queues").get_by_role("button", name="View data").click()
    expect(page.get_by_role("dialog")).to_contain_text(
        "Enterprise onboarding and access provisioning"
    )
    page.get_by_role("dialog").get_by_role("button", name="Close", exact=True).click()
    axe = Path(__file__).parents[1] / "node_modules/axe-core/axe.min.js"
    page.add_script_tag(path=str(axe))
    result = page.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa']}})")
    assert not result["violations"], [(v["id"], len(v["nodes"])) for v in result["violations"]]


def test_proxy_resolves_module_namespace_and_sessions_are_isolated(page, browser, server_url):
    page.goto(server_url + "/fixture/")
    page.wait_for_function("shinyCharts?.get('scope-plot')?.spec.rows.length===1")
    other = browser.new_page()
    try:
        other.goto(server_url + "/fixture/")
        other.wait_for_function("shinyCharts?.get('scope-plot')?.spec.rows.length===1")
        page.click("#scope-append")
        page.wait_for_function("shinyCharts.get('scope-plot').spec.rows.length===2")
        assert page.evaluate("Shiny.shinyapp.$inputValues['scope-plot_update'].status") == "applied"
        assert other.evaluate("shinyCharts.get('scope-plot').spec.rows.length") == 1
        chart_click(page, "scope-plot", item=1)
        page.wait_for_function(
            "Shiny.shinyapp.$inputValues['scope-plot_selection']?.keys[0]==='module-record-1'"
        )
    finally:
        other.close()


def test_browser_rejects_stale_and_malformed_updates_and_closes_stale_table(page, server_url):
    page.goto(server_url + "/fixture/")
    page.wait_for_function("shinyCharts?.get('example')?.spec.rows.length===2")
    original = page.evaluate("shinyCharts.get('example').spec.rows")
    for mode in ("generation", "sequence", "numeric"):
        page.select_option("#bad_update_mode", mode)
        page.click("#bad_update")
        page.wait_for_function(
            "reason=>Shiny.shinyapp.$inputValues.example_update?.reason===reason", arg=mode
        )
        assert page.evaluate("shinyCharts.get('example').spec.rows") == original
        assert page.evaluate("shinyCharts.get('example').stream.sequence") == 0
    page.locator("#example").get_by_role("button", name="View data").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    # Trigger a genuine server-side append while a keyboard data snapshot is open.
    page.evaluate("Shiny.setInputValue('append_example',1,{priority:'event'})")
    page.wait_for_function("shinyCharts.get('example').spec.rows.length===3")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.locator("#example").get_by_role("button", name="View data")).to_be_focused()
    assert page.evaluate("shinyCharts.get('example').spec.band.bounds.at(-1)") == [0, 2]


def test_express_proxy_append_and_full_render_reset(page, server_url):
    page.goto(server_url + "/express/")
    page.wait_for_function("shinyCharts?.get('revenue')?.spec.rows.length===3")
    page.click("#append")
    page.wait_for_function("shinyCharts.get('revenue').spec.rows.length===4")
    assert page.evaluate("Shiny.shinyapp.$inputValues.revenue_update.status") == "applied"
    track = page.locator(".irs-line").bounding_box()
    page.mouse.click(track["x"] + track["width"] / 2, track["y"] + track["height"] / 2)
    page.wait_for_function(
        "shinyCharts.get('revenue').spec.rows.length===3 && shinyCharts.get('revenue').stream.sequence===0"
    )


def test_escape_exits_region_selection_and_restores_focus(page, server_url):
    operations_ready(page, server_url)
    brush = page.locator("#observations").get_by_role("button", name="Select region")
    brush.press("Enter")
    expect(brush).to_have_attribute("aria-pressed", "true")
    brush.press("Escape")
    expect(brush).to_have_attribute("aria-pressed", "false")
    expect(brush).to_be_focused()


def test_operations_region_feedback_and_scope_reconcile(page, server_url):
    operations_ready(page, server_url)
    page.locator("#observations").get_by_role("button", name="View data").click()
    page.get_by_role("dialog").get_by_role("button", name="Select", exact=True).nth(200).click()
    expect(page.locator("#detail")).to_contain_text("obs-0000200")
    page.select_option("#queue", "API integrations and developer support")
    expect(page.locator("#detail")).to_contain_text("Choose an observation")
    page.select_option("#queue", "All")
    page.wait_for_function("shinyCharts.get('observations').spec.rows.length===2400")
    page.locator("#observations").scroll_into_view_if_needed()
    page.locator("#observations").get_by_role("button", name="Select region").click()
    coords = page.evaluate("""() => {
      const s=shinyCharts.get('observations'), box=s.plot.getBoundingClientRect();
      return [[10,15],[30,65]].map(v=>{
        const p=s.engine.convertToPixel({gridIndex:0},v);return [box.x+p[0],box.y+p[1]];
      });
    }""")
    page.mouse.move(*coords[0])
    page.mouse.down()
    page.mouse.move(*coords[1], steps=12)
    page.mouse.up()
    expect(page.locator("#detail")).to_contain_text("observations selected")
    event = page.evaluate("Shiny.shinyapp.$inputValues.observations_selection")
    assert event["kind"] == "range" and event["count"] > 0
    expect(page.locator("#detail")).to_contain_text(f"{event['count']:,} observations selected")
    expect(page.locator("#detail")).to_contain_text("resolution")
    page.click("#append")
    expect(page.locator("#detail")).to_contain_text("Data updated; select a region again")
    page.locator("#observations").get_by_role("button", name="Clear selection").click()
    expect(page.locator("#detail")).to_contain_text("Choose an observation")


def test_progress_empty_pairs_and_alert_recovery(page, server_url):
    page.goto(server_url + "/fixture/")
    page.wait_for_function("shinyCharts?.get('example')?.spec.rows.length === 2")
    page.select_option("#state", "slow")
    expect(page.locator("#example")).to_have_attribute("aria-busy", "true")
    expect(page.locator("#example .sc-plot svg")).to_be_visible()
    expect(page.locator("#example .sc-progress")).to_be_visible()
    expect(page.locator("#example")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#example .sc-progress")).to_be_hidden()
    page.select_option("#state", "missing-pairs")
    expect(page.locator("#example .sc-empty")).to_be_visible()
    page.select_option("#state", "error")
    expect(page.locator("#example [role=alert]")).to_contain_text("Try another example")
    page.select_option("#state", "data")
    expect(page.locator("#example .sc-plot svg")).to_be_visible()
    expect(page.locator("#example [role=alert]")).to_have_count(0)
