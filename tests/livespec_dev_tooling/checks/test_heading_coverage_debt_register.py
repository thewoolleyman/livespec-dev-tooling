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
newly-authored one, must leave an inherited row that is CORRECTLY REGISTERED
with no finding at all, and must fall back to judging everything — loudly —
when it cannot tell what changed.

Plus the ratchet's TERMINAL state — a committed register that has reached
EMPTY. Every other arm here seeds a baseline carrying at least one entry, so
each proves only that a row outside a NON-EMPTY baseline is refused. At zero
there is no baseline left to be outside of, and the pair at the bottom of this
module (a refusal and its control) is what proves the `unregistered_todo`
direction still stands between a resolved repository and a fresh cop-out.

Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` + `rc = main()`)
exactly as `test_no_todo_registry_staged_scope.py` is, so no
`COVERAGE_PROCESS_START`-instrumented child races the parallel dispatcher.

## WHY THIS MODULE CARRIES `pytestmark = pytest.mark.integration`

Every test here drives the shipped check's `main()` end to end against a real
git repository — nothing is doubled — so the file is integration-tier in
NATURE, and four `scenarios.md` headings now map to nodes in it rather than
carrying a `TODO` row in the debt register. `heading_coverage` direction 4
refuses a `scenarios.md` heading mapped to a unit-tier test, and it decides the
tier one of two ways: an allowlisted node-id prefix (`tests.consumer` and
friends), or a STATIC `pytest.mark.integration` on the resolved test. This file
cannot take the first route — `tests_mirror_pairing` requires a check's tests
to mirror the module they exercise, which puts them here — so it takes the
second. The marker is a tier LABEL the AST resolver reads, never a selector: no
recipe or workflow passes `-m`, so nothing is filtered in or out by it.
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

pytestmark = pytest.mark.integration


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


_GOVERNED_SPEC_FILE = "scenarios.md"
_GOVERNED_SPEC_RELPATH = f"SPECIFICATION/{_GOVERNED_SPEC_FILE}"
_GOVERNED_HEADING = "## Scenario: a governed behaviour already covered by a real test"

# The heading a spec-first change INTRODUCES. Absent from `HEAD`'s governed spec
# file and from `HEAD`'s coverage registry, which is the whole of what makes the
# bounded v067 exception apply to it.
_NEW_HEADING = "## Scenario: a genuinely new governed behaviour this change introduces"

_OWNER = "livespec-dev-tooling-own"

# Every spec-first fixture pins its baseline commit's date, because the
# committed-tier date direction reads the committer date of the earliest commit
# whose registry blob carried a key as a `TODO`. A fixture that let the host
# clock decide could not place a register entry on either side of it.
_BASELINE_AT = "2026-03-04T00:00:00+00:00"
_BASELINE_DATE = "2026-03-04"
_LANDING_AT = "2026-03-05T00:00:00+00:00"


def _governed_resolved_row(*, heading: str = _GOVERNED_HEADING) -> dict[str, object]:
    """The registry row for a governed heading in a repository at zero debt."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": _GOVERNED_SPEC_FILE,
        "heading": heading,
        "test": "tests.consumer.test_governed.test_it",
    }


def _governed_todo_row(
    *,
    heading: str = _GOVERNED_HEADING,
    work_item: str = _OWNER,
    reason: str = "owed integration-tier test",
) -> dict[str, object]:
    """A governed heading's row carried as transitional debt.

    At the default `heading` this is the row re-opened on a PRE-EXISTING heading
    — the new cop-out. At `_NEW_HEADING` it is the spec-first row the bounded
    v067 exception admits, and `work_item` / `reason` are the two declarations
    that exception requires: who owes the test, and an acknowledgment that a
    real test at the required tier is owed.
    """
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": _GOVERNED_SPEC_FILE,
        "heading": heading,
        "test": "TODO",
        "reason": reason,
        "work_item": work_item,
    }


def _governed_entry(
    *, heading: str, work_item: str = _OWNER, first_seen: str = _BASELINE_DATE
) -> dict[str, object]:
    """The register entry mechanical regeneration produces for a governed heading."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": _GOVERNED_SPEC_FILE,
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


def _git(*, cwd: Path, args: list[str], committed_at: str | None = None) -> None:
    """Run `git <args>` in `cwd`, optionally pinning the commit's dates.

    `committed_at` pins BOTH `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`, which
    the committed-tier date directions need: their evidence is the committer
    date of the earliest commit whose registry blob carried a key as a `TODO`,
    so a fixture that cannot choose that date cannot place a register entry on
    either side of it.
    """
    env = {"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"}
    if committed_at is not None:
        env["GIT_AUTHOR_DATE"] = committed_at
        env["GIT_COMMITTER_DATE"] = committed_at
    # S603/S607: argv is a fixed list (literal git binary + test-controlled
    # args); bare `git` is the canonical invocation per system PATH; no
    # untrusted shell input.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def _write(*, tmp_path: Path, relpath: str, entries: object) -> None:
    """Write `entries` as JSON at `relpath` under the fixture tree."""
    target = tmp_path / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def _init_repo(*, tmp_path: Path) -> None:
    """An empty git repository with a deterministic committer identity."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])


def _seed_repo(
    *,
    tmp_path: Path,
    registry: object,
    register: object | None = None,
    committed_at: str | None = None,
) -> None:
    """A git repo whose `HEAD` carries `registry`, and `register` when supplied.

    `register=None` seeds the ADOPTION shape — `HEAD` has no debt register at
    all — which is the state every consumer is in on the commit that adopts the
    ratchet.

    `committed_at` pins the baseline commit's date. Left unset the host clock
    decides, which every arm predating the committed-tier date directions
    relies on; an arm that places a register entry relative to the registry's
    own history must pin it instead.
    """
    _init_repo(tmp_path=tmp_path)
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=registry)
    _git(cwd=tmp_path, args=["add", _REGISTRY_RELPATH])
    if register is not None:
        _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=register)
        _git(cwd=tmp_path, args=["add", _REGISTER_RELPATH])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline"], committed_at=committed_at)


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


def _commit_staged(*, tmp_path: Path, committed_at: str, message: str) -> None:
    """Commit whatever `_stage` just staged, at `committed_at`."""
    _git(cwd=tmp_path, args=["commit", "-q", "-m", message], committed_at=committed_at)


def _write_governed_spec(*, tmp_path: Path, headings: list[str]) -> None:
    """Write the governed spec file so its H2 set is exactly `headings`.

    The H2 SET is the fixture's whole payload: new-heading eligibility is read
    from the difference between this file's headings in the working tree and in
    `HEAD`, and the same-file replacement disqualifier is read from what this
    set LOST. A fixture that appended text without controlling the set could
    prove neither direction.
    """
    spec = tmp_path / _GOVERNED_SPEC_RELPATH
    spec.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f"{heading}\n\nGiven a governed behaviour\n\nWhen it runs\n\nThen it holds\n\n"
        for heading in headings
    )
    _ = spec.write_text(f"# Scenarios\n\n{body}", encoding="utf-8")


def _commit_governed_spec_heading(*, tmp_path: Path) -> None:
    """Put a REAL governed heading into `HEAD`'s spec tree.

    The ratchet's four set-shaped directions never open the spec files — they
    judge the registry against the register — so this is deliberately not a
    precondition of THOSE. It is a precondition of the SCENARIO: a heading is
    only "pre-existing" if the spec really carries it at `HEAD`, and a fixture
    naming a heading that no spec file contains would prove the refusal against
    a key no governed repository could ever produce. The v067 spec-first
    direction then reads this file for real, on both revisions.
    """
    _write_governed_spec(tmp_path=tmp_path, headings=[_GOVERNED_HEADING])
    _git(cwd=tmp_path, args=["add", _GOVERNED_SPEC_RELPATH])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "seed the governed spec heading"])


def _seed_governed_repo(
    *,
    tmp_path: Path,
    headings: list[str],
    registry: object,
    register: object,
) -> None:
    """A repo whose `HEAD` carries the governed spec file AND both rows files.

    The spec-first direction compares three things against `HEAD` — the
    governed spec file's H2 set, the coverage registry's keys, and the debt
    register's keys — so every one of them has to be COMMITTED for the
    comparison to be the one a real authoring run makes.
    """
    _init_repo(tmp_path=tmp_path)
    _write_governed_spec(tmp_path=tmp_path, headings=headings)
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=registry)
    _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=register)
    _git(cwd=tmp_path, args=["add", "-A"])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline"], committed_at=_BASELINE_AT)


def _stage_governed_change(
    *,
    tmp_path: Path,
    headings: list[str],
    registry: object,
    register: object,
) -> None:
    """Overwrite and stage all three files, as a spec-first author mid-commit would."""
    _write_governed_spec(tmp_path=tmp_path, headings=headings)
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=registry)
    _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=register)
    _git(cwd=tmp_path, args=["add", "-A"])


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


def test_an_inherited_registered_todo_does_not_fail_an_unrelated_commit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a registered row the contributor did not author passes the armed tier.

    The row is in BOTH files at `HEAD` — registry `TODO` and register entry —
    and the staged change touches an unrelated file, which is the ordinary shape
    of every commit in a repository carrying debt. A correctly registered row is
    not merely spared the verdict here: it draws no ratchet finding at all, so
    an author reading the output sees nothing about a row they never touched.

    Paired with `test_the_scope_lever_still_refuses_a_newly_authored_unregistered_todo`
    below — same lever, opposite verdicts — so a narrowing that simply stopped
    judging could not satisfy both.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Inherited")],
        register=[_entry(heading="## Inherited")],
    )
    unrelated = tmp_path / "docs" / "unrelated.md"
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    _ = unrelated.write_text(
        "an edit that touches neither heading-coverage file\n", encoding="utf-8"
    )
    _git(cwd=tmp_path, args=["add", "docs/unrelated.md"])

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"an inherited, correctly registered TODO must not fail an unrelated commit; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    # Asserted on the finding CODES rather than on the heading text, because the
    # release-tier age direction names the heading too once `first_seen` ages
    # past the bound — an assertion on the heading would rot into a host-date
    # dependency the way this suite's other date-sensitive arms have.
    for code in ("unregistered_todo", "stale_register_entry", "register_grew"):
        assert code not in result.combined, (
            f"a correctly registered row must draw no {code} finding; "
            f"output={result.combined!r}"
        )


def test_the_scope_lever_still_refuses_a_newly_authored_unregistered_todo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a newly-authored `TODO` outside the register fails the armed tier.

    The narrowing keeps the ratchet's whole point: a NEW cop-out is refused, and
    the refusal NAMES the row as one — `unregistered_todo` carries the "new
    cop-out outside the frozen baseline" message, so the author is told what to
    do rather than merely told no.
    """
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
    assert "unregistered_todo" in result.combined, (
        f"the refusal must name the row as a new cop-out outside the baseline; "
        f"output={result.combined!r}"
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


def test_an_unreadable_registry_decides_no_direction_and_says_so(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a present-but-unparseable registry is its own outcome, not "no rows".

    Before `livespec-dev-tooling-qndn.15` this tree reached the directions as an
    EMPTY registry, which fires `stale_register_entry` for every register key —
    a full slate of confident findings naming the wrong file and the wrong
    cause, each of which an author would have "fixed" by deleting real debt.
    """
    _seed_repo(
        tmp_path=tmp_path, registry=[_todo(heading="## A")], register=[_entry(heading="## A")]
    )
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries={"not": "an array"})

    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 1, (
        f"an unreadable registry must not pass as an empty one; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "rows-file-not-an-array" in result.combined
    assert _REGISTRY_RELPATH in result.combined
    assert (
        "stale_register_entry" not in result.combined
    ), f"no direction may be decided from an unreadable file; output={result.combined!r}"


def test_an_unreadable_register_decides_no_direction_either(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mirror: an unparseable REGISTER used to read as "no entries".

    That fires `unregistered_todo` for every live `TODO` — the new-cop-out
    message, on rows that are all correctly registered. Both files are read
    through the same seam, so both get the same answer.
    """
    _seed_repo(
        tmp_path=tmp_path, registry=[_todo(heading="## A")], register=[_entry(heading="## A")]
    )
    _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries={"not": "an array"})

    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 1, (
        f"an unreadable register must not pass as an empty one; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "rows-file-not-an-array" in result.combined
    assert _REGISTER_RELPATH in result.combined
    assert (
        "unregistered_todo" not in result.combined
    ), f"no direction may be decided from an unreadable file; output={result.combined!r}"


def test_an_authored_first_seen_moved_later_than_head_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: the authoring tier compares an existing date against `HEAD` and refuses later.

    Moving a recorded `first_seen` forward is how debt is laundered into fresh
    debt without resolving anything: the key stays registered, the register
    neither grows nor shrinks, the schema holds — and the release-tier age
    bound's clock restarts. None of the three pre-existing directions can see
    it, which is why this one reads `HEAD`'s own register as the evidence.

    Two entries ride along to pin what the comparison PLACES and what it
    cannot: an unkeyed entry has no identity to compare, and an entry whose
    `first_seen` is not a calendar date has no date to compare. Neither may be
    convicted here — the release-tier age bound already names an unmeasurable
    date, and double-convicting one defect as two sends an author looking for
    a second problem that does not exist.
    """
    unkeyed_entry: dict[str, object] = {"heading": "## Unkeyed", "first_seen": "2026-01-02"}
    undated_entry = _entry(heading="## Undated", first_seen="not-a-date")
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), _todo(heading="## Undated")],
        register=[_entry(heading="## A", first_seen="2026-01-02"), unkeyed_entry, undated_entry],
        committed_at="2026-01-02T00:00:00+00:00",
    )
    _stage(
        tmp_path=tmp_path,
        register=[_entry(heading="## A", first_seen="2026-03-04"), unkeyed_entry, undated_entry],
    )

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a first-seen date moved later than HEAD's must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_moved_later" in result.combined, (
        f"the refusal must name the inflation direction rather than a ratchet "
        f"finding; output={result.combined!r}"
    )
    assert "## A" in result.combined
    assert "## Unkeyed" not in result.combined, (
        f"an unkeyed entry has no identity to compare and must draw no date "
        f"finding; output={result.combined!r}"
    )


def test_an_authored_first_seen_moved_earlier_than_head_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CONTROL: only moving a date LATER is forbidden — earlier is legitimate.

    Without this arm the refusal above would prove only that the check reacts
    to a changed date. The ratified clause is directional ("Once recorded,
    `first_seen` MUST NOT move later"), and a check that refused any change
    would block the correction of a date that was recorded too late — the very
    inflation it exists to remove.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A")],
        register=[_entry(heading="## A", first_seen="2026-01-02")],
        committed_at="2026-01-02T00:00:00+00:00",
    )
    _stage(tmp_path=tmp_path, register=[_entry(heading="## A", first_seen="2025-12-01")])

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"moving a recorded date EARLIER must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_moved_later" not in result.combined


def test_a_committed_first_seen_later_than_the_earliest_todo_commit_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: pre-push and CI reject a date later than the earliest TODO commit.

    The inflation here is already COMMITTED, so the `HEAD` comparison above
    cannot see it: the register on disk is byte-identical to `HEAD`'s. What
    convicts it is the registry's own history — the row was carried as a `TODO`
    from 2026-01-02, and the register claims it was first seen 2026-05-10,
    which is four months of age the repository silently did not owe.

    Run with the scope lever UNSET, because that is what the pre-push and CI
    tier IS; the paired arm below proves the authoring tier does not demand
    this evidence of a row it is still authoring.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A")],
        committed_at="2026-01-02T00:00:00+00:00",
    )
    _stage(tmp_path=tmp_path, register=[_entry(heading="## A", first_seen="2026-05-10")])
    _commit_staged(
        tmp_path=tmp_path,
        committed_at="2026-05-10T00:00:00+00:00",
        message="record the register with an inflated first-seen date",
    )

    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a committed first-seen date later than the earliest TODO commit must be "
        f"refused; got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_after_earliest_todo_commit" in result.combined, (
        f"the refusal must name the history-evidence direction; " f"output={result.combined!r}"
    )
    assert "## A" in result.combined
    assert "2026-01-02" in result.combined, (
        f"the refusal must report the committer-date evidence it judged against, "
        f"or the author cannot tell which date is wrong; output={result.combined!r}"
    )


def test_the_authoring_tier_leaves_the_committed_history_comparison_to_pre_push(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The SAME repository, under the authoring lever, draws no history finding.

    The two tiers rest on different evidence by design: an authored row's date
    is compared against `HEAD`, because the commit carrying its registry `TODO`
    does not exist yet and demanding committed evidence of it would refuse the
    very admission the ratified clause permits. Only after the commit does the
    history comparison become answerable — which is the tier this arm proves it
    is confined to.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A")],
        committed_at="2026-01-02T00:00:00+00:00",
    )
    _stage(tmp_path=tmp_path, register=[_entry(heading="## A", first_seen="2026-05-10")])
    _commit_staged(
        tmp_path=tmp_path,
        committed_at="2026-05-10T00:00:00+00:00",
        message="record the register with an inflated first-seen date",
    )

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"the authoring tier must not demand committed history evidence; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_after_earliest_todo_commit" not in result.combined


def test_committed_debt_whose_required_history_evidence_is_unavailable_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: unavailable required history evidence refuses validation.

    The registry carries the `TODO` but NO commit does, so there is no earliest
    carrying commit to read a committer date from — the shape a repository
    reaches when the registry is untracked, or when the history that holds it
    has been removed. "I could not establish the date" must never be spelled
    the same way as "the date is fine": an unanswerable comparison that passed
    would make every inflated date launderable by removing its evidence.
    """
    _init_repo(tmp_path=tmp_path)
    _write(
        tmp_path=tmp_path,
        relpath=_REGISTER_RELPATH,
        entries=[_entry(heading="## A", first_seen="2026-01-02")],
    )
    _git(cwd=tmp_path, args=["add", _REGISTER_RELPATH])
    _git(
        cwd=tmp_path,
        args=["commit", "-q", "-m", "a register with no registry history behind it"],
        committed_at="2026-01-02T00:00:00+00:00",
    )
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=[_todo(heading="## A")])

    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"registered debt whose history evidence cannot be read must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_evidence_unavailable" in result.combined, (
        f"the refusal must name the EVIDENCE as the thing that failed, not the "
        f"date; output={result.combined!r}"
    )
    assert "## A" in result.combined


def test_a_committed_first_seen_earlier_than_a_truncated_history_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CONTROL: a recorded date PRECEDING the earliest visible TODO commit is valid.

    This is the ordinary shape, not an edge: a row authored in a working tree
    is dated the day it was authored and committed later, so the recorded date
    legitimately precedes the committer date. It is also what a SHALLOW clone
    looks like — truncating history moves the earliest visible carrying commit
    forward, and a check that read that as inflation would convict a repository
    for how it was cloned rather than for anything it authored.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A")],
        register=[_entry(heading="## A", first_seen="2025-12-01")],
        committed_at="2026-03-04T00:00:00+00:00",
    )

    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"a recorded date earlier than the earliest visible TODO commit must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_after_earliest_todo_commit" not in result.combined
    assert "first_seen_evidence_unavailable" not in result.combined


def test_a_resolved_repository_needs_no_history_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CONTROL: at zero debt the committed tier asks history for nothing at all.

    The register is empty and no live row is a `TODO`, so there is no recorded
    date to validate — and a tier that demanded history evidence anyway would
    refuse the ratchet's own success condition, which is the state this
    repository is in today.
    """
    _seed_repo(tmp_path=tmp_path, registry=[_governed_resolved_row()], register=[])
    _commit_governed_spec_heading(tmp_path=tmp_path)

    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"a repository at zero debt must pass the committed tier; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "first_seen_evidence_unavailable" not in result.combined


def test_a_new_todo_for_a_governed_heading_fails_against_an_empty_committed_register(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: at an EMPTY register, a newly-authored `TODO` row is refused outright.

    The repository is in the ratchet's terminal state: the governed heading
    exists in `HEAD`'s spec tree, its registry row resolves to a real test, and
    the committed register is `[]`. The staged change re-opens that row as
    `test: "TODO"` without a register entry — which, with the baseline at zero,
    there is no legitimate way to add.

    Driven under the authoring-time scope lever, because the per-commit tier IS
    that lever: the key is one this tree authors, so the narrowing must leave
    the finding judged rather than demote it to a warning.
    """
    _seed_repo(tmp_path=tmp_path, registry=[_governed_resolved_row()], register=[])
    _commit_governed_spec_heading(tmp_path=tmp_path)
    _stage(tmp_path=tmp_path, registry=[_governed_todo_row()])

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a TODO row authored against an empty register must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert (
        "unregistered_todo" in result.combined
    ), f"the refusal must name the new-cop-out direction; output={result.combined!r}"
    assert (
        _GOVERNED_HEADING in result.combined
    ), f"the refusal must name the heading it judged; output={result.combined!r}"


def test_the_same_empty_register_passes_when_the_tree_authors_no_todo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CONTROL for the arm above: the identical repository, unstaged, is clean.

    Without it the refusal proves only that the check says no — not that it says
    no to the STAGED ROW rather than to the empty register itself. A ratchet
    that convicted a resolved repository for having finished would be refusing
    its own success condition.
    """
    _seed_repo(tmp_path=tmp_path, registry=[_governed_resolved_row()], register=[])
    _commit_governed_spec_heading(tmp_path=tmp_path)

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"an unchanged repository at zero debt must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "unregistered_todo" not in result.combined, (
        f"a register at empty with no TODO rows must draw no finding; "
        f"output={result.combined!r}"
    )


def test_spec_first_debt_for_a_new_heading_is_admitted_against_a_nonempty_register(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: the bounded v067 exception — a genuinely new H2 may carry new debt.

    Every condition the ratified clause names holds at once: the change
    INTRODUCES `_NEW_HEADING` into the governed live specification, neither that
    heading nor its coverage key exists at `HEAD`, no existing H2 is removed from
    that file, the new coverage row names an owner and acknowledges an owed
    required-tier test, and mechanical regeneration has supplied the matching
    owner and a first-seen date.

    Without the exception this is indistinguishable from `register_grew`: the
    register carries a key `HEAD`'s does not, which is the shrink-only
    direction's entire definition. What separates them is spec evidence the
    ratchet previously never read.
    """
    _seed_governed_repo(
        tmp_path=tmp_path,
        headings=[_GOVERNED_HEADING],
        registry=[_governed_resolved_row(), _todo(heading="## A")],
        register=[_entry(heading="## A", first_seen=_BASELINE_DATE)],
    )
    _stage_governed_change(
        tmp_path=tmp_path,
        headings=[_GOVERNED_HEADING, _NEW_HEADING],
        registry=[
            _governed_resolved_row(),
            _todo(heading="## A"),
            _governed_todo_row(heading=_NEW_HEADING),
        ],
        register=[
            _entry(heading="## A", first_seen=_BASELINE_DATE),
            _governed_entry(heading=_NEW_HEADING),
        ],
    )

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"spec-first debt for a genuinely new H2 heading must be admitted; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "register_grew" not in result.combined, (
        f"an admitted spec-first key must not be reported as growth at all; "
        f"output={result.combined!r}"
    )
    assert "spec_first" not in result.combined, (
        f"an admitted key must draw no admission finding either; " f"output={result.combined!r}"
    )


def test_spec_first_debt_for_a_new_heading_is_admitted_against_an_empty_register(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: reaching zero does NOT retire the exception — the same rules apply.

    The ratified clause is explicit that an empty register "MUST permit the same
    narrowly defined spec-first admission", and that reaching zero "MUST NOT
    retire scoped authorship, ownership or the reason acknowledgment needed for
    future ratification". Every arm above this one seeds a baseline carrying at
    least one entry, so each could be satisfied by an admission rule that only
    worked where a register already existed.
    """
    _seed_governed_repo(
        tmp_path=tmp_path,
        headings=[_GOVERNED_HEADING],
        registry=[_governed_resolved_row()],
        register=[],
    )
    _stage_governed_change(
        tmp_path=tmp_path,
        headings=[_GOVERNED_HEADING, _NEW_HEADING],
        registry=[_governed_resolved_row(), _governed_todo_row(heading=_NEW_HEADING)],
        register=[_governed_entry(heading=_NEW_HEADING)],
    )

    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"spec-first debt must be admitted against an EMPTY prior register too; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "register_grew" not in result.combined
    assert "spec_first" not in result.combined


def test_an_admitted_spec_first_row_stays_ordinary_registered_debt_after_commit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: an admitted row needs no override once it lands.

    Two phases of ONE repository, because the ratified clause is about what
    happens to an admitted row rather than about either tier alone: the authoring
    tier admits the row, the change is COMMITTED, and the pre-push/CI tier — the
    scope lever UNSET, no environment override of any kind — then judges it as
    ordinary registered debt and passes.

    The second phase is the one that could regress silently. After the commit the
    shrink-only direction has nothing to say (`HEAD` now carries the key), so the
    verdict passes to the committed-tier date direction, whose evidence is the
    committer date of the earliest commit whose registry blob carried the key as
    a `TODO`. The recorded date is the authoring day and the landing commit is a
    day later, which is the ordinary shape — and the one a re-derived date would
    have broken.
    """
    _seed_governed_repo(
        tmp_path=tmp_path,
        headings=[_GOVERNED_HEADING],
        registry=[_governed_resolved_row()],
        register=[],
    )
    _stage_governed_change(
        tmp_path=tmp_path,
        headings=[_GOVERNED_HEADING, _NEW_HEADING],
        registry=[_governed_resolved_row(), _governed_todo_row(heading=_NEW_HEADING)],
        register=[_governed_entry(heading=_NEW_HEADING)],
    )

    authored = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)

    assert authored.returncode == 0, (
        f"the authoring tier must admit the row before the landed tier can be "
        f"asked about it; got returncode={authored.returncode} "
        f"output={authored.combined!r}"
    )

    _commit_staged(tmp_path=tmp_path, committed_at=_LANDING_AT, message="admit spec-first debt")

    landed = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)

    assert landed.returncode == 0, (
        f"an admitted row must remain valid as ordinary registered debt at "
        f"pre-push and CI with NO override; got returncode={landed.returncode} "
        f"output={landed.combined!r}"
    )
    for code in (
        "unregistered_todo",
        "stale_register_entry",
        "register_grew",
        "register_row_incomplete",
        "first_seen_after_earliest_todo_commit",
        "first_seen_evidence_unavailable",
    ):
        assert code not in landed.combined, (
            f"a landed admitted row must draw no {code} finding; " f"output={landed.combined!r}"
        )
