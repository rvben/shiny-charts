"""A small semantic chart API. No rendering-engine options in the public spec."""

from __future__ import annotations

import copy
import math
import re
import string
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from numbers import Real
from typing import Any


def _scalar(value: Any) -> Any:
    kind = type(value)
    if kind in (str, int, bool):
        return value
    if kind is float:
        return value if math.isfinite(value) else None
    if value is None or kind.__name__ in ("NAType", "NaTType"):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat() + "T00:00:00+00:00"
    if hasattr(value, "item"):
        return _scalar(value.item())
    if isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported chart value {type(value).__name__}; use scalar columns")


def _records(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dicts"):
        data = data.to_dicts()
    elif hasattr(data, "to_dict") and not isinstance(data, Mapping):
        data = data.to_dict(orient="records")
    if isinstance(data, Mapping):
        columns = {str(k): list(v) for k, v in data.items()}
        if len({len(v) for v in columns.values()}) > 1:
            raise ValueError("Chart columns must have equal lengths")
        data = [
            dict(zip(columns, row, strict=False)) for row in zip(*columns.values(), strict=False)
        ]
    if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
        raise TypeError("Expected records, a column mapping, or a pandas/polars DataFrame")
    return [dict(row) for row in data]


def _numeric(value: Any, field: str) -> None:
    # _scalar has already converted NumPy/pandas numbers to Python primitives.
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValueError(f"Column {field!r} must contain numbers or missing values")


def _format(value: str) -> str:
    if not re.fullmatch(
        r"(?:number(?::[0-6])?|percent(?::[0-6])?|currency:[A-Z]{3}(?::[0-6])?)", value
    ):
        raise ValueError(
            "Format must be number[:digits], percent[:digits], or currency:USD[:digits]"
        )
    return value


def _finite_number(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")


def _axis_x(spec: dict[str, Any], value: Any) -> Any:
    value = _scalar(value)
    if spec["x_type"] == "value":
        _finite_number(value, "X coordinate")
    elif spec["x_type"] == "time":
        if not isinstance(value, str):
            raise ValueError("Time x coordinates must be ISO dates or datetimes")
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Time x coordinates must be ISO dates or datetimes") from error
        value = _scalar(stamp)
    elif value is None or isinstance(value, bool):
        raise ValueError("Category x coordinates must be strings or numbers")
    return value


def _group_name(value: Any) -> str:
    """Match JS String() for scalar group names, including bool/integer floats."""
    if value is None:
        return "Missing"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        value = float(value)
        if value == 0:
            return "0"
        if value.is_integer() and abs(value) < 1e21:
            return str(int(value))
        text = str(value)
        if "e" in text:
            mantissa, exponent = text.split("e")
            power = int(exponent)
            if 1e-6 <= abs(value) < 1e21:
                sign = "-" if mantissa.startswith("-") else ""
                whole, _, fraction = mantissa.lstrip("-").partition(".")
                digits = whole + fraction
                point = len(whole) + power
                return sign + (
                    "0." + "0" * -point + digits
                    if point <= 0
                    else digits[:point] + "." + digits[point:]
                )
            return (
                mantissa.removesuffix(".0") + "e" + ("+" if power >= 0 else "-") + str(abs(power))
            )
        return text
    return str(value)


def _line_label(spec: dict[str, Any], label: str) -> None:
    ci = spec["columns"].index(spec["encoding"]["color"]) if spec["encoding"]["color"] else -1
    collision = (
        any(_group_name(row[ci]) == label for row in spec["rows"])
        if ci >= 0
        else label == spec["labels"]["y"]
    )
    if collision:
        raise ValueError("Line label must differ from bar group names")


@dataclass(frozen=True)
class Chart:
    _spec: dict[str, Any]
    _source: tuple[dict[str, Any], ...] = ()

    def _with(self, **changes: Any) -> Chart:
        return replace(self, _spec={**self._spec, **changes})

    def to_spec(self) -> dict[str, Any]:
        """Return an independent, JSON-safe snapshot."""
        # Rows contain only immutable JSON scalars. Copy their containers without
        # recursively visiting every number/string in a large scatter dataset.
        spec = copy.deepcopy({k: v for k, v in self._spec.items() if k != "rows"})
        spec["rows"] = [row.copy() for row in self._spec["rows"]]
        return spec

    def line(
        self,
        data: Any,
        *,
        y: str,
        label: str,
        x: str | None = None,
        tooltip: Iterable[str] = (),
    ) -> Chart:
        """Add one non-selectable line over vertical category bars on shared axes.

        One row per category; null/missing categories create gaps. Bar proxy
        updates retain this overlay; fully re-render to change its own data.
        """
        if (
            self._spec["kind"] != "bar"
            or self._spec["x_type"] != "category"
            or self._spec.get("orientation") == "horizontal"
        ):
            raise ValueError("Line overlays require vertical bars with a category x axis")
        if "line" in self._spec:
            raise ValueError("Only one shared-axis line overlay is supported")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Line label must be a non-empty string")
        _line_label(self._spec, label)
        overlay = _make(
            "line",
            data,
            x=x or self._spec["encoding"]["x"],
            y=y,
            tooltip=tooltip,
            x_type="category",
        ).to_spec()
        xi = overlay["columns"].index(overlay["encoding"]["x"])
        seen = set()
        for row in overlay["rows"]:
            value = _axis_x(self._spec, row[xi])
            if value in seen:
                raise ValueError("Line overlay x values must be unique; aggregate first")
            seen.add(value)
        return self._with(
            line={
                "label": label,
                **{k: overlay[k] for k in ("columns", "rows", "encoding", "tooltip")},
            }
        )

    def format(self, *, x: str | None = None, y: str | None = None) -> Chart:
        formats = {**self._spec["formats"]}
        for axis, value in (("x", x), ("y", y)):
            if value is not None:
                formats[axis] = _format(value)
        return self._with(formats=formats)

    def palette(self, groups: Mapping[str, int]) -> Chart:
        """Assign named groups to one-based inherited palette slots (1 through 12)."""
        slots = dict(groups)
        if any(
            not isinstance(name, str)
            or isinstance(slot, bool)
            or not isinstance(slot, int)
            or not 1 <= slot <= 12
            for name, slot in slots.items()
        ):
            raise ValueError("Palette groups must map string names to integer slots 1 through 12")
        return self._with(palette=slots)

    def labels(
        self, *, x: str | None = None, y: str | None = None, title: str | None = None
    ) -> Chart:
        labels = {
            **self._spec["labels"],
            **{k: v for k, v in (("x", x), ("y", y), ("title", title)) if v is not None},
        }
        if "line" in self._spec:
            _line_label({**self._spec, "labels": labels}, self._spec["line"]["label"])
        return self._with(labels=labels)

    def domain(
        self,
        *,
        x: tuple[float | None, float | None] | None = None,
        y: tuple[float | None, float | None] | None = None,
    ) -> Chart:
        """Set numeric axis bounds; None on either side retains the automatic bound."""
        if self._spec["kind"] == "pie":
            raise ValueError("Pie charts do not have axis domains")
        domains = {**self._spec.get("domain", {})}
        for axis, bounds in (("x", x), ("y", y)):
            if bounds is None:
                continue
            if axis == "x" and self._spec["x_type"] != "value":
                raise ValueError("An x domain requires a numeric value axis")
            if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
                raise ValueError("Domain bounds must be a (min, max) pair")
            lo, hi = bounds
            if any(
                v is not None
                and (isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v))
                for v in bounds
            ):
                raise ValueError("Domain bounds must be finite numbers or None")
            if lo is not None and hi is not None and lo >= hi:
                raise ValueError("Domain minimum must be less than maximum")
            domains[axis] = [float(v) if v is not None else None for v in bounds]
        return self._with(domain=domains)

    def ticks(self, *, x_rotation: float = 0, x_labels: str = "auto") -> Chart:
        """Rotate ticks and choose auto thinning, all labels, or word wrapping."""
        if self._spec["kind"] == "pie":
            raise ValueError("Pie charts do not have axis ticks")
        if (
            isinstance(x_rotation, bool)
            or not isinstance(x_rotation, Real)
            or not math.isfinite(x_rotation)
            or not -90 <= x_rotation <= 90
        ):
            raise ValueError("Tick rotation must be a finite number from -90 to 90")
        if x_labels not in ("auto", "all", "wrap"):
            raise ValueError("Tick x_labels must be auto, all, or wrap")
        ticks = {"x_rotation": float(x_rotation)}
        if x_labels != "auto":
            ticks["x_labels"] = x_labels
        return self._with(ticks=ticks)

    def value_labels(self, *, show: bool = True, totals: bool = False) -> Chart:
        """Display formatted bar values and, optionally, positive/negative stack totals."""
        if self._spec["kind"] != "bar":
            raise ValueError("Value labels require a bar chart")
        if not isinstance(show, bool) or not isinstance(totals, bool):
            raise TypeError("Value-label options must be booleans")
        if totals and not self._spec["stacked"]:
            raise ValueError("Stack totals require stacked bars")
        return self._with(value_labels={"show": show, "totals": totals})

    def legend(
        self,
        *,
        order: Iterable[str] | None = None,
        placement: str | None = None,
        layout: str | None = None,
    ) -> Chart:
        """Order groups and choose top/bottom placement or wrapping/scrolling."""
        options = {**self._spec.get("legend", {})}
        if order is not None:
            if isinstance(order, (str, bytes)):
                raise TypeError("Legend order must be an iterable of group names")
            names = list(order)
            if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
                raise ValueError("Legend order must contain unique string names")
            options["order"] = names
        if placement is not None:
            if placement not in ("top", "bottom"):
                raise ValueError("Legend placement must be top or bottom")
            options["placement"] = placement
        if layout is not None:
            if layout not in ("wrap", "scroll"):
                raise ValueError("Legend layout must be wrap or scroll")
            options["layout"] = layout
        return self._with(legend=options)

    def hover(
        self,
        *,
        template: str | None = None,
        formats: Mapping[str, str] | None = None,
    ) -> Chart:
        """Use escaped literal templates and numeric column formats in hover text.

        Fields must already be encoded or included via the builder's tooltip=.
        Templates use {column} or {column:percent:1}; double braces are literal.
        No HTML, expressions, attribute access or format conversions are evaluated.
        """
        options = {**self._spec.get("hover", {})}
        column_formats = {**options.get("formats", {}), **(formats or {})}
        for field, fmt in column_formats.items():
            self._hover_field(field, _format(fmt))
        options["formats"] = column_formats
        if template is not None:
            if not isinstance(template, str) or not template.strip():
                raise ValueError("Hover template must be a non-empty string")
            tokens = []
            try:
                for text, field, fmt, conversion in string.Formatter().parse(template):
                    if text:
                        tokens.append({"text": text})
                    if field is not None:
                        if conversion is not None:
                            raise ValueError("Hover template conversions are not supported")
                        self._hover_field(field, _format(fmt) if fmt else None)
                        tokens.append({"field": field, **({"format": fmt} if fmt else {})})
            except ValueError as error:
                raise ValueError(f"Invalid hover template: {error}") from error
            options.update(template=template, tokens=tokens)
        return self._with(hover=options)

    def _hover_field(self, field: str, fmt: str | None) -> None:
        if field not in self._spec["columns"]:
            raise ValueError("Hover fields must name encoded or tooltip columns")
        if fmt:
            index = self._spec["columns"].index(field)
            for row in self._spec["rows"]:
                _numeric(row[index], field)

    def annotate(self, *, x: Any, y: float | str, text: str, position: str = "top") -> Chart:
        """Add plain text at data y, or at the plot edge with y="top"/"bottom"."""
        if self._spec["kind"] == "pie":
            raise ValueError("Plot annotations require a Cartesian chart")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Annotation text must be a non-empty string")
        if position not in ("top", "bottom", "left", "right", "inside"):
            raise ValueError("Annotation position must be top, bottom, left, right or inside")
        if isinstance(y, str):
            if y not in ("top", "bottom") or self._spec.get("orientation") == "horizontal":
                raise ValueError("Plot-edge annotation y must be top or bottom on a vertical chart")
        else:
            _finite_number(y, "Annotation y")
        annotation = {
            "x": _axis_x(self._spec, x),
            "y": y if isinstance(y, str) else float(y),
            "text": text,
            "position": position,
        }
        return self._with(annotations=[*self._spec.get("annotations", []), annotation])

    def data_table(self, *, hide: Iterable[str] = ()) -> Chart:
        """Hide columns in View data; data transport, tooltips and CSV are unchanged."""
        if isinstance(hide, (str, bytes)):
            raise TypeError("Hidden columns must be an iterable of column names")
        names = list(hide)
        if any(not isinstance(name, str) or name not in self._spec["columns"] for name in names):
            raise ValueError("Hidden columns must name encoded or tooltip columns")
        return self._with(data_table={"hide": list(dict.fromkeys(names))})

    def view(self, revision: str | int = "default", *, zoom: bool = True) -> Chart:
        """Preserve view state at the same revision. Zoom defaults to True; opt out explicitly."""
        if not isinstance(revision, (str, int)):
            raise TypeError("View revision must be a string or integer")
        return self._with(view={"revision": revision, "zoom": bool(zoom)})

    def select(self, *, brush: bool = False) -> Chart:
        """Enable click events; optional rectangle brush for scatter charts."""
        if brush and self._spec["kind"] != "scatter":
            raise ValueError("Rectangle brushing is currently supported for scatter charts")
        return self._with(selection={"click": True, "brush": bool(brush)})

    def rule(
        self,
        *,
        x: Any = None,
        y: float | None = None,
        x_between: Iterable[Any] | None = None,
        label: str,
    ) -> Chart:
        """Add one reference line at semantic x or y (including date/category x)."""
        if self._spec["kind"] == "pie":
            raise ValueError("Reference rules require a Cartesian chart")
        if sum(value is not None for value in (x, y, x_between)) != 1:
            raise ValueError("A rule requires exactly one of x, y or x_between")
        if not isinstance(label, str):
            raise TypeError("Rule label must be a string")
        if x_between is not None:
            if self._spec["x_type"] != "category":
                raise ValueError("Between-category rules require a category x axis")
            if isinstance(x_between, (str, bytes)):
                raise ValueError("x_between must contain two distinct categories")
            pair = [_axis_x(self._spec, value) for value in x_between]
            if len(pair) != 2 or pair[0] == pair[1]:
                raise ValueError("x_between must contain two distinct categories")
            rule = {"x_between": pair, "label": label}
        elif y is not None:
            _finite_number(y, "Rule y")
            rule = {"y": float(y), "label": label}
        else:
            rule = {"x": _axis_x(self._spec, x), "label": label}
        return self._with(rules=[*self._spec["rules"], rule])

    def band(self, *, lower: str, upper: str, label: str = "Interval") -> Chart:
        """Add a real low/high interval, including intervals crossing zero."""
        if self._spec["kind"] not in ("line", "area"):
            raise ValueError("Bands require a line or area chart")
        bounds = []
        for row in self._source:
            if lower not in row or upper not in row:
                raise ValueError(f"Missing band columns {lower!r} or {upper!r}")
            lo, hi = _scalar(row[lower]), _scalar(row[upper])
            _numeric(lo, lower)
            _numeric(hi, upper)
            if lo is not None and hi is not None and lo > hi:
                raise ValueError("Band lower bound exceeds upper bound")
            bounds.append([lo, hi])
        return self._with(band={"label": label, "bounds": bounds, "lower": lower, "upper": upper})

    def renderer(self, kind: str) -> Chart:
        if kind not in ("svg", "canvas"):
            raise ValueError("Renderer must be svg or canvas")
        return self._with(renderer=kind)


def _make(
    kind: str,
    data: Any,
    *,
    x: str,
    y: str,
    color: str | None = None,
    key: str | None = None,
    tooltip: Iterable[str] = (),
    x_type: str | None = None,
    stacked: bool = False,
) -> Chart:
    source = _records(data)
    tooltip = tuple(tooltip)
    fields = list(
        dict.fromkeys([x, y, *([color] if color else []), *([key] if key else []), *tooltip])
    )
    rows = []
    keys: set[Any] = set()
    time_column = False
    for record in source:
        missing = [field for field in fields if field not in record]
        if missing:
            raise ValueError(f"Missing chart columns: {', '.join(missing)}")
        time_column |= isinstance(record[x], (date, datetime))
        row = [_scalar(record[field]) for field in fields]
        _numeric(row[fields.index(y)], y)
        if kind == "pie" and row[fields.index(y)] is not None and row[fields.index(y)] < 0:
            raise ValueError("Pie values must be nonnegative")
        if kind == "scatter":
            _numeric(row[fields.index(x)], x)
        if key:
            value = row[fields.index(key)]
            if value is None or isinstance(value, bool) or value in keys:
                raise ValueError("Keys must be non-null, unique strings or numbers")
            if isinstance(value, int) and abs(value) > 2**53 - 1:
                raise ValueError("Integer keys must be JavaScript-safe; use strings for large IDs")
            keys.add(value)
        rows.append(row)
    first_x = next((row[fields.index(x)] for row in rows if row[fields.index(x)] is not None), None)
    inferred = (
        "time"
        if time_column
        else (
            "value"
            if kind == "scatter" or (kind in ("line", "area") and isinstance(first_x, (int, float)))
            else "category"
        )
    )
    axis_type = x_type or inferred
    if axis_type not in ("time", "value", "category"):
        raise ValueError("x_type must be time, value, or category")
    if axis_type == "value":
        for row in rows:
            _numeric(row[fields.index(x)], x)
    return Chart(
        {
            "version": 1,
            "kind": kind,
            "columns": fields,
            "rows": rows,
            "encoding": {"x": x, "y": y, "color": color, "key": key},
            "x_type": axis_type,
            **({"x_temporal": True} if time_column and axis_type == "category" else {}),
            "stacked": stacked,
            "formats": {"x": "number", "y": "number"},
            "labels": {
                "x": x.replace("_", " ").capitalize(),
                "y": y.replace("_", " ").capitalize(),
            },
            "view": {"revision": "default", "zoom": kind in ("line", "area", "scatter")},
            "selection": {"click": False, "brush": False},
            "rules": [],
            "renderer": "svg",
            "tooltip": list(tooltip),
        },
        # Only line/area can add a band later. Scatter/bar need no duplicate raw
        # dataset; stable keys and requested tooltip values are already in rows.
        tuple(copy.deepcopy(source)) if kind in ("line", "area") else (),
    )


def line(
    data: Any,
    *,
    x: str,
    y: str,
    color: str | None = None,
    key: str | None = None,
    tooltip: Iterable[str] = (),
    x_type: str | None = None,
) -> Chart:
    return _make("line", data, x=x, y=y, color=color, key=key, tooltip=tooltip, x_type=x_type)


def area(
    data: Any,
    *,
    x: str,
    y: str,
    color: str | None = None,
    key: str | None = None,
    stacked: bool = False,
    x_type: str | None = None,
    tooltip: Iterable[str] = (),
) -> Chart:
    return _make(
        "area",
        data,
        x=x,
        y=y,
        color=color,
        key=key,
        stacked=stacked,
        x_type=x_type,
        tooltip=tooltip,
    )


def bar(
    data: Any,
    *,
    x: str,
    y: str,
    color: str | None = None,
    key: str | None = None,
    stacked: bool = False,
    orientation: str = "vertical",
    tooltip: Iterable[str] = (),
) -> Chart:
    if orientation not in ("vertical", "horizontal"):
        raise ValueError("Bar orientation must be vertical or horizontal")
    return _make(
        "bar",
        data,
        x=x,
        y=y,
        color=color,
        key=key,
        stacked=stacked,
        x_type="category",
        tooltip=tooltip,
    )._with(orientation=orientation)


def scatter(
    data: Any,
    *,
    x: str,
    y: str,
    color: str | None = None,
    key: str | None = None,
    tooltip: Iterable[str] = (),
) -> Chart:
    return _make("scatter", data, x=x, y=y, color=color, key=key, tooltip=tooltip, x_type="value")


def pie(
    data: Any,
    *,
    names: str,
    values: str,
    key: str | None = None,
    tooltip: Iterable[str] = (),
) -> Chart:
    """Create nonnegative slices; each row retains its original selection key."""
    return _make(
        "pie", data, x=names, y=values, color=names, key=key, tooltip=tooltip, x_type="category"
    )


def histogram(
    data: Any, *, x: str, bins: int = 20, range: tuple[float, float] | None = None
) -> Chart:
    """Aggregate on the server; bin events carry a range/count, never pretend row keys."""
    if not isinstance(bins, int) or isinstance(bins, bool) or not 1 <= bins <= 500:
        raise ValueError("bins must be an integer between 1 and 500")
    source = _records(data)
    values = []
    for row in source:
        if x not in row:
            raise ValueError(f"Missing chart column {x!r}")
        value = _scalar(row[x])
        _numeric(value, x)
        if value is not None:
            values.append(value)
    lo, hi = range or ((min(values), max(values)) if values else (0, 1))
    if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
        raise ValueError("Histogram range must be finite and ordered")
    if lo == hi:
        lo, hi = lo - 0.5, hi + 0.5
    step = (hi - lo) / bins
    counts = [0] * bins
    for value in values:
        if lo <= value <= hi:
            counts[min(bins - 1, int((value - lo) / step))] += 1
    intervals = [[lo + i * step, lo + (i + 1) * step] for i in __builtins_range(bins)]
    records = [
        {"bin": (a + b) / 2, "count": count}
        for (a, b), count in zip(intervals, counts, strict=False)
    ]
    result = _make("histogram", records, x="bin", y="count", x_type="value")
    return result._with(
        intervals=intervals, labels={"x": x.replace("_", " ").capitalize(), "y": "Count"}
    )


# Keep the public histogram range= argument without shadowing the loop primitive.
__builtins_range = range
