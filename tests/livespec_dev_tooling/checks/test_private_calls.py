"""Outside-in test for `livespec_dev_tooling/checks/private_calls.py` — no cross-module `_`-prefixed calls.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-private-calls` row), no cross-module
calls to `_`-prefixed functions defined elsewhere are permitted
in `livespec/**`. Within a single module, calling `_helper()` is
fine; from another module, `other_module._helper()` is banned.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk — so each fixture is a real git repo
(`git init` + `git add -A`) before the check subprocess runs.
Phase-0 delta-WARN severity: `config.source_trees` is retained as
a classifier — a cross-module private call in a `source_trees`
file keeps today's hard gate (`error`, exit 1); the identical
violation in a NEWLY-covered file emits at WARN (`newly_covered` /
`phase="0-warn"`, exit 0).

The check is invoked as a `sys.executable` subprocess (this file is
in the documented `subprocess_spawn_allowlist`); pytest-cov's
pth-installed startup hook instruments the child.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRIVATE_CALLS = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "private_calls.py"

_CROSS_MODULE_PRIVATE_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "from livespec import other\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def main() -> int:\n"
    "    return other._helper()\n"
)


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ)."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _run_check(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    """`git init` + stage the fixture, then run the check as a consumer would."""
    _init_repo_with_files(tmp_path=cwd)
    return subprocess.run(
        [sys.executable, str(_PRIVATE_CALLS)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_private_calls_rejects_cross_module_underscore_call(*, tmp_path: Path) -> None:
    """A `other._helper()` in a `source_trees` file fails hard (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_CROSS_MODULE_PRIVATE_SOURCE,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"private_calls should reject cross-module _-call; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"private_calls diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "_helper" in combined, (
        f"private_calls diagnostic does not surface attribute `_helper`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_private_calls_accepts_self_underscore_method_call(*, tmp_path: Path) -> None:
    """A `self._helper()` (intra-class private) passes (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "class Foo:\n"
            "    def _helper(self) -> int:\n"
            "        return 0\n"
            "\n"
            "    def main(self) -> int:\n"
            "        return self._helper()\n"
        ),
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"private_calls should accept self._foo() with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_private_calls_accepts_intra_module_underscore_call(*, tmp_path: Path) -> None:
    """A `_helper()` (intra-module private) passes (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _helper() -> int:\n"
            "    return 0\n"
            "\n"
            "\n"
            "def main() -> int:\n"
            "    return _helper()\n"
        ),
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"private_calls should accept intra-module _helper() with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_private_calls_accepts_cross_module_public_call(*, tmp_path: Path) -> None:
    """A `othermod.helper()` (cross-module public) passes (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from livespec import other\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def main() -> int:\n"
            "    return other.helper()\n"
        ),
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"private_calls should accept cross-module public call with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_private_calls_warns_newly_covered_offender(*, tmp_path: Path) -> None:
    """A cross-module `_`-call OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_CROSS_MODULE_PRIVATE_SOURCE)

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "_helper" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_private_calls_accepts_codeless_repo(*, tmp_path: Path) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"private_calls should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


_BESIDE_TEST_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["pkg"]\n'
    "\n"
    "[tool.ruff.lint.per-file-ignores]\n"
    '"pkg/test_*.py" = ["SLF001"]\n'
)


def test_private_calls_exempts_a_consumer_declared_beside_test(*, tmp_path: Path) -> None:
    """A beside-test the consumer already exempted from ruff's SLF001 passes (exit 0).

    `check-private-calls` and ruff's `SLF001` police the SAME rule. Where the
    consumer's own `per-file-ignores` has already ratified that a beside-test may
    call the private decision helpers it exists to test, this check honours that
    ratification rather than contradicting it.
    """
    _write(tmp_path=tmp_path, rel_path="pyproject.toml", source=_BESIDE_TEST_PYPROJECT)
    _write(tmp_path=tmp_path, rel_path="pkg/test_foo.py", source=_CROSS_MODULE_PRIVATE_SOURCE)

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"private_calls should exempt a beside-test the consumer granted SLF001; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert '"level": "error"' not in combined, (
        f"an exempted beside-test must emit no error-level diagnostic; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_private_calls_beside_test_exemption_does_not_leak_to_production(*, tmp_path: Path) -> None:
    """The SAME repo's PRODUCTION file still fails hard (exit 1) — the other direction.

    The exemption is scoped to the consumer's declared beside-test pattern. A
    production file under the same `source_trees` tree does not match that pattern
    and keeps the hard gate, so the carve-out cannot widen into a general test
    escape hatch.
    """
    _write(tmp_path=tmp_path, rel_path="pyproject.toml", source=_BESIDE_TEST_PYPROJECT)
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_CROSS_MODULE_PRIVATE_SOURCE)

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"private_calls must still reject a cross-module _-call in PRODUCTION; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined, (
        f"private_calls diagnostic does not surface offending file `pkg/foo.py`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_private_calls_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "private_calls_for_import_test",
        str(_PRIVATE_CALLS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
