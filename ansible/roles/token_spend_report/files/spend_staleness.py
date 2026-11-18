#!/usr/bin/env python3
"""Token-spend quota helpers.

The factory quota hold is deliberately a pool decision.  A CAAM reading is an
account-wide reading, so one exhausted account cannot stop the factory while a
different committed factory credential still has sustainable headroom.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

OVER_SUFFIX = " OVER: release no more factory runs"
FACTORY_POOL_DEFAULT = ("anthropic-4", "anthropic-2")
LIVESPEC_JSONC = "/data/projects/livespec-dev-tooling/.livespec.jsonc"


def pool_slots(path: str | Path = LIVESPEC_JSONC) -> tuple[str, ...]:
    """Return numbered Anthropic slots from committed credential policy.

    JSONC is intentionally parsed only over the policy's `slots` array: the
    file carries comments, so treating it as ordinary JSON would turn a usable
    committed policy into a false unreadable pool.  A missing or malformed
    policy uses the last explicitly known factory pool.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
        policy = text[text.index('"claude_credential_policy"') :]
        slots = policy[policy.index('"slots"') : policy.index("]")]
        found = tuple(
            f"anthropic-{number}"
            for number in re.findall(r"CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_(\d+)", slots)
        )
    except (OSError, ValueError):
        return FACTORY_POOL_DEFAULT
    else:
        return found or FACTORY_POOL_DEFAULT


def pool_over(results: Iterable[Mapping[str, Any]]) -> bool:
    """Whether every pool reading is affirmatively over sustainable burn.

    `over` must be exactly True.  Missing, null, stale, or otherwise unreadable
    readings are never interpreted as a hold instruction.
    """
    reads = list(results)
    return bool(reads) and all(read.get("over") is True for read in reads)


def pool_line(slot_result: Mapping[str, Any], over_slots: Iterable[str], *, held: bool) -> str:
    """Render a slot's operator line without a false release instruction."""
    line = str(slot_result.get("line") or "").replace(OVER_SUFFIX, "")
    if held:
        return line + OVER_SUFFIX + " (every factory-pool slot is over)"
    if slot_result.get("over") is True:
        over = set(over_slots)
        headroom = ",".join(slot for slot in pool_slots() if slot not in over) or "?"
        return (
            line
            + " OVER on this slot alone: the pool is not over ("
            + headroom
            + " still has headroom), no hold"
        )
    return line


def factory_slot(slot: str, _now: object = None) -> dict[str, Any]:
    """Read a normalized slot record from the collector's persisted quota state.

    A state shape this committed collector does not recognize is intentionally
    unreadable (`over=None`), preserving the no-false-hold safety rule.
    """
    state_path = Path.home() / "token-spend-report" / "state" / "tenant-quota.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        record = state.get(slot, state.get("slots", {}).get(slot))
    except (OSError, TypeError, json.JSONDecodeError):
        return {"slot": slot, "over": None, "line": f"factory {slot}: unreadable quota reading"}
    if not isinstance(record, dict):
        return {"slot": slot, "over": None, "line": f"factory {slot}: unreadable quota reading"}
    over = record.get("over")
    if over is not True and over is not False:
        return {"slot": slot, "over": None, "line": f"factory {slot}: unreadable quota reading"}
    line = str(record.get("line") or f"factory {slot}: quota reading")
    return {"slot": slot, "over": over, "line": line}
