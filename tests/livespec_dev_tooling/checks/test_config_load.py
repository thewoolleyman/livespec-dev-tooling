"""Rendering tests for the shared config-load supervisor helpers.

`SPECIFICATION/contracts.md` section "Configuration loader" makes
`ConfigParseError` an IO-layer exception that each check's `main()`
supervisor catches and renders as a structured diagnostic. Measured on
master `dd98bbb0`, exactly ONE of the 33 `load_config` call sites under
`livespec_dev_tooling/checks/` did that — `required_role_keys_declared` —
and the other 32 let the error escape as an uncaught traceback.

That is not merely an unpolished failure mode. A raw traceback reaches
stderr through the interpreter rather than through structlog, so a check
whose whole job is enforcing this package's structlog-only output
discipline broke that discipline itself the moment a consumer's
`pyproject.toml` was malformed — the one moment its diagnostic matters.

These tests pin the RENDERING rather than the catch. Each drives a real
`main()` against a real malformed `pyproject.toml`, so the loader raises
for real and nothing is monkeypatched onto it, and then asserts the whole
supervisor contract: a NON-ZERO return AND one structured event carrying
`check_id`, `status="fail"` and a non-empty `error`. A test that asserted
only "no exception escaped" would pass against a silent `except: pass`,
which is the opposite of what the contract asks for.

The adopted modules are chosen to span the call SHAPES actually present:

- `claude_md_coverage` and `hook_trees_not_io_exempt` load the config
  DIRECTLY in `main()`;
- `check_mutation` loads it one frame DOWN, inside
  `_pure_trees_gate_exit_code`, a helper `main()` calls — so the error
  crosses a frame before anything can render it, and a `main()`-local
  `try` would have been the wrong generalization.

`required_role_keys_declared` is pinned too, deliberately UNMIGRATED. It
is the precedent the helper generalizes, and this pin is what makes
"generalizes" checkable rather than asserted: the migrated surfaces must
emit the same event with the same fields it already emits.

`_config_load` is imported through `importlib` INSIDE the test bodies
rather than at module top so that the Red leg of this change fails on a
genuine assertion — `is_file()` against a module that does not exist yet —
instead of dying at collection with a `ModuleNotFoundError`, which would
prove only unimportability.

SLICE 2 (`livespec-dev-tooling-efxa`) added the SECOND entry point and the
repo-wide scan at the bottom of this file. `resolve_check_context_or_report`
exists because a third call SHAPE turned out to be present and invisible: the
applies-to-all checks open `main()` with `resolve_check_universe()`, which
parses the consumer config ITSELF (`iter_first_party_py_files` needs
`tests_tree_prefix` to filter its git-derived walk), so for those sixteen
modules the `ConfigParseError` is raised an earlier frame up and a wrap of the
check's own `load_config` line would have rendered nothing while looking
migrated. The per-check behavioural proofs live in each check's own mirror
test file, because `check_coverage_incremental` gates every changed impl
module at 100% against its PAIRED test alone.
"""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import (
    check_mutation,
    claude_md_coverage,
    hook_trees_not_io_exempt,
    required_role_keys_declared,
)

