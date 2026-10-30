"""Lossless dictionary encoding for repeated categorical values on the Shiny wire."""

from __future__ import annotations

from typing import Any

from .chart import Chart


def pack(value: Chart) -> dict[str, Any]:
    spec = value.to_spec()
    dictionaries = {}
    for index, name in enumerate(spec["columns"]):
        values = [row[index] for row in spec["rows"]]
        if not values or not all(isinstance(v, str) for v in values):
            continue
        unique = list(dict.fromkeys(values))
        original_cost = sum(len(v) + 2 for v in values)
        encoded_cost = sum(len(v) + 3 for v in unique) + len(values) * (len(str(len(unique))) + 1)
        if encoded_cost + 40 >= original_cost:
            continue
        dictionaries[name] = unique
        lookup = {v: i for i, v in enumerate(unique)}
        for row in spec["rows"]:
            row[index] = lookup[row[index]]
    if dictionaries:
        spec["dictionaries"] = dictionaries
    return spec
