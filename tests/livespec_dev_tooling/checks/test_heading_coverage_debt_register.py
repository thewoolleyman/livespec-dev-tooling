"""FAIL-CAPABILITY PROOF for the shrink-only heading-coverage debt ratchet.

Charter D3 of plan `fleet-heading-coverage-convergence`. A ratchet that cannot
convict is worse than no ratchet: it reports a frozen baseline while the debt
grows behind it. These tests therefore drive the four directions from the
outside, each against a REAL git repository, because three of them are
verdicts about `HEAD` — what the register was before this tree touched it —
and a double would prove only that the code calls the functions it calls.

The four ratified cases (`SPECIFICATION/scenarios.md`):

- a `TODO` row absent from the register → NON-ZERO (the new cop-out);
- a register that grew → NON-ZERO;
- a row resolved AND its register entry removed → ZERO (the shrink);
- a row resolved but its register entry left behind → NON-ZERO.

Plus the authoring-time scope lever, which must spare an INHERITED finding
(charter D2b: a commit is judged on what it authors) while still refusing a
newly-authored one, and must fall back to judging everything — loudly — when
it cannot tell what changed.

Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` + `rc = main()`)
exactly as `test_no_todo_registry_staged_scope.py` is, so no
`COVERAGE_PROCESS_START`-instrumented child races the parallel dispatcher.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "heading_coverage_debt_register.py"

_SCOPE_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF"

_REGISTRY_RELPATH = "tests/heading-coverage.json"
_REGISTER_RELPATH = "tests/heading-coverage-debt.json"


def _todo(*, heading: str, work_item: str = "livespec-dev-tooling-own") -> dict[str, object]:
    """A live registry row carrying transitional debt."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "test": "TODO",
        "reason": "owed integration-tier test",
        "work_item": work_item,
    }


def _resolved(*, heading: str) -> dict[str, object]:
    """A live registry row whose heading has a real test — no longer debt."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "test": "tests.consumer.test_thing.test_it",
    }


def _entry(
    *, heading: str, work_item: str = "livespec-dev-tooling-own", first_seen: str = "2026-09-08"
) -> dict[str, object]:
    """A debt-register entry for `heading`."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "work_item": work_item,
        "first_seen": first_seen,
    }


_UNKEYED_TODO: dict[str, object] = {
    "spec_file": "spec.md",
    "heading": "## Heading with no spec_root",
    "test": "TODO",
}


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red→Green hook inspects, and so `main()`
    can be invoked in-process under a monkeypatched cwd.

    Registered in `sys.modules` under its synthetic name BEFORE execution: on
    Python 3.10 `@dataclass` resolves `KW_ONLY` by looking the defining module
    up there, and a path-loaded module absent from `sys.modules` makes that
    lookup raise on the class body rather than on anything this test asserts.
    """
    spec = importlib.util.spec_from_file_location(
        "heading_coverage_debt_register_under_test", str(_MODULE_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    combined: str


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


def _write(*, tmp_path: Path, relpath: str, entries: object) -> None:
    """Write `entries` as JSON at `relpath` under the fixture tree."""
    target = tmp_path / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def _seed_repo(*, tmp_path: Path, registry: object, register: object | None = None) -> None:
    """A git repo whose `HEAD` carries `registry`, and `register` when supplied.

    `register=None` seeds the ADOPTION shape — `HEAD` has no debt register at
    all — which is the state every consumer is in on the commit that adopts the
    ratchet.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=registry)
    _git(cwd=tmp_path, args=["add", _REGISTRY_RELPATH])
    if register is not None:
        _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=register)
        _git(cwd=tmp_path, args=["add", _REGISTER_RELPATH])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline"])


def _stage(
    *, tmp_path: Path, registry: object | None = None, register: object | None = None
) -> None:
    """Overwrite and stage either file, as an author mid-commit would."""
    if registry is not None:
        _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=registry)
        _git(cwd=tmp_path, args=["add", _REGISTRY_RELPATH])
    if register is not None:
        _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=register)
        _git(cwd=tmp_path, args=["add", _REGISTER_RELPATH])


