import asyncio
from types import SimpleNamespace

import pytest

from shiny_charts import chart, render_chart


async def controller(value, sender=None):
    messages = []

    async def send(kind, message):
        messages.append((kind, message))

    renderer = render_chart()
    renderer.output_id = "plot"
    renderer._session = SimpleNamespace(
        ns=lambda id: "scope-" + id, send_custom_message=sender or send
    )
    full = await renderer.transform(value)
    return renderer, renderer.proxy(), full, messages


@pytest.mark.asyncio
async def test_proxy_sends_only_delta_and_retains_definition():
    value = (
        chart.scatter({"x": [1, 2], "y": [3, None], "id": ["a", "b"]}, x="x", y="y", key="id")
        .format(y="currency:EUR")
        .view("stream")
        .select(brush=True)
    )
    renderer, proxy, full, messages = await controller(value)
    await proxy.append({"x": [3], "y": [4], "id": ["c"]}, max_rows=2)
    message = messages[0][1]
    assert message["id"] == "scope-plot"
    assert message["token"] == full["stream"]["token"]
    assert message["base"] == 0 and message["sequence"] == 1
    assert message["data"]["rows"] == [[3, 4, "c"]]
    assert set(message["data"]) == {"columns", "rows"}
    assert proxy.row_count == 2
    assert proxy._chart.to_spec()["rows"] == [[2, None, "b"], [3, 4, "c"]]
    assert proxy._chart.to_spec()["view"] == value.to_spec()["view"]
    await proxy.replace_data({"x": [], "y": [], "id": []})
    assert messages[-1][1]["sequence"] == 2
    assert proxy.ready and proxy.row_count == 0
    assert proxy._chart.to_spec()["formats"] == value.to_spec()["formats"]
    await renderer.transform(value)
    assert proxy._token != full["stream"]["token"]
    assert proxy._sequence == 0


@pytest.mark.asyncio
async def test_validation_is_atomic_and_failed_send_does_not_advance():
    value = chart.bar(
        {"x": ["A"], "y": [2], "id": ["a"]}, x="x", y="y", key="id", orientation="horizontal"
    )
    _, proxy, _, messages = await controller(value)
    for data in (
        {"x": ["B"], "y": [3], "id": ["a"]},
        {"x": ["B"], "y": ["wrong"], "id": ["b"]},
        {"x": ["B"], "y": [3]},
    ):
        with pytest.raises(ValueError):
            await proxy.append(data)
    for limit in (0, -1, True, 1.5, 2**53):
        with pytest.raises(ValueError):
            await proxy.append([], max_rows=limit)
    assert not messages and proxy.row_count == 1
    await proxy.append([])
    assert not messages
    await proxy.replace_data({"x": ["B"], "y": [4], "id": ["b"]})
    assert proxy._chart.to_spec()["orientation"] == "horizontal"

    async def fail(*args):
        raise ConnectionError("closed")

    _, broken, _, _ = await controller(value, fail)
    with pytest.raises(ConnectionError):
        await broken.append({"x": ["C"], "y": [5], "id": ["c"]})
    assert broken.row_count == 1 and broken._sequence == 0


@pytest.mark.asyncio
async def test_bands_remain_aligned_after_append_rolloff_and_replace():
    value = chart.line([{"x": 1, "y": 0, "lo": -1, "hi": 1}], x="x", y="y").band(
        lower="lo", upper="hi"
    )
    _, proxy, _, messages = await controller(value)
    await proxy.append(
        [{"x": 2, "y": None, "lo": None, "hi": None}, {"x": 3, "y": 2, "lo": 1, "hi": 3}],
        max_rows=2,
    )
    assert messages[-1][1]["data"]["bounds"] == [[None, None], [1, 3]]
    assert proxy._chart.to_spec()["band"]["bounds"] == [[None, None], [1, 3]]
    await proxy.replace_data([{"x": 4, "y": 3, "lo": 2, "hi": 4}])
    assert proxy._chart.to_spec()["band"]["bounds"] == [[2, 4]]
    assert proxy._chart.band(lower="lo", upper="hi").to_spec()["band"]["bounds"] == [[2, 4]]
    with pytest.raises(ValueError):
        await proxy.append([{"x": 5, "y": 2}])


