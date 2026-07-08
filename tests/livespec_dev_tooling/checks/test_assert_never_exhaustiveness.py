"""Outside-in test for `livespec_dev_tooling/checks/assert_never_exhaustiveness.py`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-assert-never-exhaustiveness` row),
every `match` statement in `livespec/**` MUST terminate with
`case _: assert_never(<subject>)`. Conservative scope: every
match, regardless of subject type.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk — so each fixture is a real git repo
(`git init` + `git add -A`) before the check subprocess runs.
Phase-0 delta-WARN severity: `config.source_trees` is retained as
a classifier — a non-compliant `match` in a `source_trees` file
keeps today's hard gate (`error`, exit 1); the identical violation
in a NEWLY-covered file emits at WARN (`newly_covered` /
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
_ASSERT_NEVER_EXHAUSTIVENESS = (
    _REPO_ROOT / "livespec_dev_tooling" / "checks" / "assert_never_exhaustiveness.py"
)

_MISSING_TERMINATOR_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def handle(val: int) -> int:\n"
    "    match val:\n"
    "        case 0:\n"
    "            return 1\n"
    "        case 1:\n"
    "            return 2\n"
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
        [sys.executable, str(_ASSERT_NEVER_EXHAUSTIVENESS)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_assert_never_exhaustiveness_rejects_match_missing_case_underscore(
    *, tmp_path: Path
) -> None:
    """A `match` in a `source_trees` file lacking the terminator fails hard (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_MISSING_TERMINATOR_SOURCE,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"assert_never_exhaustiveness should reject match without case _: assert_never; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"assert_never_exhaustiveness diagnostic does not surface offending file "
        f"`{expected_path}`; stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_assert_never_exhaustiveness_rejects_case_underscore_with_non_assert_never_body(
    *,
    tmp_path: Path,
) -> None:
    """A `case _:` body other than `assert_never(<subject>)` fails the check (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def handle(val: int) -> int:\n"
            "    match val:\n"
            "        case 0:\n"
            "            return 1\n"
            "        case _:\n"
            "            return 0\n"
        ),
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"assert_never_exhaustiveness should reject `case _:` with non-assert_never body; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_assert_never_exhaustiveness_accepts_proper_match_terminator(*, tmp_path: Path) -> None:
    """A match ending with `case _: assert_never(val)` passes the check (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from typing_extensions import assert_never\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def handle(val: int) -> int:\n"
            "    match val:\n"
            "        case 0:\n"
            "            return 1\n"
            "        case _:\n"
            "            assert_never(val)\n"
        ),
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"assert_never_exhaustiveness should accept proper terminator with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_assert_never_exhaustiveness_warns_newly_covered_offender(*, tmp_path: Path) -> None:
    """A non-compliant `match` OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_MISSING_TERMINATOR_SOURCE)

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_assert_never_exhaustiveness_accepts_codeless_repo(*, tmp_path: Path) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"assert_never_exhaustiveness should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_assert_never_exhaustiveness_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "assert_never_exhaustiveness_for_import_test",
        str(_ASSERT_NEVER_EXHAUSTIVENESS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
