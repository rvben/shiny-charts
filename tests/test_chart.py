import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from shiny_charts import chart, output_chart, render_chart
from shiny_charts._wire import pack


def test_only_required_columns_travel_and_builders_leave_input_untouched():
    rows = [{"x": 1, "y": 2, "id": "a", "secret": "never transport"}]
    base = chart.line(rows, x="x", y="y", key="id")
    formatted = base.format(y="currency:EUR:3").rule(y=3, label="Budget")
    rows[0]["y"] = 999
    assert base.to_spec()["rows"] == [[1, 2, "a"]]
    assert "secret" not in json.dumps(formatted.to_spec())
    assert base.to_spec()["formats"]["y"] == "number"
    snapshot = base.to_spec()
    snapshot["rows"][0][1] = 888
    assert base.to_spec()["rows"][0][1] == 2


def test_numpy_pandas_missing_values_are_strict_json_and_line_gaps():
    frame = pd.DataFrame({"x": [1, 2, 3], "y": [np.float64(0.1), np.nan, pd.NA]})
    spec = chart.line(frame, x="x", y="y").to_spec()
    assert spec["rows"] == [[1, 0.1], [2, None], [3, None]]
    json.dumps(spec, allow_nan=False)


def test_time_is_normalized_to_utc_with_naive_values_explicitly_utc():
    rows = [
        {"x": date(2026, 9, 1), "y": 1},
        {"x": datetime(2026, 9, 2), "y": 2},
        {"x": datetime(2026, 9, 3, 2, tzinfo=timezone(timedelta(hours=2))), "y": 3},
    ]
    spec = chart.line(rows, x="x", y="y").to_spec()
    assert spec["x_type"] == "time"
    assert spec["rows"][2][0] == "2026-09-03T00:00:00+00:00"


def test_empty_data_and_column_mapping():
    assert chart.scatter([], x="x", y="y").to_spec()["rows"] == []
    assert chart.bar({"x": ["a", "b"], "y": [1, 2]}, x="x", y="y").to_spec()["rows"] == [
        ["a", 1],
        ["b", 2],
    ]
    with pytest.raises(ValueError, match="equal lengths"):
        chart.line({"x": [1], "y": [1, 2]}, x="x", y="y")


@pytest.mark.parametrize("keys", [["a", "a"], ["a", None], ["a", True]])
def test_keys_are_unique_and_non_null(keys):
    with pytest.raises(ValueError, match="Keys"):
        chart.scatter(
            [{"x": i, "y": i, "id": key} for i, key in enumerate(keys)], x="x", y="y", key="id"
        )


@pytest.mark.parametrize("y", ["2", True, [1, 2]])
def test_non_numeric_y_fails_early(y):
    with pytest.raises((ValueError, TypeError)):
        chart.line([{"x": 1, "y": y}], x="x", y="y")


def test_band_crosses_zero_keeps_gaps_and_validates_order():
    rows = [{"x": 1, "y": 0, "lo": -1, "hi": 1}, {"x": 2, "y": None, "lo": None, "hi": None}]
    spec = chart.line(rows, x="x", y="y").band(lower="lo", upper="hi").to_spec()
    assert spec["band"]["bounds"] == [[-1, 1], [None, None]]
    with pytest.raises(ValueError, match="exceeds"):
        chart.line([{"x": 1, "y": 0, "lo": 1, "hi": -1}], x="x", y="y").band(lower="lo", upper="hi")


def test_histogram_boundary_convention_and_counts():
    spec = chart.histogram(
        {"x": [0, 0.5, 1, None, np.nan, 10]}, x="x", bins=2, range=(0, 1)
    ).to_spec()
    assert spec["rows"] == [[0.25, 1], [0.75, 2]]
    assert spec["intervals"] == [[0, 0.5], [0.5, 1]]
    assert spec["encoding"]["key"] is None
    assert (
        sum(row[1] for row in chart.histogram({"x": [2, 2, 2]}, x="x", bins=2).to_spec()["rows"])
        == 3
    )


@pytest.mark.parametrize("bins", [0, -1, 501, True, 1.5])
def test_histogram_rejects_invalid_budgets(bins):
    with pytest.raises(ValueError):
        chart.histogram([], x="x", bins=bins)


def test_format_and_selection_validation():
    base = chart.line({"x": [1], "y": [2]}, x="x", y="y")
    with pytest.raises(ValueError, match="Format"):
        base.format(y="nonsense")
    with pytest.raises(ValueError, match="scatter"):
        base.select(brush=True)
    with pytest.raises(ValueError, match="Renderer"):
        base.renderer("webgl")


