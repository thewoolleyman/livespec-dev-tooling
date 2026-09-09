"""`judged_reason_findings` puts its uncomputable scope on the `IOResult` railway.

Cluster 5 of `livespec-dev-tooling-qndn`, the CONVERT bucket's heading-coverage
row. The guard is convicted TRANSITIVELY: it reads `cwd` through
`baseline_fingerprints` → `heading_coverage_debt.head_rows`, whose whole answer
used to be a `None` sentinel.

Three different runs returned the one `list[ReasonFinding]` spelling — nothing
judged because the guard is unarmed, this exact set judged because the tree
authors it, and EVERYTHING judged because the scope could not be computed. The
third is a fail-closed fallback rather than a measurement, and the caller's only
cue was a warning it was free not to read.

The load-bearing pair is `test_an_armed_run_over_a_comparable_head_narrows`
beside `test_an_uncomputable_scope_fails_closed_on_the_failure_track`: both
hand back findings, and they are on OPPOSITE tracks now. The second also pins
that the fallback still CARRIES every finding — `livespec-dev-tooling-qndn.14`'s
shape, where the failure holds the usable answer — because with no `HEAD` copy
every live row genuinely is newly authored, and discarding them would turn an
unreadable baseline into a clean run.

Driven against a REAL git repository, because the scope is a statement about
`HEAD`; a double would prove only that the code calls the functions it calls.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._heading_coverage_reason_guard import (
    baseline_fingerprints,
    judged_reason_findings,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

__all__: list[str] = []


_SCOPE_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF"

_COP_OUT = "No independently testable assertion at runtime."

_INHERITED = "## Inherited"
_AUTHORED = "## Authored"


def _row(*, heading: str) -> dict[str, object]:
    """A `spec.md` registry row whose `reason` is a cop-out the guard must find."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "test": "TODO",
        "reason": _COP_OUT,
        "work_item": "livespec-dev-tooling-0bse.2",
    }


def _git(*, cwd: Path, args: list[str]) -> None:
    # S603/S607: argv is a fixed list (literal git binary + test-controlled
    # args); bare `git` is the canonical invocation per system PATH; no
    # untrusted shell input.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _write_registry(*, tmp_path: Path, rows: list[dict[str, object]]) -> None:
    registry = tmp_path / "tests" / "heading-coverage.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    _ = registry.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _seed_repo(*, tmp_path: Path, rows: list[dict[str, object]]) -> None:
    """A git repo whose `HEAD` carries `rows` — the debt this tree INHERITS."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    _write_registry(tmp_path=tmp_path, rows=rows)
    _git(cwd=tmp_path, args=["add", "."])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline"])


def test_an_unarmed_run_judges_nothing_on_the_success_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Judging nothing is an ANSWER: the per-commit tier the P2 burn-down runs under."""
    monkeypatch.delenv(_SCOPE_VAR, raising=False)
    _seed_repo(tmp_path=tmp_path, rows=[_row(heading=_INHERITED)])

    judged = judged_reason_findings(entries=[_row(heading=_INHERITED)], cwd=tmp_path)

    assert isinstance(judged, IOSuccess)
    assert unsafe_perform_io(judged.unwrap()) == []


def test_an_armed_run_over_a_comparable_head_narrows(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured half: an inherited row is spared, a newly-authored one is judged."""
    monkeypatch.setenv(_SCOPE_VAR, "true")
    _seed_repo(tmp_path=tmp_path, rows=[_row(heading=_INHERITED)])
    entries = [_row(heading=_INHERITED), _row(heading=_AUTHORED)]

    judged = judged_reason_findings(entries=entries, cwd=tmp_path)

    assert isinstance(judged, IOSuccess)
    findings = unsafe_perform_io(judged.unwrap())
    assert [finding.entry["heading"] for finding in findings] == [_AUTHORED]


def test_an_uncomputable_scope_fails_closed_on_the_failure_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No comparable `HEAD` registry → the FAILURE track, carrying every finding.

    The payload is deliberately identical to what the success track would have
    carried, because judging everything IS correct where `HEAD` has no copy:
    every live row is newly authored there. What the track buys is that the
    caller cannot receive the fallback in a narrowed judgement's spelling.
    """
    monkeypatch.setenv(_SCOPE_VAR, "true")
    _write_registry(tmp_path=tmp_path, rows=[_row(heading=_AUTHORED)])
    entries = [_row(heading=_INHERITED), _row(heading=_AUTHORED)]

    judged = judged_reason_findings(entries=entries, cwd=tmp_path)

    assert isinstance(judged, IOFailure)
    unnarrowed = unsafe_perform_io(judged.failure())
    assert [finding.entry["heading"] for finding in unnarrowed.findings] == [_INHERITED, _AUTHORED]


def test_the_baseline_names_which_incomparability_it_hit(*, tmp_path: Path) -> None:
    """`head_rows`' verdict passes through rather than being flattened to one word.

    A tree with no git history at all and a repository whose `HEAD` carries no
    registry blob are the same `head-copy-absent` arm; keeping the reason on the
    value is what lets the guard's warning say WHICH one an operator is looking
    at rather than only that something was unreadable.
    """
    unreadable = baseline_fingerprints(cwd=tmp_path)

    assert isinstance(unreadable, IOFailure)
    assert unsafe_perform_io(unreadable.failure()).reason == "head-copy-absent"


def test_a_comparable_head_yields_one_fingerprint_per_committed_row(*, tmp_path: Path) -> None:
    """The success half of the same call: `HEAD`'s rows, fingerprinted for comparison."""
    _seed_repo(tmp_path=tmp_path, rows=[_row(heading=_INHERITED), _row(heading=_AUTHORED)])

    fingerprinted = baseline_fingerprints(cwd=tmp_path)

    assert isinstance(fingerprinted, IOSuccess)
    assert len(unsafe_perform_io(fingerprinted.unwrap())) == 2
