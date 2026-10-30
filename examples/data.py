"""Deterministic synthetic data shared by both rendering engines."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

WORKLOADS = ["Customer experience", "Knowledge platform", "Engineering copilot"]
PALETTE = ["#087eac", "#a45ac4", "#bd6500", "#118570", "#ce5069", "#5c74ca"]


def color_for(name: str) -> str:
    value = 2166136261
    for letter in name:
        value = ((value ^ ord(letter)) * 16777619) & 0xFFFFFFFF
    return PALETTE[value % len(PALETTE)]


def requests(n: int = 2400, update: int = 0) -> list[dict]:
    rng = random.Random(43)
    rows = []
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for i in range(n):
        group = i % 3
        day = i * 30 // n
        latency = max(90, rng.lognormvariate(6.3 + group * 0.12, 0.38))
        cost = max(0.003, (0.027 + group * 0.008) * (1.3 - day / 90) + rng.gauss(0, 0.006))
        cost *= 1 + update * 0.008
        rows.append(
            {
                "id": f"req-{i:06d}",
                "date": start + timedelta(days=day),
                "workload": WORKLOADS[group],
                "latency": round(latency, 1),
                "cost": round(cost, 5),
                "success": rng.random() > 0.07 + group * 0.025,
            }
        )
    return rows


def trends(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["workload"], row["date"])].append(row)
    output = []
    for (workload, day), items in sorted(groups.items()):
        mean = sum(r["cost"] for r in items) / len(items)
        error = (
            1.96
            * math.sqrt(sum((r["cost"] - mean) ** 2 for r in items) / max(1, len(items) - 1))
            / math.sqrt(len(items))
        )
        output.append(
            {
                "date": day,
                "workload": workload,
                "cost": mean,
                "low": mean - error,
                "high": mean + error,
            }
        )
    return output


def spend(rows: list[dict]) -> list[dict]:
    return [
        {"workload": name, "spend": sum(r["cost"] for r in rows if r["workload"] == name)}
        for name in WORKLOADS
    ]
