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

import json

import pytest

from livespec_dev_tooling.cross_repo.pin_staleness import distinct_source_pins, main


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
