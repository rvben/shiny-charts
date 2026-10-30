"""Synthetic regression tests for adoption APIs and short chart layouts."""

import xml.etree.ElementTree as ET
from pathlib import Path

from playwright.sync_api import expect


def ready(page, server_url):
    page.goto(server_url + "/adoption/")
    page.wait_for_function("shinyCharts?.get('compact')?.spec.rows.length === 4")


def test_rotation_default_height_compact_legend_toolbar_and_axis_title(page, server_url):
    ready(page, server_url)
    for width in [460, 320]:
        page.evaluate(
            "width=>document.querySelector('.rotation-width').style.width=width+'px'", width
        )
        for angle in [45, -45, 90]:
            page.select_option("#angle", str(angle))
            page.wait_for_function(
                "args=>{const s=shinyCharts.get('rotation');return s.engine.getWidth()===args[0]&&s.spec.ticks.x_rotation===args[1]}",
                arg=[width, angle],
            )
            geometry = page.evaluate("""() => {
              const s=shinyCharts.get('rotation'), model=s.engine.getModel();
              const grid=model.getComponent('grid').coordinateSystem.getRect();
              const axis=model.getComponent('yAxis').axis;
              return {h:grid.height,ticks:axis.scale.getTicks().length};
            }""")
            assert geometry["h"] >= 80
            assert geometry["ticks"] >= 3
    legend = page.locator("#compact .sc-legend")
    assert legend.evaluate("el=>getComputedStyle(el).flexWrap") == "nowrap"
    assert legend.evaluate("el=>el.scrollWidth>el.clientWidth")
    items = legend.get_by_role("button")
    items.last.focus()
    assert legend.evaluate("el=>el.scrollLeft") > 0
    items.last.press("Enter")
    page.wait_for_function("shinyCharts.get('compact').hidden.has('Failed')")
    tools = page.locator("#compact .sc-tools")
    boxes = tools.evaluate("""el=>[...el.querySelectorAll('button')].filter(b=>!b.hidden)
      .map(b=>b.getBoundingClientRect().toJSON())""")
    assert max(box["y"] for box in boxes) - min(box["y"] for box in boxes) < 1
    expect(tools.get_by_role("button", name="Save image")).to_be_visible()
    # Axis name is inside the actual SVG viewport, even with wide integer ticks.
    name = page.locator("#compact .sc-plot svg text").filter(has_text="Observations")
    box = name.bounding_box()
    plot = page.locator("#compact .sc-plot").bounding_box()
    assert box["x"] >= plot["x"]


def test_pie_selection_legend_revision_tooltip_export_and_data_proxy(page, server_url):
    ready(page, server_url)
    for renderer in ["svg", "canvas"]:
        page.select_option("#engine", renderer)
        page.wait_for_function(
            "renderer=>shinyCharts.get('slices').spec.renderer===renderer", arg=renderer
        )
        plot = page.locator("#slices .sc-plot").bounding_box()
        legend = page.locator("#slices .sc-legend").bounding_box()
        assert legend["y"] >= plot["y"] + plot["height"] - 1
        page.locator("#slices").scroll_into_view_if_needed()
        x, y = page.evaluate("""() => {
          const s=shinyCharts.get('slices');
          const p=s.engine.getModel().getSeriesByIndex(0).getData().getItemLayout(0);
          const rect=s.plot.getBoundingClientRect(), a=(p.startAngle+p.endAngle)/2;
          return [rect.x+p.cx+Math.cos(a)*p.r*.65,rect.y+p.cy+Math.sin(a)*p.r*.65];
        }""")
        page.mouse.click(x, y)
        page.wait_for_function("Shiny.shinyapp.$inputValues.slices_selection?.keys[0]==='slice-3'")
        assert page.evaluate("Shiny.shinyapp.$inputValues.slices_selection.x") == "Failed"
        page.evaluate(
            "shinyCharts.get('slices').engine.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:0})"
        )
        expect(page.locator("#slices")).to_contain_text("Failed: 15,000 (4.2%)")
        page.locator("#slices .sc-legend").get_by_role("button", name="Failed", exact=True).click()
        assert (
            len(page.evaluate("shinyCharts.get('slices').engine.getOption().series[0].data")) == 3
        )
        expect(page.locator("#slices .sc-summary")).to_contain_text("3 displayed records")
        page.click("#revision")
        page.wait_for_function("Shiny.shinyapp.$inputValues.slices_selection?.kind==='clear'")
        assert page.evaluate("[...shinyCharts.get('slices').hidden]") == []
        with page.expect_download() as info:
            page.locator("#slices").get_by_role("button", name="Save image").click()
        raw = Path(info.value.path()).read_bytes()
        if renderer == "svg":
            svg = ET.fromstring(raw)
            assert "Prediction outcomes" in "".join(svg.itertext())
            assert len(svg.findall(".//{http://www.w3.org/2000/svg}path")) >= 4
        else:
            assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    page.click("#replace_pie")
    page.wait_for_function("shinyCharts.get('slices').spec.rows[0][0]==='Updated'")
    assert (
        page.evaluate("shinyCharts.get('slices').engine.getOption().series[0].data[0].value") == 7
    )
    page.check("#zero_pie")
    expect(page.locator("#slices .sc-empty")).to_be_visible()
    expect(page.locator("#slices .sc-summary")).to_contain_text("0 displayed records")
    expect(page.locator("#slices .sc-tools")).to_be_visible()
    page.uncheck("#zero_pie")
    expect(page.locator("#slices .sc-empty")).to_be_hidden()


