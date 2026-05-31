"""config — consumer source-tree layout loader for the shared checks.

Per `SPECIFICATION/contracts.md` §"Consumer configuration schema",
every shared check that depends on the consumer's source-tree layout
reads its layout-dependent paths from a `[tool.livespec_dev_tooling]`
block in the consuming repo's root `pyproject.toml`. This module is the
single loader (via stdlib `tomllib` on 3.11+, or the vendored `tomli` on
the 3.10 floor).

Two default regimes, per §"Default layout fallback" + §"Role keys":

1. **No `[tool.livespec_dev_tooling]` block at all** (the livespec-core
   case) → every role key falls back to livespec-core's historical
   pre-G.4 path constant, so livespec-core stays bit-identical (the
   criterion-5 backward-compat guarantee).
2. **Block present but a role key omitted** (a flat-layout consumer like
   livespec-dev-tooling itself) → that key defaults empty/null, which
   makes the consuming check no-op against this consumer (per §"Role
   keys"). The consumer declares only the role keys its layout actually
   has.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this package. This module raises
a typed `ConfigParseError` (an IO-layer exception caught by each check's
`main()` supervisor) rather than writing diagnostics itself.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# stdlib `tomllib` lands in 3.11; the repo floor is 3.10 (per
# `SPECIFICATION/constraints.md` §"Runtime"), so fall back to the
# vendored `tomli`, which exposes an identical `loads(text) -> dict`. The
# 3.11 `tomllib` branch is never taken under the 3.10 test run, so it is
# coverage-exempt; the 3.10 `tomli` branch is the one CI exercises.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

if sys.version_info >= (3, 11):  # pragma: no cover — 3.11 path unused on the 3.10 floor.
    import tomllib as _toml
else:
    import tomli as _toml

__all__: list[str] = [
    "Config",
    "ConfigParseError",
    "MirrorPairing",
    "iter_py_files",
    "load_config",
    "load_scenario_tiers",
]


_TABLE_KEY = "livespec_dev_tooling"
_VENDOR_MARKER = "_vendor"
_PYCACHE_MARKER = "__pycache__"


class ConfigParseError(Exception):
    """Raised on malformed TOML or a schema-violating value.

    An IO-layer exception per `SPECIFICATION/contracts.md` §"Configuration
    loader" — each check's `main()` supervisor catches it and renders a
    structured diagnostic.
    """


@dataclass(frozen=True, kw_only=True)
class MirrorPairing:
    """One source-tree to test-tree mirror, consumed by check_coverage_incremental."""

    source_tree: Path
    test_tree: Path


@dataclass(frozen=True, kw_only=True)
class Config:
    """Typed layout configuration. The bare `Config()` is the flat baseline.

    A bare `Config()` carries empty role keys — the regime a flat-layout
    consumer (one that declares a `[tool.livespec_dev_tooling]` block but
    omits a key) sees for that key: the consuming check no-ops. The
    livespec-core historical fallback (whole block absent) is built by
    `_livespec_core_config()`.
    """

    source_trees: tuple[Path, ...] = ()
    io_trees: tuple[Path, ...] = ()
    commands_trees: tuple[Path, ...] = ()
    supervisor_entry_files: tuple[Path, ...] = ()
    dataclasses_tree: Path | None = None
    pure_trees: tuple[Path, ...] = ()
    covered_trees: tuple[Path, ...] = ()
    source_tree_prefixes: tuple[str, ...] = ()
    tests_tree_prefix: str = "tests/"
    target_dirs: tuple[Path, ...] = ()
    mirror_pairings: tuple[MirrorPairing, ...] = ()


def _p(*parts: str) -> Path:
    return Path(*parts)


def _livespec_core_config() -> Config:
    """The historical livespec-core layout used when the block is absent.

    Each value is the literal path constant the corresponding check
    carried before the G.4 migration, so livespec-core (which omits the
    `[tool.livespec_dev_tooling]` block) stays bit-identical to its
    pre-G.6 behavior.
    """
    livespec = _p(".claude-plugin", "scripts", "livespec")
    return Config(
        source_trees=(livespec,),
        io_trees=(_p(".claude-plugin", "scripts", "livespec", "io"),),
        commands_trees=(_p(".claude-plugin", "scripts", "livespec", "commands"),),
        supervisor_entry_files=(
            _p(".claude-plugin", "scripts", "livespec", "doctor", "run_static.py"),
            _p(".claude-plugin", "scripts", "bin", "_bootstrap.py"),
        ),
        dataclasses_tree=_p(".claude-plugin", "scripts", "livespec", "schemas", "dataclasses"),
        pure_trees=(
            _p(".claude-plugin", "scripts", "livespec", "parse"),
            _p(".claude-plugin", "scripts", "livespec", "validate"),
        ),
        covered_trees=(
            livespec,
            _p(".claude-plugin", "scripts", "bin"),
            _p("dev-tooling"),
        ),
        source_tree_prefixes=(
            ".claude-plugin/scripts/livespec/",
            ".claude-plugin/scripts/bin/",
            "dev-tooling/checks/",
        ),
        tests_tree_prefix="tests/",
        target_dirs=(
            _p(".claude-plugin", "scripts"),
            _p("dev-tooling"),
            _p("tests"),
        ),
        mirror_pairings=(
            MirrorPairing(source_tree=livespec, test_tree=_p("tests", "livespec")),
            MirrorPairing(
                source_tree=_p(".claude-plugin", "scripts", "bin"),
                test_tree=_p("tests", "bin"),
            ),
            MirrorPairing(
                source_tree=_p("dev-tooling", "checks"),
                test_tree=_p("tests", "dev-tooling", "checks"),
            ),
            MirrorPairing(
                source_tree=_p("livespec_dev_tooling", "checks"),
                test_tree=_p("tests", "livespec_dev_tooling", "checks"),
            ),
        ),
    )


def iter_py_files(*, root: Path) -> Iterator[Path]:
    """Yield every `.py` under `root` (sorted), skipping `_vendor`/`__pycache__`.

    The shared walker every shape-checking check uses. Excluding
    `_vendor`/`__pycache__` is bit-identical for livespec-core (whose
    source trees contain neither) and is what lets a flat-package
    consumer point `source_trees` at a package directory that carries a
    vendored subtree without the check tripping on third-party code.
    """
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.py")):
        if _VENDOR_MARKER in path.parts or _PYCACHE_MARKER in path.parts:
            continue
        yield path


def _as_str_tuple(*, value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        msg = f"`{key}` must be an array of strings"
        raise ConfigParseError(msg)
    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        msg = f"`{key}` must be an array of strings"
        raise ConfigParseError(msg)
    return tuple(cast("list[str]", items))


def _as_path_tuple(*, value: object, key: str) -> tuple[Path, ...]:
    return tuple(Path(item) for item in _as_str_tuple(value=value, key=key))


def _as_path(*, value: object, key: str) -> Path:
    # TOML has no null literal: an absent `dataclasses_tree` IS the null
    # default (handled by key-absence in `load_config`); a present key is
    # always a non-None value, so only the string/non-string split remains.
    if not isinstance(value, str):
        msg = f"`{key}` must be a string or omitted"
        raise ConfigParseError(msg)
    return Path(value)


def _as_str(*, value: object, key: str) -> str:
    if not isinstance(value, str):
        msg = f"`{key}` must be a string"
        raise ConfigParseError(msg)
    return value


def _parse_mirror_pairings(*, value: object) -> tuple[MirrorPairing, ...]:
    if not isinstance(value, list):
        msg = "`mirror_pairings` must be an array of {source_tree, test_tree} tables"
        raise ConfigParseError(msg)
    entries = cast("list[object]", value)
    out: list[MirrorPairing] = []
    for entry in entries:
        if not isinstance(entry, dict):
            msg = "each `mirror_pairings` entry must be a table"
            raise ConfigParseError(msg)
        table = cast("dict[str, Any]", entry)
        source = table.get("source_tree")
        test = table.get("test_tree")
        if not isinstance(source, str) or not isinstance(test, str):
            msg = "each `mirror_pairings` entry needs string `source_tree` + `test_tree`"
            raise ConfigParseError(msg)
        out.append(MirrorPairing(source_tree=Path(source), test_tree=Path(test)))
    return tuple(out)


def _read_table(*, repo_root: Path) -> dict[str, Any] | None:
    """Return the `[tool.livespec_dev_tooling]` table, or None if absent.

    `None` distinguishes "no block at all" (livespec-core fallback regime)
    from "block present but empty" (flat-baseline regime).
    """
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        parsed = _toml.loads(pyproject.read_text(encoding="utf-8"))
    except (_toml.TOMLDecodeError, ValueError) as exc:
        msg = f"malformed pyproject.toml: {exc}"
        raise ConfigParseError(msg) from exc
    tool = parsed.get("tool")
    if not isinstance(tool, dict):
        return None
    table = cast("dict[str, Any]", tool).get(_TABLE_KEY)
    if not isinstance(table, dict):
        return None
    return cast("dict[str, Any]", table)


def load_scenario_tiers(*, repo_root: Path) -> tuple[str, ...] | None:
    """Return the `scenario_tiers` allowlist, or `None` if the key is absent.

    Reads `<repo_root>/pyproject.toml`'s `[tool.livespec_dev_tooling]` block,
    key `scenario_tiers` — a TOML array of node-id path prefixes that the
    `heading_coverage` check accepts as integration-tier-or-above for
    `scenarios.md` headings (per `SPECIFICATION/constraints.md` §"Heading
    taxonomy"). Returns `None` when the whole block is absent OR the
    `scenario_tiers` key is omitted, so the calling check applies its own
    documented default. Raises `ConfigParseError` on a non-array value or a
    non-string element, consistent with the rest of the loader.

    This is intentionally NOT a `Config` role key: `scenario_tiers` is a
    single-check concern (`heading_coverage`), so it is read directly off the
    table rather than threaded through the typed layout dataclass.
    """
    table = _read_table(repo_root=repo_root)
    if table is None or "scenario_tiers" not in table:
        return None
    return _as_str_tuple(value=table["scenario_tiers"], key="scenario_tiers")


def load_config(*, repo_root: Path) -> Config:
    """Read `<repo_root>/pyproject.toml`'s block and resolve the layout.

    No `[tool.livespec_dev_tooling]` block → the livespec-core historical
    fallback. Block present → a flat baseline (`Config()`) with each
    declared role key overridden; an omitted key stays empty/null so the
    consuming check no-ops on this consumer. Raises `ConfigParseError` on
    malformed TOML or a schema-violating value.
    """
    table = _read_table(repo_root=repo_root)
    if table is None:
        return _livespec_core_config()
    baseline = Config()
    overrides: dict[str, Any] = {}
    for key in (
        "source_trees",
        "io_trees",
        "commands_trees",
        "supervisor_entry_files",
        "pure_trees",
        "covered_trees",
        "target_dirs",
    ):
        if key in table:
            overrides[key] = _as_path_tuple(value=table[key], key=key)
    if "dataclasses_tree" in table:
        overrides["dataclasses_tree"] = _as_path(
            value=table["dataclasses_tree"], key="dataclasses_tree"
        )
    if "source_tree_prefixes" in table:
        overrides["source_tree_prefixes"] = _as_str_tuple(
            value=table["source_tree_prefixes"], key="source_tree_prefixes"
        )
    if "tests_tree_prefix" in table:
        overrides["tests_tree_prefix"] = _as_str(
            value=table["tests_tree_prefix"], key="tests_tree_prefix"
        )
    if "mirror_pairings" in table:
        overrides["mirror_pairings"] = _parse_mirror_pairings(value=table["mirror_pairings"])
    return Config(
        source_trees=overrides.get("source_trees", baseline.source_trees),
        io_trees=overrides.get("io_trees", baseline.io_trees),
        commands_trees=overrides.get("commands_trees", baseline.commands_trees),
        supervisor_entry_files=overrides.get(
            "supervisor_entry_files", baseline.supervisor_entry_files
        ),
        dataclasses_tree=overrides.get("dataclasses_tree", baseline.dataclasses_tree),
        pure_trees=overrides.get("pure_trees", baseline.pure_trees),
        covered_trees=overrides.get("covered_trees", baseline.covered_trees),
        source_tree_prefixes=overrides.get("source_tree_prefixes", baseline.source_tree_prefixes),
        tests_tree_prefix=overrides.get("tests_tree_prefix", baseline.tests_tree_prefix),
        target_dirs=overrides.get("target_dirs", baseline.target_dirs),
        mirror_pairings=overrides.get("mirror_pairings", baseline.mirror_pairings),
    )
