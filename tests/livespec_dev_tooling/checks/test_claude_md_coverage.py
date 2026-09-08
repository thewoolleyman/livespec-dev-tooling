"""Outside-in test for `dev-tooling/checks/claude_md_coverage.py` — every directory has CLAUDE.md.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-claude-md-coverage` row), every
directory under `.claude-plugin/scripts/` (excluding the
`_vendor/` subtree), `<repo-root>/tests/` (excluding the
`fixtures/` subtree at any depth), and `<repo-root>/dev-
tooling/` MUST contain a `CLAUDE.md` file.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. The five call sites
spawned identically, so they now share one `_run_check` helper; `main()`
reads `Path.cwd()`, so the monkeypatched cwd anchors the fixture exactly
as the child's `cwd=` argument did, and the assertion targets are
unchanged — the int exit code plus the offending-directory diagnostic,
now read off `capsys` instead of `CompletedProcess`.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the missing-CLAUDE.md offender, the fully-covered tree, the
`_vendor/` exemption, the `fixtures/` exemption, and the empty-tree
clean exit. The two lines the child process reached that an in-process
call cannot are the module's vendored-path guard (`sys.path.insert`) and
its `if __name__ == "__main__": raise SystemExit(main())` line; both are
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
_CLAUDE_MD_COVERAGE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "claude_md_coverage.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "claude_md_coverage_under_test", str(_CLAUDE_MD_COVERAGE)
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


def test_claude_md_coverage_rejects_directory_missing_claude_md(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory under scripts/ without CLAUDE.md fails the check.

    Fixture: `.claude-plugin/scripts/livespec/foo/` exists
    with a `.py` file inside but no `CLAUDE.md`. The check
    must walk the in-scope trees, detect the missing file,
    exit non-zero, and surface the offending directory path.
    """
    foo_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "bar.py").write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    # Need to add CLAUDE.md to ancestor dirs so the check
    # surfaces only the leaf.
    for ancestor in (
        tmp_path / ".claude-plugin" / "scripts",
        tmp_path / ".claude-plugin" / "scripts" / "livespec",
    ):
        (ancestor / "CLAUDE.md").write_text("# stub\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"claude_md_coverage should reject directory without CLAUDE.md; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo"
    assert expected_path in combined, (
        f"claude_md_coverage diagnostic does not surface offending dir `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_claude_md_coverage_accepts_fully_covered_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tree where every in-scope directory has CLAUDE.md passes (exit 0)."""
    for d in (
        tmp_path / ".claude-plugin" / "scripts",
        tmp_path / ".claude-plugin" / "scripts" / "livespec",
        tmp_path / "tests",
        tmp_path / "dev-tooling",
    ):
        d.mkdir(parents=True)
        (d / "CLAUDE.md").write_text("# stub\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"claude_md_coverage should accept fully-covered tree with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_claude_md_coverage_exempts_vendor_subtree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Directories under `_vendor/` are exempt from the CLAUDE.md requirement.

    Pass-case: `.claude-plugin/scripts/_vendor/` and any
    descendant directory has no CLAUDE.md and the check
    still exits 0.
    """
    for d in (
        tmp_path / ".claude-plugin" / "scripts",
        tmp_path / ".claude-plugin" / "scripts" / "livespec",
    ):
        d.mkdir(parents=True)
        (d / "CLAUDE.md").write_text("# stub\n", encoding="utf-8")
    vendor_lib = tmp_path / ".claude-plugin" / "scripts" / "_vendor" / "returns"
    vendor_lib.mkdir(parents=True)
    (vendor_lib / "io.py").write_text("# vendored\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"claude_md_coverage should exempt _vendor/ with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_claude_md_coverage_exempts_fixtures_subtree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Directories under any `fixtures/` subtree are exempt.

    Pass-case: `tests/fixtures/some_dir/` has no CLAUDE.md;
    the check exits 0.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "CLAUDE.md").write_text("# stub\n", encoding="utf-8")
    fixture_dir = tests_dir / "fixtures" / "deep" / "nested"
    fixture_dir.mkdir(parents=True)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"claude_md_coverage should exempt fixtures/ with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_claude_md_coverage_accepts_empty_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty repo cwd passes the check (exit 0)."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"claude_md_coverage should accept empty tree with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_claude_md_coverage_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claude_md_coverage_for_import_test",
        str(_CLAUDE_MD_COVERAGE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
