"""Unit test for `livespec_dev_tooling.config` — the consumer-layout loader.

Per `SPECIFICATION/contracts.md` §"Consumer configuration schema", the
loader resolves the consumer's source-tree layout from the optional
`[tool.livespec_dev_tooling]` block. Missing blocks and omitted keys keep
the flat `Config()` defaults, while `declared_keys` records which keys
were explicitly present so check-level gates can distinguish undeclared
keys from declared-empty opt-outs.

This test also pins every schema-violation path (→ `ConfigParseError`)
and the shared `iter_py_files` walker (skips `_vendor`/`__pycache__`,
no-ops on a missing root).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import livespec_dev_tooling.config as config_module
from livespec_dev_tooling.config import (
    REQUIRED_ROLE_KEYS,
    Config,
    ConfigParseError,
    ConventionNotAdopted,
    DeclaredPath,
    DeclaredPrefixes,
    DeclaredTrees,
    GitLsFilesError,
    GitToplevelError,
    LegacyAmbiguousEmpty,
    MirrorPairing,
    NotApplicable,
    SupersededBy,
    filter_first_party_py,
    has_first_party_py,
    is_bin_wrapper,
    is_generated,
    is_slf001_exempt,
    is_under_any_tree,
    iter_first_party_py_files,
    iter_py_files,
    load_config,
    load_destructive_cli_allowlist,
    load_mutation_staging_dir,
    load_project_name,
    load_scenario_tiers,
    load_slf001_exempt_globs,
    load_subprocess_spawn_allowlist,
    resolve_check_universe,
    resolve_repo_root,
    role_path,
    role_prefixes,
    role_trees,
)

__all__: list[str] = []


def _write_pyproject(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(body, encoding="utf-8")


def _load_plan_lifecycle_anchor(*, repo_root: Path) -> bool | None:
    loader = getattr(config_module, "load_plan_lifecycle_anchor", None)
    assert callable(loader)
    value = loader(repo_root=repo_root)
    assert value is None or isinstance(value, bool)
    return value


def test_no_pyproject_yields_flat_baseline(*, tmp_path: Path) -> None:
    """No `pyproject.toml` -> bare flat baseline with no declared keys."""
    config = load_config(repo_root=tmp_path)
    assert config == Config()
    assert config.declared_keys == frozenset()


def test_pyproject_with_no_tool_table_yields_flat_baseline(*, tmp_path: Path) -> None:
    """`pyproject.toml` with no `[tool]` table -> bare flat baseline."""
    _write_pyproject(repo_root=tmp_path, body='[project]\nname = "x"\n')
    assert load_config(repo_root=tmp_path) == Config()


def test_pyproject_with_no_livespec_block_yields_flat_baseline(*, tmp_path: Path) -> None:
    """`[tool.ruff]` present but no `[tool.livespec_dev_tooling]` -> bare baseline."""
    _write_pyproject(repo_root=tmp_path, body="[tool.ruff]\nline-length = 100\n")
    assert load_config(repo_root=tmp_path) == Config()


def test_required_role_keys_exports_exact_backfilled_keys() -> None:
    """`REQUIRED_ROLE_KEYS` includes only the backfilled role-key families."""
    tuple_path_roles = frozenset(
        {
            "source_trees",
            "io_trees",
            "commands_trees",
            "supervisor_entry_files",
            "pure_trees",
            "covered_trees",
            "target_dirs",
        }
    )
    scalar_roles = frozenset(
        {
            "source_tree_prefixes",
            "dataclasses_tree",
            "neutral_hook_body_path",
        }
    )
    excluded = frozenset(
        {
            "tests_tree_prefix",
            "mirror_pairings",
            "file_lloc_hard_gate",
            "plan_lifecycle_anchor",
            "scenario_tiers",
        }
    )
    assert len(REQUIRED_ROLE_KEYS) == 10
    assert tuple_path_roles <= REQUIRED_ROLE_KEYS
    assert scalar_roles <= REQUIRED_ROLE_KEYS
    assert REQUIRED_ROLE_KEYS.isdisjoint(excluded)


def test_present_block_omitting_keys_yields_flat_baseline(*, tmp_path: Path) -> None:
    """A block declaring only `source_trees` → omitted role keys stay empty.

    The flat-layout regime: omitted role keys keep empty/null values,
    while `declared_keys` records that only `source_trees` was present.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    config = load_config(repo_root=tmp_path)
    assert config.declared_keys == frozenset({"source_trees"})
    assert config.source_trees == (Path("pkg"),)
    assert config.io_trees == ()
    assert config.commands_trees == ()
    assert config.supervisor_entry_files == ()
    assert config.covered_trees == ()
    assert config.mirror_pairings == ()
    assert config.tests_tree_prefix == "tests/"
    # The five union role keys resolve to an EMPTY universe exactly as before —
    # asserted through the accessors, which is the contract consumers use.
    assert role_trees(role=config.pure_trees) == ()
    assert role_trees(role=config.target_dirs) == ()
    assert role_prefixes(role=config.source_tree_prefixes) == ()
    assert role_path(role=config.dataclasses_tree) is None
    assert role_path(role=config.neutral_hook_body_path) is None


