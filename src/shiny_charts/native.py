"""Experimental opt-in fluent chart API over retained Polars Arrow buffers."""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from shiny_charts import chart as python_chart
from shiny_charts.chart import Chart

try:
    from _shiny_charts_native import Columns
except ImportError as exc:
    raise ImportError(
        "Install shiny-charts[native]==0.5.0b1 to use the experimental native backend"
    ) from exc


class Rows(Sequence):
    def __init__(self, columns):
        self.columns = columns
        self._rows = None

    def __len__(self):
        return self.columns.count

    def _materialize(self):
        if self._rows is None:
            self._rows = json.loads(self.columns.json("{}", False))["rows"]
        return self._rows

    def __getitem__(self, index):
        return self._materialize()[index]

    def __iter__(self):
        return iter(self._materialize())


class Source(Sequence):
    def __init__(self, frame):
        self.frame = frame.clone()

    def __len__(self):
        return len(self.frame)

    def __getitem__(self, index):
        return self.frame.row(index, named=True)

    def __iter__(self):
        return iter(self.frame.to_dicts())


@dataclass(frozen=True)
class NativeChart(Chart):
    _columns: object = field(default=None, repr=False)

    def native_json(self):
        if not isinstance(self._spec["rows"], Rows):
            from shiny_charts._wire import pack

            return json.dumps(pack(Chart(self._spec, self._source)))
        metadata = {k: v for k, v in self._spec.items() if k != "rows"}
        return self._columns.json(json.dumps(metadata))

    def to_spec(self):
        if not isinstance(self._spec["rows"], Rows):
            return Chart(self._spec, self._source).to_spec()
        metadata = {k: v for k, v in self._spec.items() if k != "rows"}
        return json.loads(self._columns.json(json.dumps(metadata), False))


class Builders:
    def __getattr__(self, name):
        original = getattr(python_chart, name)
        if name not in ("bar", "scatter", "line", "area", "pie"):
            return original

        def build(data, **kwargs):
            # Restrict this prototype to Polars' CPU stream producer. Other input
            # types and unsupported Arrow types preserve the reference path.
            if type(data).__module__.split(".")[0] != "polars":
                return original(data, **kwargs)
            x = kwargs.get("names") if name == "pie" else kwargs["x"]
            y = kwargs.get("values") if name == "pie" else kwargs["y"]
            if name == "pie":
                return original(data, **kwargs)  # pie adapts encodings separately
            tooltip = tuple(kwargs.get("tooltip", ()))
            kwargs = {**kwargs, "tooltip": tooltip}
            fields = list(
                dict.fromkeys(
                    [
                        x,
                        y,
                        *([kwargs["color"]] if kwargs.get("color") else []),
                        *([kwargs["key"]] if kwargs.get("key") else []),
                        *tooltip,
                    ]
                )
            )
            empty = original([], **kwargs)
            spec = copy.deepcopy(empty._spec)
            if name in ("line", "area") and not kwargs.get("x_type"):
                col = data.get_column(x) if x in data.columns else None
                numeric = col is not None and (
                    col.dtype.is_numeric() or str(col.dtype) == "Boolean"
                )
                usable = col is not None and col.null_count() < len(col)
                if col is not None and str(col.dtype) == "Float64":
                    usable = bool(col.is_finite().any())
                spec["x_type"] = "value" if numeric and usable else "category"
            missing = [name for name in fields if name not in data.columns]
            if missing:
                raise ValueError(f"Missing chart columns: {', '.join(missing)}")
            # Polars' untyped Null C stream is incompatible with this Arrow
            # importer. Typed nullable columns retain the native path.
            if any(str(data.get_column(name).dtype) == "Null" for name in fields):
                return original(data, **kwargs)
            try:
                native = Columns(
                    data.select(fields),
                    fields,
                    y,
                    spec["x_type"] == "value",
                    kwargs.get("key"),
                    False,
                )
            except NotImplementedError:
                return original(data, **kwargs)
            spec["rows"] = Rows(native)
            source = Source(data) if name in ("line", "area") else ()
            return NativeChart(spec, source, native)

        return build


chart = Builders()


def is_native(value: Chart) -> bool:
    """Whether a chart retains native columns (unsupported inputs fall back)."""
    return isinstance(value, NativeChart) and isinstance(value._spec["rows"], Rows)
