"""pin_staleness — select which discovered pins the freshness scan must check.

Extracted from the embedded bash loop in
`.github/workflows/reusable-pin-freshness.yml`, which collapsed every record for
a source to ONE representative:

    current=$(echo "$RECORDS" | jq -r --arg s "$source" \\
      '[.[] | select(.source_repo == $s)] | .[0].current_value')

That is wrong whenever a source is pinned at DIFFERENT values in different
places. `SPECIFICATION/contracts.md` §"Reusable workflow inventory" requires a
bump PR per `(source_repo, current_pin, latest_tag)` triple — per PIN, not per
source — so a fresh representative silently suppressed the whole source, and the
freshness workflow (the safety net for missed dispatches) went blind exactly
where drift is most likely to hide.

The multi-pin shape is not hypothetical: since the fabro-sandbox image pin gained
its `.github/workflows/*.yml` surface (§"Pin autodiscovery rules"), one consumer
routinely carries the SAME `pin_key` at several values — a fresh Fabro
`workflow.toml` pin alongside stale per-job `container:` image pins.

The selection is a pure function so it can be tested directly; the surrounding
`gh` / `npm` queries and the bump-PR machinery stay in the workflow. Output
discipline mirrors the sibling `fabro_image_pin_rewrite`: the pure core does no
I/O, and `main()` owns the env read plus the stdout JSON contract (declared in
`pyproject.toml` `supervisor_entry_files`, the surface `no_write_direct` exempts).
"""

from __future__ import annotations

import json
import os
import sys

__all__: list[str] = ["distinct_source_pins"]


def distinct_source_pins(*, records: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Return every distinct `(source_repo, current_value)` pair, sorted.

    Sorted so the caller's iteration order — and therefore the workflow log and
    any resulting PR set — is deterministic rather than dependent on walk order.

    Records missing either field are SKIPPED rather than raising: the walk is
    contract-bound to tolerate unrecognized formats, so a malformed record must
    not abort the freshness scan for every other pin.
    """
    pairs = {
        (record["source_repo"], record["current_value"])
        for record in records
        if record.get("source_repo") and record.get("current_value")
    }
    return sorted(pairs)


def main() -> int:
    """IO entry point — read `RECORDS` JSON from env, emit the pins to check.

    Emits a JSON array of `{"source_repo": ..., "current_value": ...}` objects on
    stdout, which the freshness workflow iterates. Replaces the inline
    `jq '... | .[0].current_value'` that only ever yielded one pin per source.
    """
    raw = os.environ.get("RECORDS", "[]")
    records: list[dict[str, str]] = json.loads(raw)
    pins = distinct_source_pins(records=records)
    payload = [{"source_repo": source, "current_value": current} for source, current in pins]
    _ = sys.stdout.write(json.dumps(payload))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
