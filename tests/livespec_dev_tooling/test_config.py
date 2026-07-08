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

import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.config import (
    Config,
    ConfigParseError,
    GitLsFilesError,
    MirrorPairing,
    filter_first_party_py,
    has_first_party_py,
    is_generated,
    iter_first_party_py_files,
    iter_py_files,
    load_config,
    load_destructive_cli_allowlist,
    load_mutation_staging_dir,
    load_scenario_tiers,
    load_subprocess_spawn_allowlist,
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


def test_iter_first_party_py_files_raises_on_git_failure(*, tmp_path: Path) -> None:
    """A `repo_root` that is not a git working tree raises `GitLsFilesError`."""
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    with pytest.raises(GitLsFilesError, match="git ls-files failed"):
        _ = iter_first_party_py_files(repo_root=not_a_repo)
