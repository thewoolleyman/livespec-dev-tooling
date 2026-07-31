"""Green-leg edges for `ci_matrix_completeness.py`'s railway conversion.

A `*_edges.py` sibling rather than an addition to
`test_ci_matrix_completeness.py`, which is byte-identity-bound to its own Red
commit.

Both branches are ones the conversion CREATED. `load_canonical` reached the
filesystem and `json.loads` with NEITHER guarded, so an unreadable or
unparseable `--canonical-from` raised out of the check — no diagnostic, no
failure mode, just a traceback. These pin the replacement, including that it
is NOT lever-scoped: a broken invocation is not a gap in the repo being
checked, so the severity lever that decides whether gaps fail has no bearing
on it.

Driven IN-PROCESS via `main()` rather than by spawning the check, per
`check-tests-no-subprocess-spawn`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks.ci_matrix_completeness import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_EXIT_VIOLATIONS = 4
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST"


def _run(
    *, monkeypatch: pytest.MonkeyPatch, cwd: Path, override: str, fail_lever: str | None
) -> int:
    monkeypatch.chdir(cwd)
    monkeypatch.setattr("sys.argv", ["ci_matrix_completeness.py", "--canonical-from", override])
    if fail_lever is None:
        monkeypatch.delenv(_FAIL_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(_FAIL_ENV_VAR, fail_lever)
    return main()


def _modes(*, stderr: str) -> list[object]:
    return [
        json.loads(line).get("failure_mode")
        for line in stderr.splitlines()
        if line.strip().startswith("{")
    ]


def test_unreadable_canonical_override_is_a_diagnostic_not_a_raise(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = _run(monkeypatch=monkeypatch, cwd=tmp_path, override="absent.json", fail_lever=None)

    assert exit_code == _EXIT_VIOLATIONS
    assert "canonical_override_unusable" in _modes(stderr=capsys.readouterr().err)


def test_unparseable_canonical_override_is_a_diagnostic(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (tmp_path / "canonical.json").write_text("{ not json at all :::", encoding="utf-8")

    exit_code = _run(
        monkeypatch=monkeypatch, cwd=tmp_path, override="canonical.json", fail_lever=None
    )

    assert exit_code == _EXIT_VIOLATIONS
    assert "canonical_override_unusable" in _modes(stderr=capsys.readouterr().err)


def test_canonical_override_failure_ignores_the_severity_lever(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unloadable override fails whether or not the gap lever is set.

    Every FINDING this check emits is lever-scoped — it warns and exits 0
    unless `LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST` is set. A `--canonical-from`
    the check cannot load is not a finding about the repo; it means the check
    never ran. Asserting BOTH lever states is what makes that a claim rather
    than a coincidence of however the suite's environment happens to be set.
    """
    for lever in (None, "true"):
        exit_code = _run(
            monkeypatch=monkeypatch, cwd=tmp_path, override="absent.json", fail_lever=lever
        )
        _ = capsys.readouterr()
        assert exit_code == _EXIT_VIOLATIONS, f"lever={lever!r} changed the exit code"
