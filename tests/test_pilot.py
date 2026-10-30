"""Synthetic browser regressions for the 0.4.0b1 client pilot."""

from pathlib import Path

from playwright.sync_api import expect


def ready(page, server_url):
    page.goto(server_url + "/pilot/")
    page.wait_for_function("shinyCharts?.get('shares')?.spec.rows.length === 10")


def click_bar(page, id="stale"):
    page.locator(f"#{id} .sc-plot").scroll_into_view_if_needed()
    x, y = page.evaluate(
        """id => {
        const s=shinyCharts.get(id);
        const layout=s.engine.getModel().getSeriesByIndex(0).getData().getItemLayout(0);
        const box=s.plot.getBoundingClientRect();
        return [box.x+layout.x+layout.width/2,box.y+layout.y+layout.height/2];
    }""",
        id,
    )
    page.mouse.click(x, y)


def test_revision_resets_server_selection_legend_view_and_click(page, server_url):
    ready(page, server_url)
    click_bar(page)
    page.wait_for_function("Shiny.shinyapp.$inputValues.stale_selection?.keys.length === 1")
    page.locator("#stale .sc-legend-item").filter(has_text="B").click()
    page.wait_for_function("Shiny.shinyapp.$inputValues.stale_legend?.hidden[0] === 'B'")
    # Same-revision refresh must retain the existing view/selection contract.
    selected = page.evaluate("Shiny.shinyapp.$inputValues.stale_selection")
    page.click("#refresh")
    page.wait_for_function("shinyCharts.get('stale').spec.rows[0][1] === 2")
    assert page.evaluate("Shiny.shinyapp.$inputValues.stale_selection") == selected
    assert page.evaluate("[...shinyCharts.get('stale').hidden]") == ["B"]
    page.click("#shift")
    page.wait_for_function("Shiny.shinyapp.$inputValues.stale_selection?.revision === '1'")
    assert page.evaluate("Shiny.shinyapp.$inputValues.stale_selection") == {
        "kind": "clear",
        "keys": [],
        "revision": "1",
    }
    assert page.evaluate("Shiny.shinyapp.$inputValues.stale_legend") == {
        "hidden": [],
        "revision": "1",
    }
    assert page.evaluate("Shiny.shinyapp.$inputValues.stale_view") == {
        "reset": True,
        "revision": "1",
    }
    assert page.evaluate("Shiny.shinyapp.$inputValues.stale_click") is None
    expect(page.locator("#pilot_state")).to_contain_text('"kind": "clear"')
    expect(page.locator("#pilot_state")).to_contain_text('"hidden": []')
    assert page.locator('#stale .sc-legend-item[aria-pressed="false"]').count() == 0
    click_bar(page)
    page.locator("#stale .sc-legend-item").filter(has_text="B").click()
    page.select_option("#pilot_renderer", "canvas")
    page.wait_for_function("shinyCharts.get('stale').spec.renderer === 'canvas'")
    page.wait_for_function("Shiny.shinyapp.$inputValues.stale_selection?.kind === 'clear'")
    assert page.evaluate("Shiny.shinyapp.$inputValues.stale_legend") == {
        "hidden": [],
        "revision": "1",
    }