@pytest.mark.asyncio
async def test_concurrent_appends_are_ordered_and_full_render_wins():
    messages = []

    async def send(kind, message):
        await asyncio.sleep(0)
        messages.append(message)

    value = chart.scatter({"x": [1], "y": [1], "id": ["a"]}, x="x", y="y", key="id")
    renderer, proxy, full, _ = await controller(value, send)
    await asyncio.gather(
        proxy.append([{"x": 2, "y": 2, "id": "b"}]), proxy.append([{"x": 3, "y": 3, "id": "c"}])
    )
    assert [m["base"] for m in messages] == [0, 1]
    assert proxy.row_count == 3

    entered, finish = asyncio.Event(), asyncio.Event()

    async def blocked(kind, message):
        entered.set()
        await finish.wait()

    renderer._session.send_custom_message = blocked
    task = asyncio.create_task(proxy.append([{"x": 4, "y": 4, "id": "d"}]))
    await entered.wait()
    newer = await renderer.transform(value)
    finish.set()
    await task
    assert newer["stream"]["token"] != full["stream"]["token"]
    assert proxy.row_count == 1 and proxy._sequence == 0


@pytest.mark.asyncio
async def test_unrendered_proxy_and_histogram_have_actionable_errors():
    renderer = render_chart()
    assert not renderer.proxy().ready
    with pytest.raises(RuntimeError, match="Render the chart"):
        await renderer.proxy().append([])
    _, proxy, _, _ = await controller(chart.histogram({"x": [1, 2]}, x="x"))
    with pytest.raises(ValueError, match="full render"):
        await proxy.replace_data({"x": [3]})


@pytest.mark.asyncio
async def test_empty_append_can_shrink_a_rolling_window():
    _, proxy, _, messages = await controller(chart.line({"x": [1, 2], "y": [3, 4]}, x="x", y="y"))
    await proxy.append([], max_rows=1)
    assert proxy.row_count == 1 and proxy._chart.to_spec()["rows"] == [[2, 4]]
    assert messages[0][1]["data"]["rows"] == []


def test_integer_keys_must_survive_json_transport_exactly():
    with pytest.raises(ValueError, match="JavaScript-safe"):
        chart.scatter({"x": [1], "y": [2], "id": [2**53 + 1]}, x="x", y="y", key="id")
    value = chart.scatter({"x": [1], "y": [2], "id": [str(2**53 + 1)]}, x="x", y="y", key="id")
    assert value.to_spec()["rows"][0][2] == str(2**53 + 1)


@pytest.mark.asyncio
async def test_pie_proxy_retains_hover_and_rejects_negative_or_bad_formatted_values():
    value = chart.pie(
        [{"name": "A", "y": 1, "share": 0.5}], names="name", values="y", tooltip=["share"]
    ).hover(formats={"share": "percent:0"})
    renderer, proxy, full, messages = await controller(value)
    await proxy.replace_data([{"name": "B", "y": 2, "share": 0.7}])
    assert proxy._chart.to_spec()["hover"] == value.to_spec()["hover"]
    with pytest.raises(ValueError, match="nonnegative"):
        await proxy.replace_data([{"name": "B", "y": -1, "share": 0.7}])
    with pytest.raises(ValueError, match="numbers"):
        await proxy.replace_data([{"name": "B", "y": 1, "share": "invalid"}])
    assert proxy._sequence == 1


@pytest.mark.asyncio
async def test_bar_updates_retain_line_snapshot_and_reject_label_collision():
    combined = chart.bar({"m": ["Mar"], "n": [2], "g": ["A"]}, x="m", y="n", color="g").line(
        {"m": ["Mar"], "total": [3]}, y="total", label="Forecast"
    )
    renderer, proxy, full, messages = await controller(combined)
    await proxy.replace_data({"m": ["Apr"], "n": [4], "g": ["A"]})
    assert proxy._chart.to_spec()["line"] == combined.to_spec()["line"]
    before = proxy._sequence
    with pytest.raises(ValueError, match="group names"):
        await proxy.replace_data({"m": ["Apr"], "n": [4], "g": ["Forecast"]})
    assert proxy._sequence == before
    assert len(messages) == 1
