"""FAIL-CAPABILITY PROOF for `heading_coverage`'s TODO-`reason` acknowledgment guard.

Charter D4 of plan `fleet-heading-coverage-convergence` (epic
`livespec-dev-tooling-0bse`), ratified into this repository's
`SPECIFICATION/non-functional-requirements.md` at v064:

> The `reason` MUST acknowledge that a real test at the required tier is owed
> and MUST name nothing else. A `reason` asserting that the heading is not
> testable, is enforced elsewhere, or is prose without behavior MUST be
> rejected by `heading_coverage`.

A guard that cannot convict is worse than no guard: it reports an
acknowledgment regime while the cop-outs keep landing. The three wordings
below are the ones the 2026-09-06 fleet resolution actually produced (plan
research `003`), so they are the fixtures — one per ratified family:

- `No independently testable assertion at runtime` → non-testability;
- `Enforced by CHECKS rather than a pytest test` → enforced-elsewhere;
- `orientation prose` → prose-without-behavior.

Plus the fourth defect the positive half of the predicate produces — a reason
that asserts nothing but acknowledges nothing either — and the ACCEPTING case
the guard exists to leave alone: a reason acknowledging an owed
integration-tier test, naming a live owning `work_item`.

The scope lever is exercised as its own three cases, because at P1 landing the
fleet's 373 inherited rows carry rejected reasons: the guard must refuse a
NEWLY-AUTHORED cop-out, must spare an INHERITED one while still reporting it
(charter D2b — a commit is judged on what it authors), and must fall back to
judging everything, loudly, when it cannot tell what changed.

Driven against a REAL git repository, because the scope verdict is a statement
about `HEAD`; a double would prove only that the code calls the functions it
calls. Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` +
`rc = main()`) exactly as `test_heading_coverage.py` and
`test_heading_coverage_debt_register.py` are, so no
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
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "heading_coverage.py"

_SCOPE_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF"

_REGISTRY_RELPATH = "tests/heading-coverage.json"
_SPEC_RELPATH = "SPECIFICATION/spec.md"

_INHERITED = "## Inherited"
_AUTHORED = "## Authored"

_ACKNOWLEDGING = (
    "The owed integration-tier test for this heading lands with work-item "
    "livespec-dev-tooling-0bse.2; replace TODO with its node id when it lands."
)

_COP_OUTS: tuple[tuple[str, str], ...] = (
    ("No independently testable assertion at runtime.", "asserts-non-testability"),
    ("Enforced by CHECKS rather than a pytest test.", "asserts-enforced-elsewhere"),
    ("This heading is orientation prose.", "asserts-prose-without-behavior"),
    ("Seeded by the revise pass on 2026-09-06.", "does-not-acknowledge-an-owed-test"),
)


def _load_check_module() -> ModuleType:
    """Import `heading_coverage` fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red→Green hook inspects, and so `main()`
    can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "heading_coverage_reason_guard_under_test", str(_MODULE_PATH)
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


def _row(*, heading: str, reason: str) -> dict[str, object]:
    """A `spec.md` registry row carrying transitional debt.

    `spec.md` rather than `scenarios.md` on purpose: direction 4 governs only
    `scenarios.md`, so these fixtures isolate the reason guard from the
    pre-existing tier direction.
    """
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": heading,
        "test": "TODO",
        "reason": reason,
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


def _write(*, tmp_path: Path, relpath: str, body: str) -> None:
    target = tmp_path / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")


def _write_tree(*, tmp_path: Path, rows: list[dict[str, object]]) -> None:
    """Write a spec tree whose headings are exactly the ones `rows` covers.

    Both files move together so the uncovered and orphan directions stay
    silent and the run's verdict is the reason guard's alone.
    """
    headings = "\n\n".join(f"{row['heading']}\n\nbody" for row in rows)
    _write(tmp_path=tmp_path, relpath=_SPEC_RELPATH, body=f"# Title\n\n{headings}\n")
    _write(tmp_path=tmp_path, relpath=_REGISTRY_RELPATH, body=json.dumps(rows, indent=2) + "\n")