def _run_check(
    *,
    cwd: Path,
    scope: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd`; `scope=None` removes the lever."""
    monkeypatch.chdir(cwd)
    if scope is None:
        monkeypatch.delenv(_SCOPE_VAR, raising=False)
    else:
        monkeypatch.setenv(_SCOPE_VAR, scope)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, combined=captured.out + captured.err)


def test_a_register_equal_to_the_live_todo_set_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The baseline state every repository adopts: register == today's `TODO` set.

    This is what makes the ratchet non-breaking by construction — it is
    generated from the live registry, so an untouched tree satisfies every
    direction. An unkeyed row rides along to pin that it is `heading_coverage`'s
    business, not this check's.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _UNKEYED_TODO, _resolved(heading="## R")],
        register=[_entry(heading="## A")],
    )
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"a register equal to the live TODO set must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )


def test_a_todo_row_absent_from_the_register_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a new `TODO` row absent from the debt register is a new cop-out."""
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _todo(heading="## New")],
        register=[_entry(heading="## A")],
    )
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a TODO row outside the frozen baseline must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "unregistered_todo" in result.combined
    assert (
        "## New" in result.combined
    ), f"the refusal must name the row it judged; output={result.combined!r}"


def test_a_register_that_grew_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: adding an entry to the register rather than removing one is refused.

    The registry grows in lockstep, so the three history-free directions are all
    satisfied — only the shrink-only comparison against `HEAD` can catch this,
    which is exactly why it exists.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A")],
        register=[_entry(heading="## A")],
    )
    _stage(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _todo(heading="## Grown")],
        register=[_entry(heading="## A"), _entry(heading="## Grown")],
    )
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a grown register must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "register_grew" in result.combined
    assert "## Grown" in result.combined


def test_resolving_a_row_and_removing_its_register_entry_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: the shrink — a real test lands and the register loses a row."""
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _todo(heading="## B")],
        register=[_entry(heading="## A"), _entry(heading="## B")],
    )
    _stage(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _resolved(heading="## B")],
        register=[_entry(heading="## A")],
    )
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"resolving a row and removing its register entry is the ratchet's whole "
        f"point and must pass; got returncode={result.returncode} "
        f"output={result.combined!r}"
    )


def test_resolving_a_row_but_leaving_its_register_entry_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a banked shrink that never happened — the entry outlives its row.

    Left in place the entry is a pre-approved slot: a later commit could
    reintroduce that heading as a `TODO` and the cop-out direction would not
    fire.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _todo(heading="## B")],
        register=[_entry(heading="## A"), _entry(heading="## B")],
    )
    _stage(tmp_path=tmp_path, registry=[_todo(heading="## A"), _resolved(heading="## B")])
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a resolved row whose register entry was left behind must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "stale_register_entry" in result.combined
    assert "## B" in result.combined


def test_a_register_entry_without_an_owner_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Debt with no owner and no clock is debt the liveness and age gates cannot judge."""
    unowned = _entry(heading="## A")
    del unowned["work_item"]
    _seed_repo(tmp_path=tmp_path, registry=[_todo(heading="## A")], register=[unowned])
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a register entry missing a required field must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "register_row_incomplete" in result.combined


def test_the_scope_lever_spares_an_inherited_finding_and_still_reports_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a commit is judged on what it authors, never on debt it inherited.

    Narrowing the VERDICT must not narrow the REPORT — a silent narrowing would
    make an inherited offender indistinguishable from a clean register, the
    failure shape this repository treats as worse than the red it replaces.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Inherited")],
        register=[],
    )
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"an inherited unregistered TODO must not fail an unrelated commit; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "out_of_staged_scope" in result.combined
    assert "## Inherited" in result.combined
    assert (
        '"level": "error"' not in result.combined
    ), f"an out-of-scope finding must not be error-level; output={result.combined!r}"


def test_the_scope_lever_still_refuses_a_newly_authored_unregistered_todo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The narrowing keeps the ratchet's whole point: a NEW cop-out is refused."""
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A")],
        register=[_entry(heading="## A")],
    )
    _stage(tmp_path=tmp_path, registry=[_todo(heading="## A"), _todo(heading="## New")])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a newly-authored unregistered TODO must still be refused under the scope "
        f"lever; got returncode={result.returncode} output={result.combined!r}"
    )
    assert "## New" in result.combined


def test_an_uncomputable_scope_falls_back_to_judging_everything(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No comparable `HEAD` registry → FAIL CLOSED over every finding, and say so.

    "I could not tell what changed" must never be spelled the same way as
    "nothing changed".
    """
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=[_todo(heading="## A")])
    _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=[])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"an uncomputable scope must judge every finding; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "baseline_unreadable" in result.combined


def test_adoption_leaves_the_shrink_only_direction_unjudged_and_says_so(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`HEAD` carries no register: growth is undefined, so it is UNJUDGED, not fatal.

    Fail-closed here would red the very commit that adopts the ratchet in every
    consumer repository — the arm-ahead-of-adoption trap. The report still names
    the gap, so an unjudged run never reads as a verified one.
    """
    _seed_repo(tmp_path=tmp_path, registry=[_todo(heading="## A")])
    _stage(tmp_path=tmp_path, register=[_entry(heading="## A")])
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"the adoption commit must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "baseline_unreadable" in result.combined


def test_adoption_under_the_scope_lever_treats_an_absent_head_register_as_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent `HEAD` register does not defeat the scope — it puts entries IN it.

    That is the fail-closed direction: the judged set stays a SUPERSET of the
    staged diff rather than collapsing to nothing on the one commit where the
    register first appears.
    """
    _seed_repo(tmp_path=tmp_path, registry=[_todo(heading="## A")])
    _stage(tmp_path=tmp_path, register=[_entry(heading="## A")])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"the adoption commit must pass under the scope lever too; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
