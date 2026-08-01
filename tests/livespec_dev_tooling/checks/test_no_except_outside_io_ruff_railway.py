"""The Ruff BLE001 backstop probe is railway-typed — `8o8e.5`, epic `8o8e`.

Its own file rather than beside the existing `no_except_outside_io` tests, for
the Red-leg reason `test_cli_e2e_railway.py` records: this repo enforces 100%
per-file coverage, and at the RED moment every line AFTER the first failing
assertion is unexecuted and therefore UNCOVERED. Every assertion here is the
LAST statement of its test, and each one CALLS the subject inside the assert
so the statement still executes at Red — where two of these arms RAISE rather
than return.

## WHAT `8o8e.5` FILED, AND THE THREE IT DID NOT

The filed defect was "an unreadable `pyproject.toml` makes the BLE001 backstop
check report no gaps" — a vacuous zero. Reading the module found FOUR fused
outcomes, and the filed one is the mildest:

- an unreadable `pyproject.toml` (filed) — reported as "no gaps";
- `ruff` ABSENT from PATH — an UNGUARDED `subprocess.run`, so it raised
  `FileNotFoundError` out of a function annotated `list`;
- `ruff check --show-files` FAILING — its `returncode` was NEVER READ, so an
  empty stdout made EVERY inspected file look excluded from Ruff. That one
  does not go quiet; it manufactures a gap for every file and blames Ruff's
  exclusion rules for a Ruff that never ran;
- `ruff check --show-settings` FAILING — fused with "BLE001 is off", so a
  broken invocation reached the operator as a verdict about their `select`.

⚠️ NO `chmod 000` ANYWHERE: this suite runs as ROOT. Unreadability is spelled
as a DIRECTORY where a file is expected (`IsADirectoryError`), and the two
ruff-invocation arms use a PATH SHIM — the pattern `test_master_ci_green.py`
already uses for `gh`. The test itself spawns nothing; the subject does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import _no_except_outside_io_ruff as subject

_VENDOR_DIR = Path(subject.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


def _reason_of(*, outcome: object) -> str:
    """The failure track's `reason`, or a marker NAMING what came back instead.

    Returning a marker rather than asserting here is what lets each test put
    its whole subject call inside ONE assert statement: at the Red moment the
    pre-conversion code returns a bare `list`, and the marker makes that show
    up in the assertion message instead of an opaque `False`.
    """
    if not isinstance(outcome, IOFailure):
        return f"not-a-failure: {outcome!r}"
    return unsafe_perform_io(outcome.failure()).reason


def _gaps_of(*, outcome: object) -> object:
    """The success track's value, or a marker naming what came back instead."""
    if not isinstance(outcome, IOSuccess):
        return f"not-a-success: {outcome!r}"
    return unsafe_perform_io(outcome.unwrap())


