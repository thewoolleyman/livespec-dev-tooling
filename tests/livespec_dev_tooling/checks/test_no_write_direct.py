"""Outside-in test for `dev-tooling/checks/no_write_direct.py` — bans `sys.stdout.write`/`sys.stderr.write`.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-write-direct` row), `sys.stdout.
write(...)` and `sys.stderr.write(...)` calls are banned in
`.claude-plugin/scripts/livespec/**`, `.claude-plugin/scripts/
bin/**`, and `<repo-root>/dev-tooling/**`. The full ban tier
pairs with ruff `T20` (which bans `print` / `pprint`).

Three documented exemption surfaces, all file-scope (each
supervisor file owns the private helpers its main()
dispatches to):

- `bin/_bootstrap.py` (pre-import version-check stderr).
- `livespec/doctor/run_static.py` (findings JSON stdout —
  main() calls a private `_emit_findings_json` helper).
- Every `.py` under `livespec/commands/**` (supervisor
  surface for each command).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` reads
`Path.cwd()`, so the monkeypatched cwd anchors the fixture exactly as the
child's `cwd=` argument did, and the assertion targets are unchanged —
the int exit code plus the diagnostic text, now read off `capsys` instead
of `CompletedProcess`.

The `git` spawn in `_git` STAYS: this check resolves its file universe
from the git index, so a real `git init` + `git add -A` is the behaviour
the fixture exists to produce, and replacing it with an in-process call
would be a test that no longer tests what it claims. Its hardcoded 3-key
env keeps `COVERAGE_PROCESS_START` / `COV_CORE_*` out of that child,
which is the standing requirement on an allowlisted spawn — so this file
KEEPS its `subprocess_spawn_allowlist` entry.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the `sys.stdout.write` rejection under `livespec/`, the
`sys.stderr.write` rejection under `dev-tooling/`, both `.buffer.write`
dodges (stderr under `dev-tooling/`, stdout under `livespec/`), the clean
module with no banned call, all three file-scope exemptions
(`bin/_bootstrap.py`, `doctor/run_static.py`, and a `commands/**` file),
and the empty tree. The two lines the child reached that an in-process
call cannot are the module's vendored-path guard (`sys.path.insert`) and
its `if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so neither was ever measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from tests.livespec_dev_tooling.checks.config_parse_rendering import (
    assert_main_renders_the_parse_failure,
)

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_WRITE_DIRECT = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_write_direct.py"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so `tests_no_subprocess_spawn` permits it;
    the hardcoded env is a REPLACEMENT rather than a filtered copy of
    `os.environ`, so `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach
    this child, and the developer's own git config cannot reach the fixture.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red-Green-Replay hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "no_write_direct_under_test",
        str(_NO_WRITE_DIRECT),
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
    """Seed the git fixture, then invoke the check's `main()` in-process under `cwd`."""
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_no_write_direct_rejects_sys_stdout_write_in_livespec(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `sys.stdout.write(...)` call inside livespec/ fails the check.

    Fixture: `.claude-plugin/scripts/livespec/foo.py` calls
    `sys.stdout.write("hello\\n")` inside a function. The
    check, invoked with `cwd=tmp_path`, must walk the
    livespec/bin/dev-tooling subtrees, parse each file, detect
    the banned call, exit non-zero, and surface the offending
    file plus line number.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    sys.stdout.write("hello\\n")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_write_direct should reject sys.stdout.write call; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"no_write_direct diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "9" in combined, (
        f"no_write_direct diagnostic does not surface offending line number 9; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_rejects_sys_stderr_write_in_dev_tooling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `sys.stderr.write(...)` call inside dev-tooling/ fails the check.

    Fixture: `dev-tooling/checks/foo.py` calls `sys.stderr.
    write(...)`. Confirms the check covers all three roots
    (livespec, bin, dev-tooling).
    """
    package_dir = tmp_path / "dev-tooling" / "checks"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    sys.stderr.write("oops\\n")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_write_direct should reject sys.stderr.write call in dev-tooling/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = "dev-tooling/checks/foo.py"
    assert expected_path in combined, (
        f"no_write_direct diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_rejects_sys_stderr_buffer_write_in_dev_tooling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `sys.stderr.buffer.write(...)` byte-stream call inside dev-tooling/ fails the check.

    Closes the `.buffer.write` dodge: rewriting `sys.stderr.write(...)`
    into `sys.stderr.buffer.write(...)` reaches the same stream but
    evaded the check's exact-AST match. The banned-target set now
    carries the `.buffer.write` forms, so this must be flagged
    identically to the plain write.
    """
    package_dir = tmp_path / "dev-tooling" / "checks"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    _ = sys.stderr.buffer.write(b"oops\\n")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_write_direct should reject sys.stderr.buffer.write dodge in dev-tooling/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = "dev-tooling/checks/foo.py"
    assert expected_path in combined, (
        f"no_write_direct diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_rejects_sys_stdout_buffer_write_in_livespec(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `sys.stdout.buffer.write(...)` byte-stream call inside livespec/ fails the check.

    The stdout `.buffer.write` form is banned identically to the stderr
    form — both were escape hatches around the exact-AST match.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    _ = sys.stdout.buffer.write(b"hello\\n")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_write_direct should reject sys.stdout.buffer.write dodge in livespec/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"no_write_direct diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_accepts_module_without_banned_calls(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A module with no `sys.{stdout,stderr}.write` calls passes the check (exit 0).

    Pass-case: a livespec module that uses the structlog facade
    instead of direct sys.{stdout,stderr}.write. The check
    walks every relevant subtree and exits 0.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_write_direct should accept clean module with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_accepts_bin_bootstrap_file_scope_exemption(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`bin/_bootstrap.py` is exempted file-scope; `sys.stderr.write` permitted.

    Pass-case: `.claude-plugin/scripts/bin/_bootstrap.py`
    contains the canonical pre-import version-check stderr
    write. The check skips the file entirely (file-scope
    exemption) and exits 0.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "_bootstrap.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def bootstrap() -> None:\n"
        '    sys.stderr.write("python too old\\n")\n',
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_write_direct should exempt bin/_bootstrap.py with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_accepts_doctor_run_static_file_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`livespec/doctor/run_static.py` is file-scope exempt.

    Pass-case: `.claude-plugin/scripts/livespec/doctor/
    run_static.py` calls `sys.stdout.write(...)` from inside
    its private helper `_emit_findings_json`, which the
    supervisor's `main()` dispatches to (findings JSON
    contract). File-scope exemption covers the helper.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "doctor"
    package_dir.mkdir(parents=True)
    source = package_dir / "run_static.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def _emit_findings_json() -> None:\n"
        '    _ = sys.stdout.write("{\\"findings\\": []}\\n")\n'
        "\n"
        "\n"
        "def main() -> int:\n"
        "    _emit_findings_json()\n"
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_write_direct should exempt doctor/run_static.py file-scope with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_accepts_commands_file_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Files under `livespec/commands/**` are file-scope exempt.

    Pass-case: `.claude-plugin/scripts/livespec/commands/
    seed.py` calls `sys.stdout.write(...)` from a private
    helper. File-scope exemption covers the entire commands
    subtree (each command supervisor owns its private
    helpers).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "commands"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def _render_help() -> None:\n"
        '    _ = sys.stdout.write("usage: seed ...\\n")\n'
        "\n"
        "\n"
        "def main() -> int:\n"
        "    _render_help()\n"
        "    return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_write_direct should exempt commands/ file-scope with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_accepts_empty_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo cwd without any in-scope subtrees passes the check (exit 0).

    Closes the `if root.is_dir():` False arm for every covered
    subtree.
    """
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_write_direct should accept empty tree with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_write_direct_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_write_direct_for_import_test",
        str(_NO_WRITE_DIRECT),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_main_renders_the_consumer_config_parse_failure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed consumer config is a structured diagnostic, never a traceback.

    `SPECIFICATION/contracts.md` section "Configuration loader" puts the catch
    at this check's `main()` supervisor; before `livespec-dev-tooling-efxa`
    the `ConfigParseError` escaped from here as an uncaught traceback, which
    reaches stderr through the interpreter rather than through structlog and
    so broke the very output discipline this package exists to enforce.
    """
    assert_main_renders_the_parse_failure(
        module_slug="no_write_direct",
        check_id="no_write_direct",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