_VENDOR_DIR = Path(claude_md_coverage.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_HELPER_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_config_load.py"
_HELPER_MODULE = "livespec_dev_tooling.checks._config_load"
_HELPER_MISSING = (
    "the shared config-load supervisor helper must live beside the other check "
    f"helpers at {_HELPER_PATH}"
)
# The one wording `required_role_keys_declared` already emits. Generalizing
# that module rather than inventing a second diagnostic shape is the whole
# point, so the string is pinned here rather than read off the new module.
_EVENT = "consumer config parse failed"
# `not [toml` is the same unparseable payload `test_config.py` and
# `test_required_role_keys_declared_edges.py` use, so every one of these
# tests exercises the REAL loader raising a REAL `ConfigParseError`.
_MALFORMED_PYPROJECT = "not [toml"
_RUN_MUTATION_ENV_VAR = "LIVESPEC_RUN_MUTATION"
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"
# The module that DEFINES the rendering is the one place a raw `load_config`
# call is expected to sit beside a `ConfigParseError` handler, so the scan
# below would convict it for doing its job.
_HELPER_FILENAME = "_config_load.py"
_TRACKED_MODULE_BODY = "from __future__ import annotations\n\n__all__: list[str] = []\n"


def _records(*, captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


def _rendered_the_diagnostic(*, captured: str, check_id: str) -> bool:
    """True iff stderr carries one structured parse-failure event for `check_id`."""
    return any(
        record.get("event") == _EVENT
        and record.get("check_id") == check_id
        and record.get("status") == "fail"
        and bool(record.get("error"))
        for record in _records(captured=captured)
    )


def _write_malformed_config(*, repo_root: Path) -> None:
    _ = (repo_root / "pyproject.toml").write_text(_MALFORMED_PYPROJECT, encoding="utf-8")


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so `tests_no_subprocess_spawn` permits it; the
    hardcoded env keeps `COVERAGE_PROCESS_START` out of this child.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _init_tracked_repo(*, repo_root: Path) -> None:
    """Make `repo_root` a git working tree with one tracked first-party module.

    `resolve_check_context_or_report` resolves the universe from the git index,
    so its callers need a real tree; the tracked `.py` keeps the universe
    non-empty, which is what the applies-to-all checks require before they look
    at any config at all.
    """
    package = repo_root / "pkg"
    package.mkdir()
    _ = (package / "mod.py").write_text(_TRACKED_MODULE_BODY, encoding="utf-8")
    _git(cwd=repo_root, args=["init", "-q"])
    _git(cwd=repo_root, args=["add", "-A"])


def _reaches_the_loader(*, tree: ast.Module) -> bool:
    """True iff the module can raise `ConfigParseError` from its own frames.

    TWO call names, because there are two ways to reach the loader and the
    second is INVISIBLE at the call site. `load_config` is the direct reach.
    `resolve_check_universe` is the TRANSITIVE one: it parses the consumer
    config itself, via `iter_first_party_py_files` needing `tests_tree_prefix`
    to filter its git-derived walk, so a module that never names `load_config`
    still raises `ConfigParseError` out of `main()`.

    Scanning only for the direct name is not a stricter-but-safe scan, it is a
    BLIND one, and it was measurably blind: the first sweep of
    `livespec-dev-tooling-efxa` used exactly that predicate and passed green
    while `file_lloc` and `no_fmt_directives` — which reach the loader only
    transitively — still emitted raw tracebacks. Both were confirmed by
    running their `main()` against a malformed `pyproject.toml` on 2026-09-08.
    That is the whole reason this predicate is spelled by REACHABILITY rather
    than by the loader's name.
    """
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"load_config", "resolve_check_universe"}
        for node in ast.walk(tree)
    )


def _handles_config_parse_error(*, tree: ast.Module) -> bool:
    """True iff the module renders the parse failure, by either sanctioned route.

    TWO kinds of evidence, because there are two legitimate shapes and a scan
    accepting only the first would convict a compliant module:

    - an inline `except ConfigParseError` — what `required_role_keys_declared`,
      the unmigrated precedent, does; and
    - importing a `_config_load` entry point — what every migrated supervisor
      does.

    The second admits `red_green_replay`, whose raw `load_config` sits in
    `_impl_prefixes_for_current_repo`, three frames below `main()` behind a
    `tuple[str, ...]` return with nowhere to carry an absent config. It renders
    through a PRE-FLIGHT `load_config_or_report` at the supervisor instead,
    which covers both arms that descend to that loader.

    The looseness this buys — a module could import the helper and never call
    it — is closed for every migrated module by the per-check rendering test in
    its own mirror file, which drives the real `main()` against a real
    malformed config. This scan is the tripwire for the module NOT yet written:
    the next check someone adds.
    """
    catches = any(
        isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "ConfigParseError"
        for node in ast.walk(tree)
    )
    adopts_helper = any(
        isinstance(node, ast.ImportFrom) and node.module == _HELPER_MODULE
        for node in ast.walk(tree)
    )
    return catches or adopts_helper


def _supervisor_logger(*, name: str) -> structlog.stdlib.BoundLogger:
    """Bind a JSON-to-stderr logger shaped exactly like a check supervisor's."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(name)


def test_shared_loader_lives_beside_the_other_check_helpers() -> None:
    """The single definition exists and is exported under the working name."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING

    module = importlib.import_module(_HELPER_MODULE)

    assert "load_config_or_report" in module.__all__


def test_shared_loader_returns_the_config_when_the_consumer_block_parses(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The happy path is a pass-through: the helper adds no behavior to a good load."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING
    module = importlib.import_module(_HELPER_MODULE)
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\n', encoding="utf-8"
    )

    config = module.load_config_or_report(
        repo_root=tmp_path,
        log=_supervisor_logger(name="probe"),
        check_id="probe",
    )

    _ = capsys.readouterr()
    assert config is not None
    assert config.source_trees == (Path("src"),)


def test_shared_loader_renders_the_parse_failure_and_returns_none(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed block yields the structured event and `None` — never a raise."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING
    module = importlib.import_module(_HELPER_MODULE)
    _write_malformed_config(repo_root=tmp_path)

    config = module.load_config_or_report(
        repo_root=tmp_path,
        log=_supervisor_logger(name="probe"),
        check_id="probe",
    )

    assert config is None, "the helper must never propagate `ConfigParseError`"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="probe")


