"""Config-driven behaviour of the shared checks (li-asybpo).

Per `SPECIFICATION/contracts.md` §"Consumer configuration schema", a
shared check reads its layout-dependent source trees from the
`[tool.livespec_dev_tooling]` block in the consumer's `pyproject.toml`
rather than from hardcoded constants. This test pins two behaviours the
per-check fixture suites (which exercise only the livespec-core default
fallback) do not:

1. **Override** — a source-tree-walking check walks a CONFIG-DECLARED
   tree, not the hardcoded livespec-core tree. Proves the check honours
   `source_trees` (criterion 1).
2. **No-op on absent role key** — a layered-ROP check (e.g.
   `no_except_outside_io`) NO-OPS (exits 0, emits a structured `info`
   log) when its governing role key is omitted from a present block, the
   flat-layout-consumer regime per §"Role keys". Proves the
   self-application no-op documented in §"Per-consumer pyproject
   declarations" for livespec-dev-tooling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    The source-tree-walking checks now derive their file universe from the
    git index (`config.resolve_check_universe`), so the fixture must be a
    real git working tree. `git` is not a Python spawn, so it is allowed;
    the hardcoded env keeps `COVERAGE_PROCESS_START` out of this child.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _run_check(*, slug: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    # S603: argv is a fixed list (the venv interpreter + a repo-controlled
    # check path); no untrusted shell input. `git init` + stage first, so the
    # git-derived universe (and root-anchoring) resolves against the fixture.
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    return subprocess.run(
        [sys.executable, str(_CHECKS_DIR / f"{slug}.py")],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_block(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{body}",
        encoding="utf-8",
    )


def test_source_trees_check_walks_config_declared_tree(*, tmp_path: Path) -> None:
    """`no_inheritance` walks the `source_trees` tree declared in pyproject.

    The violation lives under `custom_pkg/` (NOT the hardcoded
    livespec-core `.claude-plugin/scripts/livespec/` tree). The check is
    invoked with `cwd=tmp_path` whose pyproject declares
    `source_trees = ["custom_pkg"]`; it must walk that tree, find the
    disallowed base class, and exit non-zero.
    """
    _write_block(repo_root=tmp_path, body='source_trees = ["custom_pkg"]\n')
    pkg = tmp_path / "custom_pkg"
    pkg.mkdir()
    _ = (pkg / "mod.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n\n"
        "class Bar:\n    pass\n\n\nclass Foo(Bar):\n    pass\n",
        encoding="utf-8",
    )
    result = _run_check(slug="no_inheritance", cwd=tmp_path)
    assert result.returncode == 1, (
        f"no_inheritance must walk the config-declared tree and fail; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "custom_pkg/mod.py" in result.stderr


def test_source_trees_violation_outside_declared_trees_is_newly_covered_warn(
    *, tmp_path: Path
) -> None:
    """A violation OUTSIDE the declared `source_trees` is newly-covered (WARN), not a hard fail.

    Under the git-derived reroute, `source_trees` no longer SELECTS the file
    universe (the check walks the whole git index via
    `config.resolve_check_universe`); it is the delta-WARN severity
    classifier. So a violation seeded under the livespec-core default tree
    `.claude-plugin/scripts/livespec/` — outside the declared
    `source_trees = ["custom_pkg"]` — IS walked, but emits at WARN
    (`newly_covered`, `phase="0-warn"`) and does NOT contribute to exit 1.
    """
    _write_block(repo_root=tmp_path, body='source_trees = ["custom_pkg"]\n')
    (tmp_path / "custom_pkg").mkdir()
    _ = (tmp_path / "custom_pkg" / "ok.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    legacy = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    legacy.mkdir(parents=True)
    _ = (legacy / "bad.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n\n"
        "class Bar:\n    pass\n\n\nclass Foo(Bar):\n    pass\n",
        encoding="utf-8",
    )
    result = _run_check(slug="no_inheritance", cwd=tmp_path)
    assert result.returncode == 0, (
        f"a violation outside the declared source_trees must NOT hard-fail; "
        f"stderr={result.stderr!r}"
    )
    assert ".claude-plugin/scripts/livespec/bad.py" in result.stderr
    assert "newly_covered" in result.stderr


def _assert_noop_on_absent_role_key(*, slug: str, role: str, tmp_path: Path) -> None:
    """A layered check no-ops (exit 0 + info log) when its role key is absent."""
    _write_block(repo_root=tmp_path, body='source_trees = ["pkg"]\n')
    result = _run_check(slug=slug, cwd=tmp_path)
    assert result.returncode == 0, (
        f"{slug} must no-op (exit 0) when `{role}` is absent; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "role key absent" in result.stderr
    assert role in result.stderr


def test_no_except_outside_io_noops_without_io_trees(*, tmp_path: Path) -> None:
    """`no_except_outside_io` no-ops when `io_trees` is absent (flat-layout consumer)."""
    _assert_noop_on_absent_role_key(slug="no_except_outside_io", role="io_trees", tmp_path=tmp_path)


def test_no_raise_outside_io_noops_without_io_trees(*, tmp_path: Path) -> None:
    """`no_raise_outside_io` no-ops when `io_trees` is absent."""
    _assert_noop_on_absent_role_key(slug="no_raise_outside_io", role="io_trees", tmp_path=tmp_path)


def test_public_api_result_typed_noops_without_pure_trees(*, tmp_path: Path) -> None:
    """`public_api_result_typed` no-ops when `pure_trees` is absent."""
    _assert_noop_on_absent_role_key(
        slug="public_api_result_typed", role="pure_trees", tmp_path=tmp_path
    )


def test_newtype_domain_primitives_noops_without_dataclasses_tree(*, tmp_path: Path) -> None:
    """`newtype_domain_primitives` no-ops when `dataclasses_tree` is null."""
    _assert_noop_on_absent_role_key(
        slug="newtype_domain_primitives", role="dataclasses_tree", tmp_path=tmp_path
    )


def test_no_write_direct_noops_without_covered_trees(*, tmp_path: Path) -> None:
    """`no_write_direct` no-ops when `covered_trees` is absent."""
    _assert_noop_on_absent_role_key(slug="no_write_direct", role="covered_trees", tmp_path=tmp_path)


def test_no_lloc_soft_warnings_noops_without_covered_trees(*, tmp_path: Path) -> None:
    """`no_lloc_soft_warnings` no-ops when `covered_trees` is absent."""
    _assert_noop_on_absent_role_key(
        slug="no_lloc_soft_warnings", role="covered_trees", tmp_path=tmp_path
    )
