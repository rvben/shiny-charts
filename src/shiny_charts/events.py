"""Typed Shiny selection contract. Input IDs are <output_id>_selection/click."""

from __future__ import annotations

from typing import Literal, TypedDict

Scalar = str | int | float | bool | None
Key = str | int | float
Revision = str | int


class Event(TypedDict):
    revision: Revision


class RecordSelection(Event):
    kind: Literal["records"]
    keys: list[Key]
    x: Scalar
    y: Scalar
    group: Scalar
    row: int


class CategorySelection(Event):
    kind: Literal["category"]
    keys: list[Key]
    x: Scalar
    y: Scalar
    group: Scalar
    row: int


class BinRange(TypedDict):
    min: float
    max: float
    upper_inclusive: bool


class BinSelection(Event):
    kind: Literal["bin"]
    range: BinRange
    count: int


class Rectangle(TypedDict):
    x: list[float]
    y: list[float]


class RangeSelection(Event):
    kind: Literal["range"]
    range: Rectangle
    count: int
    keys: list[Key]
    truncated: bool


class ClearSelection(Event):
    kind: Literal["clear"]
    keys: list[Key]


Selection = RecordSelection | CategorySelection | BinSelection | RangeSelection | ClearSelection