def test_dataclasses_tree_empty_string_is_declared_none(*, tmp_path: Path) -> None:
    """`dataclasses_tree = ""` still parses and still resolves to no path.

    Phase 1 of the role-key union accepts the legacy spelling unchanged — it is
    the ACCEPTING loader, and rejecting here would redden every repo before any
    of them could migrate. What changes is that the value is now a distinct
    `LegacyAmbiguousEmpty` rather than a bare `None`, so consumers can announce
    it (livespec-dev-tooling-8o8e.1).
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\ndataclasses_tree = ""\n',
    )
    config = load_config(repo_root=tmp_path)
    assert role_path(role=config.dataclasses_tree) is None
    assert isinstance(config.dataclasses_tree, LegacyAmbiguousEmpty)
    assert "dataclasses_tree" in config.declared_keys


def test_neutral_hook_body_path_empty_string_is_declared_none(*, tmp_path: Path) -> None:
    """`neutral_hook_body_path = ""` declares the null/no-op role key."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = ""\n',
    )
    config = load_config(repo_root=tmp_path)
    assert role_path(role=config.neutral_hook_body_path) is None
    assert isinstance(config.neutral_hook_body_path, LegacyAmbiguousEmpty)
    assert "neutral_hook_body_path" in config.declared_keys


def test_full_override(*, tmp_path: Path) -> None:
    """Every role key declared in the block overrides the flat baseline."""
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'source_trees = ["pkg"]\n'
            'io_trees = ["pkg/io"]\n'
            'commands_trees = ["pkg/commands"]\n'
            'supervisor_entry_files = ["pkg/run.py"]\n'
            'dataclasses_tree = "pkg/schemas"\n'
            'pure_trees = ["pkg/pure"]\n'
            'covered_trees = ["pkg"]\n'
            'source_tree_prefixes = ["pkg/"]\n'
            'tests_tree_prefix = "t/"\n'
            'target_dirs = ["pkg"]\n'
            'mirror_pairings = [{ source_tree = "pkg", test_tree = "t/pkg" }]\n'
            'neutral_hook_body_path = "hooks/no_shadow_ledger.py"\n'
        ),
    )
    config = load_config(repo_root=tmp_path)
    assert config.source_trees == (Path("pkg"),)
    assert config.io_trees == (Path("pkg/io"),)
    assert config.commands_trees == (Path("pkg/commands"),)
    assert config.supervisor_entry_files == (Path("pkg/run.py"),)
    assert config.covered_trees == (Path("pkg"),)
    assert config.tests_tree_prefix == "t/"
    assert config.mirror_pairings == (
        MirrorPairing(source_tree=Path("pkg"), test_tree=Path("t/pkg")),
    )
    # A POPULATED union role key parses into its `Declared*` wrapper, which is
    # what makes "declared but empty" unrepresentable after parsing: the
    # populated case is non-empty by construction.
    assert config.dataclasses_tree == DeclaredPath(path=Path("pkg/schemas"))
    assert config.pure_trees == DeclaredTrees(trees=(Path("pkg/pure"),))
    assert config.target_dirs == DeclaredTrees(trees=(Path("pkg"),))
    assert config.source_tree_prefixes == DeclaredPrefixes(prefixes=("pkg/",))
    assert config.neutral_hook_body_path == DeclaredPath(path=Path("hooks/no_shadow_ledger.py"))
    assert config.declared_keys == frozenset(
        {
            "source_trees",
            "io_trees",
            "commands_trees",
            "supervisor_entry_files",
            "dataclasses_tree",
            "pure_trees",
            "covered_trees",
            "source_tree_prefixes",
            "tests_tree_prefix",
            "target_dirs",
            "mirror_pairings",
            "neutral_hook_body_path",
        }
    )


def test_malformed_toml_raises(*, tmp_path: Path) -> None:
    """Unparseable TOML raises `ConfigParseError`."""
    _write_pyproject(repo_root=tmp_path, body="[tool.livespec_dev_tooling\nsource_trees = ")
    with pytest.raises(ConfigParseError, match="malformed pyproject.toml"):
        _ = load_config(repo_root=tmp_path)


def test_source_trees_not_a_list_raises(*, tmp_path: Path) -> None:
    """A scalar where an array is required raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = "pkg"\n',
    )
    with pytest.raises(ConfigParseError, match="`source_trees` must be an array of strings"):
        _ = load_config(repo_root=tmp_path)


def test_source_trees_non_string_element_raises(*, tmp_path: Path) -> None:
    """An array with a non-string element raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nsource_trees = [1]\n",
    )
    with pytest.raises(ConfigParseError, match="`source_trees` must be an array of strings"):
        _ = load_config(repo_root=tmp_path)


def test_dataclasses_tree_non_string_raises(*, tmp_path: Path) -> None:
    """A non-string `dataclasses_tree` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndataclasses_tree = 3\n",
    )
    with pytest.raises(ConfigParseError, match="`dataclasses_tree` must be a populated value"):
        _ = load_config(repo_root=tmp_path)


def test_tests_tree_prefix_non_string_raises(*, tmp_path: Path) -> None:
    """A non-string `tests_tree_prefix` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ntests_tree_prefix = 7\n",
    )
    with pytest.raises(ConfigParseError, match="`tests_tree_prefix` must be a string"):
        _ = load_config(repo_root=tmp_path)


def test_tests_tree_prefix_empty_string_raises(*, tmp_path: Path) -> None:
    """An empty `tests_tree_prefix` would exempt every path and must fail closed."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\ntests_tree_prefix = ""\n',
    )
    with pytest.raises(ConfigParseError, match="`tests_tree_prefix` must be a non-empty string"):
        _ = load_config(repo_root=tmp_path)


def test_mirror_pairings_not_a_list_raises(*, tmp_path: Path) -> None:
    """A scalar `mirror_pairings` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nmirror_pairings = "nope"\n',
    )
    with pytest.raises(ConfigParseError, match="`mirror_pairings` must be an array"):
        _ = load_config(repo_root=tmp_path)