def test_annotations_vertical_rules_and_formatted_hover_render_in_both_engines(page, server_url):
    ready(page, server_url)
    for renderer in ["svg", "canvas"]:
        page.select_option("#engine", renderer)
        page.wait_for_function(
            "renderer=>shinyCharts.get('annotated').spec.renderer===renderer", arg=renderer
        )
        labels = page.evaluate("""() => shinyCharts.get('annotated').engine.getZr().storage.getDisplayList()
          .filter(el=>el.type==='tspan').map(el=>el.style.text)""")
        assert "Peak <literal>" in labels
        assert "Cutoff" in labels and "Target" in labels
        page.locator("#annotated").scroll_into_view_if_needed()
        point = page.evaluate("""() => {
          const s=shinyCharts.get('annotated'), row=s.spec.rows[1];
          const p=s.engine.convertToPixel({seriesIndex:0},[Date.parse(row[0]),row[1]]);
          const rect=s.plot.getBoundingClientRect();return [rect.x+p[0],rect.y+p[1]+1];
        }""")
        page.mouse.move(*point)
        expect(page.locator("#annotated")).to_contain_text("12 observations (20.0%)")
        assert page.evaluate(
            "shinyCharts.get('horizontal').engine.getOption().series[0].markLine.data.map(p=>({...(p.xAxis!==undefined?{xAxis:p.xAxis}:{yAxis:p.yAxis}),name:p.name}))"
        ) == [{"yAxis": 2, "name": "Status"}, {"xAxis": 150000, "name": "Threshold"}]
        with page.expect_download() as info:
            page.locator("#annotated").get_by_role("button", name="Save image").click()
        data = Path(info.value.path()).read_bytes()
        if renderer == "svg":
            svg = ET.fromstring(data)
            assert "Peak <literal>" in "".join(svg.itertext())
        else:
            assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_share_ticks_date_bars_and_plot_edge_divider(page, server_url):
    ready(page, server_url)
    for renderer in ["svg", "canvas"]:
        page.select_option("#engine", renderer)
        page.wait_for_function("r=>shinyCharts.get('divider').spec.renderer===r", arg=renderer)
        for width in [300, 440, 900]:
            page.evaluate("w=>document.querySelector('.shares-width').style.width=w+'px'", width)
            page.wait_for_function("w=>shinyCharts.get('shares').engine.getWidth()===w", arg=width)
            labels = page.evaluate("""() => shinyCharts.get('shares').engine.getZr().storage.getDisplayList()
              .filter(el=>el.type==='tspan').map(el=>el.style.text)""")
            assert "100%" in labels
            assert not any(label.startswith("10") and "…" in label for label in labels)
        labels = page.evaluate("""() => shinyCharts.get('dates_bar').engine.getZr().storage.getDisplayList()
          .filter(el=>el.type==='tspan').map(el=>el.style.text)""")
        assert sum(label.startswith("Jan ") for label in labels) >= 3
        assert not any("T00:" in label for label in labels)
        geometry = page.evaluate("""() => {
          const s=shinyCharts.get('divider'), model=s.engine.getModel();
          const grid=model.getComponent('grid').coordinateSystem.getRect();
          const series=model.getSeries().find(m=>m.id==='between-rules');
          const line=series.getData().getItemGraphicEl(0).children()[0].shape;
          const center=(s.engine.convertToPixel({seriesIndex:0},[1,0])[0]+
                        s.engine.convertToPixel({seriesIndex:0},[2,0])[0])/2;
          const text=s.engine.getZr().storage.getDisplayList().filter(el=>el.type==='tspan')
            .filter(el=>['Peak','Actuals','Forecast'].includes(el.style.text)).map(el=> {
              const box=el.getBoundingRect().clone();box.applyTransform(el.getComputedTransform());
              return {text:el.style.text,y:box.y,bottom:box.y+box.height,clips:el.__clipPaths?.length||0};
            });
          return {line:line.x1,center,top:grid.y,text};
        }""")
        assert abs(geometry["line"] - geometry["center"]) < 1
        assert len(geometry["text"]) == 3
        for text in geometry["text"]:
            assert text["y"] >= 0
            assert text["clips"] == 0
            if text["text"] != "Peak":
                assert text["bottom"] < geometry["top"]
        with page.expect_download() as info:
            page.locator("#divider").get_by_role("button", name="Save image").click()
        raw = Path(info.value.path()).read_bytes()
        if renderer == "svg":
            assert all(
                label in "".join(ET.fromstring(raw).itertext())
                for label in ["Actuals", "Forecast", "Peak"]
            )
        else:
            assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_narrow_forecast_overlay_anchors_legend_selection_data_and_proxy(page, server_url):
    ready(page, server_url)
    expect(page.locator("#slices .sc-summary")).to_contain_text("4 displayed records")
    for renderer in ["svg", "canvas"]:
        page.select_option("#engine", renderer)
        page.wait_for_function("r=>shinyCharts.get('forecast').spec.renderer===r", arg=renderer)
        geometry = page.evaluate("""() => {
          const s=shinyCharts.get('forecast'),m=s.engine.getModel();
          const grid=m.getComponent('grid').coordinateSystem.getRect();
          const lines=m.getSeries().filter(x=>x.subType==='line');
          const labels=s.engine.getZr().storage.getDisplayList().filter(el=>el.type==='tspan')
            .filter(el=>['Actuals','Forecast (plan)','Forecast starts'].includes(el.style.text))
            .map(el=>{const b=el.getBoundingRect().clone();b.applyTransform(el.getComputedTransform());
              return {text:el.style.text,x:b.x,right:b.x+b.width,y:b.y,bottom:b.y+b.height};});
          return {grid:{x:grid.x,right:grid.x+grid.width,top:grid.y},labels,
            values:lines[0].getData().mapArray(['x','y'],(x,y)=>[x,Number.isNaN(y)?null:y])};
        }""")
        assert geometry["values"] == [[0, 12], [1, 13], [2, 16], [3, 17], [4, None], [5, 21]]
        labels = {item["text"]: item for item in geometry["labels"]}
        assert set(labels) == {"Actuals", "Forecast (plan)", "Forecast starts"}
        assert labels["Actuals"]["right"] + 4 <= labels["Forecast (plan)"]["x"]
        for label in labels.values():
            assert label["x"] >= geometry["grid"]["x"] - 1
            assert label["right"] <= geometry["grid"]["right"] + 1
            assert label["y"] >= 0
        assert labels["Actuals"]["bottom"] < geometry["grid"]["top"]
        assert labels["Forecast (plan)"]["bottom"] < geometry["grid"]["top"]
        legend = page.locator("#forecast .sc-legend")
        total = legend.get_by_role("button", name="Total forecast", exact=True)
        total.focus()
        total.press("Enter")
        page.wait_for_function("shinyCharts.get('forecast').hidden.has('Total forecast')")
        assert (
            page.evaluate(
                "shinyCharts.get('forecast').engine.getOption().series.find(s=>s.id==='line-overlay').data.length"
            )
            == 0
        )
        total.press("Enter")
        page.click("#revision")
        page.wait_for_function("Shiny.shinyapp.$inputValues.forecast_legend?.hidden.length===0")
        page.locator("#forecast").scroll_into_view_if_needed()
        point = page.evaluate("""() => {
          const s=shinyCharts.get('forecast'),p=s.engine.convertToPixel({seriesIndex:0},[3,1]);
          const r=s.plot.getBoundingClientRect();return [r.x+p[0],r.y+p[1]];
        }""")
        page.mouse.click(*point)
        page.wait_for_function("Shiny.shinyapp.$inputValues.forecast_selection?.keys[0]==='Apr|A'")
        page.evaluate("""() => {const s=shinyCharts.get('forecast'),series=s.engine.getModel().getSeries().find(m=>m.id==='line-overlay');
          s.engine.dispatchAction({type:'showTip',seriesIndex:series.seriesIndex,dataIndex:3});}""")
        expect(page.locator("#forecast")).to_contain_text("17.00")
        with page.expect_download() as info:
            page.locator("#forecast").get_by_role("button", name="Save image").click()
        raw = Path(info.value.path()).read_bytes()
        if renderer == "svg":
            assert "Forecast starts" in "".join(ET.fromstring(raw).itertext())
        else:
            assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    page.locator("#forecast").get_by_role("button", name="View data").click()
    dialog = page.locator("#forecast dialog")
    assert dialog.locator("table").count() == 2
    expect(dialog.locator("table").last).to_contain_text("21.00")
    with page.expect_download() as info:
        dialog.get_by_role("button", name="Download line CSV").click()
    text = Path(info.value.path()).read_text()
    assert '"m","total"' in text and '"Jun","21"' in text
    dialog.get_by_role("button", name="Close", exact=True).click()
    page.check("#forecast_filter")
    page.wait_for_function("shinyCharts.get('forecast').spec.rows.length===10")
    assert not page.evaluate(
        "shinyCharts.get('forecast').engine.getOption().series.some(s=>s.id==='between-rules')"
    )
    assert not page.evaluate(
        "shinyCharts.get('forecast').engine.getZr().storage.getDisplayList().some(el=>el.type==='tspan'&&el.style.text==='Actuals')"
    )
    page.uncheck("#forecast_filter")
    page.wait_for_function("shinyCharts.get('forecast').spec.rows.length===12")
    page.click("#replace_forecast")
    page.wait_for_function("shinyCharts.get('forecast').stream.sequence===1")
    assert page.evaluate("shinyCharts.get('forecast').spec.line.rows.length") == 6
    assert page.evaluate(
        "shinyCharts.get('forecast').engine.getOption().series.find(s=>s.id==='line-overlay').data.map(d=>d.value[1])"
    ) == [12, 17, 21]
