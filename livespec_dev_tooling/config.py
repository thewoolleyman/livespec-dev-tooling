"""config — consumer source-tree layout loader for the shared checks.

Per `SPECIFICATION/contracts.md` §"Consumer configuration schema",
every shared check that depends on the consumer's source-tree layout
reads its layout-dependent paths from a `[tool.livespec_dev_tooling]`
block in the consuming repo's root `pyproject.toml`. This module is the
single loader (via stdlib `tomllib` on 3.11+, or the vendored `tomli` on
the 3.10 floor).

The typed `Config` carries both the parsed role-key values and the
set of keys explicitly declared in the consumer block. That declared-ness
is semantically meaningful: a scalar role key can be declared empty (for
example `dataclasses_tree = ""`) and parse to `None`, which must remain
distinguishable from an omitted key at the check layer.

Alongside the consumer-config loader, this module also derives the
git-index first-party `.py` universe (`iter_first_party_py_files`) — the
foundation of the fleet-check-coverage mechanism (`livespec` repo's
`plan/fleet-check-coverage/research/design.md`; epic `livespec-i5ebqd`,
item `livespec-fa3eu5`): `git ls-files '*.py'` minus the exemptions
`filter_first_party_py` applies (`_vendor/`, the configured test tree,
`templates/**`, and any `@generated`-marked file per `is_generated`).
This is a PURE ADDITION — nothing here reroutes any existing check or
changes its behavior; wiring an actual check through this choke point
is a later PR.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this package. This module raises
a typed `ConfigParseError` (an IO-layer exception caught by each check's
`main()` supervisor) rather than writing diagnostics itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from fnmatch import fnmatch
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
    "BIN_WRAPPER_TREE",
    "REQUIRED_ROLE_KEYS",
    "Config",
    "ConfigParseError",
    "GitLsFilesError",
    "GitToplevelError",
    "MirrorPairing",
    "filter_first_party_py",
    "has_first_party_py",
    "is_bin_wrapper",
    "is_generated",
    "is_slf001_exempt",
    "is_under_any_tree",
    "iter_first_party_py_files",
    "iter_py_files",
    "load_config",
    "load_destructive_cli_allowlist",
    "load_mutation_staging_dir",
    "load_plan_lifecycle_anchor",
    "load_scenario_tiers",
    "load_slf001_exempt_globs",
    "load_subprocess_spawn_allowlist",
    "resolve_check_universe",
    "resolve_repo_root",
]


_TABLE_KEY = "livespec_dev_tooling"
# Ruff's `private-member-access` — the ONE rule that polices the same invariant
# `check-private-calls` does, and therefore the only grant this check honours.
_SLF001 = "SLF001"
_VENDOR_MARKER = "_vendor"
_PYCACHE_MARKER = "__pycache__"

REQUIRED_ROLE_KEYS = frozenset(
    {
        "source_trees",
        "io_trees",
        "commands_trees",
        "supervisor_entry_files",
        "pure_trees",
        "covered_trees",
        "target_dirs",
        "source_tree_prefixes",
        "dataclasses_tree",
        "neutral_hook_body_path",
    }
)

_PATH_TUPLE_ROLE_KEYS = REQUIRED_ROLE_KEYS - frozenset(
    {"source_tree_prefixes", "dataclasses_tree", "neutral_hook_body_path"}
)


class ConfigParseError(Exception):
    """Raised on malformed TOML or a schema-violating value.

    An IO-layer exception per `SPECIFICATION/contracts.md` §"Configuration
    loader" — each check's `main()` supervisor catches it and renders a
    structured diagnostic.
    """


class GitLsFilesError(Exception):
    """Raised when the `git ls-files` subprocess fails.

    An IO-layer exception (the `iter_first_party_py_files` analog of
    `ConfigParseError`) raised when `repo_root` is not inside a git
    working tree, or the `git` binary otherwise exits non-zero, rather
    than silently returning an empty universe — the exact fail-open
    shape the fleet-check-coverage design replaces.
    """


class GitToplevelError(Exception):
    """Raised when the `git rev-parse --show-toplevel` subprocess fails.

    The `resolve_repo_root` analog of `GitLsFilesError` — an IO-layer
    exception raised when the process working directory is not inside a
    git working tree (or `git` otherwise exits non-zero), so the
    applies-to-all checks fail closed rather than anchoring on a
    mis-resolved root.
    """


@dataclass(frozen=True, kw_only=True)
class MirrorPairing:
    """One source-tree to test-tree mirror, consumed by check_coverage_incremental."""

    source_tree: Path
    test_tree: Path


@dataclass(frozen=True, kw_only=True)
class Config:
    """Typed layout configuration. The bare `Config()` is the flat baseline.

    `declared_keys` records which keys were present in the consumer's
    `[tool.livespec_dev_tooling]` block. Value emptiness and declared-ness
    are separate signals: omitted role keys are configuration errors for
    role-gated checks, while declared-empty role keys are sanctioned opt-outs.
    """

    declared_keys: frozenset[str] = frozenset()
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
    neutral_hook_body_path: str | None = None


def _p(*parts: str) -> Path:
    return Path(*parts)


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
    if not isinstance(value, str):
        msg = f"`{key}` must be a string or omitted"
        raise ConfigParseError(msg)
    return Path(value)


def _as_optional_path(*, value: object, key: str) -> Path | None:
    # TOML has no null literal, so scalar role keys use the empty string as
    # the declared-none spelling while preserving key omission as None.
    if not isinstance(value, str):
        msg = f"`{key}` must be a string or omitted"
        raise ConfigParseError(msg)
    if value == "":
        return None
    return Path(value)


def _as_str(*, value: object, key: str) -> str:
    if not isinstance(value, str):
        msg = f"`{key}` must be a string"
        raise ConfigParseError(msg)
    if key == "tests_tree_prefix" and value == "":
        msg = "`tests_tree_prefix` must be a non-empty string"
        raise ConfigParseError(msg)
    return value


def _as_bool(*, value: object, key: str) -> bool:
    # TOML `true`/`false` parse to Python `bool`; anything else (string,
    # int, array) is a schema violation. `bool` is checked before `int`
    # would matter because in TOML a bare `1` is an int, not a bool — so
    # `isinstance(value, bool)` rejects it, matching the `_as_str` shape.
    if not isinstance(value, bool):
        msg = f"`{key}` must be a boolean"
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


def _parse_pyproject(*, repo_root: Path) -> dict[str, Any] | None:
    """Return the parsed `pyproject.toml` document, or None if the file is absent."""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        return _toml.loads(pyproject.read_text(encoding="utf-8"))
    except (_toml.TOMLDecodeError, ValueError) as exc:
        msg = f"malformed pyproject.toml: {exc}"
        raise ConfigParseError(msg) from exc


def _read_table(*, repo_root: Path) -> dict[str, Any] | None:
    """Return the `[tool.livespec_dev_tooling]` table, or None if absent.

    `None` means no consumer block was declared, which `load_config` maps
    to the same flat baseline as an empty block but with no declared keys.
    """
    parsed = _parse_pyproject(repo_root=repo_root)
    if parsed is None:
        return None
    tool = parsed.get("tool")
    if not isinstance(tool, dict):
        return None
    table = cast("dict[str, Any]", tool).get(_TABLE_KEY)
    if not isinstance(table, dict):
        return None
    return cast("dict[str, Any]", table)


def load_project_name(*, repo_root: Path) -> str | None:
    """Return `<repo_root>/pyproject.toml`'s `[project].name`, or None if absent.

    Raises `ConfigParseError` on malformed TOML, matching `load_config`.
    """
    parsed = _parse_pyproject(repo_root=repo_root)
    if parsed is None:
        return None
    project = parsed.get("project")
    if not isinstance(project, dict):
        return None
    name = cast("dict[str, Any]", project).get("name")
    return name if isinstance(name, str) else None


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


def load_slf001_exempt_globs(*, repo_root: Path) -> tuple[str, ...]:
    """Return the consumer's own glob patterns that already grant ruff's `SLF001`.

    Reads `<repo_root>/pyproject.toml`'s `[tool.ruff.lint.per-file-ignores]` — a
    map of glob pattern to ignored rule codes — and returns every pattern whose
    ignore list contains `SLF001` (`private-member-access`). Empty when the file,
    the table, or any such grant is absent.

    This deliberately reads the CONSUMER'S ruff config rather than a
    `[tool.livespec_dev_tooling]` key of our own. `SLF001` and
    `check-private-calls` police the SAME invariant — do not reach into another
    module's privates — so where a consumer has already ratified an exemption for
    ruff, a second, independently-declared list would be a drift source rather
    than a decision. Keying off that one rule is also what keeps the exemption
    narrow: a consumer granting a file some UNRELATED rule gets no exemption here,
    so this can never widen into a general "tests may do anything" hatch.

    A non-conforming shape is IGNORED rather than raising: this reads a table the
    consumer maintains for ruff, not for us, and a future ruff schema change must
    not break an unrelated check. A malformed `per-file-ignores` is ruff's own
    error to report.
    """
    parsed = _parse_pyproject(repo_root=repo_root)
    if parsed is None:
        return ()
    node: dict[str, Any] = parsed
    for key in ("tool", "ruff", "lint", "per-file-ignores"):
        child: object = node.get(key)
        if not isinstance(child, dict):
            return ()
        node = cast("dict[str, Any]", child)
    return tuple(
        pattern
        for pattern, codes in node.items()
        if isinstance(codes, list) and _SLF001 in cast("list[Any]", codes)
    )


def is_slf001_exempt(*, rel: Path, globs: tuple[str, ...]) -> bool:
    """True iff `rel` matches any pattern in `globs`, the way ruff matches them.

    Ruff matches a `per-file-ignores` key against the path relative to the
    project root AND against the bare file name, so `"overseer/test_*.py"` and
    `"test_*.py"` both select the same beside-tests. Both forms are honoured
    here, or the check would disagree with ruff about the very config it reads.
    """
    posix = rel.as_posix()
    return any(fnmatch(posix, pattern) or fnmatch(rel.name, pattern) for pattern in globs)


def load_destructive_cli_allowlist(*, repo_root: Path) -> tuple[str, ...] | None:
    """Return the `destructive_cli_allowlist` entries, or `None` if the key is absent.

    Reads `<repo_root>/pyproject.toml`'s `[tool.livespec_dev_tooling]` block,
    key `destructive_cli_allowlist` — a TOML array of repo-root-relative
    path prefixes (POSIX separators; directory entries should end with `/`)
    that the `no_direct_destructive_cli` check exempts from its
    destructive-default CLI scan (per
    `livespec/SPECIFICATION/non-functional-requirements.md`
    §"Destructive-default CLI wrapping"). Returns `None` when the whole
    block is absent OR the `destructive_cli_allowlist` key is omitted, so
    the calling check applies its documented default (empty — nothing
    exempt). Raises `ConfigParseError` on a non-array value or a non-string
    element, consistent with the rest of the loader.

    Like `scenario_tiers`, this is intentionally NOT a `Config` role key:
    it is a single-check concern (`no_direct_destructive_cli`), so it is
    read directly off the table rather than threaded through the typed
    layout dataclass.
    """
    table = _read_table(repo_root=repo_root)
    if table is None or "destructive_cli_allowlist" not in table:
        return None
    return _as_str_tuple(value=table["destructive_cli_allowlist"], key="destructive_cli_allowlist")


def load_subprocess_spawn_allowlist(*, repo_root: Path) -> tuple[str, ...] | None:
    """Return the `subprocess_spawn_allowlist` entries, or `None` if the key is absent.

    Reads `<repo_root>/pyproject.toml`'s `[tool.livespec_dev_tooling]` block,
    key `subprocess_spawn_allowlist` — a TOML array of repo-root-relative
    path prefixes (POSIX separators) that the `tests_no_subprocess_spawn`
    check exempts from its test-spawned-Python-subprocess scan (epic 7us,
    work-item livespec-dev-tooling-4i5). Allowlisted tests genuinely need a
    real subprocess (git / commit-refuse-hook / CLI-binary behavior) and MUST
    scrub `COVERAGE_PROCESS_START` + `COV_CORE_*` from the child env. The
    allowlist is the honest current state and shrinks as gratuitous spawns are
    converted to the in-process `main()` pattern (the deferred conversion
    follow-up, tracked separately). Returns `None` when the whole block is
    absent OR the key is omitted, so the calling check applies its documented
    default (empty — nothing exempt). Raises `ConfigParseError` on a non-array
    value or a non-string element, consistent with the rest of the loader.

    Like `scenario_tiers` and `destructive_cli_allowlist`, this is
    intentionally NOT a `Config` role key: it is a single-check concern
    (`tests_no_subprocess_spawn`), so it is read directly off the table rather
    than threaded through the typed layout dataclass.
    """
    table = _read_table(repo_root=repo_root)
    if table is None or "subprocess_spawn_allowlist" not in table:
        return None
    return _as_str_tuple(
        value=table["subprocess_spawn_allowlist"], key="subprocess_spawn_allowlist"
    )


def load_mutation_staging_dir(*, repo_root: Path) -> Path | None:
    """Return the `mutation_staging_dir`, or `None` if the key is absent.

    Reads `<repo_root>/pyproject.toml`'s `[tool.livespec_dev_tooling]` block,
    key `mutation_staging_dir` — a single repo-root-relative path (POSIX
    separators) naming the import-root staging directory `check_mutation`
    runs mutmut from. Nested-layout repos (livespec + livespec-orchestrator-git-jsonl,
    source under `.claude-plugin/scripts/`) need mutmut run from an
    import-root staging dir so mutant keys (module-name keyed via the
    trampoline) match the file-path-dotted `paths_to_mutate`; otherwise every
    mutant is unkillable (the livespec-mutreal.1 Layer-B finding). Flat-layout
    repos (livespec-dev-tooling, livespec-runtime) omit the key, so the check
    runs mutmut from the repo root unchanged.

    Returns `None` when the whole block is absent OR the key is omitted, so
    `check_mutation` defaults the staging cwd to the repo root (flat-layout
    behavior is byte-identical). Raises `ConfigParseError` on a non-string
    value, consistent with the rest of the loader.

    Like `scenario_tiers` and `destructive_cli_allowlist`, this is
    intentionally NOT a `Config` role key: it is a single-check concern
    (`check_mutation`), so it is read directly off the table rather than
    threaded through the typed layout dataclass.
    """
    table = _read_table(repo_root=repo_root)
    if table is None or "mutation_staging_dir" not in table:
        return None
    return _as_path(value=table["mutation_staging_dir"], key="mutation_staging_dir")


def load_plan_lifecycle_anchor(*, repo_root: Path) -> bool | None:
    """Return the `plan_lifecycle_anchor` opt-in, or `None` if the key is absent.

    Reads `<repo_root>/pyproject.toml`'s `[tool.livespec_dev_tooling]` block,
    key `plan_lifecycle_anchor` — a single boolean the
    `plan_thread_anchor_declared` check reads to decide whether THIS repo uses
    the dev-tooling plan-thread convention where every active handoff declares
    a concrete `**Ledger anchor:**` line. Fleet siblings write plan-thread
    handoffs without that convention, so the check self-skips unless a
    consumer explicitly opts in with `plan_lifecycle_anchor = true`.

    Returns `None` when the whole block is absent OR the key is omitted, so the
    calling check no-ops for consumers that have not declared this convention.
    Raises `ConfigParseError` on a non-boolean value, consistent with the rest
    of the loader.

    Like `scenario_tiers`, `destructive_cli_allowlist`,
    `mutation_staging_dir`, and `file_lloc_hard_gate`, this is intentionally
    NOT a `Config` role key: it is a single-check concern
    (`plan_thread_anchor_declared`), so it is read directly off the table
    rather than threaded through the typed layout dataclass.
    """
    table = _read_table(repo_root=repo_root)
    if table is None or "plan_lifecycle_anchor" not in table:
        return None
    return _as_bool(value=table["plan_lifecycle_anchor"], key="plan_lifecycle_anchor")


def load_config(*, repo_root: Path) -> Config:
    """Read `<repo_root>/pyproject.toml`'s block and resolve the layout.

    No `[tool.livespec_dev_tooling]` block → a bare flat baseline with no
    declared keys. Block present → the same flat baseline with each declared
    key overridden and `declared_keys` preserving key presence. Raises
    `ConfigParseError` on malformed TOML or a schema-violating value.
    """
    table = _read_table(repo_root=repo_root)
    if table is None:
        return Config()
    baseline = Config()
    overrides: dict[str, Any] = {}
    for key in _PATH_TUPLE_ROLE_KEYS:
        if key in table:
            overrides[key] = _as_path_tuple(value=table[key], key=key)
    if "dataclasses_tree" in table:
        overrides["dataclasses_tree"] = _as_optional_path(
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
    if "neutral_hook_body_path" in table:
        neutral_hook_body_path = _as_optional_path(
            value=table["neutral_hook_body_path"], key="neutral_hook_body_path"
        )
        overrides["neutral_hook_body_path"] = (
            neutral_hook_body_path.as_posix() if neutral_hook_body_path is not None else None
        )
    return Config(
        declared_keys=frozenset(table),
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
        neutral_hook_body_path=overrides.get(
            "neutral_hook_body_path", baseline.neutral_hook_body_path
        ),
    )


# ---------------------------------------------------------------------------
# Git-derived first-party `.py` universe — fleet-check-coverage Phase-0
# foundation (epic `livespec-i5ebqd`, item `livespec-fa3eu5`). Pure
# addition: no existing check is rerouted through this choke point yet.
# ---------------------------------------------------------------------------

# Ecosystem-generic file-extension -> native comment prefix(es) registry
# `is_generated` uses to recognize the `@generated` sentinel in EACH
# ecosystem's own comment syntax — never hardcoded to Python's `#`. A
# prefix is matched at line start, so it may be a line-comment marker
# (`#`, `//`, `--`) OR a block-comment OPEN delimiter (`/*`, `<!--`);
# that lets a single-line block comment such as `/* @generated */` count.
# Only `.py` is exercised by any current fleet repo; the rest is
# future-proofing for the day a non-Python first-party tree needs the
# same sentinel.
_COMMENT_PREFIXES_BY_EXTENSION: dict[str, tuple[str, ...]] = {
    ".py": ("#",),
    ".sh": ("#",),
    ".yaml": ("#",),
    ".yml": ("#",),
    ".toml": ("#",),
    ".rs": ("//", "/*"),
    ".ts": ("//", "/*"),
    ".js": ("//", "/*"),
    ".go": ("//", "/*"),
    ".c": ("//", "/*"),
    ".h": ("//", "/*"),
    ".sql": ("--",),
    ".html": ("<!--",),
    ".md": ("<!--",),
}
_GENERATED_MARKER = "@generated"
_TEMPLATES_PREFIX = "templates/"
_CLAUDE_SKILLS_PREFIX = ".claude/skills/"


def is_generated(*, path: Path) -> bool:
    """True iff `path` carries the `@generated` sentinel in its native comment syntax.

    Per the fleet-check-coverage design's OQ1 resolution, a file counts
    as generated ONLY when the literal token `@generated` appears on a
    line that IS a comment in that file's own ecosystem — looked up by
    extension in `_COMMENT_PREFIXES_BY_EXTENSION` — never merely a
    directory name and never a per-repo glob list (which would recreate
    the fail-open allowlist this mechanism replaces). A line counts as a
    comment when its text, stripped of leading whitespace, starts with
    one of the extension's native prefixes — a line-comment marker (`#`,
    `//`, `--`) or a block-comment OPEN delimiter (`/*`, `<!--`), so a
    single-line block comment such as `/* @generated */` counts.
    `@generated` appearing on a non-comment line (e.g. inside a docstring,
    which does not start with `#`), or on a block-comment CONTINUATION
    line (` * @generated`, which starts with `*` not `/*`), does NOT
    count. An unrecognized extension is treated as not-generated.
    """
    prefixes = _COMMENT_PREFIXES_BY_EXTENSION.get(path.suffix)
    if prefixes is None:
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(prefixes) and _GENERATED_MARKER in stripped:
            return True
    return False


def filter_first_party_py(
    *,
    tracked_py: Iterable[Path],
    repo_root: Path,
    tests_tree_prefix: str,
    neutral_hook_body_path: str | None = None,
) -> tuple[Path, ...]:
    """Filter a tracked `.py` set down to its first-party subset (pure — no listing IO).

    Per the fleet-check-coverage design's recommended predicate: a
    `git ls-files`-tracked, repo-root-relative `.py` path is first-party
    unless it (a) has a `_vendor` path segment, (b) is under the
    configured test tree (`tests_tree_prefix`, prefix-matched exactly
    like `config.tests_tree_prefix` is used elsewhere in this module) or
    is named `conftest.py`, (c) is under `templates/` (copier payload
    livespec ships but does not govern), (d) is under `.claude/skills/`
    (host-only, LOCAL-ONLY agent-runtime skill infra — e.g. the overseer
    daemon — which livespec ships to no one and governs under its own
    thread, not the product/dev-tooling code rules). The exemption is
    deliberately narrowed to `.claude/skills/` and NOT all of `.claude/`:
    `.claude/hooks/**` holds first-party hook `.py` (e.g. the Driver-shipped
    footgun/no-shadow guards) that the fleet-check-coverage epic requires
    COVERED — a Driver repo's hooks are its entire first-party universe.
    A file is exempt if it (e) carries the `@generated` sentinel
    (`is_generated`). Finally (f), the exact path declared as
    `neutral_hook_body_path` is exempt: that file is INSTALLED FOREIGN
    CONTENT, byte-synced from the packaged canonical constant and
    forbidden to hand-edit (`no-shadow-ledger-body-identical` enforces
    the sync), so a universe-derived check demanding an edit to it (e.g.
    `check-all-declared` demanding `__all__`) would deadlock against the
    byte-identity rule; the identity check reads the configured path
    directly, not via this universe, so drift detection is unaffected.
    This function does no subprocess/listing
    IO of its own — `tracked_py` is assumed already obtained (e.g. from
    `git ls-files`) — though `is_generated` DOES read file contents, so
    `repo_root` is needed to resolve each candidate to an absolute path
    for that read. Returns the sorted survivors.
    """
    out: list[Path] = []
    for rel in tracked_py:
        if _VENDOR_MARKER in rel.parts:
            continue
        posix = rel.as_posix()
        if posix.startswith(tests_tree_prefix) or rel.name == "conftest.py":
            continue
        if posix.startswith(_TEMPLATES_PREFIX):
            continue
        if posix.startswith(_CLAUDE_SKILLS_PREFIX):
            continue
        if neutral_hook_body_path is not None and posix == neutral_hook_body_path:
            continue
        if is_generated(path=repo_root / rel):
            continue
        out.append(rel)
    return tuple(sorted(out))


def iter_first_party_py_files(*, repo_root: Path) -> tuple[Path, ...]:
    """Return the first-party `.py` universe: `git ls-files '*.py'` minus exemptions.

    The git-index-derived choke point the fleet-check-coverage design
    introduces: shells `git ls-files '*.py'` in `repo_root` (an argv
    list, so the glob is passed literally with no shell expansion),
    loads the consumer's configured `tests_tree_prefix` via `load_config`
    (the single source of truth), and passes both through
    `filter_first_party_py`. Unlike `iter_py_files` (a filesystem
    `rglob` under a caller-supplied root), this walks the git INDEX —
    auto-excluding gitignored scratch (`.venv/`, `mutants/`,
    `__pycache__/`) and finding a non-`livespec`-named package directory
    with no per-repo config.

    Raises `GitLsFilesError` if the `git ls-files` subprocess exits
    non-zero (e.g. `repo_root` is not a git working tree). Returns an
    empty tuple for a repo with genuinely zero first-party `.py` (the
    verified fleet case: livespec-console-beads-fabro) — that is a
    legitimate result, not an error; telling the two cases apart is a
    later fail-closed guard's job, not this function's.
    """
    # S603/S607: argv is a fixed list of literal git args; no shell input.
    # Every GIT_* var is stripped from the child env: a parent process
    # (e.g. a git hook) can inject GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE,
    # which would override `cwd` and point the listing at the WRONG repo.
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    completed = subprocess.run(  # noqa: S603
        ["git", "ls-files", "*.py"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
        env=git_env,
    )
    if completed.returncode != 0:
        msg = f"git ls-files failed (exit {completed.returncode}): {completed.stderr.strip()}"
        raise GitLsFilesError(msg)
    tracked = tuple(Path(line) for line in completed.stdout.splitlines() if line)
    config = load_config(repo_root=repo_root)
    return filter_first_party_py(
        tracked_py=tracked,
        repo_root=repo_root,
        tests_tree_prefix=config.tests_tree_prefix,
        neutral_hook_body_path=config.neutral_hook_body_path,
    )


def has_first_party_py(*, repo_root: Path) -> bool:
    """True iff `repo_root` has at least one first-party `.py` file.

    A trivial derivation of `iter_first_party_py_files`. Exported as a
    standalone predicate a cross-check completeness meta-check (the
    fleet-check-coverage partition check) can consume; the applies-to-all
    checks themselves do NOT call it — they derive their whole universe
    from the single `resolve_check_universe` entry point.
    """
    return bool(iter_first_party_py_files(repo_root=repo_root))


# ---------------------------------------------------------------------------
# Applies-to-all check anchoring + delta-WARN helpers — fleet-check-coverage
# (epic `livespec-i5ebqd`). The shared surface the seven `source_trees`
# structural checks and `file_lloc` route through so every applies-to-all
# check derives its file universe from the SAME root-anchored git index and
# classifies each file legacy-vs-newly identically. `resolve_check_universe`
# is the single entry point: it OWNS root-resolution, so no check can pass a
# mis-anchored root. Root-anchoring plus the typed git errors
# (`GitToplevelError` / `GitLsFilesError`) are the fail-closed protection —
# a check cannot silently walk zero files from a wrong root or a git failure.
# ---------------------------------------------------------------------------


def resolve_repo_root() -> Path:
    """Return the absolute git working-tree root (`git rev-parse --show-toplevel`).

    The root-anchoring primitive every applies-to-all check resolves its
    `repo_root` from, replacing a bare `Path.cwd()`. Anchoring on the
    toplevel (not the invocation cwd) makes each check
    invocation-location-independent: `iter_first_party_py_files` shells
    `git ls-files` with `cwd=repo_root`, so a cwd inside a SUBDIRECTORY
    would otherwise list only that subdir's `.py` — a partial universe
    that silently exits 0.

    Every `GIT_*` env var is stripped from the child env exactly as
    `iter_first_party_py_files` does: a parent process (e.g. a git hook)
    can inject `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`, which would
    mis-point the resolution. Raises `GitToplevelError` on a non-zero
    exit (e.g. the cwd is not inside a git working tree) rather than
    returning a mis-anchored root.
    """
    # S603/S607: argv is a fixed list of literal git args; no shell input.
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        env=git_env,
    )
    if completed.returncode != 0:
        msg = (
            f"git rev-parse --show-toplevel failed (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
        raise GitToplevelError(msg)
    return Path(completed.stdout.strip())


def is_under_any_tree(*, rel: Path, trees: tuple[Path, ...]) -> bool:
    """True iff `rel` (a repo-root-relative path) sits under any tree in `trees`.

    The shared delta-WARN legacy classifier: a file under one of a
    check's legacy trees keeps today's hard severity; a file outside
    every legacy tree is newly-covered and emits at WARN. Promoted from
    `file_lloc`'s private `_under_legacy_hardfail_tree` so every
    applies-to-all check shares one implementation.
    """
    return any(rel.is_relative_to(tree) for tree in trees)


# The single definition of the `bin/*.py` shebang-wrapper set. A wrapper is
# a DIRECT-CHILD `*.py` under `.claude-plugin/scripts/bin/`, excluding
# `_bootstrap.py` (which carries real bootstrap logic, not the canonical
# 5-statement wrapper shape). `wrapper_shape` enforces that exact shape over
# this set — a shape that by construction carries NO `__all__` — and
# `all_declared` imports the SAME predicate to drop these launchers from its
# `__all__` universe (they are thin launchers with no public API to declare).
# Factored here beside `is_under_any_tree` so neither check hardcodes a
# second, independently-drifting `bin/*.py` glob. `BIN_WRAPPER_TREE` is
# exported so `wrapper_shape` scans exactly the tree the predicate matches.
BIN_WRAPPER_TREE = _p(".claude-plugin", "scripts", "bin")
_BIN_WRAPPER_EXEMPT_NAMES = frozenset({"_bootstrap.py"})


def is_bin_wrapper(*, rel: Path) -> bool:
    """True iff `rel` (a repo-root-relative path) is a `bin/*.py` shebang wrapper.

    The shared wrapper-identity both `wrapper_shape` and `all_declared`
    read as their single source of truth: `rel` is a wrapper when it is a
    DIRECT-CHILD `.py` file of `BIN_WRAPPER_TREE`
    (`.claude-plugin/scripts/bin/`) and is not one of
    `_BIN_WRAPPER_EXEMPT_NAMES` (`_bootstrap.py`). A file nested deeper than
    a direct child, a non-`.py` file, a file outside the tree, and the
    exempt `_bootstrap.py` are all NOT wrappers — mirroring `wrapper_shape`'s
    non-recursive `bin/*.py` glob minus its `_bootstrap.py` exemption.
    """
    return (
        rel.parent == BIN_WRAPPER_TREE
        and rel.suffix == ".py"
        and rel.name not in _BIN_WRAPPER_EXEMPT_NAMES
    )


def resolve_check_universe() -> tuple[Path, tuple[Path, ...]]:
    """Resolve the repo root and its first-party `.py` universe for a check.

    The single entry point every applies-to-all check (the seven
    `source_trees` checks and `file_lloc`) uses to obtain BOTH the
    root-anchored `repo_root` and its git-derived first-party universe. It
    OWNS root-resolution — resolving the git toplevel via
    `resolve_repo_root` (every `GIT_*` var stripped) rather than trusting a
    caller-supplied root — so a check cannot pass a wrong or subdirectory
    root and silently walk a partial universe. That ownership, together
    with the typed git errors, is the fail-closed protection: a
    non-git-tree cwd raises `GitToplevelError`, a `git ls-files` failure
    raises `GitLsFilesError`, and neither yields a spuriously-empty walk.

    Returns `(repo_root, universe)`. An empty `universe` means the repo is
    genuinely codeless (zero tracked first-party `.py`) — a legitimate
    result the caller passes on with an info-level "nothing to check".
    Because every applies-to-all check derives from THIS one entry point,
    there is no reachable per-check "empty-but-code-exists" divergence to
    guard at runtime; cross-check completeness is a separate meta-check's
    concern, not a same-function comparison here.
    """
    root = resolve_repo_root()
    return root, iter_first_party_py_files(repo_root=root)
