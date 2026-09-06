"""Outside-in test for `no_todo_registry`'s STAGED-DIFF scope lever.

The doc-only pre-commit (`scripts/just/check-pre-commit-doc-only.sh`) arms
the release tier whenever the staged changeset touches
`tests/heading-coverage.json`, on the reasoning that "the commit that
AUTHORS a TODO entry" should be refused an unowned one. Armed over the
WHOLE registry that reasoning does not hold: the tier judged all 58
pre-existing unowned entries too, so every commit that added a heading was
refused for entries it never touched — the registry became unwritable
(`livespec-dev-tooling-3ztbdq`).

`LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF` narrows the armed
tier's VERDICT to entries that differ from `HEAD:tests/heading-coverage.json`
— added or modified — which is the scope the script's own comment always
claimed. Pre-existing entries are still SURFACED, at warning level and
carrying an explicit `out_of_staged_scope` marker, so the narrowing never
makes an offender invisible.

Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` + `rc =
main()`) exactly as `test_no_todo_registry.py` is, so no
`COVERAGE_PROCESS_START`-instrumented child races the parallel
dispatcher. The fixtures ARE real git repositories, because the baseline
this lever reads is a real `git show HEAD:<path>` blob.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_TODO_REGISTRY = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_todo_registry.py"

_FAIL_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"
_SCOPE_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF"

_PREEXISTING_UNOWNED: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "heading": "## Pre-existing heading",
    "test": "TODO",
    "reason": "seeded before the ownership rule existed",
}
_ADDED_OWNED: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "heading": "## Added heading",
    "test": "TODO",
    "reason": "authored by the staged commit",
    "work_item": "livespec-dev-tooling-3ztbdq",
}
_ADDED_UNOWNED: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "heading": "## Added heading",
    "test": "TODO",
    "reason": "authored by the staged commit with no owner",
}


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red→Green hook inspects, and so `main()`
    can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "no_todo_registry_staged_scope_under_test", str(_NO_TODO_REGISTRY)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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


def _write_registry(*, tmp_path: Path, entries: object) -> Path:
    """Write `entries` to the fixture's `tests/heading-coverage.json`."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    registry = tests_dir / "heading-coverage.json"
    registry.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return registry


def _seed_repo(*, tmp_path: Path, baseline: object) -> None:
    """Create a git repo whose HEAD carries `baseline` as the registry."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    _ = _write_registry(tmp_path=tmp_path, entries=baseline)
    _git(cwd=tmp_path, args=["add", "tests/heading-coverage.json"])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "baseline registry"])


def _stage_registry(*, tmp_path: Path, entries: object) -> None:
    """Overwrite the registry with `entries` and stage it, as an author would."""
    _ = _write_registry(tmp_path=tmp_path, entries=entries)
    _git(cwd=tmp_path, args=["add", "tests/heading-coverage.json"])


def _run_check(
    *,
    cwd: Path,
    scope: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd` with the release tier ARMED.

    `scope=None` removes the staged-diff lever (the whole-registry state the
    bug report measured); any string sets it.
    """
    monkeypatch.chdir(cwd)
    monkeypatch.setenv(_FAIL_VAR, "true")
    if scope is None:
        monkeypatch.delenv(_SCOPE_VAR, raising=False)
    else:
        monkeypatch.setenv(_SCOPE_VAR, scope)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, combined=captured.out + captured.err)


def test_armed_tier_passes_an_added_owned_todo_beside_a_preexisting_unowned_one(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE BUG: adding one OWNED TODO must pass while an unowned one predates the commit.

    This is the exact shape that made the registry unwritable — a commit
    authoring a properly-owned entry was refused for 58 entries it never
    touched.
    """
    _seed_repo(tmp_path=tmp_path, baseline=[_PREEXISTING_UNOWNED])
    _stage_registry(tmp_path=tmp_path, entries=[_PREEXISTING_UNOWNED, _ADDED_OWNED])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"an added OWNED TODO must pass even though a pre-existing unowned entry "
        f"remains in the registry; got returncode={result.returncode} "
        f"output={result.combined!r}"
    )


def test_armed_tier_refuses_an_added_unowned_todo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The narrowing keeps the tier's whole point: an UNOWNED new entry is refused."""
    _seed_repo(tmp_path=tmp_path, baseline=[_PREEXISTING_UNOWNED])
    _stage_registry(tmp_path=tmp_path, entries=[_PREEXISTING_UNOWNED, _ADDED_UNOWNED])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"an added UNOWNED TODO must still be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert (
        "## Added heading" in result.combined
    ), f"the refusal must name the entry it judged; output={result.combined!r}"