def test_mirror_pairings_non_table_entry_raises(*, tmp_path: Path) -> None:
    """A `mirror_pairings` array with a non-table entry raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nmirror_pairings = [1]\n",
    )
    with pytest.raises(ConfigParseError, match="each `mirror_pairings` entry must be a table"):
        _ = load_config(repo_root=tmp_path)


def test_mirror_pairings_entry_missing_keys_raises(*, tmp_path: Path) -> None:
    """A `mirror_pairings` table missing `test_tree` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nmirror_pairings = [{ source_tree = "a" }]\n',
    )
    with pytest.raises(ConfigParseError, match="needs string `source_tree`"):
        _ = load_config(repo_root=tmp_path)


def test_iter_py_files_skips_vendor_and_pycache(*, tmp_path: Path) -> None:
    """`iter_py_files` yields first-party `.py`, skipping `_vendor`/`__pycache__`."""
    pkg = tmp_path / "pkg"
    (pkg / "_vendor" / "lib").mkdir(parents=True)
    (pkg / "__pycache__").mkdir(parents=True)
    _ = (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    _ = (pkg / "_vendor" / "lib" / "v.py").write_text("y = 2\n", encoding="utf-8")
    _ = (pkg / "__pycache__" / "c.py").write_text("z = 3\n", encoding="utf-8")
    found = list(iter_py_files(root=pkg))
    assert found == [pkg / "a.py"]


def test_iter_py_files_missing_root_yields_nothing(*, tmp_path: Path) -> None:
    """`iter_py_files` against an absent root yields nothing (no-op walk)."""
    assert list(iter_py_files(root=tmp_path / "absent")) == []


def test_neutral_hook_body_path_non_string_raises(*, tmp_path: Path) -> None:
    """A non-string `neutral_hook_body_path` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nneutral_hook_body_path = 3\n",
    )
    with pytest.raises(
        ConfigParseError, match="`neutral_hook_body_path` must be a populated value"
    ):
        _ = load_config(repo_root=tmp_path)


def test_bare_config_is_flat_baseline() -> None:
    """`Config()` is the flat baseline — every role key empty/null."""
    config = Config()
    assert config.declared_keys == frozenset()
    assert config.source_trees == ()
    assert config.tests_tree_prefix == "tests/"
    assert role_path(role=config.dataclasses_tree) is None
    assert role_path(role=config.neutral_hook_body_path) is None


_SLF001_GRANT = (
    "[tool.ruff.lint.per-file-ignores]\n"
    '"overseer/test_*.py" = ["SLF001", "PLR2004"]\n'
    '"scripts/one_off.py" = ["T201"]\n'
)


def test_slf001_exempt_globs_empty_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → no consumer grant to honour."""
    assert load_slf001_exempt_globs(repo_root=tmp_path) == ()


def test_slf001_exempt_globs_empty_when_ruff_table_absent(*, tmp_path: Path) -> None:
    """A `pyproject.toml` with no `[tool.ruff]` at all → no grant."""
    _write_pyproject(
        repo_root=tmp_path, body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n'
    )
    assert load_slf001_exempt_globs(repo_root=tmp_path) == ()


def test_slf001_exempt_globs_empty_when_ruff_lacks_per_file_ignores(*, tmp_path: Path) -> None:
    """`[tool.ruff.lint]` present but no `per-file-ignores` → no grant."""
    _write_pyproject(repo_root=tmp_path, body='[tool.ruff.lint]\nselect = ["ALL"]\n')
    assert load_slf001_exempt_globs(repo_root=tmp_path) == ()


def test_slf001_exempt_globs_returns_only_slf001_patterns(*, tmp_path: Path) -> None:
    """ONLY a pattern whose ignore list contains `SLF001` is returned.

    The narrow scope is the point: a consumer granting some file an UNRELATED
    rule (here `T201`) gets no exemption from this check, so the carve-out can
    never widen into a general test escape hatch.
    """
    _write_pyproject(repo_root=tmp_path, body=_SLF001_GRANT)
    assert load_slf001_exempt_globs(repo_root=tmp_path) == ("overseer/test_*.py",)


def test_slf001_exempt_globs_ignores_a_non_conforming_shape(*, tmp_path: Path) -> None:
    """A non-list ignore value is skipped rather than raising.

    This reads a table the consumer maintains for ruff, not for us; a future
    ruff schema change must not break an unrelated check.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.ruff.lint.per-file-ignores]\n"pkg/test_*.py" = "SLF001"\n',
    )
    assert load_slf001_exempt_globs(repo_root=tmp_path) == ()


def test_slf001_exempt_globs_ignores_a_non_table_per_file_ignores(*, tmp_path: Path) -> None:
    """A `per-file-ignores` that is not a table at all is skipped rather than raising."""
    _write_pyproject(repo_root=tmp_path, body='[tool.ruff.lint]\nper-file-ignores = "nope"\n')
    assert load_slf001_exempt_globs(repo_root=tmp_path) == ()


def test_is_slf001_exempt_matches_a_root_relative_pattern() -> None:
    """Ruff matches `per-file-ignores` keys against the root-relative path."""
    assert is_slf001_exempt(rel=Path("overseer/test_foo.py"), globs=("overseer/test_*.py",))
    assert not is_slf001_exempt(rel=Path("overseer/foo.py"), globs=("overseer/test_*.py",))


def test_is_slf001_exempt_matches_a_bare_file_name_pattern() -> None:
    """Ruff also matches a bare-name key, so `"test_*.py"` selects the same files."""
    assert is_slf001_exempt(rel=Path("deep/nested/test_foo.py"), globs=("test_*.py",))


def test_is_slf001_exempt_is_false_with_no_globs() -> None:
    """A consumer that granted nothing exempts nothing."""
    assert not is_slf001_exempt(rel=Path("overseer/test_foo.py"), globs=())


def test_scenario_tiers_none_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → `load_scenario_tiers` returns `None` (caller defaults)."""
    assert load_scenario_tiers(repo_root=tmp_path) is None


def test_scenario_tiers_none_when_key_absent(*, tmp_path: Path) -> None:
    """A block present but omitting `scenario_tiers` → `None`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    assert load_scenario_tiers(repo_root=tmp_path) is None


def test_scenario_tiers_read_from_block(*, tmp_path: Path) -> None:
    """A declared `scenario_tiers` array is returned verbatim as a tuple."""
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n" 'scenario_tiers = ["tests.e2e", "tests.acceptance"]\n'
        ),
    )
    assert load_scenario_tiers(repo_root=tmp_path) == ("tests.e2e", "tests.acceptance")


def test_scenario_tiers_non_array_raises(*, tmp_path: Path) -> None:
    """A scalar `scenario_tiers` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nscenario_tiers = "tests.e2e"\n',
    )
    with pytest.raises(ConfigParseError, match="`scenario_tiers` must be an array of strings"):
        _ = load_scenario_tiers(repo_root=tmp_path)


