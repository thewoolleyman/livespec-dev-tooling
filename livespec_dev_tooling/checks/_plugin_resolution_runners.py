"""plugin_resolution live-runner implementations.

This module owns the harness-specific live-resolution seams for
`plugin_resolution`: Claude/Codex command-surface rendering, Codex delegation,
and Pi's non-interactive skill runner with explicit per-run trust approval.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from livespec_dev_tooling.testing.cli_e2e import CliRunner

__all__: list[str] = [
    "CliResolutionRunner",
    "DelegatedResolutionRunner",
    "PiProcessResult",
    "PiProcessRunner",
    "PiResolutionRunner",
    "ResolutionOutcome",
    "ResolutionRunner",
]


# Coverage child-process env vars scrubbed from the real `pi` subprocess so it
# does not self-instrument under `pytest --cov`, matching the Claude CLI runner
# boundary in `testing._cli_e2e_driver`.
_COVERAGE_PROCESS_START_VAR = "COVERAGE_PROCESS_START"
_COVERAGE_CHILD_VAR_PREFIX = "COV_CORE_"


@dataclass(frozen=True, kw_only=True)
class ResolutionOutcome:
    """Facts a resolution runner reports for one supported harness.

    `available` is whether the harness binary is present in this environment;
    `resolved` is whether the canonical command resolved AND returned exit 0
    through the command surface (never via a raw-CLI substitute).
    """

    available: bool
    resolved: bool


class ResolutionRunner(Protocol):
    """Injectable per-harness resolution seam.

    `resolve` issues a harness's canonical command through its command surface
    ONLY and reports the facts the decision logic consumes — it NEVER invokes a
    raw CLI. Tests inject deterministic fakes so no subprocess is spawned.
    """

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome: ...


def _command_surface_prompt(*, harness: str, canonical_command: str) -> str:
    """Render the canonical command as Claude/Codex command-surface text."""
    if harness == "codex":
        return canonical_command
    return "/" + canonical_command


@dataclass(frozen=True, kw_only=True)
class CliResolutionRunner:
    """Production `ResolutionRunner` backed by the cli_e2e `CliRunner` seam.

    Availability is `shutil.which(<harness>)`; the canonical command is issued
    as the harness's command-surface invocation through the injected
    `cli_runner`. This is the single place real-subprocess code can run (inside
    `CliRunner.run`); a test injects a fake `cli_runner` plus a stubbed
    `shutil.which`, so the runner is fully exercised without spawning.
    """

    cli_runner: CliRunner

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome:
        if shutil.which(harness) is None:
            return ResolutionOutcome(available=False, resolved=False)
        result = self.cli_runner.run(
            prompt=_command_surface_prompt(harness=harness, canonical_command=canonical_command),
            home=Path.home(),
            cwd=Path.cwd(),
            resume_session_id=None,
        )
        return ResolutionOutcome(available=True, resolved=result.exit_code == 0)


@dataclass(frozen=True, kw_only=True)
class DelegatedResolutionRunner:
    """A `ResolutionRunner` for a harness whose genuine live smoke is repo-local.

    Some harnesses' resolve-and-run proof lives in the harness's OWN repo — codex's
    is the repo-local `check-codex-skill-picker` PTY smoke — not this dev-tooling
    cross-harness live layer, whose `CliResolutionRunner` shells the `claude` binary.
    Routing such a harness here returns an unavailable outcome (→ SKIP) so the
    dev-tooling check NEVER mis-routes the canonical command through a DIFFERENT
    harness's binary (e.g. `claude -p "livespec:next"` for a codex command); the
    genuine live proof is the delegated repo-local check. `reason` is the
    human-readable delegation note for diagnostics.
    """

    reason: str

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome:
        _ = (harness, canonical_command)
        return ResolutionOutcome(available=False, resolved=False)


@dataclass(frozen=True, kw_only=True)
class PiProcessResult:
    """One non-interactive `pi` invocation's result."""

    exit_code: int
    stdout: str
    stderr: str


class PiProcessRunner(Protocol):
    """Injectable `pi -p` process seam."""

    def run(self, *, prompt: str, cwd: Path) -> PiProcessResult: ...


@dataclass(frozen=True, kw_only=True)
class RealPiProcessRunner:
    """Production process runner for unattended Pi skill resolution.

    The `--approve` flag is load-bearing: pi silently ignores project-local
    packages in non-interactive mode unless the project trust decision is
    pre-seeded or approved for the run.
    """

    pi_binary: str = "pi"

    def run(self, *, prompt: str, cwd: Path) -> PiProcessResult:
        env = {
            k: v
            for k, v in os.environ.items()
            if k != _COVERAGE_PROCESS_START_VAR and not k.startswith(_COVERAGE_CHILD_VAR_PREFIX)
        }
        completed = subprocess.run(
            [self.pi_binary, "--approve", "-p", prompt],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return PiProcessResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _pi_skill_command(*, canonical_command: str) -> str:
    """Render a canonical LiveSpec command as Pi's flat `/skill:` command."""
    if canonical_command.startswith("livespec:"):
        return "/skill:" + canonical_command.replace(":", "-", 1)
    if canonical_command.startswith("livespec-"):
        return "/skill:" + canonical_command
    return canonical_command


@dataclass(frozen=True, kw_only=True)
class PiResolutionRunner:
    """Production Pi live-resolution runner.

    Pi exposes LiveSpec operations as flat skills named `livespec-<operation>`.
    A `livespec:next` declaration is therefore driven as
    `/skill:livespec-next` through `pi --approve -p`, preserving the unattended
    project-trust contract while still skipping cleanly when `pi` is unavailable.
    """

    process_runner: PiProcessRunner = field(default_factory=RealPiProcessRunner)

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome:
        if shutil.which(harness) is None:
            return ResolutionOutcome(available=False, resolved=False)
        result = self.process_runner.run(
            prompt=_pi_skill_command(canonical_command=canonical_command),
            cwd=Path.cwd(),
        )
        return ResolutionOutcome(available=True, resolved=result.exit_code == 0)