def test_armed_tier_refuses_a_modified_preexisting_unowned_entry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """MODIFIED counts as in-scope: editing an unowned entry re-opens the ownership question."""
    _seed_repo(tmp_path=tmp_path, baseline=[_PREEXISTING_UNOWNED])
    edited = {**_PREEXISTING_UNOWNED, "reason": "reworded by the staged commit"}
    _stage_registry(tmp_path=tmp_path, entries=[edited])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a MODIFIED unowned entry is in the staged diff and must be refused; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )


def test_preexisting_unowned_entry_is_surfaced_as_out_of_scope_rather_than_hidden(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Narrowing the VERDICT must not narrow the REPORT — the entry still surfaces.

    A silent narrowing would make the pre-existing unowned entries
    indistinguishable from a clean registry, which is the failure shape this
    repo treats as worse than the red it replaces.
    """
    _seed_repo(tmp_path=tmp_path, baseline=[_PREEXISTING_UNOWNED])
    _stage_registry(tmp_path=tmp_path, entries=[_PREEXISTING_UNOWNED, _ADDED_OWNED])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert (
        "out_of_staged_scope" in result.combined
    ), f"an unjudged pre-existing TODO must still be reported; output={result.combined!r}"
    assert (
        "## Pre-existing heading" in result.combined
    ), f"the out-of-scope report must name the entry; output={result.combined!r}"
    assert (
        '"level": "error"' not in result.combined
    ), f"an out-of-scope entry must not be error-level; output={result.combined!r}"


def test_scope_lever_unset_keeps_the_whole_registry_armed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The narrowing is OPT-IN: without the lever the armed tier judges every entry.

    Release CI does not set the lever, so this pins that the release gate's
    verdict is untouched by the pre-commit fix.
    """
    _seed_repo(tmp_path=tmp_path, baseline=[_PREEXISTING_UNOWNED])
    _stage_registry(tmp_path=tmp_path, entries=[_PREEXISTING_UNOWNED, _ADDED_OWNED])
    result = _run_check(cwd=tmp_path, scope=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"with no scope lever the armed tier must still judge pre-existing entries; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )


def test_unreadable_baseline_falls_back_to_the_whole_registry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No readable HEAD copy → FAIL CLOSED over the whole registry, and say so.

    A directory that is not a git repository cannot answer what changed, and a
    scope that cannot be computed must never be silently read as "nothing is
    in scope".
    """
    _ = _write_registry(tmp_path=tmp_path, entries=[_PREEXISTING_UNOWNED, _ADDED_OWNED])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"an uncomputable scope must fall back to the whole registry; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert "baseline_unreadable" in result.combined, (
        f"the fallback must be reported, never indistinguishable from a computed scope; "
        f"output={result.combined!r}"
    )


def test_non_list_baseline_falls_back_to_the_whole_registry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A HEAD copy that is not a JSON array yields no comparable entries → fail closed."""
    _seed_repo(tmp_path=tmp_path, baseline={})
    _stage_registry(tmp_path=tmp_path, entries=[_PREEXISTING_UNOWNED, _ADDED_OWNED])
    result = _run_check(cwd=tmp_path, scope="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a non-array HEAD copy must fall back to the whole registry; "
        f"got returncode={result.returncode} output={result.combined!r}"
    )
    assert (
        "baseline_unreadable" in result.combined
    ), f"the fallback must be reported; output={result.combined!r}"
