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


def _run_check(
    *, slug: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
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
        env=env,
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


def _assert_errors_on_undeclared_role_key(
    *, slug: str, role: str, tmp_path: Path, env: dict[str, str] | None = None
) -> None:
    """A layered check fails closed when its governing role key is undeclared."""
    _write_block(repo_root=tmp_path, body='source_trees = ["pkg"]\n')
    result = _run_check(slug=slug, cwd=tmp_path, env=env)
    assert result.returncode == 1, (
        f"{slug} must fail when `{role}` is undeclared; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "role key undeclared" in result.stderr
    assert "declare the real value" in result.stderr
    # The remediation hint must name the blessed spellings, NOT the retired
    # "declare it explicitly empty" advice — that wording sent authors straight
    # into the ambiguous spelling this union exists to retire
    # (livespec-dev-tooling-8o8e.1).
    assert "not_applicable / superseded_by / unarmed_until / convention_not_adopted" in (
        result.stderr
    )
    assert role in result.stderr


def _assert_noop_on_declared_empty_role_key(
    *,
    slug: str,
    role: str,
    declaration: str,
    tmp_path: Path,
    env: dict[str, str] | None = None,
) -> None:
    """A declared-empty role key still no-ops, and now ANNOUNCES itself.

    Phase 1 of the role-key union (livespec-dev-tooling-8o8e.1) preserves the
    OUTCOME — exit 0, so no repo goes red — while replacing the old
    "sanctioned opt-out" INFO with a WARN that names the ambiguous spelling.
    The outcome is the contract; the wording is the migration signal.
    """
    _write_block(repo_root=tmp_path, body=declaration)
    result = _run_check(slug=slug, cwd=tmp_path, env=env)
    assert result.returncode == 0, (
        f"{slug} must no-op (exit 0) when `{role}` is declared empty; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "legacy-ambiguous-empty" in result.stderr
    assert "AMBIGUOUS legacy empty spelling" in result.stderr
    assert role in result.stderr


def _write_pkg_module(*, tmp_path: Path, body: str) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir(exist_ok=True)
    _ = (pkg / "mod.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n\n" + body,
        encoding="utf-8",
    )


def test_no_except_outside_io_runs_without_io_trees(*, tmp_path: Path) -> None:
    """`no_except_outside_io` INSPECTS the source tree when `io_trees` is absent.

    An absent `io_trees` means nothing is wholesale exempt, not that
    there is nothing to check. A flat-layout consumer declares only
    `source_trees`, and its broad catches must still be caught.
    """
    _write_block(repo_root=tmp_path, body='source_trees = ["pkg"]\n')
    _write_pkg_module(
        tmp_path=tmp_path,
        body=(
            "def do_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )
    result = _run_check(slug="no_except_outside_io", cwd=tmp_path)
    assert result.returncode == 1, (
        f"no_except_outside_io must inspect `pkg/` when `io_trees` is absent; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "pkg/mod.py" in result.stderr


def test_no_raise_outside_io_runs_without_io_trees(*, tmp_path: Path) -> None:
    """`no_raise_outside_io` INSPECTS the source tree when `io_trees` is absent."""
    _write_block(repo_root=tmp_path, body='source_trees = ["pkg"]\n')
    _write_pkg_module(
        tmp_path=tmp_path,
        body='def do_thing() -> None:\n    raise ValidationError("boom")\n',
    )
    result = _run_check(slug="no_raise_outside_io", cwd=tmp_path)
    assert result.returncode == 1, (
        f"no_raise_outside_io must inspect `pkg/` when `io_trees` is absent; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "pkg/mod.py" in result.stderr


# `_assert_announces_absent_source_trees` and its two callers were retired when
# `livespec-dev-tooling-i532` moved `no_except_outside_io` / `no_raise_outside_io`
# onto the git-derived universe. Neither check consults `source_trees` now, so
# "announces an absent source_trees" is not a behavior they can have. The
# invariant is NOT dropped: `source_trees` remains in `REQUIRED_ROLE_KEYS` and
# `check-required-role-keys-declared` owns enforcing its declaration.


def test_public_api_result_typed_noops_without_pure_trees(*, tmp_path: Path) -> None:
    """`public_api_result_typed` fails when `pure_trees` is undeclared."""
    _assert_errors_on_undeclared_role_key(
        slug="public_api_result_typed", role="pure_trees", tmp_path=tmp_path
    )


def test_newtype_domain_primitives_noops_without_dataclasses_tree(*, tmp_path: Path) -> None:
    """`newtype_domain_primitives` fails when `dataclasses_tree` is undeclared."""
    _assert_errors_on_undeclared_role_key(
        slug="newtype_domain_primitives", role="dataclasses_tree", tmp_path=tmp_path
    )


def test_all_role_gated_checks_error_on_undeclared_keys(*, tmp_path: Path) -> None:
    """Every role-key-gated check fails closed on an undeclared governing key."""
    cases = (
        ("no_shadow_ledger_body_identical", "neutral_hook_body_path", None),
        ("pbt_coverage_pure_modules", "pure_trees", None),
        ("check_mutation", "pure_trees", {"LIVESPEC_RUN_MUTATION": "true"}),
    )
    for index, (slug, role, env) in enumerate(cases):
        case_root = tmp_path / f"case_{index}"
        case_root.mkdir()
        _assert_errors_on_undeclared_role_key(
            slug=slug,
            role=role,
            tmp_path=case_root,
            env=env,
        )


def test_declared_empty_role_keys_are_sanctioned_opt_outs(*, tmp_path: Path) -> None:
    """Declared-empty keys stay a visible no-op rather than a misconfiguration."""
    cases = (
        ("public_api_result_typed", "pure_trees", "pure_trees = []\n", None),
        ("pbt_coverage_pure_modules", "pure_trees", "pure_trees = []\n", None),
        (
            "check_mutation",
            "pure_trees",
            "pure_trees = []\n",
            {"LIVESPEC_RUN_MUTATION": "true"},
        ),
        ("newtype_domain_primitives", "dataclasses_tree", 'dataclasses_tree = ""\n', None),
        (
            "no_shadow_ledger_body_identical",
            "neutral_hook_body_path",
            'neutral_hook_body_path = ""\n',
            None,
        ),
    )
    for index, (slug, role, declaration, env) in enumerate(cases):
        case_root = tmp_path / f"case_{index}"
        case_root.mkdir()
        _assert_noop_on_declared_empty_role_key(
            slug=slug,
            role=role,
            declaration=declaration,
            tmp_path=case_root,
            env=env,
        )


# `test_declared_source_trees_with_no_python_files_errors` was retired with the
# same i532 change: it drove `no_raise_outside_io` through the
# `source_trees_exit_code` gate, which that check no longer has. The
# "declared role key resolves to no Python files" behavior still exists and is
# still covered — `ensure_declared_paths_contain_python` is exercised through
# `public_api_result_typed`, `pbt_coverage_pure_modules`, `check_mutation` and
# `newtype_domain_primitives` in the cases above.


def test_io_exempt_source_tree_still_passes_when_tree_contains_python(*, tmp_path: Path) -> None:
    """`files_inspected == 0` is not an error when declared source files are IO-exempt."""
    _write_block(repo_root=tmp_path, body='source_trees = ["pkg"]\nio_trees = ["pkg"]\n')
    _write_pkg_module(
        tmp_path=tmp_path,
        body=(
            "def do_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )
    result = _run_check(slug="no_except_outside_io", cwd=tmp_path)
    assert result.returncode == 0, (
        f"IO-exempt source files should not be treated as a misdeclared source tree; "
        f"stderr={result.stderr!r}"
    )
    assert '"files_inspected": 0' in result.stderr
    assert '"offenses": 0' in result.stderr


def test_scalar_role_paths_must_exist_when_declared_non_empty(*, tmp_path: Path) -> None:
    """Non-walking scalar role keys fail when their declared path is missing."""
    cases = (
        (
            "newtype_domain_primitives",
            'dataclasses_tree = "missing_dataclasses"\n',
            "declared dataclasses_tree is not a directory",
        ),
        (
            "no_shadow_ledger_body_identical",
            'neutral_hook_body_path = "missing-hook.sh"\n',
            "declared neutral_hook_body_path is not a file",
        ),
    )
    for index, (slug, declaration, message) in enumerate(cases):
        case_root = tmp_path / f"case_{index}"
        case_root.mkdir()
        _write_block(repo_root=case_root, body=declaration)
        result = _run_check(slug=slug, cwd=case_root)
        assert (
            result.returncode == 1
        ), f"{slug} must reject a missing declared path; stderr={result.stderr!r}"
        assert message in result.stderr


def test_no_write_direct_noops_without_covered_trees(*, tmp_path: Path) -> None:
    """`no_write_direct` scans newly-covered files outside `covered_trees` at WARN."""
    _write_block(repo_root=tmp_path, body='covered_trees = ["legacy"]\n')
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    _ = (legacy / "ok.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    _ = (pkg / "bad.py").write_text(
        "from __future__ import annotations\n\n"
        "__all__: list[str] = []\n\n"
        "import sys\n\n"
        "sys.stderr.write('bad')\n",
        encoding="utf-8",
    )
    result = _run_check(slug="no_write_direct", cwd=tmp_path)
    assert result.returncode == 0, (
        f"newly-covered no_write_direct offender should warn, not fail; "
        f"stderr={result.stderr!r}"
    )
    assert "pkg/bad.py" in result.stderr
    assert "newly_covered" in result.stderr
    assert '"level": "warning"' in result.stderr


def test_no_lloc_soft_warnings_noops_without_covered_trees(*, tmp_path: Path) -> None:
    """`no_lloc_soft_warnings` scans newly-covered files despite the release lever."""
    _write_block(repo_root=tmp_path, body='covered_trees = ["legacy"]\n')
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    _ = (legacy / "ok.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    body_lines = "\n".join(f"x_{i} = {i}" for i in range(220))
    _ = (pkg / "medium.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n" + body_lines + "\n",
        encoding="utf-8",
    )
    result = _run_check(slug="no_lloc_soft_warnings", cwd=tmp_path)
    assert result.returncode == 0, (
        f"newly-covered no_lloc_soft_warnings offender should warn, not fail; "
        f"stderr={result.stderr!r}"
    )
    assert "pkg/medium.py" in result.stderr
    assert "newly_covered" in result.stderr
    assert '"level": "warning"' in result.stderr


def test_comment_line_anchors_warns_for_newly_covered_file(*, tmp_path: Path) -> None:
    """A line-anchor comment outside `target_dirs` is newly-covered at WARN."""
    _write_block(repo_root=tmp_path, body='target_dirs = ["legacy"]\n')
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    _ = (legacy / "ok.py").write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    _ = (pkg / "bad.py").write_text(
        "from __future__ import annotations\n\n"
        "__all__: list[str] = []\n\n"
        "# See lines 12-14 in sibling.py\n"
        "x = 1\n",
        encoding="utf-8",
    )
    result = _run_check(slug="comment_line_anchors", cwd=tmp_path)
    assert result.returncode == 0, (
        f"newly-covered comment_line_anchors offender should warn, not fail; "
        f"stderr={result.stderr!r}"
    )
    assert "pkg/bad.py" in result.stderr
    assert "newly_covered" in result.stderr
    assert '"level": "warning"' in result.stderr


def test_main_guard_warns_for_newly_covered_package(*, tmp_path: Path) -> None:
    """A `__main__` guard in a non-legacy plugin tree is newly-covered at WARN.

    main_guard is ROLE-SCOPED to the plugin-packaging convention: the ban
    applies only under `.claude-plugin/scripts/`. A `__main__` guard in a
    non-legacy plugin package there (not the legacy
    `.claude-plugin/scripts/livespec/` tree) is newly-covered at WARN. A
    package OUTSIDE `.claude-plugin/scripts/` is not subject to the ban at all
    (covered by test_main_guard_ignores_main_guard_outside_plugin_scripts_tree).
    """
    _write_block(repo_root=tmp_path, body="")
    pkg = tmp_path / ".claude-plugin" / "scripts" / "pkg"
    pkg.mkdir(parents=True)
    _ = (pkg / "bad.py").write_text(
        "from __future__ import annotations\n\n"
        "__all__: list[str] = []\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(0)\n",
        encoding="utf-8",
    )
    result = _run_check(slug="main_guard", cwd=tmp_path)
    assert (
        result.returncode == 0
    ), f"newly-covered main_guard offender should warn, not fail; stderr={result.stderr!r}"
    assert ".claude-plugin/scripts/pkg/bad.py" in result.stderr
    assert "newly_covered" in result.stderr
    assert '"level": "warning"' in result.stderr


def test_rop_pipeline_shape_warns_for_newly_covered_package(*, tmp_path: Path) -> None:
    """A malformed `@rop_pipeline` class outside the old livespec tree warns."""
    _write_block(repo_root=tmp_path, body="")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    _ = (pkg / "bad.py").write_text(
        "from __future__ import annotations\n\n"
        "__all__: list[str] = []\n\n"
        "def rop_pipeline(cls: type[object]) -> type[object]:\n"
        "    return cls\n\n\n"
        "@rop_pipeline\n"
        "class Bad:\n"
        "    def first(self) -> None:\n"
        "        pass\n\n"
        "    def second(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )
    result = _run_check(slug="rop_pipeline_shape", cwd=tmp_path)
    assert result.returncode == 0, (
        f"newly-covered rop_pipeline_shape offender should warn, not fail; "
        f"stderr={result.stderr!r}"
    )
    assert "pkg/bad.py" in result.stderr
    assert "newly_covered" in result.stderr
    assert '"level": "warning"' in result.stderr


def test_superseded_by_declaration_is_announced_by_name(*, tmp_path: Path) -> None:
    """A `superseded_by` role key no-ops and reports its own variant and reason.

    The severities are deliberately NOT uniform across the union: a settled
    declaration like this logs at INFO, while `unarmed_until` and the legacy
    ambiguous spelling log at WARN because those are the states that should stay
    visible (livespec-dev-tooling-8o8e.1).
    """
    _write_block(
        repo_root=tmp_path,
        body=(
            'source_trees = ["pkg"]\n'
            'pure_trees = { superseded_by = "git-derived universe via resolve_check_universe" }\n'
        ),
    )
    result = _run_check(slug="public_api_result_typed", cwd=tmp_path)

    assert result.returncode == 0, (
        f"a `superseded_by` declaration must pass; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "superseded_by" in result.stderr
    assert "git-derived universe via resolve_check_universe" in result.stderr
    assert "SUPERSEDED" in result.stderr


def test_convention_not_adopted_declaration_is_announced_by_name(*, tmp_path: Path) -> None:
    """A `convention_not_adopted` role key no-ops and reports its own variant.

    Maintainer-blessed 2026-07-28, and blessed only BECAUSE the coupling break
    landed first: before that, declining one convention also switched off a
    commit-time gate the declaration never named.
    """
    _write_block(
        repo_root=tmp_path,
        body=(
            'source_trees = ["pkg"]\n'
            'pure_trees = { convention_not_adopted = "pure-layer split not adopted here" }\n'
        ),
    )
    result = _run_check(slug="public_api_result_typed", cwd=tmp_path)

    assert result.returncode == 0, (
        f"a `convention_not_adopted` declaration must pass; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "convention_not_adopted" in result.stderr
    assert "pure-layer split not adopted here" in result.stderr
    assert "CONVENTION NOT ADOPTED" in result.stderr
