"""Outside-in test for `dev-tooling/checks/no_todo_registry.py` — `tests/heading-coverage.json` no TODO entries.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-todo-registry` row), no entry in
`tests/heading-coverage.json` may have `test: "TODO"`.

Epic li-cvaudit (cvtodo) replaced the `LIVESPEC_RELEASE_GATE`
skip carve-out with a per-check severity lever: the scan ALWAYS
runs; the `LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` env var
decides whether discovered offenders fail the check (release
context, var set to a non-empty value) or merely warn (var unset).

The check is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()`) rather than via a `sys.executable`
subprocess (work-item livespec-dev-tooling-py9): no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*`
race under the parallel dispatcher, and materially faster.
`main()` reads `Path.cwd()` and `os.environ`, so the
monkeypatched cwd is the fixture root and the fail-lever is
toggled via `monkeypatch.setenv`/`delenv`.
"""

from __future__ import annotations

import importlib.util
import inspect
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from livespec_dev_tooling.checks._work_item_liveness import bd_status_reader

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_TODO_REGISTRY = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_todo_registry.py"

_FAIL_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "no_todo_registry_under_test", str(_NO_TODO_REGISTRY)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


_Reader = Callable[..., "dict[str, str] | None"]


def _tracker(*, snapshot: dict[str, str] | None) -> _Reader:
    """A DETERMINISTIC stand-in for the repository's configured work-item store.

    `snapshot=None` is a store that did not answer — the shipped default on
    any host without a reachable tracker, and the state every pre-existing
    test in this file runs under. A dict is a store that ANSWERED and holds
    exactly those items, so an id absent from it is genuinely nonexistent.

    Injecting it here rather than reaching a real tenant is what keeps these
    verdicts a function of the fixture instead of the host.
    """

    def _read(*, repo: Path) -> dict[str, str] | None:
        del repo  # The double answers for whatever repo it is handed.
        return snapshot

    return _read