def test_scenario_tiers_non_string_element_raises(*, tmp_path: Path) -> None:
    """A `scenario_tiers` array with a non-string element raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nscenario_tiers = [1]\n",
    )
    with pytest.raises(ConfigParseError, match="`scenario_tiers` must be an array of strings"):
        _ = load_scenario_tiers(repo_root=tmp_path)


def test_project_name_none_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → `load_project_name` returns `None`."""
    assert load_project_name(repo_root=tmp_path) is None


def test_project_name_none_when_project_table_absent(*, tmp_path: Path) -> None:
    """A pyproject without a `[project]` table → `None`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    assert load_project_name(repo_root=tmp_path) is None


def test_project_name_none_when_name_not_a_string(*, tmp_path: Path) -> None:
    """A non-string `[project].name` → `None`."""
    _write_pyproject(repo_root=tmp_path, body="[project]\nname = 3\n")
    assert load_project_name(repo_root=tmp_path) is None


def test_project_name_read_from_project_table(*, tmp_path: Path) -> None:
    """`[project].name` is returned verbatim."""
    _write_pyproject(repo_root=tmp_path, body='[project]\nname = "livespec"\n')
    assert load_project_name(repo_root=tmp_path) == "livespec"


def test_destructive_cli_allowlist_none_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → `load_destructive_cli_allowlist` returns `None`."""
    assert load_destructive_cli_allowlist(repo_root=tmp_path) is None


def test_destructive_cli_allowlist_none_when_key_absent(*, tmp_path: Path) -> None:
    """A block present but omitting `destructive_cli_allowlist` → `None`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    assert load_destructive_cli_allowlist(repo_root=tmp_path) is None


def test_destructive_cli_allowlist_read_from_block(*, tmp_path: Path) -> None:
    """A declared `destructive_cli_allowlist` array is returned verbatim as a tuple."""
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'destructive_cli_allowlist = ["dev-tooling/research/", ".claude-plugin/prose/x.md"]\n'
        ),
    )
    assert load_destructive_cli_allowlist(repo_root=tmp_path) == (
        "dev-tooling/research/",
        ".claude-plugin/prose/x.md",
    )


def test_destructive_cli_allowlist_non_array_raises(*, tmp_path: Path) -> None:
    """A scalar `destructive_cli_allowlist` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\ndestructive_cli_allowlist = "dev-tooling/"\n',
    )
    with pytest.raises(
        ConfigParseError, match="`destructive_cli_allowlist` must be an array of strings"
    ):
        _ = load_destructive_cli_allowlist(repo_root=tmp_path)


def test_destructive_cli_allowlist_non_string_element_raises(*, tmp_path: Path) -> None:
    """A `destructive_cli_allowlist` array with a non-string element raises."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndestructive_cli_allowlist = [1]\n",
    )
    with pytest.raises(
        ConfigParseError, match="`destructive_cli_allowlist` must be an array of strings"
    ):
        _ = load_destructive_cli_allowlist(repo_root=tmp_path)


def test_mutation_staging_dir_none_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → `load_mutation_staging_dir` returns `None` (caller defaults)."""
    assert load_mutation_staging_dir(repo_root=tmp_path) is None


def test_mutation_staging_dir_none_when_key_absent(*, tmp_path: Path) -> None:
    """A block present but omitting `mutation_staging_dir` → `None` (flat-layout repo)."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    assert load_mutation_staging_dir(repo_root=tmp_path) is None


def test_mutation_staging_dir_read_from_block(*, tmp_path: Path) -> None:
    """A declared `mutation_staging_dir` string is returned as a `Path`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nmutation_staging_dir = ".mutmut-staging"\n',
    )
    assert load_mutation_staging_dir(repo_root=tmp_path) == Path(".mutmut-staging")


def test_mutation_staging_dir_non_string_raises(*, tmp_path: Path) -> None:
    """A non-string `mutation_staging_dir` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nmutation_staging_dir = [1]\n",
    )
    with pytest.raises(ConfigParseError, match="`mutation_staging_dir` must be a string"):
        _ = load_mutation_staging_dir(repo_root=tmp_path)


def test_plan_lifecycle_anchor_none_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` -> `load_plan_lifecycle_anchor` returns `None`."""
    assert _load_plan_lifecycle_anchor(repo_root=tmp_path) is None