async def test_renderer_sends_semantic_spec_without_html_or_engine_options():
    value = chart.bar({"x": ["A"], "y": [3]}, x="x", y="y")
    renderer = render_chart(height="280px")
    result = await renderer.transform(value)
    assert result["height"] == "280px"
    assert result["spec"]["kind"] == "bar"
    assert "series" not in result["spec"]
    with pytest.raises(TypeError, match="expects"):
        await renderer.transform({})
    assert "html-fill-item" in str(output_chart("chart"))
    assert "html-fill-item" not in str(output_chart("chart", height="200px"))


def test_wire_dictionary_encoding_is_lossless_and_does_not_touch_snapshot():
    rows = [{"x": i, "y": i / 10, "g": "A long workload name"} for i in range(100)]
    value = chart.scatter(rows, x="x", y="y", color="g")
    wire = pack(value)
    assert wire["dictionaries"]["g"] == ["A long workload name"]
    assert wire["rows"][0] == [0, 0, 0]
    assert value.to_spec()["rows"][0][2] == "A long workload name"
    assert len(json.dumps(wire)) < len(json.dumps(value.to_spec()))


def test_wire_and_public_snapshots_are_independent_after_large_data_copy_optimization():
    value = chart.scatter(
        {"x": [1, 2], "y": [2, None], "id": ["a", "b"]}, x="x", y="y", key="id"
    ).labels(title="Original")
    wire = pack(value)
    wire["rows"][0][1] = 999
    wire["labels"]["title"] = "Changed"
    assert value.to_spec()["rows"][0] == [1, 2, "a"]
    assert value.to_spec()["labels"]["title"] == "Original"


def test_band_source_and_bounds_do_not_follow_caller_mutation():
    data = [{"x": 1, "y": 2, "low": 1, "high": 3}]
    value = chart.line(data, x="x", y="y")
    data[0]["low"] = 888
    band = value.band(lower="low", upper="high")
    snapshot = band.to_spec()
    snapshot["band"]["bounds"][0][0] = 777
    assert band.to_spec()["band"]["bounds"] == [[1, 3]]


def test_named_palette_slots_are_validated_and_snapshotted():
    mapping = {"Email": 1, "Chat": 2}
    value = chart.line({"x": [1], "y": [2]}, x="x", y="y").palette(mapping)
    mapping["Email"] = 3
    assert value.to_spec()["palette"] == {"Email": 1, "Chat": 2}
    for bad in ({"Email": 0}, {"Email": 13}, {"Email": True}, {"Email": "#fff"}, {1: 2}):
        with pytest.raises(ValueError, match="slots"):
            value.palette(bad)


@pytest.mark.parametrize("builder", [chart.bar, chart.area])
def test_bar_area_tooltip_fields_are_explicit_snapshots(builder):
    rows = [{"x": 1, "y": 0.42, "scope": "Europe", "private": "exclude"}]
    result = builder(rows, x="x", y="y", tooltip=["scope"])
    rows[0]["scope"] = "changed"
    assert result.to_spec()["columns"] == ["x", "y", "scope"]
    assert result.to_spec()["rows"] == [[1, 0.42, "Europe"]]
    assert "private" not in json.dumps(result.to_spec())


def test_polars_frame_native_records_and_missing_values():
    import polars as pl

    frame = pl.DataFrame({"x": ["a", "b"], "y": [1.0, None], "g": ["A", None], "key": ["a", "b"]})
    native = chart.bar(frame, x="x", y="y", color="g", key="key")
    assert (
        native.to_spec()
        == chart.bar(frame.to_dicts(), x="x", y="y", color="g", key="key").to_spec()
    )
    assert chart.bar(frame.head(0), x="x", y="y").to_spec()["rows"] == []


