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

from livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite import tag_version_component

__all__: list[str] = ["denotes_same_release", "distinct_source_pins", "ordinal_distance"]


def denotes_same_release(*, pinned_tag: str, release_tag: str) -> bool:
    """Return whether a pin's tag names the SAME release as `release_tag`.

    The freshness scan used to answer this with raw string equality on the
    release-tag path (`[[ "$current" == "$latest" ]]`). That is correct only for
    pin formats whose value IS a bare release tag. The
    `fabro_sandbox_docker_image` format's value is a LAYER-PREFIXED image tag
    (`python-v0.51.4`) over the bare release version (`v0.51.4`), so the two
    strings are never equal even when they name the same release — and that pin
    was therefore reported stale by construction on every sweep, forever
    (work-item `livespec-dev-tooling-clrk`).

    The grammar deciding what the version component IS comes from the sibling
    `fabro_image_pin_rewrite.tag_version_component`, the same module the REWRITE
    half already used. The two halves holding independent copies of the rule is
    what let them disagree, so there is deliberately no second regex here.

    The literal-equality short-circuit comes FIRST and is load-bearing: every
    answer the old comparison called current stays current, so this is a pure
    WIDENING and no unprefixed pin format can regress. Only the additional case —
    two tags carrying the same version component but different surrounding text —
    is newly recognized.

    A pin with no version anchor at all (`sha-deadbeef`, a `master` bootstrap
    placeholder) matches nothing but an identical literal, so it keeps reading as
    STALE rather than silently as fresh — the same fail-toward-visible direction
    `ordinal_distance` takes for an absent tag.
    """
    if pinned_tag == release_tag:
        return True
    pinned_version = tag_version_component(tag=pinned_tag)
    if pinned_version is None:
        return False
    return pinned_version == tag_version_component(tag=release_tag)


def distinct_source_pins(*, records: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Return every distinct `(source_repo, current_value)` pair, sorted.

    Sorted so the caller's iteration order — and therefore the workflow log and
    any resulting PR set — is deterministic rather than dependent on walk order.

    Records missing either field are SKIPPED rather than raising. The reason
    is now DEFENCE-IN-DEPTH rather than a contract obligation, and the
    difference is worth stating because the old justification has expired:
    this guard used to be required, because the walk emitted a half-populated
    `pin_format: "unrecognized"` record — empty `source_repo` and
    `current_value` — for any file it could not parse. Since
    livespec-dev-tooling-2j2l that record no longer exists; an unparseable
    file leaves on the failure track instead, so `discover` cannot hand this
    function a record with either field blank. The skip is retained because
    this function takes a plain `list[dict[str, str]]` and does not know its
    caller — the CLI's JSON output is a public surface others may re-feed —
    and a malformed record from some other producer must still not abort the
    freshness scan for every other pin.
    """
    pairs = {
        (record["source_repo"], record["current_value"])
        for record in records
        if record.get("source_repo") and record.get("current_value")
    }
    return sorted(pairs)


def ordinal_distance(*, tags: list[str], current: str, fallback: int) -> int:
    """Return how many releases `current` is behind the newest, or `fallback`.

    `tags` is the release list newest-first, so the index of `current` IS the
    ordinal distance: 0 means the pin is the latest release.

    Consumes the WHOLE list rather than stopping at the match. That is the point
    of this function, not an inefficiency: the shell version it replaces stopped
    early, which SIGPIPEd the upstream producer, and under `pipefail` the failed
    pipeline triggered a `||` fallback whose output was captured ALONGSIDE the
    real answer. Reading to the end means there is no early exit for a producer
    to trip over.

    A `current` absent from the list (an unrecognizable or pre-scheme tag) yields
    `fallback` — deliberately the staleness threshold, so an unreadable pin reads
    as STALE rather than silently as fresh.

    Matching goes through `denotes_same_release`, not raw equality, for the same
    reason the currency check does: `tags` is a list of BARE release tags, so a
    layer-prefixed `current` matched nothing and silently took the `fallback`
    branch. That returned the threshold itself, which — since the caller tests
    `distance >= threshold` — reported EVERY prefixed pin as maximally stale
    regardless of how far behind it actually was. At the default threshold of 1
    the wrong answer coincides with the right one for a genuinely stale pin, which
    is why it hid; at any higher threshold a prefixed pin one release behind would
    trip a gate meant to tolerate it (work-item `livespec-dev-tooling-clrk`).
    """
    found = -1
    for index, tag in enumerate(tags):
        if found < 0 and denotes_same_release(pinned_tag=current, release_tag=tag):
            found = index
    return fallback if found < 0 else found


def _ordinal_distance_main(*, current: str, fallback: str) -> int:
    """`--ordinal-distance` mode — read the tag list on stdin, print ONE integer.

    Reads stdin to EOF, so the upstream producer is never SIGPIPEd, and prints a
    single bare integer with no fallback path that could append a second value.
    Both properties are the fix: the shell version this replaces could emit two
    lines, which made the caller's numeric comparison syntax-error and silently
    evaluate false.

    Blank lines are ignored so a producer's trailing newline cannot shift the
    distance by one.
    """
    tags = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    distance = ordinal_distance(tags=tags, current=current, fallback=int(fallback))
    _ = sys.stdout.write(f"{distance}\n")
    return 0


def _is_current_main(*, current: str, latest: str) -> int:
    """`--is-current` mode — print exactly `true` or `false`, nothing else.

    A bare two-valued token rather than an exit status, so a crash in this module
    can never be mistaken for a verdict: the caller pattern-matches the output and
    fails LOUDLY on anything else, mirroring the `^[0-9]+$` guard the sibling
    `--ordinal-distance` caller already applies. An exit-status predicate would
    have collapsed "not current" and "the tool broke" into the same signal.
    """
    verdict = "true" if denotes_same_release(pinned_tag=current, release_tag=latest) else "false"
    _ = sys.stdout.write(f"{verdict}\n")
    return 0


def main() -> int:
    """IO entry point — three modes, selected by argv.

    With `--is-current <current> <latest>`: print whether the pin already names
    the latest release, comparing the VERSION each tag denotes rather than the
    raw tag strings.

    With `--ordinal-distance <current> <fallback>`: read the release-tag list on
    stdin and print how many releases `current` is behind.

    Otherwise: read `RECORDS` JSON from env and emit a JSON array of
    `{"source_repo": ..., "current_value": ...}` objects, which the freshness
    workflow iterates. Replaces the inline `jq '... | .[0].current_value'` that
    only ever yielded one pin per source.
    """
    argv = sys.argv[1:]
    if argv and argv[0] == "--is-current":
        return _is_current_main(current=argv[1], latest=argv[2])
    if argv and argv[0] == "--ordinal-distance":
        return _ordinal_distance_main(current=argv[1], fallback=argv[2])

    raw = os.environ.get("RECORDS", "[]")
    records: list[dict[str, str]] = json.loads(raw)
    pins = distinct_source_pins(records=records)
    payload = [{"source_repo": source, "current_value": current} for source, current in pins]
    _ = sys.stdout.write(json.dumps(payload))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
