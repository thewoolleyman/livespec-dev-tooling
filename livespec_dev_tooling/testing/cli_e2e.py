"""cli_e2e — the single canonical CLI-driven, user-surface end-to-end harness.

This module is the Phase 2 implementation of the `## CLI end-to-end harness
contract` in `livespec/SPECIFICATION/contracts.md`. It is the *top-of-pyramid*
tier of the fleet's end-to-end testing: a sibling to (not a superset of) the
wrapper-chain tier (`## E2E harness contract`), exercising the `claude` CLI
binary itself exactly as a real end user does. Both tiers coexist in CI.

The harness ships from `livespec-dev-tooling` and is consumed by every plugin
repo via the existing pin-bump dependency flow (contract requirement 6). Each
consumer wires the imported `test_workflow_full_round_trip` entry point into
its own pytest collection. The five components the contract enumerates split
across three cohesive modules:

1. **Driver** (`RealCliRunner`, `CliRunner`, `CliResult`) — in
   `_cli_e2e_driver`; every workflow step is a `claude -p` subprocess issuing
   a slash command. The harness never reaches around to wrapper Python files
   and never depends on cache layout (contract requirement 1).
2. **Structural skill discovery** (`discover_skills`) and **per-skill fixtures
   loader** (`discover_fixtures`, `FixturedSkill`) — in `_cli_e2e_discovery`;
   the plugin directory structure IS the source of truth (contract
   requirements 3, 4).
3. **Time-bomb coverage gate** (`assert_coverage`) and **step orchestrator**
   (`run_workflow`) — here; the gate fails closed on any un-fixtured,
   non-exempt skill (requirement 5), and the orchestrator drives each
   discovered skill's fixture through the injected runner (requirement 5).

The driver and discovery components are re-exported below so the public
surface (`__all__`) is unchanged for consumers importing from this module.
The impl-plugin id is a parameter (`HarnessConfig.impl_plugin_id`); the
spec-side skill set is fixed, the impl-side skill set is whatever the installed
impl plugin exposes (contract requirement 2).

## The injected runner seam — `LIVESPEC_E2E_HARNESS=mock|real`

The one boundary the harness mocks is the `claude -p` subprocess itself — the
single non-deterministic, API-key-requiring, network-touching step. Everything
else (discovery, fixture loading, the coverage gate, the orchestration loop)
runs for real. This mirrors the wrapper-chain tier, which "replaces ONLY the
payload-generation step that a real LLM would perform". The seam is the
`CliRunner` protocol: `RealCliRunner` shells out to the real `claude` binary;
a consumer's (or this library's own) self-test injects a deterministic fake.

`select_runner` reads the fleet-wide `LIVESPEC_E2E_HARNESS` selector — the
SAME env-var dialect the wrapper-chain tier uses, NOT a new one:

- `mock` (default) — the caller MUST supply an injected runner; `claude` is
  never invoked, so the tier runs in `just check` with no API cost and full
  determinism.
- `real` — `RealCliRunner` shells out to the real `claude` binary; requires
  `ANTHROPIC_API_KEY` and is NOT part of `just check`.

Output discipline mirrors the rest of the package: structured stderr via
structlog; no `print`, no direct `sys.stderr.write`.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware.

from livespec_dev_tooling.testing._cli_e2e_discovery import (  # noqa: E402
    FixturedSkill,
    discover_fixtures,
    discover_skills,
)
from livespec_dev_tooling.testing._cli_e2e_driver import (  # noqa: E402
    CliResult,
    CliRunner,
    RealCliRunner,
)

__all__: list[str] = [
    "CliResult",
    "CliRunner",
    "CoverageGateError",
    "FixturedSkill",
    "HarnessConfig",
    "HarnessSelectionError",
    "RealCliRunner",
    "StepResult",
    "WorkflowFailedError",
    "WorkflowResult",
    "assert_coverage",
    "discover_fixtures",
    "discover_skills",
    "run_workflow",
    "select_runner",
    "test_workflow_full_round_trip",
]


_HARNESS_SELECTOR_ENV = "LIVESPEC_E2E_HARNESS"
_HARNESS_MOCK = "mock"
_HARNESS_REAL = "real"

# Module-level message constant keeps the raise site terse (TRY003); `{mode}`
# is the resolved selector value.
_MOCK_TIER_NEEDS_RUNNER_MSG = (
    "LIVESPEC_E2E_HARNESS={mode!r} (mock tier) requires an injected CliRunner; "
    "none was supplied. Pass injected_runner=... or set LIVESPEC_E2E_HARNESS=real "
    "to drive the real claude binary."
)


class CoverageGateError(Exception):
    """The time-bomb coverage gate tripped: a discovered skill lacks a fixture.

    Raised (not asserted) so the gate fails the run fail-closed (contract
    requirement 5) without a bare `assert` in product code — pytest surfaces
    any raised exception as a test failure. The message — built in `__init__`
    so the raise site stays terse (TRY003) — enumerates the un-fixtured,
    non-exempt skills and the two remediations.
    """

    def __init__(self, *, missing_skills: list[str]) -> None:
        super().__init__(
            f"CLI e2e coverage gate: {len(missing_skills)} discovered skill(s) "
            f"lack a fixture and are not exempt: {missing_skills}. Add a fixture "
            f"directory under the fixtures root, or list each in EXEMPT_SKILLS "
            f"with a written justification."
        )
        self.missing_skills = missing_skills


class HarnessSelectionError(Exception):
    """The `mock` tier was selected with no injected runner — a wiring error.

    Carried on `select_runner`'s FAILURE track rather than raised. The message is
    built in `__init__` so the construction site stays terse (TRY003), matching
    the sibling error classes here.
    """

    def __init__(self, *, mode: str) -> None:
        super().__init__(_MOCK_TIER_NEEDS_RUNNER_MSG.format(mode=mode))
        self.mode = mode


class WorkflowFailedError(Exception):
    """A harness round-trip had one or more failing steps (fail-closed).

    Raised by the entry point so a failing step surfaces as an ordinary pytest
    failure without a bare `assert` in product code. The message is built in
    `__init__` to keep the raise site terse (TRY003).
    """

    def __init__(self, *, failed_skills: list[str]) -> None:
        super().__init__(f"CLI e2e workflow had failing step(s): {failed_skills}")
        self.failed_skills = failed_skills


@dataclass(frozen=True, kw_only=True)
class HarnessConfig:
    """Inputs to one harness run — the parameter object the contract requires.

    - `impl_plugin_id` — the impl plugin driven in lockstep with `livespec`
      (today `livespec-orchestrator-git-jsonl`); the contract's pluggable-impl
      parameter (requirement 2).
    - `marketplace` — the marketplace coordinates declared in the tmp
      `~/.claude/settings.json` (requirement 1).
    - `enabled_plugins` — the plugin ids enabled in that settings file (the
      spec-side `livespec` plugin plus `impl_plugin_id`).
    - `plugin_install_dirs` — the installed-location roots discovery walks for
      `skills/*/SKILL.md` + `plugin.json` (requirement 3).
    - `fixtures_root` — the `tests/e2e-cli/fixtures/` directory (requirement 4).
    - `exempt_skills` — the consumer's `EXEMPT_SKILLS` escape table for the
      coverage gate (requirement 5).
    - `install_command` — the optional first-step slash command that installs
      the plugin (`/plugin install …`); `None` means settings.json alone
      declares the install.
    """

    impl_plugin_id: str
    marketplace: str
    enabled_plugins: tuple[str, ...]
    plugin_install_dirs: tuple[Path, ...]
    fixtures_root: Path
    exempt_skills: frozenset[str] = frozenset()
    install_command: str | None = None


@dataclass(frozen=True, kw_only=True)
class StepResult:
    """The outcome of running one skill's fixture through the driver."""

    skill: str
    exit_code: int
    session_id: str | None
    missing_files: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and len(self.missing_files) == 0


