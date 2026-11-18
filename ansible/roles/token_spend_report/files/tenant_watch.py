#!/usr/bin/env python3
"""Publish the factory quota result from the committed pool guard."""

from __future__ import annotations

import datetime as dt
from typing import Any

from spend_staleness import factory_slot, pool_line, pool_over, pool_slots


def factory_quota(factory: str) -> dict[str, Any]:
    """Return the quota fields consumed by the dispatcher-facing tenant watch."""
    now = dt.datetime.now(dt.timezone.utc)
    pool = pool_slots()
    reads = {slot: factory_slot(slot, now) for slot in pool}
    held = pool_over(reads.values())
    over_slots = [slot for slot, read in reads.items() if read.get("over") is True]
    current = reads.get(factory, factory_slot(factory, now))
    return {
        "quota.factory_over": int(held),
        "quota.factory_slot_over": ",".join(over_slots) or "none",
        "quota.factory_pool": ",".join(pool),
        "quota.factory_line": pool_line(current, over_slots, held),
    }
