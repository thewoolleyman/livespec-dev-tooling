"""Tests for `pin_staleness` — which discovered pins the freshness scan checks.

The defect these pin down (work-item `livespec-dev-tooling-p73`): the freshness
workflow collapsed every record for a source to ONE representative
(`.[0].current_value`), so a source whose FIRST record was fresh never produced a
bump PR even when its other records were stale. `SPECIFICATION/contracts.md`
§"Reusable workflow inventory" already requires a bump PR per
`(source_repo, current_pin, latest_tag)` triple, so the contract was right and
the implementation was not.
"""

from __future__ import annotations

import io
import json

import pytest

from livespec_dev_tooling.cross_repo.pin_staleness import (
    distinct_source_pins,
    main,
    ordinal_distance,
)


def _record(*, source_repo: str, current_value: str, file_path: str) -> dict[str, str]:
    return {
        "pin_format": "fabro_sandbox_docker_image",
        "file_path": file_path,
        "pin_key": "ghcr.io/thewoolleyman/livespec-fabro-sandbox",
        "current_value": current_value,
        "source_repo": source_repo,
    }


def test_distinct_source_pins_keeps_every_distinct_pin_not_only_the_first() -> None:
    """The exact shape that hid the drift: a FRESH first record masking stale ones.

    `livespec-dev-tooling` pinned the fabro image fresh in its Fabro
    `workflow.toml` while its `.github/workflows/ci.yml` sat six releases behind.
    Taking `.[0]` saw only the fresh value and emitted no bump PR at all.
    """
    records = [
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.49.2",
            file_path=".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
        ),
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.43.2",
            file_path=".github/workflows/ci.yml",
        ),
    ]

    assert distinct_source_pins(records=records) == [
        ("livespec-dev-tooling", "python-v0.43.2"),
        ("livespec-dev-tooling", "python-v0.49.2"),
    ]


def test_distinct_source_pins_deduplicates_repeated_identical_pins() -> None:
    """Several jobs pinning the SAME tag are ONE pin to check, not N.

    A cut-over consumer repeats the `container:` block per job, so the same
    `(source, value)` pair recurs; checking it once keeps the log and any
    resulting PR set proportional to distinct pins rather than to job count.
    """
    records = [
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.43.2",
            file_path=".github/workflows/ci.yml",
        )
        for _ in range(5)
    ]

    assert distinct_source_pins(records=records) == [("livespec-dev-tooling", "python-v0.43.2")]


def test_distinct_source_pins_separates_distinct_sources_and_sorts() -> None:
    """Pairs are sorted so iteration order is deterministic, not walk-order."""
    records = [
        _record(
            source_repo="livespec-runtime",
            current_value="v0.3.0",
            file_path="pyproject.toml",
        ),
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.49.2",
            file_path=".github/workflows/ci.yml",
        ),
    ]

    assert distinct_source_pins(records=records) == [
        ("livespec-dev-tooling", "python-v0.49.2"),
        ("livespec-runtime", "v0.3.0"),
    ]


def test_distinct_source_pins_is_empty_for_no_records() -> None:
    assert distinct_source_pins(records=[]) == []


@pytest.mark.parametrize(
    "malformed",
    [
        {"source_repo": "livespec-runtime"},
        {"current_value": "v0.3.0"},
        {"source_repo": "", "current_value": "v0.3.0"},
        {"source_repo": "livespec-runtime", "current_value": ""},
    ],
)
def test_distinct_source_pins_skips_a_malformed_record_without_raising(
    *, malformed: dict[str, str]
) -> None:
    """A malformed record is skipped, never fatal.

    The walk is contract-bound to tolerate unrecognized formats, so one bad
    record must not abort the freshness scan for every other pin.
    """
    good = _record(
        source_repo="livespec-dev-tooling",
        current_value="python-v0.43.2",
        file_path=".github/workflows/ci.yml",
    )

    assert distinct_source_pins(records=[malformed, good]) == [
        ("livespec-dev-tooling", "python-v0.43.2")
    ]