def _repo(*, tmp_path: Path, pyproject: str) -> Path:
    """A repo root carrying `pyproject` and one inspected file.

    Built in a SUBDIRECTORY of `tmp_path` rather than in it: this package's
    conftest already populates `tmp_path` itself, so writing there would have
    the fixture fight a fixture.
    """
    root = tmp_path / "probe-root"
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _ = (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    return root


def _shim_ruff(*, tmp_path: Path, script: str) -> str:
    """Install a fake `ruff` on a PATH of our own and return that PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    ruff = bin_dir / "ruff"
    _ = ruff.write_text(script, encoding="utf-8")
    ruff.chmod(0o755)
    return str(bin_dir)


_SELECT = '[tool.ruff.lint]\nselect = ["BLE"]\n'

# Duplicated from the subject rather than imported: it is the OPERATOR-FACING
# string, so pinning the literal is what makes a silent reword show up here.
_EXCLUDED_REASON = "inspected file is excluded from Ruff; BLE001 backstop is absent"


# ---------------------------------------------------------------------------
# The ANSWER arms — "no explicit select" is not a failure.
# ---------------------------------------------------------------------------


def test_an_absent_pyproject_is_an_answer_not_a_failure(*, tmp_path: Path) -> None:
    """No `pyproject.toml` means no explicit Ruff select, so there are no gaps.

    The pin-walker ruling, unchanged: an absent path is an ordinary answer.
    """
    bare = tmp_path / "bare-root"
    bare.mkdir()

    assert (
        _gaps_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=bare, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == []
    ), "an absent pyproject.toml is an ANSWER (no explicit select), not a failure"


def test_a_pyproject_without_an_explicit_select_is_an_answer(*, tmp_path: Path) -> None:
    """A `pyproject.toml` that configures no Ruff `select` yields no gaps."""
    root = _repo(tmp_path=tmp_path, pyproject="[project]\nname = 'x'\n")

    assert (
        _gaps_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == []
    ), "a pyproject with no explicit Ruff select is an ANSWER, not a failure"


# ---------------------------------------------------------------------------
# The FAILURE arms — "could not probe" is never reported as "no gaps".
# ---------------------------------------------------------------------------


def test_an_unreadable_pyproject_is_a_failure_not_zero_gaps(*, tmp_path: Path) -> None:
    """⛔ THIS IS `8o8e.5` EXACTLY. It answered `[]` — "the backstop is fine"."""
    root = tmp_path / "unreadable-root"
    (root / "pyproject.toml").mkdir(parents=True)

    assert (
        _reason_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == "pyproject-not-read"
    ), "an unreadable pyproject.toml must not be reported as a probed, gap-free repo"


def test_an_absent_ruff_binary_is_a_value_not_a_raised_oserror(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `subprocess.run` was UNGUARDED — livespec v179 clause (a).

    The call sits INSIDE the assert so the statement still executes at the Red
    moment, where it raises `FileNotFoundError` instead of returning.
    """
    root = _repo(tmp_path=tmp_path, pyproject=_SELECT)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    assert (
        _reason_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == "ruff-not-run"
    ), "an absent ruff binary must flow as a value, not raise out of a function typed `list`"


def test_a_failing_show_files_is_named_not_read_as_total_exclusion(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ THE `returncode` WAS NEVER READ, and this arm is the loud one.

    A failed enumeration yields empty stdout, so every inspected file looked
    EXCLUDED from Ruff — a gap manufactured for every file in the repo, blamed
    on exclusion rules, from a Ruff that never produced a listing.
    """
    root = _repo(tmp_path=tmp_path, pyproject=_SELECT)
    monkeypatch.setenv(
        "PATH",
        _shim_ruff(tmp_path=tmp_path, script='#!/bin/sh\necho "boom" >&2\nexit 2\n'),
    )

    assert (
        _reason_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == "ruff-show-files-failed"
    ), "a failing `ruff --show-files` must not read as every file being excluded"


def test_a_failing_show_settings_is_split_from_ble001_being_off(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`returncode == 0 and <setting> in stdout` FUSED a broken run with a verdict."""
    root = _repo(tmp_path=tmp_path, pyproject=_SELECT)
    script = (
        "#!/bin/sh\n"
        'if [ "$2" = "--show-files" ]; then\n'
        f'  echo "{root / "a.py"}"\n'
        "  exit 0\n"
        "fi\n"
        'echo "settings blew up" >&2\n'
        "exit 2\n"
    )
    monkeypatch.setenv("PATH", _shim_ruff(tmp_path=tmp_path, script=script))

    assert (
        _reason_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == "ruff-show-settings-failed"
    ), "a failing `ruff --show-settings` must not read as a verdict about `select`"


# ---------------------------------------------------------------------------
# The success track still carries real gaps.
# ---------------------------------------------------------------------------


def test_a_genuinely_excluded_file_is_still_a_gap_on_the_success_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe that SUCCEEDS and finds a real gap carries it on the success track.

    The positive control for the whole conversion: without it, an implementation
    that put every outcome on the failure track would satisfy every test above
    while destroying the check.
    """
    root = _repo(tmp_path=tmp_path, pyproject=_SELECT)
    monkeypatch.setenv("PATH", _shim_ruff(tmp_path=tmp_path, script="#!/bin/sh\nexit 0\n"))

    assert _gaps_of(
        outcome=subject.find_ruff_backstop_gaps(
            repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
        )
    ) == [
        (Path("a.py"), _EXCLUDED_REASON)
    ], "a file Ruff does not list is still a GAP, carried on the success track"
