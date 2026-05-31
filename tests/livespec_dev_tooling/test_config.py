"""Unit test for `livespec_dev_tooling.config` — the consumer-layout loader.

Per `SPECIFICATION/contracts.md` §"Consumer configuration schema", the
loader resolves the consumer's source-tree layout in two regimes:

1. No `[tool.livespec_dev_tooling]` block (the livespec-core case) → the
   full livespec-core historical fallback (every role key carries its
   pre-G.4 path constant), so livespec-core stays bit-identical
   (criterion 5).
2. Block present but a role key omitted (a flat-layout consumer like
   livespec-dev-tooling) → that key defaults empty/null, so the
   consuming check no-ops; declared keys override.

This test also pins every schema-violation path (→ `ConfigParseError`)
and the shared `iter_py_files` walker (skips `_vendor`/`__pycache__`,
no-ops on a missing root).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.config import (
    Config,
    ConfigParseError,
    MirrorPairing,
    iter_py_files,
    load_config,
    load_scenario_tiers,
)

__all__: list[str] = []


_LIVESPEC = Path(".claude-plugin") / "scripts" / "livespec"


def _write_pyproject(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(body, encoding="utf-8")


def test_livespec_core_fallback_when_no_pyproject(*, tmp_path: Path) -> None:
    """No `pyproject.toml` → the full livespec-core historical layout."""
    config = load_config(repo_root=tmp_path)
    assert config.source_trees == (_LIVESPEC,)
    assert config.io_trees == (_LIVESPEC / "io",)
    assert config.commands_trees == (_LIVESPEC / "commands",)
    assert config.supervisor_entry_files == (
        _LIVESPEC / "doctor" / "run_static.py",
        Path(".claude-plugin") / "scripts" / "bin" / "_bootstrap.py",
    )
    assert config.dataclasses_tree == _LIVESPEC / "schemas" / "dataclasses"
    assert config.pure_trees == (_LIVESPEC / "parse", _LIVESPEC / "validate")
    assert config.covered_trees == (
        _LIVESPEC,
        Path(".claude-plugin") / "scripts" / "bin",
        Path("dev-tooling"),
    )
    assert config.source_tree_prefixes == (
        ".claude-plugin/scripts/livespec/",
        ".claude-plugin/scripts/bin/",
        "dev-tooling/checks/",
    )
    assert config.tests_tree_prefix == "tests/"
    assert config.target_dirs == (
        Path(".claude-plugin") / "scripts",
        Path("dev-tooling"),
        Path("tests"),
    )
    assert config.mirror_pairings == (
        MirrorPairing(source_tree=_LIVESPEC, test_tree=Path("tests") / "livespec"),
        MirrorPairing(
            source_tree=Path(".claude-plugin") / "scripts" / "bin",
            test_tree=Path("tests") / "bin",
        ),
        MirrorPairing(
            source_tree=Path("dev-tooling") / "checks",
            test_tree=Path("tests") / "dev-tooling" / "checks",
        ),
        MirrorPairing(
            source_tree=Path("livespec_dev_tooling") / "checks",
            test_tree=Path("tests") / "livespec_dev_tooling" / "checks",
        ),
    )


def test_livespec_core_fallback_when_pyproject_has_no_tool_table(*, tmp_path: Path) -> None:
    """`pyproject.toml` with no `[tool]` table → livespec-core fallback."""
    _write_pyproject(repo_root=tmp_path, body='[project]\nname = "x"\n')
    assert load_config(repo_root=tmp_path).source_trees == (_LIVESPEC,)


def test_livespec_core_fallback_when_no_livespec_block(*, tmp_path: Path) -> None:
    """`[tool.ruff]` present but no `[tool.livespec_dev_tooling]` → fallback."""
    _write_pyproject(repo_root=tmp_path, body="[tool.ruff]\nline-length = 100\n")
    assert load_config(repo_root=tmp_path).io_trees == (_LIVESPEC / "io",)


def test_present_block_omitting_keys_yields_flat_baseline(*, tmp_path: Path) -> None:
    """A block declaring only `source_trees` → omitted role keys stay empty.

    The flat-layout regime: a consumer that declares a block opts out of
    the livespec-core fallback entirely; omitted role keys are empty/null
    so the corresponding checks no-op against it.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    config = load_config(repo_root=tmp_path)
    assert config.source_trees == (Path("pkg"),)
    assert config.io_trees == ()
    assert config.commands_trees == ()
    assert config.supervisor_entry_files == ()
    assert config.dataclasses_tree is None
    assert config.pure_trees == ()
    assert config.covered_trees == ()
    assert config.source_tree_prefixes == ()
    assert config.target_dirs == ()
    assert config.mirror_pairings == ()
    assert config.tests_tree_prefix == "tests/"


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
        ),
    )
    config = load_config(repo_root=tmp_path)
    assert config.source_trees == (Path("pkg"),)
    assert config.io_trees == (Path("pkg/io"),)
    assert config.commands_trees == (Path("pkg/commands"),)
    assert config.supervisor_entry_files == (Path("pkg/run.py"),)
    assert config.dataclasses_tree == Path("pkg/schemas")
    assert config.pure_trees == (Path("pkg/pure"),)
    assert config.covered_trees == (Path("pkg"),)
    assert config.source_tree_prefixes == ("pkg/",)
    assert config.tests_tree_prefix == "t/"
    assert config.target_dirs == (Path("pkg"),)
    assert config.mirror_pairings == (
        MirrorPairing(source_tree=Path("pkg"), test_tree=Path("t/pkg")),
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
    with pytest.raises(ConfigParseError, match="`dataclasses_tree` must be a string or omitted"):
        _ = load_config(repo_root=tmp_path)


def test_tests_tree_prefix_non_string_raises(*, tmp_path: Path) -> None:
    """A non-string `tests_tree_prefix` raises `ConfigParseError`."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ntests_tree_prefix = 7\n",
    )
    with pytest.raises(ConfigParseError, match="`tests_tree_prefix` must be a string"):
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


def test_bare_config_is_flat_baseline() -> None:
    """`Config()` is the flat baseline — every role key empty/null."""
    config = Config()
    assert config.source_trees == ()
    assert config.dataclasses_tree is None
    assert config.tests_tree_prefix == "tests/"


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