def test_claude_md_coverage_main_renders_the_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 1 — `main()` loads the config directly."""
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = claude_md_coverage.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="claude_md_coverage")


def test_hook_trees_not_io_exempt_main_renders_the_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 1 again, in a check whose `main()` loads before anything else."""
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = hook_trees_not_io_exempt.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(
        captured=capsys.readouterr().err, check_id="hook_trees_not_io_exempt"
    )


def test_check_mutation_main_renders_the_parse_failure_from_one_frame_down(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 2 — the load happens inside `_pure_trees_gate_exit_code`, not in `main()`.

    The RUN lever is set because the gate sits behind it; without it `main()`
    logs "skipped" and exits 0 long before any config is read, and the test
    would pass against an unfixed tree for the wrong reason.
    """
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.setenv(_RUN_MUTATION_ENV_VAR, "true")
    monkeypatch.chdir(tmp_path)

    rc = check_mutation.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="check_mutation")


def test_required_role_keys_declared_still_renders_the_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The unmigrated precedent is unchanged — same event, same fields, same exit.

    This one passes before AND after the change on purpose. It is the control
    that makes the generalization checkable: if the shared helper had invented
    a second diagnostic shape, the migrated surfaces above would disagree with
    this one and the divergence would be visible in a single test file.
    """
    _ = (tmp_path / "justfile").write_text(
        "check:\n    targets=(\n        check-no-inheritance\n    )\n", encoding="utf-8"
    )
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = required_role_keys_declared.main()

    assert rc == 1
    assert _rendered_the_diagnostic(
        captured=capsys.readouterr().err, check_id="required_role_keys_declared"
    )


def test_check_context_resolver_returns_the_universe_and_config_when_the_block_parses(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The happy path hands back the root, the git-derived universe, and the config."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING
    module = importlib.import_module(_HELPER_MODULE)
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n', encoding="utf-8"
    )
    _init_tracked_repo(repo_root=tmp_path)

    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(tmp_path)
        resolved = module.resolve_check_context_or_report(
            log=_supervisor_logger(name="probe"), check_id="probe"
        )

    _ = capsys.readouterr()
    assert resolved is not None
    _root, universe, config = resolved
    assert Path("pkg/mod.py") in universe
    assert config.source_trees == (Path("pkg"),)


def test_check_context_resolver_renders_the_failure_raised_inside_the_universe_walk(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The parse failure raised one frame down, in the universe walk, still renders.

    This is the case a per-call-site wrap CANNOT reach: the config is parsed
    inside `resolve_check_universe` (via `iter_first_party_py_files`, which
    needs `tests_tree_prefix` to filter the git-derived walk), so the exception
    escapes before an applies-to-all check's own `load_config` line runs.
    """
    assert _HELPER_PATH.is_file(), _HELPER_MISSING
    module = importlib.import_module(_HELPER_MODULE)
    _write_malformed_config(repo_root=tmp_path)
    _init_tracked_repo(repo_root=tmp_path)

    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(tmp_path)
        resolved = module.resolve_check_context_or_report(
            log=_supervisor_logger(name="probe"), check_id="probe"
        )

    assert resolved is None, "the helper must never propagate `ConfigParseError`"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="probe")


def test_no_check_module_reaches_the_loader_without_handling_the_parse_error() -> None:
    """The repo-wide scan the adoption owes: no unhandled loader reach is left.

    Stated as a post-condition over the tree rather than over a migration
    table, so it also convicts a NEW check added later that reaches for the raw
    loader. `required_role_keys_declared` passes it by catching
    `ConfigParseError` inline — the precedent — and every migrated module
    passes it either by no longer reaching the loader unguarded at all or, for
    `red_green_replay`, by rendering at the supervisor above the frame that
    still does.

    REACHABILITY, not the loader's NAME, is the predicate — see
    `_reaches_the_loader`. The narrower name-only spelling is what let
    `file_lloc` and `no_fmt_directives` sit unmigrated behind a green scan.
    """
    trees = {
        path.name: ast.parse(path.read_text(encoding="utf-8"))
        for path in _CHECKS_DIR.glob("*.py")
        if path.name != _HELPER_FILENAME
    }

    unhandled = sorted(
        name
        for name, tree in trees.items()
        if _reaches_the_loader(tree=tree) and not _handles_config_parse_error(tree=tree)
    )

    assert unhandled == [], (
        f"these check modules reach the consumer-config loader without rendering "
        f"`ConfigParseError` and so escape a raw traceback: {unhandled}. Adopt "
        f"`_config_load.load_config_or_report` (direct `load_config` callers) or "
        f"`_config_load.resolve_check_context_or_report` (applies-to-all checks, "
        f"which reach it transitively through `resolve_check_universe`)"
    )