def test_plan_lifecycle_anchor_none_when_no_livespec_block(*, tmp_path: Path) -> None:
    """No `[tool.livespec_dev_tooling]` block -> `None`, not core fallback."""
    _write_pyproject(repo_root=tmp_path, body="[tool.ruff]\nline-length = 100\n")
    assert _load_plan_lifecycle_anchor(repo_root=tmp_path) is None


def test_plan_lifecycle_anchor_none_when_key_absent(*, tmp_path: Path) -> None:
    """A present block omitting `plan_lifecycle_anchor` -> `None`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    assert _load_plan_lifecycle_anchor(repo_root=tmp_path) is None


def test_plan_lifecycle_anchor_true(*, tmp_path: Path) -> None:
    """`plan_lifecycle_anchor = true` -> `True`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nplan_lifecycle_anchor = true\n",
    )
    assert _load_plan_lifecycle_anchor(repo_root=tmp_path) is True


def test_plan_lifecycle_anchor_false(*, tmp_path: Path) -> None:
    """`plan_lifecycle_anchor = false` -> `False`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nplan_lifecycle_anchor = false\n",
    )
    assert _load_plan_lifecycle_anchor(repo_root=tmp_path) is False


def test_plan_lifecycle_anchor_non_bool_raises(*, tmp_path: Path) -> None:
    """A non-boolean `plan_lifecycle_anchor` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nplan_lifecycle_anchor = "true"\n',
    )
    with pytest.raises(ConfigParseError, match="`plan_lifecycle_anchor` must be a boolean"):
        _ = _load_plan_lifecycle_anchor(repo_root=tmp_path)


def test_subprocess_spawn_allowlist_none_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → `load_subprocess_spawn_allowlist` returns `None`."""
    assert load_subprocess_spawn_allowlist(repo_root=tmp_path) is None


def test_subprocess_spawn_allowlist_none_when_key_absent(*, tmp_path: Path) -> None:
    """A block present but omitting `subprocess_spawn_allowlist` → `None` (caller defaults empty)."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    assert load_subprocess_spawn_allowlist(repo_root=tmp_path) is None


def test_subprocess_spawn_allowlist_read_from_block(*, tmp_path: Path) -> None:
    """A declared `subprocess_spawn_allowlist` array is returned verbatim as a tuple."""
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'subprocess_spawn_allowlist = ["tests/consumer/", "tests/x/test_y.py"]\n'
        ),
    )
    assert load_subprocess_spawn_allowlist(repo_root=tmp_path) == (
        "tests/consumer/",
        "tests/x/test_y.py",
    )


def test_subprocess_spawn_allowlist_non_array_raises(*, tmp_path: Path) -> None:
    """A scalar `subprocess_spawn_allowlist` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsubprocess_spawn_allowlist = "tests/"\n',
    )
    with pytest.raises(
        ConfigParseError, match="`subprocess_spawn_allowlist` must be an array of strings"
    ):
        _ = load_subprocess_spawn_allowlist(repo_root=tmp_path)


def test_subprocess_spawn_allowlist_non_string_element_raises(*, tmp_path: Path) -> None:
    """A `subprocess_spawn_allowlist` array with a non-string element raises."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\nsubprocess_spawn_allowlist = [1]\n",
    )
    with pytest.raises(
        ConfigParseError, match="`subprocess_spawn_allowlist` must be an array of strings"
    ):
        _ = load_subprocess_spawn_allowlist(repo_root=tmp_path)


# --- is_generated ------------------------------------------------------------
#
# Per the fleet-check-coverage OQ1 resolution, `@generated` counts only on a
# line that IS a comment in the file's own native syntax (looked up by
# extension) — never a bare directory/filename convention.


def test_is_generated_true_for_hash_comment_marker(*, tmp_path: Path) -> None:
    """A `# @generated` line in a `.py` file is recognized via the `#` comment prefix."""
    target = tmp_path / "gen.py"
    _ = target.write_text("# @generated by tool X\nx = 1\n", encoding="utf-8")
    assert is_generated(path=target) is True


def test_is_generated_false_when_marker_absent(*, tmp_path: Path) -> None:
    """A file with no `@generated` token anywhere is not generated."""
    target = tmp_path / "plain.py"
    _ = target.write_text("# a normal comment\nx = 1\n", encoding="utf-8")
    assert is_generated(path=target) is False


def test_is_generated_false_for_unknown_extension(*, tmp_path: Path) -> None:
    """An unrecognized extension is treated as not-generated, even with the marker present."""
    target = tmp_path / "notes.txt"
    _ = target.write_text("@generated\n", encoding="utf-8")
    assert is_generated(path=target) is False


def test_is_generated_ignores_marker_inside_docstring(*, tmp_path: Path) -> None:
    """`@generated` inside a Python docstring (not a `#` comment) does not count."""
    target = tmp_path / "docstring.py"
    _ = target.write_text(
        '"""Module docstring mentioning @generated for illustration."""\nx = 1\n',
        encoding="utf-8",
    )
    assert is_generated(path=target) is False


def test_is_generated_recognizes_non_python_comment_syntax(*, tmp_path: Path) -> None:
    """The registry recognizes `//`-style comments for a non-Python extension (`.rs`)."""
    target = tmp_path / "lib.rs"
    _ = target.write_text("// @generated by codegen\nfn main() {}\n", encoding="utf-8")
    assert is_generated(path=target) is True


