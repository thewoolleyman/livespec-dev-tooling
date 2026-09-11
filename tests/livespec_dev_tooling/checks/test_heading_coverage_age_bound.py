"""FAIL-CAPABILITY PROOF for the release-tier heading-coverage age bound.

Charter D5 of plan `fleet-heading-coverage-convergence`, ratified into this
repository's `SPECIFICATION/non-functional-requirements.md` at v064:

> A `TODO` older than the repository's configured age bound (default 30 days
> from first-seen) MUST fail the release tier. Liveness and age are evaluated
> ONLY at the release tier, so no per-commit verdict depends on mutable
> external state.

A bound that cannot convict is worse than no bound: it reports a converging
transition while the debt ages behind it. These tests therefore drive the
direction from the OUTSIDE — through `heading_coverage_debt_register.main()`,
the check an operator actually runs — against real fixture trees, and they
prove BOTH halves of the ratified sentence:

- the same unchanged row is REFUSED with the release lever set and PASSES
  without it, which is what "release-tier-only" means operationally; and
- a row inside the bound passes at the release tier, so the direction is not
  a check that fails on everything.

Ages are computed RELATIVE TO TODAY (`datetime.now(timezone.utc).date()`, the
same basis the check reads) rather than written as literals. A literal date
would make each test's verdict flip on a calendar day nobody chose, which is
the mutable-external-state failure this whole direction is confined to the
release tier to avoid.

Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` + `rc = main()`)
exactly as `test_heading_coverage_debt_register.py` is, so no
`COVERAGE_PROCESS_START`-instrumented child races the parallel dispatcher.

## WHY THIS MODULE CARRIES `pytestmark = pytest.mark.integration`

Every test here drives the shipped check's `main()` end to end against a real
git repository — nothing is doubled — so the file is integration-tier in
NATURE, and the `scenarios.md` heading this mechanism answers now maps to a node
in it rather than carrying a `TODO` row in the debt register. `heading_coverage`
direction 4 refuses a `scenarios.md` heading mapped to a unit-tier test, and it
decides the tier one of two ways: an allowlisted node-id prefix (`tests.consumer`
and friends), or a STATIC `pytest.mark.integration` on the resolved test. This
file cannot take the first route — `tests_mirror_pairing` requires a check's
tests to mirror the module they exercise, which puts them here — so it takes the
second. The marker is a tier LABEL the AST resolver reads, never a selector: no
recipe or workflow passes `-m`, so nothing is filtered in or out by it.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from livespec_dev_tooling.config import ConfigParseError

__all__: list[str] = []

pytestmark = pytest.mark.integration


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "heading_coverage_debt_register.py"

_FAIL_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"
_SCOPE_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF"

_REGISTRY_RELPATH = "tests/heading-coverage.json"
_REGISTER_RELPATH = "tests/heading-coverage-debt.json"

_DEFAULT_BOUND_DAYS = 30


def _days_ago(*, days: int) -> str:
    """An ISO date `days` before today, on the check's own UTC basis."""
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


def _todo(*, heading: str) -> dict[str, object]:
    """A live registry row carrying transitional debt."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "test": "TODO",
        "reason": "owed integration-tier test",
        "work_item": "livespec-dev-tooling-own",
    }


def _resolved(*, heading: str) -> dict[str, object]:
    """A live registry row whose heading has a real test — no longer debt."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "test": "tests.consumer.test_thing.test_it",
    }


def _entry(*, heading: str, first_seen: str) -> dict[str, object]:
    """A debt-register entry for `heading`, first seen on `first_seen`."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "work_item": "livespec-dev-tooling-own",
        "first_seen": first_seen,
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
        "heading_coverage_age_bound_under_test", str(_MODULE_PATH)
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


def _seed_repo(*, tmp_path: Path, registry: object, register: object) -> None:
    """A git repo whose `HEAD` already carries both files.

    Both are committed so the three history-bearing directions are satisfied on
    an untouched tree: whatever these tests catch is the AGE direction and not a
    ratchet finding riding along.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, entries=registry)
    _write(tmp_path=tmp_path, relpath=_REGISTER_RELPATH, entries=register)
    _git(cwd=tmp_path, args=["add", _REGISTRY_RELPATH, _REGISTER_RELPATH])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline"])