def test_beta_optional_apis_are_immutable_validated_and_preserve_view_default():
    base = chart.bar({"x": ["a"], "y": [1], "key": ["a"]}, x="x", y="y", key="key", stacked=True)
    changed = (
        base.domain(y=(0, 10))
        .ticks(x_rotation=45)
        .value_labels(totals=True)
        .legend(order=["B", "A"])
        .data_table(hide=["key"])
        .palette({"B": 12})
    )
    spec = changed.to_spec()
    assert spec["domain"] == {"y": [0, 10]}
    assert spec["ticks"] == {"x_rotation": 45}
    assert spec["value_labels"] == {"show": True, "totals": True}
    assert spec["legend"] == {"order": ["B", "A"]}
    assert spec["data_table"] == {"hide": ["key"]}
    assert "domain" not in base.to_spec()
    assert base.view("1").to_spec()["view"] == {"revision": "1", "zoom": True}
    for bounds in [(1, 1), (2, 1), (float("inf"), 2), (True, 2), (1,), "bad"]:
        with pytest.raises(ValueError):
            base.domain(y=bounds)
    with pytest.raises(ValueError, match="numeric"):
        base.domain(x=(0, 1))
    for angle in [91, -91, True, float("nan"), "45"]:
        with pytest.raises(ValueError):
            base.ticks(x_rotation=angle)
    with pytest.raises(ValueError, match="stacked"):
        chart.bar([], x="x", y="y").value_labels(totals=True)
    with pytest.raises(ValueError, match="bar"):
        chart.line([], x="x", y="y").value_labels()
    with pytest.raises(ValueError):
        base.legend(order=["A", "A"])
    with pytest.raises(ValueError):
        base.data_table(hide=["not-transported"])
    with pytest.raises(ValueError):
        base.palette({"A": 13})
    assert base.domain(y=(None, 10)).domain(y=(0, None)).to_spec()["domain"]["y"] == [0, None]


def test_custom_empty_messages_are_output_configuration_not_chart_data():
    message = "No observations <yet> & waiting."
    output = output_chart("waiting", empty_message=message)
    assert output.attrs["data-empty-message"] == message
    assert "&lt;yet&gt;" in str(output)
    assert "No data for this filter." in str(output_chart("default"))
    renderer = render_chart(empty_message=message)
    renderer.output_id = "waiting"
    assert renderer.auto_output_ui().attrs["data-empty-message"] == message
    for invalid in [None, 42, "", "   "]:
        with pytest.raises(ValueError, match="empty_message"):
            output_chart("invalid", empty_message=invalid)
        with pytest.raises(ValueError, match="empty_message"):
            render_chart(empty_message=invalid)


def test_category_label_modes():
    base = chart.bar([{"x": "Made prediction", "y": 1}], x="x", y="y")
    assert base.ticks(x_labels="wrap").to_spec()["ticks"]["x_labels"] == "wrap"
    assert base.ticks(x_labels="all", x_rotation=45).to_spec()["ticks"] == {
        "x_rotation": 45,
        "x_labels": "all",
    }
    with pytest.raises(ValueError, match="auto, all, or wrap"):
        base.ticks(x_labels="invalid")


