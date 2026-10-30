"""Deterministic synthetic service observations, including missing measurements."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

QUEUES = (
    "Enterprise onboarding and access provisioning",
    "Billing, refunds and subscription changes",
    "API integrations and developer support",
    "International orders and delivery exceptions",
    "Security reviews and account recovery",
    "Partner operations and marketplace enquiries",
)
CHANNELS = ("Email", "Chat", "Phone")
ORIGIN = datetime(2026, 9, 1, tzinfo=timezone.utc)


def observations(start: int, count: int, *, gaps: bool = True) -> list[dict]:
    rows = []
    for i in range(start, start + count):
        channel = CHANNELS[i % 3]
        queue = QUEUES[(i // 3) % len(QUEUES)]
        response = round(3 + (i * 37 % 360) / 10 + (i % 3) * 4, 1)
        # Whole missing dates make gaps visible in aggregate trends as well.
        missing = gaps and (i % 17 == 0 or (i // 80) % 14 == 6)
        rows.append(
            {
                "id": f"obs-{i:07d}",
                "time": ORIGIN + timedelta(minutes=i * 18),
                "queue": queue,
                "channel": channel,
                "response": None if missing else response,
                "resolution": None if missing else round(response * (1.4 + i % 7 / 10), 1),
                "handled": i % 5 + 1,
            }
        )
    return rows


def daily(rows: list[dict], *, by_channel: bool = True) -> list[dict]:
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row["time"].date(), row["channel"] if by_channel else "All")].append(row)
    result = []
    for (day, channel), records in sorted(buckets.items()):
        values = [r["response"] for r in records if r["response"] is not None]
        result.append(
            {
                "day": day,
                "channel": channel,
                "response": round(sum(values) / len(values), 2) if values else None,
                "handled": sum(r["handled"] for r in records),
            }
        )
    return result


def queue_totals(rows: list[dict]) -> list[dict]:
    counts = defaultdict(int)
    for row in rows:
        counts[row["queue"]] += row["handled"]
    return [{"queue": queue, "handled": counts[queue]} for queue in QUEUES if queue in counts]
