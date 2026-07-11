"""Tests for dev-tooling/checks/no_fmt_directives.

The check bans formatter-suppression directives (`# fmt: off` /
`# fmt: on` / `# fmt: skip`) in the git-derived first-party `.py`
universe. Such directives suppress the formatter's honest
one-element-per-line expansion and are the mechanism of `file_lloc`
counter-shaving (packing `__all__`/collection entries onto fewer
physical lines to dodge the LLOC target).

Severity is controlled by the `LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST`
env lever ONLY (never run-vs-skip): unset → WARN / exit 0 (Phase-0
newly-covered propagation); set → ERROR / exit 1. Vendored, test-tree,
`templates/`, and `@generated`-marked files are outside the universe and
are never flagged, armed or not.

The fixtures are real git repos (`git init` + `git add`) because the
check derives its universe from `git ls-files` via
`resolve_check_universe`. The check itself is exercised as a subprocess
so coverage instruments it (this test is on the pyproject
`subprocess_spawn_allowlist` for that reason). Each subprocess inherits
the parent env (so subprocess coverage keeps working) MINUS the lever,
which each test sets deterministically — never depending on the ambient
value.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_CHECK_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "checks" / "no_fmt_directives.py"
)
_FAIL_ENV = "LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST"


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _run_check(*, cwd: Path, armed: bool) -> subprocess.CompletedProcess[str]:
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    # Inherit the parent env (so the pth-installed coverage startup hook still
    # instruments the child) but set the lever DETERMINISTICALLY — drop any
    # ambient value, then arm it only when the test asks — so severity never
    # depends on the shell/CI that runs the suite.
    env = {k: v for k, v in os.environ.items() if k != _FAIL_ENV}
    if armed:
        env[_FAIL_ENV] = "true"
    return subprocess.run(
        [sys.executable, str(_CHECK_PATH)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _write(*, root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


# A first-party file (not `_vendor`, not `tests/`, not `templates/`, not
# `@generated`); its location no longer affects severity — the lever does.
_FIRST_PARTY_REL = "pkg/mod.py"


def test_fmt_off_unarmed_warns_exit_0(*, tmp_path: Path) -> None:
    """A `# fmt: off` with the lever UNSET → WARNING diagnostic, exit 0."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="# fmt: off\nfrom __future__ import annotations\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=False)
    assert result.returncode == 0, result.stderr
    assert _FIRST_PARTY_REL in result.stderr
    assert '"level": "warning"' in result.stderr
    assert '"newly_covered": true' in result.stderr


def test_fmt_skip_unarmed_warns_exit_0(*, tmp_path: Path) -> None:
    """A trailing `# fmt: skip` with the lever UNSET → WARNING, exit 0."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="from __future__ import annotations\n\n_K = [1, 2, 3]  # fmt: skip\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=False)
    assert result.returncode == 0, result.stderr
    assert '"level": "warning"' in result.stderr
    assert '"directive": "# fmt: skip"' in result.stderr


def test_fmt_off_armed_errors_exit_1(*, tmp_path: Path) -> None:
    """A `# fmt: off` with the lever SET → ERROR diagnostic, exit 1."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="# fmt: off\nfrom __future__ import annotations\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 1, result.stderr
    assert _FIRST_PARTY_REL in result.stderr
    assert '"level": "error"' in result.stderr
    assert '"failing": true' in result.stderr


def test_armed_clean_file_exit_0(*, tmp_path: Path) -> None:
    """A clean file with the lever SET → exit 0, no finding (armed-but-clean)."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body='"""A clean module."""\n\nfrom __future__ import annotations\n\n__all__: list[str] = []\n',
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_spacing_variants_all_match(*, tmp_path: Path) -> None:
    """`# fmt: off`, `# fmt:off`, and `#fmt: off` all match (armed → exit 1)."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body=(
            "# fmt: off\n"
            "from __future__ import annotations\n"
            "# fmt:off\n"
            "_A = 1\n"
            "#fmt: off\n"
            "_B = 2\n"
            "\n"
            "__all__: list[str] = []\n"
        ),
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 1, result.stderr
    assert '"directive": "# fmt: off"' in result.stderr
    assert '"directive": "# fmt:off"' in result.stderr
    assert '"directive": "#fmt: off"' in result.stderr


def test_benign_fmt_comment_does_not_match(*, tmp_path: Path) -> None:
    """Comments that merely contain "fmt" (or `fmt: offset`) do NOT match, even armed → exit 0."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body=(
            "from __future__ import annotations\n"
            "\n"
            "# reformatting the fmt string happens later\n"
            "# fmt is a nice tool\n"
            "_OFFSET = 3  # fmt: offset = 3\n"
            "\n"
            "__all__: list[str] = []\n"
        ),
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_vendored_file_fmt_off_not_flagged(*, tmp_path: Path) -> None:
    """A `# fmt: off` inside a `_vendor/` file is out of the universe (armed → exit 0)."""
    _write(
        root=tmp_path,
        rel=".claude-plugin/scripts/_vendor/upstream/shipped.py",
        body="# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_generated_file_fmt_off_not_flagged(*, tmp_path: Path) -> None:
    """An `@generated`-marked file's `# fmt: off` is out of the universe (armed → exit 0)."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="# @generated\n# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_test_tree_file_fmt_off_not_flagged(*, tmp_path: Path) -> None:
    """A `# fmt: off` inside the configured test tree is out of the universe (armed → exit 0)."""
    _write(
        root=tmp_path,
        rel="tests/test_something.py",
        body="# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Exercises the false arms of (a) the vendor `sys.path` guard at
    module-load time and (b) the `if __name__ == "__main__"` guard at the
    bottom — both untaken under subprocess invocation. Mirrors the pattern
    in `test_comment_line_anchors`.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_fmt_directives_for_import_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