def test_is_generated_recognizes_indented_comment(*, tmp_path: Path) -> None:
    """A `@generated` comment indented with leading whitespace still counts."""
    target = tmp_path / "indented.py"
    _ = target.write_text("if True:\n    # @generated\n    pass\n", encoding="utf-8")
    assert is_generated(path=target) is True


def test_is_generated_recognizes_c_family_block_comment_marker(*, tmp_path: Path) -> None:
    """A single-line `/* @generated */` block comment counts for a C-family extension.

    Regression for the fleet-check-coverage foundation: the design's OQ1 resolution
    requires BOTH `//` and `/* */` native comment syntax for Rust/TS/JS/Go/C, but the
    initial registry gave the C-family only `//`, so block-comment markers were missed.
    """
    target = tmp_path / "gen.c"
    _ = target.write_text(
        "/* @generated by tool */\nint main(void) { return 0; }\n", encoding="utf-8"
    )
    assert is_generated(path=target) is True


def test_is_generated_recognizes_html_block_comment_marker(*, tmp_path: Path) -> None:
    """A single-line `<!-- @generated -->` block comment counts for an HTML/markdown extension."""
    target = tmp_path / "gen.md"
    _ = target.write_text("<!-- @generated by tool -->\n# Title\n", encoding="utf-8")
    assert is_generated(path=target) is True


# --- filter_first_party_py -----------------------------------------------------
#
# Pure set-logic over an already-obtained tracked-`.py` list; no subprocess.


def test_filter_first_party_py_excludes_vendor_segment(*, tmp_path: Path) -> None:
    """A `_vendor` path segment anywhere in the path is excluded."""
    kept = Path("pkg") / "a.py"
    vendored = Path("pkg") / "_vendor" / "lib" / "v.py"
    for rel in (kept, vendored):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=[kept, vendored], repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (kept,)


def test_filter_first_party_py_excludes_configured_test_tree(*, tmp_path: Path) -> None:
    """A path under the configured `tests_tree_prefix` is excluded."""
    kept = Path("pkg") / "a.py"
    test_file = Path("tests") / "test_a.py"
    for rel in (kept, test_file):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=[kept, test_file], repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (kept,)


def test_filter_first_party_py_excludes_conftest_anywhere(*, tmp_path: Path) -> None:
    """A `conftest.py` is excluded regardless of its directory (not only under `tests/`)."""
    kept = Path("pkg") / "a.py"
    conftest = Path("pkg") / "sub" / "conftest.py"
    for rel in (kept, conftest):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=[kept, conftest], repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (kept,)


def test_filter_first_party_py_excludes_templates_tree(*, tmp_path: Path) -> None:
    """A path under `templates/` (copier payload) is excluded."""
    kept = Path("pkg") / "a.py"
    templated = Path("templates") / "impl-plugin" / "hook.py"
    for rel in (kept, templated):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=[kept, templated], repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (kept,)


def test_filter_first_party_py_excludes_claude_skills_but_covers_claude_hooks(
    *, tmp_path: Path
) -> None:
    """`.claude/skills/` is excluded (local-only skill infra); `.claude/hooks/` stays COVERED.

    The exemption is deliberately narrowed to `.claude/skills/` — host-only,
    LOCAL-ONLY agent-runtime skills (e.g. the overseer daemon) livespec ships to
    no one and governs under its own thread — and NOT all of `.claude/`.
    `.claude/hooks/**` holds first-party hook `.py` (e.g. the Driver-shipped
    footgun/no-shadow guards) that the fleet-check-coverage epic requires
    COVERED: a Driver repo's hooks are its entire first-party universe, so
    dropping them would leave that repo's product code ungoverned. A skill
    module AND a `test_`-prefixed skill file (which the tests-tree rule does NOT
    catch — not under `tests/`, not named `conftest.py`) are excluded, while a
    `.claude/hooks/` file and a normal first-party path survive. The pre-existing
    `_vendor` / tests-tree / `templates/` exemptions are re-asserted so the
    narrowed branch is proven additive, not a replacement.
    """
    kept = Path("livespec_dev_tooling") / "config.py"
    claude_hook = Path(".claude") / "hooks" / "livespec_footgun_guard.py"
    claude_skill = Path(".claude") / "skills" / "overseer" / "registry.py"
    claude_skill_test = Path(".claude") / "skills" / "overseer" / "test_registry.py"
    vendored = Path("pkg") / "_vendor" / "v.py"
    tested = Path("tests") / "test_a.py"
    templated = Path("templates") / "hook.py"
    inputs = (kept, claude_hook, claude_skill, claude_skill_test, vendored, tested, templated)
    for rel in inputs:
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=list(inputs), repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (claude_hook, kept)


