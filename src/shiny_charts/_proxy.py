"""Session-local, ordered data updates for an existing chart output."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ._wire import pack
from .chart import Chart, _line_label, _make

if TYPE_CHECKING:
    from ._render import render_chart


def _data_chart(current: Chart, data: Any) -> Chart:
    spec = current._spec
    if spec["kind"] == "histogram":
        raise ValueError("Histogram data updates require a full render to recompute bins")
    encoding = spec["encoding"]
    fresh = _make(
        spec["kind"],
        data,
        **encoding,
        tooltip=spec["tooltip"],
        x_type=spec["x_type"],
        stacked=spec["stacked"],
    )
    if "line" in spec:
        _line_label(fresh._spec, spec["line"]["label"])
    hover = spec.get("hover", {})
    for field, fmt in hover.get("formats", {}).items():
        fresh._hover_field(field, fmt)
    for token in hover.get("tokens", []):
        if "format" in token:
            fresh._hover_field(token["field"], token["format"])
    if "band" in spec:
        band = spec["band"]
        fresh = fresh.band(lower=band["lower"], upper=band["upper"], label=band["label"])
    metadata = {k: v for k, v in spec.items() if k not in ("rows", "band")}
    return replace(
        fresh,
        _spec={
            **metadata,
            "rows": fresh._spec["rows"],
            **({"band": fresh._spec["band"]} if "band" in spec else {}),
        },
    )


class ChartProxy:
    """Use ``renderer.proxy()`` inside a Shiny server to obtain this controller.

    Async methods send data only and retain the rendered definition. A successful
    send is not a browser acknowledgement; inspect ``<id>_update`` for application.
    A full render starts a new generation and supersedes its earlier updates.
    """

    def __init__(self, renderer: render_chart):
        self._renderer = renderer
        self._chart: Chart | None = None
        self._token = ""
        self._sequence = 0
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        """Whether a successful full render has established a server snapshot."""
        return self._chart is not None

    @property
    def row_count(self) -> int:
        """Number of rows in the latest server-side snapshot; zero before rendering."""
        return len(self._chart._spec["rows"]) if self._chart is not None else 0

    def _reset(self, value: Chart) -> dict[str, Any]:
        self._chart = value
        self._token = uuid4().hex
        self._sequence = 0
        return {"token": self._token, "sequence": 0}

    def _invalidate(self) -> None:
        self._chart = None
        self._token = ""
        self._sequence = 0

    async def replace_data(self, data: Any) -> None:
        """Replace displayed records, preserving encodings, formatting, and view."""
        await self._update("replace", data)

    async def append(self, data: Any, *, max_rows: int | None = None) -> None:
        """Append records; optional positive ``max_rows`` retains the newest rows.

        Existing keys cannot be reused, even when their older rows would roll off.
        The row limit spans all groups and uses arrival order, not sorted x values.
        """
        if max_rows is not None and (
            isinstance(max_rows, bool)
            or not isinstance(max_rows, int)
            or not 1 <= max_rows <= 2**53 - 1
        ):
            raise ValueError("max_rows must be a positive JavaScript-safe integer or None")
        await self._update("append", data, max_rows=max_rows)

    async def _update(self, operation: str, data: Any, *, max_rows: int | None = None) -> None:
        async with self._lock:
            current = self._chart
            session = self._renderer._session
            if current is None or session is None:
                raise RuntimeError("Render the chart in an active Shiny session before updating it")
            fresh = _data_chart(current, data)
            if (
                operation == "append"
                and not fresh._spec["rows"]
                and (max_rows is None or len(current._spec["rows"]) <= max_rows)
            ):
                return
            candidate = fresh
            if operation == "append":
                key = current._spec["encoding"]["key"]
                if key:
                    ki = current._spec["columns"].index(key)
                    existing = {row[ki] for row in current._spec["rows"]}
                    if any(row[ki] in existing for row in fresh._spec["rows"]):
                        raise ValueError(
                            "Appended keys must be unique across the displayed dataset"
                        )
                rows = [*current._spec["rows"], *fresh._spec["rows"]]
                source = (*current._source, *fresh._source)
                metadata = {**current._spec, "rows": rows[-max_rows:] if max_rows else rows}
                if "band" in metadata:
                    bounds = [*current._spec["band"]["bounds"], *fresh._spec["band"]["bounds"]]
                    metadata["band"] = {
                        **metadata["band"],
                        "bounds": bounds[-max_rows:] if max_rows else bounds,
                    }
                candidate = Chart(metadata, source[-max_rows:] if max_rows else source)
            wire = pack(fresh)
            token, sequence = self._token, self._sequence
            message = {
                "id": str(session.ns(self._renderer.output_id)),
                "token": token,
                "base": sequence,
                "sequence": sequence + 1,
                "operation": operation,
                "max_rows": max_rows,
                "data": {k: wire[k] for k in ("columns", "rows", "dictionaries") if k in wire},
            }
            if "band" in wire:
                message["data"]["bounds"] = wire["band"]["bounds"]
            # Commit only after successful transport. A concurrent full render
            # owns its new generation and must not be overwritten on return.
            await session.send_custom_message("shiny-charts:update", message)
            if self._token == token:
                self._chart = candidate
                self._sequence = sequence + 1