def _seed_repo(*, tmp_path: Path, rows: list[dict[str, object]]) -> None:
    """A git repo whose `HEAD` carries `rows` — the debt this tree INHERITS."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    _write_tree(tmp_path=tmp_path, rows=rows)
    _git(cwd=tmp_path, args=["add", "."])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline"])


def _stage(*, tmp_path: Path, rows: list[dict[str, object]]) -> None:
    """Overwrite and stage the tree, as an author mid-commit would."""
    _write_tree(tmp_path=tmp_path, rows=rows)
    _git(cwd=tmp_path, args=["add", "."])


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


@pytest.mark.parametrize(("reason", "defect"), _COP_OUTS)
def test_a_newly_authored_cop_out_reason_is_rejected(
    *,
    reason: str,
    defect: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SCENARIO: a `reason` asserting non-testability is rejected.

    There is no non-testable category: a heading a repository believes has no
    behavior is a specification-structure defect to be fixed in the
    specification, never a coverage exemption.
    """
    _seed_repo(tmp_path=tmp_path, rows=[_row(heading=_INHERITED, reason=_ACKNOWLEDGING)])
    _stage(
        tmp_path=tmp_path,
        rows=[
            _row(heading=_INHERITED, reason=_ACKNOWLEDGING),
            _row(heading=_AUTHORED, reason=reason),
        ],
    )
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a newly-authored TODO reason of the {defect} family must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert (
        defect in result.combined
    ), f"the refusal must name the defect family it found; output={result.combined!r}"
    assert (
        _AUTHORED in result.combined
    ), f"the refusal must name the row it judged; output={result.combined!r}"


def test_a_reason_acknowledging_an_owed_integration_tier_test_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: the one legal justification — an owed test with a live owner.

    The guard must leave the ratified transitional state alone, or it would
    forbid the spec-first placeholder the v009 clause exists to permit.
    """
    _seed_repo(tmp_path=tmp_path, rows=[_row(heading=_INHERITED, reason=_ACKNOWLEDGING)])
    _stage(
        tmp_path=tmp_path,
        rows=[
            _row(heading=_INHERITED, reason=_ACKNOWLEDGING),
            _row(heading=_AUTHORED, reason=_ACKNOWLEDGING),
        ],
    )
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"a reason acknowledging an owed integration-tier test with a live owner is "
        f"the legal transitional state and must pass; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )


def test_the_scope_lever_spares_an_inherited_cop_out_and_still_reports_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A commit is judged on what it authors, never on debt it inherited.

    At P1 landing the fleet's 373 rows carry rejected reasons; convicting them
    on an unrelated commit is the `livespec-dev-tooling-3ztbdq` shape that made
    the shared co-edit registry unwritable. Narrowing the VERDICT must not
    narrow the REPORT, or an inherited cop-out becomes indistinguishable from
    an acknowledgment.
    """
    _seed_repo(
        tmp_path=tmp_path,
        rows=[_row(heading=_INHERITED, reason="No independently testable assertion at runtime.")],
    )
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"an inherited cop-out must not fail an unrelated commit; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "out_of_staged_scope" in result.combined
    assert _INHERITED in result.combined
    assert (
        '"level": "error"' not in result.combined
    ), f"an out-of-scope finding must not be error-level; output={result.combined!r}"


def test_the_unarmed_tier_reports_every_cop_out_without_judging_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lever unset: the per-commit tier the P2 burn-down runs under.

    Reporting without judging is what keeps the guard landable ahead of the
    burn-down — and the diagnostic names the lever, so a warn-only run is never
    mistaken for a clean registry.
    """
    _seed_repo(
        tmp_path=tmp_path,
        rows=[_row(heading=_INHERITED, reason="Enforced by CHECKS rather than a pytest test.")],
    )
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"the unarmed tier must not fail; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "asserts-enforced-elsewhere" in result.combined
    assert _SCOPE_VAR in result.combined, (
        f"the warn-only diagnostic must name the lever that arms it; " f"output={result.combined!r}"
    )


def test_an_uncomputable_baseline_judges_every_finding(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No comparable `HEAD` registry → FAIL CLOSED over every finding, and say so.

    "I could not tell what changed" must never be spelled the same way as
    "nothing changed" — and where there is no `HEAD` copy at all, every row IS
    newly authored.
    """
    _write_tree(
        tmp_path=tmp_path,
        rows=[_row(heading=_AUTHORED, reason="This heading is orientation prose.")],
    )
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"an uncomputable baseline must judge every finding; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "baseline_unreadable" in result.combined


def test_an_empty_reason_stays_the_missing_reason_direction_alone(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent acknowledgment is direction 3's finding, not the guard's.

    Double-reporting one defect under two names would leave an author fixing
    the wrong thing; the guard reads only reasons that HAVE text.
    """
    _seed_repo(tmp_path=tmp_path, rows=[_row(heading=_INHERITED, reason=_ACKNOWLEDGING)])
    _stage(
        tmp_path=tmp_path,
        rows=[
            _row(heading=_INHERITED, reason=_ACKNOWLEDGING),
            _row(heading=_AUTHORED, reason="   "),
        ],
    )
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a TODO row with a blank reason must still fail; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "TODO registry entry missing reason" in result.combined
    assert (
        "reason_defect" not in result.combined
    ), f"a blank reason is direction 3's finding alone; output={result.combined!r}"