def test_adoption_apis_preserve_semantic_fields_and_validate_inputs():
    rows = [{"status": "Made prediction", "n": 300000, "share": 0.42, "key": "a"}]
    pie = chart.pie(rows, names="status", values="n", key="key", tooltip=["share"])
    assert pie.to_spec()["kind"] == "pie"
    assert pie.to_spec()["encoding"] == {"x": "status", "y": "n", "color": "status", "key": "key"}
    spec = pie.hover(template="{{status}}: {status}: {n:number:0} ({share:percent:1})").to_spec()
    assert spec["hover"]["tokens"][-2] == {"field": "share", "format": "percent:1"}
    assert pie.hover(formats={"share": "percent:1"}).to_spec()["hover"]["formats"] == {
        "share": "percent:1"
    }
    for bad in [-1, -100]:
        with pytest.raises(ValueError, match="nonnegative"):
            chart.pie([{"status": "a", "n": bad}], names="status", values="n")
    with pytest.raises(ValueError, match="axis domains"):
        pie.domain(y=(0, 1))
    with pytest.raises(ValueError, match="axis ticks"):
        pie.ticks()
    with pytest.raises(ValueError, match="Cartesian"):
        pie.rule(x="Made prediction", label="Rule")
    with pytest.raises(ValueError, match="Cartesian"):
        pie.annotate(x="Made prediction", y=1, text="Text")
    base = chart.bar(rows, x="status", y="n", tooltip=["share"])
    for template in ["{secret}", "{status!r}", "{n:bad}", "{n", "{n.__class__}", "{n:{share}}"]:
        with pytest.raises(ValueError):
            base.hover(template=template)
    with pytest.raises(ValueError, match="numbers"):
        base.hover(formats={"status": "number:0"})
    for options in [{}, {"x": "a", "y": 1}, {"y": float("inf")}, {"y": True}]:
        with pytest.raises(ValueError):
            base.rule(label="Bad", **options)
    spec = (
        base.rule(x="Made prediction", label="Cutoff")
        .annotate(x="Made prediction", y=300000, text="Peak", position="inside")
        .legend(order=["First"])
        .legend(placement="bottom", layout="scroll")
        .to_spec()
    )
    assert spec["rules"] == [{"x": "Made prediction", "label": "Cutoff"}]
    assert spec["annotations"][0]["text"] == "Peak"
    assert spec["legend"] == {"order": ["First"], "placement": "bottom", "layout": "scroll"}
    dated = chart.line([{"x": date(2026, 1, 1), "y": 1}], x="x", y="y")
    assert (
        dated.rule(x=date(2026, 1, 2), label="Day").to_spec()["rules"][0]["x"]
        == "2026-01-02T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="ISO"):
        dated.rule(x="not a date", label="Day")


def test_dividers_plot_edge_annotations_and_date_categories():
    from datetime import date

    bars = chart.bar({"x": ["Mar", "Apr"], "y": [2, 3]}, x="x", y="y")
    spec = (
        bars.rule(x_between=("Mar", "Apr"), label="Divider")
        .annotate(x="Mar", y="top", text="Actuals")
        .to_spec()
    )
    assert spec["rules"] == [{"x_between": ["Mar", "Apr"], "label": "Divider"}]
    assert spec["annotations"][0]["y"] == "top"
    for kwargs in [
        {"x_between": "Mar"},
        {"x_between": ["Mar"]},
        {"x_between": ["Mar", "Mar"]},
        {"x": "Mar", "x_between": ["Mar", "Apr"]},
    ]:
        with pytest.raises(ValueError):
            bars.rule(label="Divider", **kwargs)
    with pytest.raises(ValueError):
        chart.line({"x": [1], "y": [2]}, x="x", y="y").rule(x_between=(1, 2), label="No")
    with pytest.raises(ValueError):
        bars.annotate(x="Mar", y="paper", text="No")
    dated = chart.bar({"d": [date(2026, 1, 1)], "y": [2]}, x="d", y="y").to_spec()
    assert dated["x_type"] == "category" and dated["x_temporal"] is True
    assert dated["rows"][0][0] == "2026-01-01T00:00:00+00:00"


def test_shared_axis_bar_line_overlay_validation_and_snapshot():
    bars = chart.bar({"m": ["Mar", "Apr"], "n": [2, 3]}, x="m", y="n", stacked=True)
    combined = bars.line({"m": ["Apr", "Mar"], "total": [4, None]}, y="total", label="Forecast")
    assert "line" not in bars.to_spec()
    assert combined.to_spec()["line"]["rows"] == [["Apr", 4], ["Mar", None]]
    with pytest.raises(ValueError, match="group names"):
        combined.labels(y="Forecast")
    spec = combined.to_spec()
    spec["line"]["rows"][0][1] = 99
    assert combined.to_spec()["line"]["rows"][0][1] == 4
    invalid = [
        ({"m": ["Mar", "Mar"], "t": [1, 2]}, "Forecast"),
        ({"m": [None], "t": [1]}, "Forecast"),
        ({"m": ["Mar"], "t": ["bad"]}, "Forecast"),
        ({"m": ["Mar"], "t": [1]}, "N"),
        ({"m": ["Mar"], "t": [1]}, " "),
    ]
    for data, label in invalid:
        with pytest.raises(ValueError):
            bars.line(data, y="t", label=label)
    with pytest.raises(ValueError):
        combined.line({"m": ["Mar"], "t": [1]}, y="t", label="Second")
    for other in [
        chart.line({"m": ["Mar"], "n": [2]}, x="m", y="n"),
        chart.bar({"m": ["Mar"], "n": [2]}, x="m", y="n", orientation="horizontal"),
    ]:
        with pytest.raises(ValueError):
            other.line({"m": ["Mar"], "t": [1]}, y="t", label="Forecast")


@pytest.mark.parametrize(
    "group,label",
    [(True, "true"), (1.0, "1"), (None, "Missing"), (1e-6, "0.000001"), (1e-7, "1e-7")],
)
def test_line_labels_cannot_collide_with_scalar_bar_groups(group, label):
    bars = chart.bar({"x": ["a"], "y": [2], "g": [group]}, x="x", y="y", color="g")
    with pytest.raises(ValueError, match="group names"):
        bars.line({"x": ["a"], "total": [3]}, y="total", label=label)