def test_filter_first_party_py_excludes_generated_marker(*, tmp_path: Path) -> None:
    """A file carrying the `@generated` sentinel is excluded."""
    kept = Path("pkg") / "a.py"
    generated = Path("pkg") / "gen.py"
    for rel, body in ((kept, "x = 1\n"), (generated, "# @generated\ny = 2\n")):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text(body, encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=[kept, generated], repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (kept,)


def test_filter_first_party_py_keeps_and_sorts_first_party(*, tmp_path: Path) -> None:
    """Multiple first-party survivors are returned sorted, regardless of input order."""
    first = Path("pkg") / "b.py"
    second = Path("pkg") / "a.py"
    for rel in (first, second):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    result = filter_first_party_py(
        tracked_py=[first, second], repo_root=tmp_path, tests_tree_prefix="tests/"
    )
    assert result == (second, first)


# --- iter_first_party_py_files / has_first_party_py ---------------------------
#
# The IO wrapper: a real `tmp_path` git repo, `git ls-files` shelled for real.
# `git` is not a Python spawn (tests_no_subprocess_spawn only forbids
# `sys.executable`/`python`/`python3` argv[0]), so this is allowed in tests/.
# The env passed to every `git` call below is a hardcoded 3-key dict (never
# `os.environ` passthrough), so COVERAGE_PROCESS_START / COV_CORE_* can never
# leak into it — belt-and-suspenders per the repo's documented subprocess-spawn
# discipline, though moot here since the child is `git`, not an instrumented
# Python interpreter.


def _git(*, cwd: Path, args: list[str]) -> None:
    # S603/S607: argv is a fixed list (literal git binary + repo-controlled
    # args); no untrusted shell input.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def test_iter_first_party_py_files_empty_repo_returns_empty(*, tmp_path: Path) -> None:
    """A repo with zero tracked `.py` returns an empty tuple (the genuinely-codeless case)."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _ = (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "README.md"])
    assert iter_first_party_py_files(repo_root=tmp_path) == ()
    assert has_first_party_py(repo_root=tmp_path) is False


def test_iter_first_party_py_files_applies_exemptions(*, tmp_path: Path) -> None:
    """The wrapper composes `git ls-files` with `filter_first_party_py`'s exemptions."""
    _git(cwd=tmp_path, args=["init", "-q"])
    kept = Path("pkg") / "a.py"
    vendored = Path("pkg") / "_vendor" / "v.py"
    tested = Path("tests") / "test_a.py"
    templated = Path("templates") / "hook.py"
    generated = Path("pkg") / "gen.py"
    for rel, body in (
        (kept, "x = 1\n"),
        (vendored, "y = 2\n"),
        (tested, "z = 3\n"),
        (templated, "w = 4\n"),
        (generated, "# @generated\nv = 5\n"),
    ):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text(body, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    assert iter_first_party_py_files(repo_root=tmp_path) == (kept,)
    assert has_first_party_py(repo_root=tmp_path) is True


def test_iter_first_party_py_files_respects_configured_tests_tree_prefix(*, tmp_path: Path) -> None:
    """A consumer-declared `tests_tree_prefix` (not the default `tests/`) is honored."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\ntests_tree_prefix = "spec_tests/"\n', encoding="utf-8"
    )
    kept = Path("pkg") / "a.py"
    custom_tested = Path("spec_tests") / "test_a.py"
    for rel in (kept, custom_tested):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    assert iter_first_party_py_files(repo_root=tmp_path) == (kept,)


def test_iter_first_party_py_files_excludes_declared_neutral_hook_body(*, tmp_path: Path) -> None:
    """The config-declared `neutral_hook_body_path` is exempt from the first-party universe.

    The neutral hook body is INSTALLED FOREIGN CONTENT — byte-synced from the
    packaged canonical constant and forbidden to hand-edit (the
    `no-shadow-ledger-body-identical` check enforces the sync) — so no
    universe-derived structural check may demand edits to it (the observed
    conflict: `check-all-declared` demanding `__all__` in a Driver's installed
    body, deadlocking against the byte-identity requirement). The identity
    check itself reads the configured path directly, not via this universe, so
    exempting the path here cannot mask body drift. A sibling `.py` beside the
    body stays covered, proving the exemption is exact-path, not tree-wide.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'neutral_hook_body_path = ".claude-plugin/hooks/no_shadow_ledger.py"\n',
        encoding="utf-8",
    )
    sibling = Path(".claude-plugin") / "hooks" / "a_sibling_hook.py"
    body = Path(".claude-plugin") / "hooks" / "no_shadow_ledger.py"
    kept = Path("pkg") / "a.py"
    for rel in (sibling, body, kept):
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _ = full.write_text("x = 1\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    assert iter_first_party_py_files(repo_root=tmp_path) == (sibling, kept)


def test_iter_first_party_py_files_raises_on_git_failure(*, tmp_path: Path) -> None:
    """A `repo_root` that is not a git working tree raises `GitLsFilesError`."""
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    with pytest.raises(GitLsFilesError, match="git ls-files failed"):
        _ = iter_first_party_py_files(repo_root=not_a_repo)


# --- resolve_repo_root / is_under_any_tree / resolve_check_universe ----------
#
# The applies-to-all check anchoring + delta-WARN helpers (fleet-check-coverage).
# Both `resolve_repo_root` and `resolve_check_universe` run git in the PROCESS
# cwd — `resolve_check_universe` OWNS root-resolution (it takes no `repo_root`),
# so a caller cannot pass a mis-anchored root — so their tests
# `monkeypatch.chdir(...)` a real `tmp_path` git repo; `is_under_any_tree` is a
# pure classifier over explicit args.


def test_resolve_repo_root_returns_toplevel_from_subdirectory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From a repo SUBDIRECTORY, `resolve_repo_root` still returns the toplevel.

    This is the invocation-location-independence the reroute buys: a check
    invoked from a subdir anchors on the git toplevel, not the subdir cwd,
    so `git ls-files` walks the WHOLE universe rather than the subdir slice.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    sub = tmp_path / "pkg" / "nested"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert resolve_repo_root().samefile(tmp_path)


def test_resolve_repo_root_strips_git_env_vars(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A poisoned `GIT_DIR` in the env does NOT mis-point the resolution.

    `resolve_repo_root` strips every `GIT_*` var before shelling git; without
    that, an injected `GIT_DIR` (e.g. from a parent git hook) would override
    `cwd` and either fail or resolve the wrong tree.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "definitely-not-a-git-dir"))
    assert resolve_repo_root().samefile(tmp_path)


def test_resolve_repo_root_raises_outside_git_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cwd not inside any git working tree raises `GitToplevelError` (fail closed)."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    with pytest.raises(GitToplevelError, match="git rev-parse --show-toplevel failed"):
        _ = resolve_repo_root()


def test_is_under_any_tree_classifies_relative_paths() -> None:
    """A path under any tree is legacy; outside every tree it is newly-covered."""
    trees = (Path("src"), Path(".claude-plugin") / "scripts" / "livespec")
    assert is_under_any_tree(rel=Path("src") / "mod.py", trees=trees) is True
    assert (
        is_under_any_tree(rel=Path(".claude-plugin") / "scripts" / "livespec" / "x.py", trees=trees)
        is True
    )
    assert is_under_any_tree(rel=Path("pkg") / "mod.py", trees=trees) is False
    assert is_under_any_tree(rel=Path("mod.py"), trees=()) is False


def test_is_bin_wrapper_identifies_the_wrapper_set() -> None:
    """`is_bin_wrapper` is the single wrapper-identity both checks share.

    A DIRECT-CHILD `.claude-plugin/scripts/bin/*.py` file is a wrapper
    UNLESS it is the exempt `_bootstrap.py`. A non-`.py` file under the
    tree, a file nested deeper than a direct child, and a file outside the
    tree are all NOT wrappers. This pins every branch of the predicate so
    `wrapper_shape` and `all_declared` read ONE definition.
    """
    bin_tree = Path(".claude-plugin") / "scripts" / "bin"
    assert is_bin_wrapper(rel=bin_tree / "seed.py") is True
    assert is_bin_wrapper(rel=bin_tree / "_bootstrap.py") is False
    assert is_bin_wrapper(rel=bin_tree / "notes.txt") is False
    assert is_bin_wrapper(rel=Path("pkg") / "mod.py") is False
    assert is_bin_wrapper(rel=bin_tree / "sub" / "deep.py") is False


def test_resolve_check_universe_returns_root_and_universe(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From inside the repo, `resolve_check_universe()` returns `(root, universe)`.

    It OWNS root-resolution (no `repo_root` argument), so a caller cannot pass a
    mis-anchored root — the root is the git toplevel of the process cwd.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    kept = Path("pkg") / "a.py"
    full = tmp_path / kept
    full.parent.mkdir(parents=True)
    _ = full.write_text("x = 1\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    monkeypatch.chdir(tmp_path)
    root, universe = resolve_check_universe()
    assert root.samefile(tmp_path)
    assert universe == (kept,)


def test_resolve_check_universe_empty_for_genuinely_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo with zero first-party `.py` yields an empty universe (a legitimate PASS)."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    monkeypatch.chdir(tmp_path)
    root, universe = resolve_check_universe()
    assert root.samefile(tmp_path)
    assert universe == ()


def test_resolve_check_universe_raises_outside_git_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside any git working tree, `resolve_check_universe()` fails closed.

    Real fail-closed coverage: because the resolver OWNS root-resolution, a
    non-git cwd raises `GitToplevelError` — never a spuriously-empty walk. This
    replaces the former monkeypatch-only `EmptyUniverseError` test, which
    exercised a provably-unreachable branch (`not X and bool(X)` is always
    False), and pins the protection that actually holds.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    with pytest.raises(GitToplevelError, match="git rev-parse --show-toplevel failed"):
        _ = resolve_check_universe()


def test_superseded_by_variant_parses(*, tmp_path: Path) -> None:
    """`{ superseded_by = "<reason>" }` parses to its own type, not to not-applicable.

    (C) is materially different from (A): under not-applicable there is nothing to
    check, while under superseded-by the concept IS being checked, elsewhere.
    Collapsing them would force three fleet repos to mis-declare
    (livespec-dev-tooling-8o8e.1).
    """
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            "covered_trees = []\n"
            'target_dirs = { superseded_by = "git-derived universe owns this" }\n'
        ),
    )
    config = load_config(repo_root=tmp_path)
    assert config.target_dirs == SupersededBy(reason="git-derived universe owns this")
    assert role_trees(role=config.target_dirs) == ()


def test_convention_not_adopted_variant_parses(*, tmp_path: Path) -> None:
    """`{ convention_not_adopted = "<reason>" }` parses to its own type.

    (D) — maintainer-blessed 2026-07-28. It is the state `livespec-runtime` was
    already in, written in a comment no checker could read.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'target_dirs = { convention_not_adopted = "per-directory CLAUDE.md not adopted" }\n'
        ),
    )
    config = load_config(repo_root=tmp_path)
    assert config.target_dirs == ConventionNotAdopted(reason="per-directory CLAUDE.md not adopted")


def test_prefix_role_accepts_a_blessed_variant(*, tmp_path: Path) -> None:
    """`source_tree_prefixes` takes the same inline-table vocabulary as the tree keys.

    It is the key whose emptiness silently disarmed the commit-time TDD pairing
    gate in three repos, so it must be able to say WHY it is absent.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'source_tree_prefixes = { not_applicable = "no mirrored source surface" }\n'
        ),
    )
    config = load_config(repo_root=tmp_path)
    assert config.source_tree_prefixes == NotApplicable(reason="no mirrored source surface")
    assert role_prefixes(role=config.source_tree_prefixes) == ()
