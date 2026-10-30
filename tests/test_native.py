import asyncio
import gc
import json
from datetime import date

import polars as pl
import pytest

pytest.importorskip("_shiny_charts_native")
from shiny_charts import chart as reference
from shiny_charts import render_chart
from shiny_charts._wire import pack
from shiny_charts.native import NativeChart, chart


@pytest.mark.parametrize("kind", ["bar", "line", "area", "scatter"])
@pytest.mark.parametrize("rows", [0, 3, 1000])
def test_equivalent(kind, rows):
    df = pl.DataFrame(
        {
            "x": list(range(rows)),
            "y": [None if i % 17 == 0 else i / 3 for i in range(rows)],
            "g": ["café🦀" + str(i % 3) for i in range(rows)],
            "k": list(range(rows)),
        },
        schema={"x": pl.Int64, "y": pl.Float64, "g": pl.String, "k": pl.Int64},
    )
    a = (
        getattr(chart, kind)(df, x="x", y="y", color="g", key="k")
        .format(y="number:2")
        .hover(template="{y:number:2}")
        .view("2", zoom=False)
    )
    b = (
        getattr(reference, kind)(df, x="x", y="y", color="g", key="k")
        .format(y="number:2")
        .hover(template="{y:number:2}")
        .view("2", zoom=False)
    )
    assert a.to_spec() == b.to_spec()
    assert json.loads(a.native_json()) == pack(b)
    snapshot = a.to_spec()
    snapshot["rows"].clear()
    assert len(a.to_spec()["rows"]) == rows


@pytest.mark.parametrize(
    "frame,kwargs",
    [
        (pl.DataFrame({"x": [1, 2], "y": [1, 2], "k": ["a", "a"]}), {"key": "k"}),
        (pl.DataFrame({"x": [1], "y": ["bad"]}), {}),
        (pl.DataFrame({"x": [1], "y": [1], "k": [None]}), {"key": "k"}),
        (pl.DataFrame({"x": [1], "y": [1], "k": [2**53]}), {"key": "k"}),
        (pl.DataFrame({"x": [1], "y": [1], "k": [True]}), {"key": "k"}),
        (pl.DataFrame({"x": [1]}), {}),
    ],
)
def test_invalid(frame, kwargs):
    for builder in (chart, reference):
        with pytest.raises(ValueError):
            builder.bar(frame, x="x", y="y", **kwargs)


def test_lifetime_chunking_nulls_and_special_floats():
    df = pl.concat(
        [
            pl.DataFrame({"x": [i], "y": [v], "g": [None if i == 1 else "A"]})
            for i, v in enumerate([float("nan"), float("inf"), -float("inf"), 2.0])
        ]
    )
    expected = reference.scatter(df, x="x", y="y", color="g").to_spec()
    actual = chart.scatter(df, x="x", y="y", color="g")
    del df
    gc.collect()
    assert actual.to_spec() == expected
    assert json.loads(actual.native_json()) == expected


def test_dates_fallback():
    df = pl.DataFrame({"x": [date(2026, 1, 1)], "y": [1.0]})
    actual = chart.line(df, x="x", y="y")
    assert not isinstance(actual, NativeChart)
    assert actual.to_spec() == reference.line(df, x="x", y="y").to_spec()


def test_band_overlay_and_renderer():
    df = pl.DataFrame(
        {"x": ["a", "b"], "y": [2.0, 4.0], "lo": [1.0, 3.0], "hi": [3.0, 5.0], "g": ["A", "B"]}
    )
    for builder in (chart, reference):
        c = builder.line(df, x="x", y="y").band(lower="lo", upper="hi")
        if builder is chart:
            actual = c
        else:
            expected = c
    assert actual.to_spec() == expected.to_spec()
    a = chart.bar(df, x="x", y="y", color="g").line(df, y="hi", label="Forecast")
    b = reference.bar(df, x="x", y="y", color="g").line(df, y="hi", label="Forecast")
    assert json.loads(a.native_json()) == pack(b)
    output = asyncio.run(render_chart().transform(a))
    assert json.loads(output["spec_json"]) == pack(b)


def test_materialize_rows_fallback():
    a = chart.bar(pl.DataFrame({"x": ["a"], "y": [1]}), x="x", y="y")
    assert list(a._spec["rows"]) == [["a", 1]]
    b = a._with(rows=[["b", 2]])
    assert json.loads(b.native_json())["rows"] == [["b", 2]]


@pytest.mark.parametrize("kind", ["line", "area"])
@pytest.mark.parametrize("xs", [[float("nan"), float("inf")], [None, None], [True, False]])
def test_axis_inference_matches_scalar_normalization(kind, xs):
    df = pl.DataFrame({"x": xs, "y": [1.0, 2.0]})
    if xs == [True, False]:
        for builder in (chart, reference):
            with pytest.raises(ValueError):
                getattr(builder, kind)(df, x="x", y="y")
    else:
        actual = getattr(chart, kind)(df, x="x", y="y")
        expected = getattr(reference, kind)(df, x="x", y="y")
        assert actual.to_spec() == expected.to_spec()