def test_none_zero_error_loading_and_recovery(page, server_url):
    ready(page, server_url)
    expect(page.locator("#empty .sc-empty")).to_have_text("No observations available yet.")
    expect(page.locator("#empty .sc-empty")).to_be_visible()
    expect(page.locator("#empty .sc-tools")).to_have_count(0)
    page.select_option("#empty_mode", "data")
    page.wait_for_function("shinyCharts.get('empty')?.spec.rows.length === 1")
    click_bar(page, "empty")
    page.wait_for_function("Shiny.shinyapp.$inputValues.empty_selection?.keys[0] === 'internal-a'")
    page.select_option("#empty_mode", "none")
    expect(page.locator("#empty .sc-empty")).to_have_text("No observations available yet.")
    expect(page.locator("#empty .sc-empty")).to_be_visible()
    page.wait_for_function("Shiny.shinyapp.$inputValues.empty_selection === null")
    for suffix in ["selection", "legend", "view", "click"]:
        assert (
            page.evaluate("suffix => Shiny.shinyapp.$inputValues['empty_'+suffix]", suffix) is None
        )
    page.select_option("#empty_mode", "slow")
    expect(page.locator("#empty .sc-progress")).to_be_visible()
    expect(page.locator("#empty")).to_have_attribute("aria-busy", "false")
    page.select_option("#empty_mode", "zero")
    expect(page.locator("#empty .sc-empty")).to_have_text("No observations available yet.")
    expect(page.locator("#empty .sc-empty")).to_be_visible()
    expect(page.locator("#empty .sc-plot svg text")).to_have_count(0)
    expect(page.locator("#empty .sc-tools")).to_be_hidden()
    page.select_option("#empty_mode", "slow")
    expect(page.locator("#empty .sc-progress")).to_be_visible()
    expect(page.locator("#empty")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#empty .sc-progress")).to_be_hidden()
    page.select_option("#empty_mode", "error")
    expect(page.locator("#empty [role=alert]")).to_contain_text("Synthetic renderer failure")
    page.select_option("#empty_mode", "data")
    expect(page.locator("#empty .sc-plot svg")).to_be_visible()


def test_percent_domain_title_value_labels_table_keys_and_export(page, server_url):
    ready(page, server_url)
    for width in [440, 480, 390]:
        page.evaluate(
            "width => document.querySelector('.pilot-width').style.width=width+'px'", width
        )
        page.wait_for_function(
            "width => Math.abs(shinyCharts.get('shares').engine.getWidth() - (width-32)) < 4",
            arg=width,
        )
        ticks = page.evaluate(
            "shinyCharts.get('shares').engine.getModel().getComponent('yAxis').axis.scale.getTicks().map(t=>t.value)"
        )
        assert ticks[0] == 0 and ticks[-1] == 1
        expect(page.locator("#shares .sc-title")).to_have_text("Daily percentage shares")
    totals = page.evaluate(
        "shinyCharts.get('shares').engine.getOption().series.filter(s=>s.id.startsWith('total:')).flatMap(s=>s.data).map(p=>p.total)"
    )
    assert totals == [1] * 5
    page.click("#append_shares")
    page.wait_for_function("shinyCharts.get('shares').spec.rows.length === 12")
    assert page.evaluate("shinyCharts.get('shares').spec.data_table.hide") == ["key"]
    totals = page.evaluate(
        "shinyCharts.get('shares').engine.getOption().series.filter(s=>s.id.startsWith('total:')).flatMap(s=>s.data).map(p=>p.total)"
    )
    assert totals == [1] * 6
    page.locator("#shares").get_by_role("button", name="View data").click()
    headers = page.get_by_role("dialog").locator("th").all_text_contents()
    assert headers == ["x", "share", "who", "Select"]
    assert "key" not in headers
    page.get_by_role("dialog").get_by_role("button", name="Select", exact=True).first.press("Enter")
    page.wait_for_function(
        "Shiny.shinyapp.$inputValues.shares_selection?.keys[0] === '2026-01-01|A'"
    )
    with page.expect_download() as info:
        page.locator("#shares").get_by_role("button", name="Download CSV").click()
    assert '"key"' in Path(info.value.path()).read_text()
    with page.expect_download() as info:
        page.locator("#shares").get_by_role("button", name="Save image").click()
    assert "Daily percentage shares" in Path(info.value.path()).read_text()


def test_date_ticks_zero_ticks_and_distinct_explicit_palette(page, server_url):
    ready(page, server_url)
    assert (
        page.evaluate("shinyCharts.get('dates').engine.getOption().xAxis[0].axisLabel.overflow")
        == "truncate"
    )
    texts = page.locator("#dates .sc-plot svg text").all_text_contents()
    assert all("\n" not in text for text in texts if text.startswith("2026"))
    labels = page.evaluate(
        """() => {
        const axis=shinyCharts.get('zeros').engine.getModel().getComponent('yAxis');
        return axis.axis.scale.getTicks().map(t=>axis.get('axisLabel.formatter')(t.value));
        }"""
    )
    assert len(labels) == len(set(labels))
    colors = page.evaluate(
        "shinyCharts.get('groups').engine.getOption().series.filter(s=>s.id.startsWith('series:')).map(s=>s.itemStyle.color)"
    )
    assert len(set(colors)) == 8
    assert page.locator("#groups .sc-legend-item").all_text_contents() == [
        f"Group {i}" for i in range(8, 0, -1)
    ]
    assert page.locator("#groups .sc-swatch-bar").first.bounding_box()["height"] == 10
    assert (
        page.evaluate("shinyCharts.get('rotated').engine.getOption().xAxis[0].axisLabel.rotate")
        == 45
    )
    assert page.evaluate(
        "shinyCharts.get('rotated').engine.getModel().getComponent('yAxis').axis.scale.getExtent()"
    ) == [0, 10]


def test_title_precedes_legend_in_both_renderers_and_exports_without_changing_state(
    page, server_url
):
    import struct
    import xml.etree.ElementTree as ET

    ready(page, server_url)
    for renderer in ["svg", "canvas"]:
        page.select_option("#pilot_renderer", renderer)
        page.wait_for_function(
            "renderer => shinyCharts.get('shares').spec.renderer === renderer", arg=renderer
        )
        title = page.locator("#shares .sc-title").bounding_box()
        legend = page.locator("#shares .sc-legend").bounding_box()
        plot = page.locator("#shares .sc-plot").bounding_box()
        assert title["y"] + title["height"] <= legend["y"] + 0.1
        assert legend["y"] + legend["height"] <= plot["y"] + 0.1
        if renderer == "svg":
            text = page.locator("#shares .sc-plot svg").text_content()
            assert "Daily percentage shares" not in text
        page.locator("#shares .sc-legend-item").filter(has_text="A").click()
        assert page.evaluate("[...shinyCharts.get('shares').hidden]") == ["A"]
        size = page.evaluate(
            "[shinyCharts.get('shares').engine.getWidth(), "
            "shinyCharts.get('shares').engine.getHeight()]"
        )
        before = page.evaluate("shinyCharts.get('shares').el.dataset.renderCount")
        with page.expect_download() as info:
            page.locator("#shares").get_by_role("button", name="Save image").click()
        data = Path(info.value.path()).read_bytes()
        assert page.evaluate("[...shinyCharts.get('shares').hidden]") == ["A"]
        assert page.evaluate("shinyCharts.get('shares').el.dataset.renderCount") == before
        if renderer == "svg":
            svg = ET.fromstring(data)
            assert float(svg.attrib["height"]) == size[1] + 32
            ns = {"svg": "http://www.w3.org/2000/svg"}
            assert svg.find("svg:text", ns).text == "Daily percentage shares"
            assert svg.find("svg:g", ns).attrib["transform"] == "translate(0 32)"
        else:
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            width, height = struct.unpack(">II", data[16:24])
            assert width == size[0] * 2
            assert height == size[1] * 2 + 64


def test_express_custom_empty_message_survives_none_zero_recovery(page, server_url):
    page.goto(server_url + "/express/")
    page.wait_for_function("shinyCharts?.get('revenue')?.spec.rows.length === 3")
    page.check("#hide_revenue")
    expect(page.locator("#revenue .sc-empty")).to_have_text("Revenue data has not arrived.")
    page.uncheck("#hide_revenue")
    page.wait_for_function("shinyCharts.get('revenue')?.spec.rows.length === 3")
    expect(page.locator("#revenue .sc-empty")).to_be_hidden()
    page.check("#hide_revenue")
    expect(page.locator("#revenue .sc-empty")).to_have_text("Revenue data has not arrived.")


def test_fixed_percent_ticks_fitting_stack_labels_and_long_categories(page, server_url):
    ready(page, server_url)
    for renderer in ["svg", "canvas"]:
        page.select_option("#pilot_renderer", renderer)
        page.wait_for_function(
            "renderer => shinyCharts.get('fixed_shares').spec.renderer === renderer", arg=renderer
        )
        for width in [440, 260]:
            page.evaluate(
                "width => document.querySelector('.feedback-shares').style.width=width+'px'", width
            )
            page.wait_for_function(
                "width => Math.abs(shinyCharts.get('fixed_shares').engine.getWidth()-width)<2",
                arg=width,
            )
            assert page.evaluate(
                "shinyCharts.get('fixed_shares').engine.getModel().getComponent('yAxis').axis.scale.getTicks().map(t=>t.value)"
            ) == [0, 0.25, 0.5, 0.75, 1]
        # Read the actual renderer's text bounds, not just serialized options.
        labels = page.evaluate("""() => {
          const s=shinyCharts.get('fixed_shares'), result=[];
          s.engine.getModel().eachSeries(series=>{
            if(!series.id.startsWith('series:'))return;
            series.getData().eachItemGraphicEl((el,i)=>{
              const text=el.getTextContent(); if(!text || text.ignore)return;
              const box=text.getBoundingRect(), bar=series.getData().getItemLayout(i);
              if(box.width)result.push({w:box.width,h:box.height,bw:Math.abs(bar.width),bh:Math.abs(bar.height)});
            });
          }); return result;
        }""")
        assert all(p["w"] + 8 <= p["bw"] + 0.1 and p["h"] + 8 <= p["bh"] + 0.1 for p in labels)
        small = page.evaluate("""() => {
          const s=shinyCharts.get('small_segments'), labels=[];
          s.engine.getModel().eachSeries(series=>series.getData().eachItemGraphicEl(el=>{
            const text=el.getTextContent() || el.getSymbolPath?.().getTextContent();
            if(text&&!text.ignore)
              labels.push({text:text.style.text,width:text.getBoundingRect().width});
          }));return labels;
        }""")
        assert not any(p["text"] == "21,812" and p["width"] > 0 for p in small)
        assert any(p["text"] == "1,642,217" and p["width"] > 0 for p in small)
        assert any(p["text"] == "888,202" and p["width"] > 0 for p in small)
        page.check("#zero_segments")
        page.wait_for_function("shinyCharts.get('small_segments').spec.rows.every(row=>row[1]===0)")
        zeros = page.evaluate("""() => {
          const result=[];shinyCharts.get('small_segments').engine.getModel().eachSeries(series=>{
            series.getData().eachItemGraphicEl(el=>{
              const t=el.getTextContent() || el.getSymbolPath?.().getTextContent();
              if(t&&!t.ignore&&t.style.text)result.push({id:series.id,text:t.style.text});});
          });return result;
        }""")
        assert len(zeros) == 2 and all(p["id"].startswith("total:") for p in zeros)
        page.uncheck("#zero_segments")
        page.wait_for_function("shinyCharts.get('small_segments').spec.rows[0][1]===705062")
        names = ["Made prediction", "Declined prediction", "Timed out", "Failed"]
        for rotated in [False, True]:
            page.set_checked("#rotate_words", rotated)
            page.wait_for_function(
                "rotated=>shinyCharts.get('word_categories').engine.getOption()"
                ".xAxis[0].axisLabel.rotate===(rotated?45:0)",
                arg=rotated,
            )
            shown = page.evaluate("""() => {
              const model=shinyCharts.get('word_categories').engine.getModel();
              const axis=model.getComponent('xAxis').axis;
              return axis.getViewLabels().map(label=>label.formattedLabel.replaceAll('\\n',' '));
            }""")
            assert shown == names
        page.uncheck("#rotate_words")