def _declare_bound(*, tmp_path: Path, value: str) -> None:
    """Declare `heading_coverage_todo_age_bound_days = <value>` in the fixture repo."""
    _ = (tmp_path / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\nheading_coverage_todo_age_bound_days = {value}\n",
        encoding="utf-8",
    )


def _run_check(
    *,
    cwd: Path,
    release: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd`; `release=False` removes the lever.

    The staged-diff scope lever is removed on every run. It narrows the RATCHET
    directions only, and leaving an ambient one set would make these tests read
    a scope decision as an age verdict.
    """
    monkeypatch.chdir(cwd)
    monkeypatch.delenv(_SCOPE_VAR, raising=False)
    if release:
        monkeypatch.setenv(_FAIL_VAR, "true")
    else:
        monkeypatch.delenv(_FAIL_VAR, raising=False)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, combined=captured.out + captured.err)


def test_a_row_older_than_the_bound_fails_the_release_tier(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a `TODO` past its age bound is refused at the release tier.

    31 days under the default 30-day bound: one day past, so the conviction
    rests on the bound itself rather than on a comfortable margin.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Aged")],
        register=[_entry(heading="## Aged", first_seen=_days_ago(days=_DEFAULT_BOUND_DAYS + 1))],
    )
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a TODO first seen 31 days ago must fail the release tier under the "
        f"30-day default; got returncode={result.returncode} output={result.combined!r}"
    )
    assert "todo_past_age_bound" in result.combined
    assert (
        "## Aged" in result.combined
    ), f"the refusal must name the row it judged; output={result.combined!r}"
    assert '"age_days": 31' in result.combined
    assert '"age_bound_days": 30' in result.combined


def test_the_same_aged_row_passes_the_per_commit_tier(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: the same unchanged row does not fail the per-commit tier.

    This is the half of the ratified sentence that protects master: age is
    mutable external state, so a per-commit verdict on it could turn the branch
    red with no landed change. The row is still REPORTED, and the report names
    the lever that would judge it — an unarmed run must never be
    indistinguishable from a clean register.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Aged")],
        register=[_entry(heading="## Aged", first_seen=_days_ago(days=_DEFAULT_BOUND_DAYS + 1))],
    )
    result = _run_check(cwd=tmp_path, release=False, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"age is evaluated ONLY at the release tier, so the per-commit tier must "
        f"warn and pass; got returncode={result.returncode} output={result.combined!r}"
    )
    assert "## Aged" in result.combined
    assert _FAIL_VAR in result.combined
    assert (
        '"level": "error"' not in result.combined
    ), f"the per-commit tier must not report at error level; output={result.combined!r}"


def test_a_row_younger_than_the_bound_passes_the_release_tier(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a one-day-old `TODO` is a transition, not a violation."""
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Fresh")],
        register=[_entry(heading="## Fresh", first_seen=_days_ago(days=1))],
    )
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"a TODO first seen 1 day ago must pass the release tier; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "todo_past_age_bound" not in result.combined


def test_a_row_exactly_at_the_bound_passes_the_release_tier(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The bound is the age a `TODO` may REACH, not the first age it may not.

    Pinned because an off-by-one here is invisible in ordinary use and silently
    shortens every repository's stated window by a day.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Exactly")],
        register=[_entry(heading="## Exactly", first_seen=_days_ago(days=_DEFAULT_BOUND_DAYS))],
    )
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"a TODO exactly at the bound must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )


def test_the_bound_is_configurable_and_a_shorter_one_convicts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository may declare its own bound; 30 is the default, not the rule.

    The same 8-day-old row passes under the default and fails under a declared
    7-day bound, so the declaration is proven to be READ rather than merely
    accepted.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Aged")],
        register=[_entry(heading="## Aged", first_seen=_days_ago(days=8))],
    )
    under_default = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert under_default.returncode == 0, (
        f"8 days is inside the 30-day default; "
        f"got returncode={under_default.returncode} output={under_default.combined!r}"
    )
    _declare_bound(tmp_path=tmp_path, value="7")
    under_declared = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert under_declared.returncode != 0, (
        f"a declared 7-day bound must refuse an 8-day-old row; "
        f"got returncode={under_declared.returncode} output={under_declared.combined!r}"
    )
    assert '"age_bound_days": 7' in under_declared.combined


def test_a_non_positive_declared_bound_is_a_config_error(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A zero bound is unsatisfiable, not strict — the loader refuses it outright.

    Every row is born past a zero-day bound, including the row a spec-first
    change is OBLIGED to file, so accepting it would make the registry
    unwritable. Refusing it at the loader is what keeps that from being
    discovered as a mysterious release red.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Aged")],
        register=[_entry(heading="## Aged", first_seen=_days_ago(days=1))],
    )
    _declare_bound(tmp_path=tmp_path, value="0")
    with pytest.raises(ConfigParseError, match="heading_coverage_todo_age_bound_days"):
        _ = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)


def test_a_true_declared_bound_is_refused_rather_than_read_as_one_day(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """TOML `true` is a Python `bool`, and `bool` is an `int` — so it must be caught.

    Unrefused it would parse as a ONE-DAY bound, which fails almost every row
    while looking like an enthusiastic opt-in rather than a typo.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Aged")],
        register=[_entry(heading="## Aged", first_seen=_days_ago(days=1))],
    )
    _declare_bound(tmp_path=tmp_path, value="true")
    with pytest.raises(ConfigParseError, match="positive integer"):
        _ = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)


def test_an_unmeasurable_first_seen_is_convicted_at_the_release_tier(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `first_seen` that is not a date has no age, and that is a conviction.

    "I cannot tell how old this is" must never be spelled the same way as "it is
    young": read as young, a malformed entry would be exactly the hand-edit that
    buys an unbounded extension.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## Undated")],
        register=[_entry(heading="## Undated", first_seen="someday")],
    )
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"an unmeasurable first_seen must be refused at the release tier; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "todo_first_seen_unmeasurable" in result.combined
    assert "## Undated" in result.combined


def test_a_non_string_first_seen_is_unmeasurable_too(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A JSON number is not a date either, and must not crash the date read.

    The register's schema direction convicts this row as well; both diagnostics
    firing is correct — the entry is BOTH incomplete and unmeasurable — and this
    pins that the age direction reaches its own verdict rather than raising.
    """
    numeric = _entry(heading="## Numeric", first_seen="unused")
    numeric["first_seen"] = 20260909
    _seed_repo(tmp_path=tmp_path, registry=[_todo(heading="## Numeric")], register=[numeric])
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a non-string first_seen must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "todo_first_seen_unmeasurable" in result.combined


def test_an_entry_whose_row_is_no_longer_todo_gets_no_age_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale entry is ONE defect, and the ratchet already names it.

    Aging it too would report a single mistake as two findings and send the
    author to resolve a heading that is already resolved.
    """
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_resolved(heading="## Stale")],
        register=[_entry(heading="## Stale", first_seen=_days_ago(days=365))],
    )
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a stale register entry must still be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "stale_register_entry" in result.combined
    assert (
        "todo_past_age_bound" not in result.combined
    ), f"a resolved heading must get no age verdict; output={result.combined!r}"


def test_unkeyed_rows_on_either_side_get_no_age_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a `(spec_root, spec_file, heading)` key there is nothing to age.

    An unkeyed row is `heading_coverage`'s business, exactly as it is for the
    ratchet directions — the age bound must not invent a second, differently
    worded complaint about it.
    """
    unkeyed_entry = _entry(heading="## Unkeyed", first_seen=_days_ago(days=365))
    del unkeyed_entry["spec_root"]
    unkeyed_todo = _todo(heading="## Unkeyed")
    del unkeyed_todo["spec_root"]
    _seed_repo(
        tmp_path=tmp_path,
        registry=[_todo(heading="## A"), unkeyed_todo],
        register=[_entry(heading="## A", first_seen=_days_ago(days=1)), unkeyed_entry],
    )
    result = _run_check(cwd=tmp_path, release=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"unkeyed rows belong to heading_coverage, not to the age bound; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "## Unkeyed" not in result.combined
