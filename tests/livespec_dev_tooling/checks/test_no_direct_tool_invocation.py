"""Outside-in test for `dev-tooling/checks/no_direct_tool_invocation.py` — `lefthook.yml` + CI only call `just <target>`.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-direct-tool-invocation` row),
`lefthook.yml` and `.github/workflows/*.yml` only invoke
`just <target>` — no direct calls to `uv run`, `pytest`,
`ruff`, `pyright`, `lint-imports`, etc. The justfile is the
single source of truth for how dev tools are invoked.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. The four call sites
spawned identically, so they now share one `_run_check` helper; `main()`
reads `Path.cwd()`, so the monkeypatched cwd anchors the fixture exactly
as the child's `cwd=` argument did, and the assertion targets are
unchanged — the int exit code plus the diagnostic text, now read off
`capsys` instead of `CompletedProcess`.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the `uv run` lefthook offender, the `pytest` workflow offender,
the comment/blank-line skip branch on a just-only lefthook, and the
empty-tree clean exit. The two lines the child process reached that an
in-process call cannot are the module's vendored-path guard
(`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so neither was ever measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_DIRECT_TOOL = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_direct_tool_invocation.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "no_direct_tool_invocation_under_test", str(_NO_DIRECT_TOOL)
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


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and capture output."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_no_direct_tool_invocation_rejects_uv_run_in_lefthook(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `lefthook.yml` containing `uv run` fails the check."""
    lefthook = tmp_path / "lefthook.yml"
    lefthook.write_text(
        "pre-commit:\n" "  commands:\n" "    pytest:\n" "      run: uv run pytest\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_direct_tool_invocation should reject uv-run in lefthook.yml; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "lefthook.yml" in combined, (
        f"diagnostic does not surface offending file `lefthook.yml`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_direct_tool_invocation_rejects_pytest_in_workflow(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A workflow YAML calling `pytest` directly fails the check."""
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "ci.yml"
    workflow.write_text(
        "jobs:\n" "  test:\n" "    runs-on: ubuntu-latest\n" "    steps:\n" "      - run: pytest\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_direct_tool_invocation should reject `pytest` in workflow; "
        f"got returncode={result.returncode}"
    )


def test_no_direct_tool_invocation_accepts_just_only_lefthook(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `lefthook.yml` invoking only `just <target>` passes (exit 0).

    Fixture includes blank lines and `#`-prefixed comments to
    exercise the `if not stripped or stripped.startswith("#")`
    skip branch.
    """
    lefthook = tmp_path / "lefthook.yml"
    lefthook.write_text(
        "# Top-level comment skipped by the line scan.\n"
        "\n"
        "pre-commit:\n"
        "  commands:\n"
        "    check:\n"
        "      # nested comment\n"
        "      run: just check\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_direct_tool_invocation should accept just-only lefthook; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_direct_tool_invocation_accepts_empty_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty repo cwd passes (exit 0)."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_direct_tool_invocation should accept empty tree; "
        f"got returncode={result.returncode}"
    )


def test_no_direct_tool_invocation_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_direct_tool_invocation_for_import_test",
        str(_NO_DIRECT_TOOL),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