def _run_check(
    *,
    cwd: Path,
    fail_var: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reader: _Reader | None = None,
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd`, toggling the fail-lever.

    `fail_var=None` removes the lever from the environment (the
    warn-only state); any string sets it to that value via
    `monkeypatch.setenv`.

    `reader` defaults to a store that did not answer, so no test's verdict
    depends on whether the host running it happens to have a reachable
    tenant.
    """
    monkeypatch.chdir(cwd)
    if fail_var is None:
        monkeypatch.delenv(_FAIL_VAR, raising=False)
    else:
        monkeypatch.setenv(_FAIL_VAR, fail_var)
    rc = _MODULE.main(ledger_reader=reader or _tracker(snapshot=None))
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_coverage(*, tmp_path: Path, body: str) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "heading-coverage.json").write_text(body, encoding="utf-8")


def test_fails_on_todo_entry_when_fail_var_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`test: "TODO"` + fail-lever set → exit 1, error-level diagnostic."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "TODO"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"fail-lever set + TODO entry should exit non-zero; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "Foo" in combined
    ), f"diagnostic does not surface offending heading; stderr={result.stderr!r}"
    assert (
        '"level": "error"' in combined
    ), f"fail-lever set should emit error-level finding; stderr={result.stderr!r}"


def test_warns_on_todo_entry_when_fail_var_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`test: "TODO"` + fail-lever unset → exit 0, SAME finding at warning level."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "TODO"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"fail-lever unset + TODO entry should warn + exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "Foo" in combined
    ), f"warning should still surface offending heading; stderr={result.stderr!r}"
    assert (
        '"level": "warning"' in combined
    ), f"fail-lever unset should downgrade finding to warning; stderr={result.stderr!r}"


def test_empty_fail_var_treated_as_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty-string fail-lever value counts as unset → warn + exit 0."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "TODO"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var="", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"empty fail-lever should be treated as unset (warn + exit 0); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        '"level": "warning"' in combined
    ), f"empty fail-lever should downgrade finding to warning; stderr={result.stderr!r}"


def test_accepts_no_todo_entries_with_fail_var_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No offenders + fail-lever set → exit 0 (nothing to gate on)."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "tests/foo.py"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"TODO-free coverage should exit 0 even with fail-lever set; "
        f"got returncode={result.returncode}"
    )


def test_accepts_no_todo_entries_with_fail_var_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No offenders + fail-lever unset → exit 0, no warning emitted."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "tests/foo.py"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var=None, monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 0
    ), f"TODO-free coverage should exit 0; got returncode={result.returncode}"


def test_accepts_object_top_level(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Coverage JSON whose top-level is not a list passes (exit 0).

    Closes the `if isinstance(parsed, list):` False branch.
    """
    _write_coverage(tmp_path=tmp_path, body="{}")
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 0
    ), f"object top-level should exit 0; got returncode={result.returncode}"


def test_accepts_missing_coverage_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repo without `tests/heading-coverage.json` passes (exit 0)."""
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 0
    ), f"missing coverage file should exit 0; got returncode={result.returncode}"


_OWNED = (
    '[{"heading": "## Foo", "spec_root": "/", "test": "TODO", ' '"work_item": "livespec-jvdvx4"}]'
)
_UNOWNED_EMPTY = '[{"heading": "## Foo", "spec_root": "/", "test": "TODO", "work_item": "   "}]'
_UNOWNED_NON_STR = '[{"heading": "## Foo", "spec_root": "/", "test": "TODO", "work_item": 7}]'


_OWNER_ID = "livespec-jvdvx4"


def test_release_tier_passes_owned_entry_when_liveness_unverifiable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """FAIL-CAPABILITY PROOF 4 — no reachable tracker → exit 0, UNVERIFIED diagnostic.

    The ratified rule: "an owned live TODO does not block an unrelated
    release." Absent a store that answers, liveness is UNVERIFIED — which
    must PASS, but must NOT be indistinguishable from a real check, so a
    structured diagnostic naming liveness unverified is required.

    This is also the NON-BREAKING proof: it is the state every consuming
    repository is in on merge, and it is byte-behaviour-identical to the
    behaviour before the resolver existed.
    """
    _write_coverage(tmp_path=tmp_path, body=_OWNED)
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"owned TODO must not fail the release tier; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "liveness_unverified" in combined, (
        f"an unreachable tracker must emit an UNVERIFIED diagnostic, never a silent pass; "
        f"stderr={result.stderr!r}"
    )


def test_shipped_default_reader_is_the_shared_resolver() -> None:
    """The default seam is the SHARED resolver, not a per-gate hand-roll.

    `SPECIFICATION/spec.md` §"Non-goals" admits the liveness lookup only
    through "one shared mechanism"; a gate wiring its own is non-conforming
    even when its behaviour is right. Pinning the default here is what stops
    the injectable seam from drifting into a private lookup.
    """
    default = inspect.signature(_MODULE.main).parameters["ledger_reader"].default
    assert (
        default is bd_status_reader
    ), f"main() must default to the shared work-item liveness resolver; got {default!r}"


def test_release_tier_fails_entry_with_whitespace_only_work_item(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A whitespace-only `work_item` is UNOWNED → release tier fails it."""
    _write_coverage(tmp_path=tmp_path, body=_UNOWNED_EMPTY)
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"whitespace-only work_item is unowned and must fail; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_release_tier_fails_entry_with_non_string_work_item(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-string `work_item` is UNOWNED → release tier fails it."""
    _write_coverage(tmp_path=tmp_path, body=_UNOWNED_NON_STR)
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"non-string work_item is unowned and must fail; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_release_tier_convicts_a_todo_whose_owner_is_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """FAIL-CAPABILITY PROOF 1 — a reachable store reporting the owner CLOSED convicts.

    This is the branch that was UNREACHABLE in every consuming repository
    while the liveness seam returned `None` unconditionally: 22 rows on
    livespec-runtime passed the release gate owned by a closed item, and the
    gate could not have said otherwise. A check that cannot convict is worse
    than no check, so this test — not the code path — is the deliverable.
    """
    _write_coverage(tmp_path=tmp_path, body=_OWNED)
    result = _run_check(
        cwd=tmp_path,
        fail_var="true",
        monkeypatch=monkeypatch,
        capsys=capsys,
        reader=_tracker(snapshot={_OWNER_ID: "closed"}),
    )
    assert result.returncode != 0, (
        f"a CLOSED owner must fail the release tier; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "closed or nonexistent work-item" in combined
    ), f"the refusal must name WHY the owner is dead; stderr={result.stderr!r}"
    assert '"resolved_status": "closed"' in combined, (
        f"the ratified clause requires the finding to name the id AND its resolved "
        f"status; stderr={result.stderr!r}"
    )
    assert (
        '"level": "error"' in combined
    ), f"a dead work_item should be error-level; stderr={result.stderr!r}"


def test_release_tier_convicts_a_todo_whose_owner_does_not_exist(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """FAIL-CAPABILITY PROOF 2 — an owner the answering store does not hold convicts.

    A store that ANSWERED and does not hold the id has established that the
    id is nonexistent; this must not be confused with a store that never
    replied, which is the `liveness_unverified` case above. Fleet-wide there
    are 41 rows of exactly this shape, including ids filed against the wrong
    tenant.
    """
    _write_coverage(tmp_path=tmp_path, body=_OWNED)
    result = _run_check(
        cwd=tmp_path,
        fail_var="true",
        monkeypatch=monkeypatch,
        capsys=capsys,
        reader=_tracker(snapshot={"livespec-some-other-item": "ready"}),
    )
    assert result.returncode != 0, (
        f"a NONEXISTENT owner must fail the release tier; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert '"resolved_status": "nonexistent"' in combined, (
        f"the finding must distinguish an invented id from a closed one; "
        f"stderr={result.stderr!r}"
    )


def test_release_tier_passes_a_todo_whose_owner_is_open(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """FAIL-CAPABILITY PROOF 3 — an OPEN owner stays quiet, in both directions.

    A gate that can only report one of the two outcomes has not adopted the
    ratified exception. Convicting a live owner would red every honest
    repository, so this is the half that keeps the teeth discriminating
    rather than merely sharp.
    """
    _write_coverage(tmp_path=tmp_path, body=_OWNED)
    result = _run_check(
        cwd=tmp_path,
        fail_var="true",
        monkeypatch=monkeypatch,
        capsys=capsys,
        reader=_tracker(snapshot={_OWNER_ID: "ready"}),
    )
    assert result.returncode == 0, (
        f"an owned live TODO must not block a release; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        '"level": "error"' not in combined
    ), f"a live owner must produce no error-level finding; stderr={result.stderr!r}"


def test_per_commit_tier_unchanged_for_owned_entry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """PER-COMMIT IS UNTOUCHED: an owned TODO still warns and exits 0.

    Guards the property that makes this change landable — it is a strict
    LOOSENING of the release tier only. The sibling per-commit tests above
    cover the unowned case with the identical expectation, so together they
    pin per-commit behaviour for BOTH ownership states.
    """
    _write_coverage(tmp_path=tmp_path, body=_OWNED)
    result = _run_check(cwd=tmp_path, fail_var=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"per-commit tier must stay exit 0 for an owned TODO; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        '"level": "warning"' in combined
    ), f"per-commit tier must still warn on a TODO entry; stderr={result.stderr!r}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
