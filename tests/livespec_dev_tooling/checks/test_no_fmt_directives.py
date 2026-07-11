"""Tests for dev-tooling/checks/no_fmt_directives.

The check bans formatter-suppression directives (`# fmt: off` /
`# fmt: on` / `# fmt: skip`) in the git-derived first-party `.py`
universe. Such directives suppress the formatter's honest
one-element-per-line expansion and are the mechanism of `file_lloc`
counter-shaving (packing `__all__`/collection entries onto fewer
physical lines to dodge the LLOC target). Files under a legacy tree
(`config.target_dirs`) fail hard (exit 1); newly-git-derived files
outside every legacy tree warn (exit 0) under the Phase-0 delta-WARN
model. Vendored, test-tree, `templates/`, and `@generated`-marked files
are outside the universe and are never flagged.

The fixtures are real git repos (`git init` + `git add`) because the
check derives its universe from `git ls-files` via
`resolve_check_universe`. The check itself is exercised as a subprocess
so coverage instruments it (this test is on the pyproject
`subprocess_spawn_allowlist` for that reason).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_CHECK_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "checks" / "no_fmt_directives.py"
)


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _run_check(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    return subprocess.run(
        [sys.executable, str(_CHECK_PATH)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(*, root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


# A file at the repo root's `pkg/` is first-party (not `_vendor`, not
# `tests/`, not `templates/`, not `@generated`) yet sits under NONE of the
# livespec-core fallback `target_dirs` (`.claude-plugin/scripts`,
# `dev-tooling`, `tests`) — so it is a NEWLY-covered file and warns.
_NEWLY_COVERED_REL = "pkg/mod.py"
# A file under `.claude-plugin/scripts/livespec/` sits under a fallback
# `target_dir`, so it is a LEGACY file and hard-fails.
_LEGACY_REL = ".claude-plugin/scripts/livespec/mod.py"


def test_fmt_off_in_newly_covered_tree_warns_exit_0(*, tmp_path: Path) -> None:
    """A `# fmt: off` in a newly-covered file → WARNING diagnostic, exit 0."""
    _write(
        root=tmp_path,
        rel=_NEWLY_COVERED_REL,
        body="# fmt: off\nfrom __future__ import annotations\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert _NEWLY_COVERED_REL in result.stderr
    assert '"level": "warning"' in result.stderr
    assert '"newly_covered": true' in result.stderr


def test_fmt_skip_in_newly_covered_tree_warns_exit_0(*, tmp_path: Path) -> None:
    """A trailing `# fmt: skip` in a newly-covered file → WARNING, exit 0."""
    _write(
        root=tmp_path,
        rel=_NEWLY_COVERED_REL,
        body="from __future__ import annotations\n\n_K = [1, 2, 3]  # fmt: skip\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert '"level": "warning"' in result.stderr
    assert '"directive": "# fmt: skip"' in result.stderr


def test_fmt_off_in_legacy_tree_errors_exit_1(*, tmp_path: Path) -> None:
    """A `# fmt: off` under a legacy `target_dir` → ERROR diagnostic, exit 1."""
    _write(
        root=tmp_path,
        rel=_LEGACY_REL,
        body="# fmt: off\nfrom __future__ import annotations\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 1, result.stderr
    assert _LEGACY_REL in result.stderr
    assert '"level": "error"' in result.stderr


def test_clean_file_no_diagnostic_exit_0(*, tmp_path: Path) -> None:
    """A file with no formatter-suppression directive → exit 0, no finding."""
    _write(
        root=tmp_path,
        rel=_LEGACY_REL,
        body='"""A clean module."""\n\nfrom __future__ import annotations\n\n__all__: list[str] = []\n',
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_spacing_variants_all_match(*, tmp_path: Path) -> None:
    """`# fmt: off`, `# fmt:off`, and `#fmt: off` all match (in a legacy file)."""
    _write(
        root=tmp_path,
        rel=_LEGACY_REL,
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
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 1, result.stderr
    assert '"directive": "# fmt: off"' in result.stderr
    assert '"directive": "# fmt:off"' in result.stderr
    assert '"directive": "#fmt: off"' in result.stderr


def test_benign_fmt_comment_does_not_match(*, tmp_path: Path) -> None:
    """Comments that merely contain "fmt" (or `fmt: offset`) do NOT match → exit 0."""
    _write(
        root=tmp_path,
        rel=_LEGACY_REL,
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
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_vendored_file_fmt_off_not_flagged(*, tmp_path: Path) -> None:
    """A `# fmt: off` inside a `_vendor/` file is out of the universe → exit 0."""
    _write(
        root=tmp_path,
        rel=".claude-plugin/scripts/_vendor/upstream/shipped.py",
        body="# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_generated_file_fmt_off_not_flagged(*, tmp_path: Path) -> None:
    """An `@generated`-marked file's `# fmt: off` is out of the universe → exit 0."""
    _write(
        root=tmp_path,
        rel=_NEWLY_COVERED_REL,
        body="# @generated\n# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_test_tree_file_fmt_off_not_flagged(*, tmp_path: Path) -> None:
    """A `# fmt: off` inside the configured test tree is out of the universe → exit 0."""
    _write(
        root=tmp_path,
        rel="tests/test_something.py",
        body="# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path)
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
