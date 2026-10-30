from __future__ import annotations

from htmltools import HTMLDependency, Tag, css, tags
from shiny import ui
from shiny.module import resolve_id
from shiny.render.renderer import Renderer, ValueFn
from shiny.types import Jsonifiable

from ._proxy import ChartProxy
from ._version import __version__
from ._wire import pack
from .chart import Chart


def dependency() -> HTMLDependency:
    return HTMLDependency(
        name="shiny-charts",
        version=__version__,
        source={"package": "shiny_charts", "subdir": "www"},
        script={"src": "shiny-charts.js"},
        stylesheet={"href": "shiny-charts.css"},
    )


DEFAULT_EMPTY_MESSAGE = "No data for this filter. Adjust the dashboard filters to show records."


def output_chart(
    id: str,
    *,
    height: str | None = None,
    width: str = "100%",
    empty_message: str = DEFAULT_EMPTY_MESSAGE,
) -> Tag:
    """Create a Core chart output, with a host-specific no-data message."""
    if not isinstance(empty_message, str) or not empty_message.strip():
        raise ValueError("empty_message must be a non-empty string")
    tag = tags.div(
        dependency(),
        tags.div("Loading chart…", class_="sc-loading", role="status"),
        id=resolve_id(id),
        class_="shiny-charts-output",
        data_empty_message=empty_message,
        style=css(height=height, width=width),
    )
    tag = ui.fill.as_fillable_container(tag)
    return ui.fill.as_fill_item(tag) if height is None else tag


class render_chart(Renderer[Chart]):
    """Render a semantic Chart through a native Shiny output binding, Core or Express."""

    def __init__(
        self,
        _fn: ValueFn[Chart | None] | None = None,
        *,
        height: str | None = None,
        empty_message: str = DEFAULT_EMPTY_MESSAGE,
    ):
        if not isinstance(empty_message, str) or not empty_message.strip():
            raise ValueError("empty_message must be a non-empty string")
        self.empty_message = empty_message
        self.height = height
        self._proxy = ChartProxy(self)
        super().__init__(_fn)

    def proxy(self) -> ChartProxy:
        """Return the session-local controller for data updates after first render."""
        return self._proxy

    async def render(self) -> Jsonifiable:
        try:
            result = await super().render()
        except Exception:
            self._proxy._invalidate()
            raise
        if result is None:
            self._proxy._invalidate()
        return result

    def auto_output_ui(self) -> Tag:
        return output_chart(self.output_id, height=self.height, empty_message=self.empty_message)

    async def transform(self, value: Chart) -> Jsonifiable:
        if not isinstance(value, Chart):
            raise TypeError("render_chart expects a shiny_charts.chart.Chart")
        # Optional local/native adapters can serialize retained columns without
        # allocating one Python object per cell. Shiny still encodes the envelope.
        native_json = getattr(value, "native_json", None)
        if callable(native_json):
            return {
                "spec_json": native_json(),
                "height": self.height,
                "stream": self._proxy._reset(value),
            }
        return {"spec": pack(value), "height": self.height, "stream": self._proxy._reset(value)}