def test_main_emits_every_distinct_pin_as_json(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.49.2",
            file_path=".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
        ),
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.43.2",
            file_path=".github/workflows/ci.yml",
        ),
    ]
    monkeypatch.setenv("RECORDS", json.dumps(records))

    assert main() == 0

    assert json.loads(capsys.readouterr().out) == [
        {"source_repo": "livespec-dev-tooling", "current_value": "python-v0.43.2"},
        {"source_repo": "livespec-dev-tooling", "current_value": "python-v0.49.2"},
    ]


def test_main_defaults_to_an_empty_record_set(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent RECORDS env yields an empty list, not a crash."""
    monkeypatch.delenv("RECORDS", raising=False)

    assert main() == 0
    assert json.loads(capsys.readouterr().out) == []


# `ordinal_distance` — work-item `livespec-dev-tooling-ews`. The freshness scan
# used to compute this in shell, where an early `awk` exit SIGPIPEd the upstream
# producer; under `pipefail` that made the whole pipeline non-zero, so the
# `||` fallback ALSO ran and the substitution captured TWO values. The numeric
# comparison then syntax-errored, evaluated false, and silently dropped a stale
# source. See the regression test below for the full shell form and why the
# failure mode is inverted from safe.


def test_ordinal_distance_counts_releases_back_to_the_current_tag() -> None:
    tags = ["v0.49.2", "v0.49.1", "v0.49.0", "v0.48.2", "v0.47.0", "v0.46.5"]

    assert ordinal_distance(tags=tags, current="v0.46.5", fallback=1) == 5


def test_ordinal_distance_is_zero_when_the_pin_is_the_latest_release() -> None:
    tags = ["v0.49.2", "v0.49.1"]

    assert ordinal_distance(tags=tags, current="v0.49.2", fallback=1) == 0


def test_ordinal_distance_falls_back_when_the_tag_is_absent() -> None:
    """An unrecognizable pin (e.g. a pre-layer `sha-` tag) must not read as fresh."""
    tags = ["v0.49.2", "v0.49.1"]

    assert ordinal_distance(tags=tags, current="sha-deadbeef", fallback=7) == 7


def test_ordinal_distance_falls_back_on_an_empty_tag_list() -> None:
    assert ordinal_distance(tags=[], current="v0.49.2", fallback=3) == 3


def test_ordinal_distance_reads_every_tag_rather_than_stopping_at_the_match() -> None:
    """The regression guard for the SIGPIPE defect.

    The shell form was::

        ordinal_distance=$(gh release list ... \
          | awk -v current="$current" '{if($0==current){print n; exit} n++}' \
          || echo "$STALENESS_THRESHOLD")

    awk's early `exit` closed the pipe, `gh` took SIGPIPE, and under `pipefail`
    the PIPELINE went non-zero — so the `|| echo` fallback ALSO ran and the
    command substitution captured BOTH values ("9\n1"). The arithmetic then
    syntax-errored and evaluated FALSE, silently dropping a stale source.

    The failure mode is inverted from safe: the early exit only fires when the
    current tag IS found, i.e. the normal stale case the scan exists to catch.
    Consuming the WHOLE list makes the pure function total and the CLI immune by
    construction — there is no early exit for a producer to trip over.
    """
    tags = [f"v9.9.{index}" for index in range(5000)]
    tags.append("v0.1.0")

    assert ordinal_distance(tags=tags, current="v9.9.3", fallback=1) == 3
    assert ordinal_distance(tags=tags, current="v0.1.0", fallback=1) == 5000


def test_main_ordinal_distance_mode_prints_a_bare_integer(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI must emit ONE integer and nothing else.

    This is the property whose absence caused the outage: the shell captured two
    values and the arithmetic silently evaluated false. A caller must be able to
    feed this straight into a numeric comparison.
    """
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO("v0.49.2\nv0.49.1\nv0.49.0\n"),
    )
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "v0.49.0", "1"])

    assert main() == 0

    out = capsys.readouterr().out
    assert out.splitlines() == ["2"]
    assert int(out.strip()) == 2


def test_main_ordinal_distance_mode_emits_the_fallback_for_an_absent_tag(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("v0.49.2\nv0.49.1\n"))
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "sha-old", "4"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["4"]


def test_main_ordinal_distance_mode_ignores_blank_lines(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A trailing newline from the producer must not shift the distance."""
    monkeypatch.setattr("sys.stdin", io.StringIO("v0.49.2\n\nv0.49.1\n\n"))
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "v0.49.1", "1"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["1"]
