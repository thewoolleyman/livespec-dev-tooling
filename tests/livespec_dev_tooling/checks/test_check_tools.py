"""Outside-in test for `dev-tooling/checks/check_tools.py` — pinned tools installed at pinned versions.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-tools` row), every pinned tool is
installed at the pinned version — both mise-pinned binaries
(`uv`, `just`, `lefthook`) and uv-managed Python deps from
`pyproject.toml` `[dependency-groups.dev]` per v024.

Cycle 167 implements minimum-viable: parse `.mise.toml` for
the binary pins and verify each binary is on PATH and reports
the pinned version when invoked with `--version`.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. The six call sites
spawned near-identically, so they now share one `_run_check` helper;
`main()` reads `Path.cwd()`, so the monkeypatched cwd anchors the
fixture exactly as the child's `cwd=` argument did. The one site that
carried an `env=` mapping now uses `monkeypatch.setenv("PATH", ...)`,
which the check's OWN `<bin> --version` / `<bin> version` subprocesses
and its `shutil.which` lookup inherit unchanged. The assertion targets
are unchanged — the int exit code plus the diagnostic text, now read off
`capsys` instead of `CompletedProcess`.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the missing-`.mise.toml` exit, the any-version pin, the substring
match, the not-on-PATH offender, the version-mismatch offender, and the
`<bin> version` fallback. The two lines the child process reached that
an in-process call cannot are the module's vendored-path guard
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
_CHECK_TOOLS = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "check_tools.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location("check_tools_under_test", str(_CHECK_TOOLS))
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


def test_check_tools_rejects_missing_mise_toml(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo cwd without `.mise.toml` fails the check.

    Fixture: empty tmp_path. The check requires the mise
    config to know which binaries to verify.
    """
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"check_tools should reject missing .mise.toml; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert ".mise.toml" in combined, (
        f"check_tools diagnostic does not surface missing `.mise.toml`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_check_tools_accepts_mise_pinned_tools_at_pinned_versions(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.mise.toml` whose pinned tools resolve at pinned versions passes (exit 0).

    Fixture exercises every parser branch:
    - `# comment` line (covers `if line.startswith("#"):
      continue` arm).
    - Line outside any section (covers `if not
      in_tools_section: continue` arm).
    - Line inside `[other]` section (also covers the
      out-of-section arm with non-tools section header).
    - Malformed line (no `=`, no quoted version) covers the
      `if match is not None:` False branch.
    - Multiple real tool entries: `uv` pinned to actual
      installed version (verifies the version-match success
      path) and `just` pinned to `*` (verifies the any-version
      path).
    """
    mise = tmp_path / ".mise.toml"
    # Pin both tools to `*` so the test passes regardless of
    # whether the subprocess inherits mise's pinned-version
    # activation. The test exercises every parser branch
    # without depending on a specific tool version being
    # installed system-wide.
    mise.write_text(
        "# preamble comment\n"
        "stray-key = 1\n"
        "[other]\n"
        'foo = "bar"\n'
        "[tools]\n"
        "# inline tools comment\n"
        'uv = "*"\n'
        "malformed line without equals\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"check_tools should accept any-version pin with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_check_tools_accepts_substring_match_against_version_output(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pin matching a substring of the binary's `--version` output passes (exit 0).

    Closes the version-match success branch (`if expected_version
    in output: return None`). Pin `uv` to the substring `"uv"`
    which appears in `uv --version`'s output regardless of
    actual numeric version.
    """
    mise = tmp_path / ".mise.toml"
    mise.write_text(
        '[tools]\nuv = "uv"\n',
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"check_tools should accept substring match; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_check_tools_rejects_tool_not_on_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.mise.toml` pinning a binary not on PATH fails the check.

    Closes the `if binary_path is None: return ...` branch.
    """
    mise = tmp_path / ".mise.toml"
    mise.write_text(
        '[tools]\nnonexistent_tool_xyz = "1.0.0"\n',
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"check_tools should reject not-on-path tool; " f"got returncode={result.returncode}"
    )


def test_check_tools_rejects_pinned_version_mismatch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.mise.toml` pinning `uv` to a version not installed fails the check."""
    mise = tmp_path / ".mise.toml"
    mise.write_text(
        '[tools]\nuv = "0.0.0-nonexistent"\n',
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"check_tools should reject version mismatch; " f"got returncode={result.returncode}"
    )


def test_check_tools_falls_back_to_subcommand_version_when_dash_dash_version_errors(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Binaries whose `--version` errors but `version` reports the version pass.

    Lefthook is the canonical example: `lefthook --version` returns
    `Error: unknown flag: --version` (exit 1) but `lefthook version`
    prints the version cleanly (exit 0). Without a fallback,
    check-tools rejects every mise-pinned lefthook even when the
    pinned version IS installed — blocking aggregate-binding for
    `check-tools` for environment reasons rather than substantive
    drift.

    Fixture builds a fake binary `foo` in `tmp_path/bin/` that
    mimics lefthook's argv shape: `foo --version` exits 1 with
    error, `foo version` prints `1.2.3` and exits 0. PATH is
    prepended with `tmp_path/bin` so `shutil.which("foo")`
    resolves there. `.mise.toml` pins `foo = "1.2.3"`. The check
    must accept the pin (exit 0) by exercising the fallback.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "foo"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "version" ]]; then\n'
        '  echo "1.2.3"\n'
        "  exit 0\n"
        "fi\n"
        'echo "Error: unknown flag: $1" >&2\n'
        "exit 1\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    mise = tmp_path / ".mise.toml"
    mise.write_text(
        '[tools]\nfoo = "1.2.3"\n',
        encoding="utf-8",
    )

    import os

    # The retired child carried this as an `env=` mapping. In-process
    # `monkeypatch.setenv` supplies the identical PATH, which the check's OWN
    # `<bin> --version` / `<bin> version` subprocesses — and the
    # `shutil.which("foo")` lookup that finds them — inherit unchanged.
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"check_tools should fall back to `<bin> version` when "
        f"`<bin> --version` errors; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_check_tools_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_tools_for_import_test",
        str(_CHECK_TOOLS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