@dataclass(frozen=True, kw_only=True)
class WorkflowResult:
    """The aggregate outcome of a full harness round-trip."""

    discovered_skills: tuple[str, ...]
    fixtured_skills: tuple[str, ...]
    steps: tuple[StepResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(step.passed for step in self.steps)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("cli_e2e")


def _flatten_discovered(*, discovered: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Flatten the per-plugin discovery map into a sorted, de-duplicated set."""
    names: set[str] = set()
    for skills in discovered.values():
        names.update(skills)
    return tuple(sorted(names))


def assert_coverage(
    *,
    discovered_skills: tuple[str, ...],
    fixtured_skills: frozenset[str],
    exempt_skills: frozenset[str],
) -> None:
    """Time-bomb coverage gate: fail closed unless every skill has a fixture.

    Raises `CoverageGateError` when `discovered - fixtured - exempt` is
    non-empty — a new skill added to either plugin trips the gate until either
    (a) a fixture directory is added, or (b) the skill is listed in the
    consumer's `EXEMPT_SKILLS` table with a written justification (contract
    requirement 5).
    """
    log = _configure_logger()
    missing = sorted(set(discovered_skills) - fixtured_skills - exempt_skills)
    if missing:
        log.error(
            "coverage gate tripped — discovered skills lack fixtures",
            missing_skills=missing,
        )
        raise CoverageGateError(missing_skills=missing)


def _write_settings(*, home: Path, config: HarnessConfig) -> None:
    """Pre-populate `<home>/.claude/settings.json` with marketplace + plugins.

    Declares the marketplace coordinates and the enabled plugin set so the
    `claude` binary resolves the fleet plugins on the first turn — the
    sole-entry-point setup the contract requires (requirement 1).
    """
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings = {
        "marketplaces": [config.marketplace],
        "enabledPlugins": list(config.enabled_plugins),
    }
    _ = (claude_dir / "settings.json").write_text(
        json.dumps(settings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _missing_expected_files(*, project_root: Path, expected: tuple[str, ...]) -> tuple[str, ...]:
    """Return the subset of `expected` paths that do NOT exist under the root."""
    return tuple(rel for rel in expected if not (project_root / rel).exists())


def run_workflow(
    *,
    config: HarnessConfig,
    runner: CliRunner,
    home: Path,
    project_root: Path,
) -> WorkflowResult:
    """Step orchestrator — the full discovery → gate → per-skill drive loop.

    1. Writes the tmp-`HOME` settings.json (and optionally runs the install
       slash command as the first `claude -p` turn).
    2. Discovers skills structurally and fixtures by directory convention.
    3. Asserts the time-bomb coverage gate (raises `CoverageGateError` on a
       gap — the harness fails closed BEFORE running any skill turn).
    4. Drives each fixtured skill through the injected runner, resuming the
       session across turns, and records exit codes + missing expected files.

    `home` and `project_root` are the tmp dirs the consumer's pytest fixture
    provides (`HOME` and the foreign project the slash commands run against).
    """
    _write_settings(home=home, config=config)
    session_id: str | None = None
    if config.install_command is not None:
        install = runner.run(
            prompt=config.install_command,
            home=home,
            cwd=project_root,
            resume_session_id=None,
        )
        session_id = install.session_id

    discovered_map = discover_skills(plugin_install_dirs=config.plugin_install_dirs)
    discovered = _flatten_discovered(discovered=discovered_map)
    fixtures = discover_fixtures(fixtures_root=config.fixtures_root)
    fixtured = tuple(sorted(fixtures))

    assert_coverage(
        discovered_skills=discovered,
        fixtured_skills=frozenset(fixtured),
        exempt_skills=config.exempt_skills,
    )

    steps: list[StepResult] = []
    for skill in discovered:
        if skill in config.exempt_skills:
            continue
        fixture = fixtures[skill]
        result = runner.run(
            prompt=fixture.prompt,
            home=home,
            cwd=project_root,
            resume_session_id=session_id,
        )
        session_id = result.session_id if result.session_id is not None else session_id
        missing = _missing_expected_files(
            project_root=project_root, expected=fixture.expected_files
        )
        steps.append(
            StepResult(
                skill=skill,
                exit_code=result.exit_code,
                session_id=result.session_id,
                missing_files=missing,
            )
        )

    return WorkflowResult(
        discovered_skills=discovered,
        fixtured_skills=fixtured,
        steps=tuple(steps),
    )


def select_runner(*, injected_runner: CliRunner | None) -> Result[CliRunner, HarnessSelectionError]:
    """Resolve the driver from the `LIVESPEC_E2E_HARNESS` fleet selector.

    - `real` → `RealCliRunner` (shells out to `claude`; needs ANTHROPIC_API_KEY;
      NOT in `just check`).
    - `mock` (default) → the caller-supplied `injected_runner` (deterministic;
      runs in `just check`). A `mock` selection with no injected runner is a
      configuration error and lands on the FAILURE track.

    On the railway rather than raising, per ratified livespec v179: clause (a)
    disqualifies any `raise` from the no-expected-failure-mode member, whichever
    flavour the raise is. The misconfiguration is a real outcome a caller can act
    on, so it flows as a value instead of being thrown.
    """
    mode = os.environ.get(_HARNESS_SELECTOR_ENV, _HARNESS_MOCK).strip().lower()
    if mode == _HARNESS_REAL:
        return Success(RealCliRunner())
    if injected_runner is None:
        return Failure(HarnessSelectionError(mode=mode))
    return Success(injected_runner)


def test_workflow_full_round_trip(
    *,
    config: HarnessConfig,
    home: Path,
    project_root: Path,
    injected_runner: CliRunner | None = None,
) -> WorkflowResult:
    """The importable pytest entry point consumers wire into their collection.

    A consumer imports this as
    `from livespec_dev_tooling.testing.cli_e2e import test_workflow_full_round_trip`
    and calls it from a thin per-repo test that supplies the `HarnessConfig`,
    a tmp `home`, a tmp `project_root`, and — for the `mock` tier — an injected
    deterministic runner. The runner is resolved via `select_runner`, the full
    workflow runs, and the aggregate `WorkflowResult` is asserted to pass.

    Returns the `WorkflowResult` so a caller can make further assertions; raises
    `CoverageGateError` (fail-closed) on a fixture gap and `AssertionError` on a
    failing step.
    """
    # `.unwrap()` re-raises on the failure track, preserving this entry point's
    # existing fail-closed contract: a wiring error still surfaces as a test
    # failure rather than a silently-skipped run.
    runner = select_runner(injected_runner=injected_runner).unwrap()
    result = run_workflow(
        config=config,
        runner=runner,
        home=home,
        project_root=project_root,
    )
    if not result.passed:
        raise WorkflowFailedError(
            failed_skills=[step.skill for step in result.steps if not step.passed]
        )
    return result
