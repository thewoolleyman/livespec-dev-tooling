"""_cli_e2e_driver — the injectable `claude -p` runner seam.

Extracted verbatim from `cli_e2e` (the Driver component of the CLI
end-to-end harness contract). The one boundary the harness mocks is the
`claude -p` subprocess itself — the single non-deterministic,
API-key-requiring, network-touching step. This module carries the
`CliResult` return shape, the `CliRunner` injection protocol, and the
`RealCliRunner` production driver that shells out to the real `claude`
binary; `cli_e2e` re-exports all three so the public surface is
unchanged.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "CliResult",
    "CliRunner",
    "RealCliRunner",
]


# Coverage child-process env vars scrubbed from the real `claude` subprocess
# so it does not self-instrument under `pytest --cov` (the cmn-pairing
# belt-and-suspenders against the coverage-collision race; see
# `tests_no_subprocess_spawn`, work-item livespec-dev-tooling-4i5).
_COVERAGE_PROCESS_START_VAR = "COVERAGE_PROCESS_START"
_COVERAGE_CHILD_VAR_PREFIX = "COV_CORE_"


@dataclass(frozen=True, kw_only=True)
class CliResult:
    """One `claude -p` invocation's outcome — the driver's return shape.

    `session_id` is the resumable session identifier the CLI prints for the
    turn (consumed by `--resume <session-id>` on the next turn); it is `None`
    when the invocation did not produce one.
    """

    exit_code: int
    stdout: str
    stderr: str
    session_id: str | None = None


class CliRunner(Protocol):
    """The injectable driver seam — one `claude -p` slash-command invocation.

    `RealCliRunner` is the production implementation; a self-test (this
    library's own or a consumer's) injects a deterministic fake conforming to
    this protocol so the harness's discovery / coverage-gate / orchestration
    logic is exercised WITHOUT a real `claude` binary or API key.
    """

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        """Issue one `claude -p <prompt>` turn under `HOME=home`, `cwd=cwd`.

        When `resume_session_id` is not None the turn MUST continue the named
        session (`--resume <session-id>`); otherwise it starts a fresh session.
        """
        ...


@dataclass(frozen=True, kw_only=True)
class RealCliRunner:
    """Production driver — shells out to the real `claude` CLI binary.

    Selected when `LIVESPEC_E2E_HARNESS=real`; requires `ANTHROPIC_API_KEY`.
    The argv is a fixed list anchored on the `claude_binary` name (default
    `claude`, overridable for a self-test that points at a fake shim on PATH);
    the only variable element is the prompt text and the optional resume id.
    """

    claude_binary: str = "claude"

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        argv = [self.claude_binary, "-p", prompt]
        if resume_session_id is not None:
            argv = [self.claude_binary, "--resume", resume_session_id, "-p", prompt]
        # Scrub COVERAGE_PROCESS_START + COV_CORE_* so the spawned `claude`
        # child (a Python process) does NOT self-instrument under
        # `pytest --cov`: an instrumented child writes `.coverage.*` that
        # races concurrent coverage runs under the parallel dispatcher (the
        # 7us.6 flaky "No data to report" failure). `claude` is never a
        # coverage target, so dropping these is purely the belt-and-suspenders
        # pairing with cmn — see the `tests_no_subprocess_spawn` check (4i5).
        env = {
            k: v
            for k, v in os.environ.items()
            if k != _COVERAGE_PROCESS_START_VAR and not k.startswith(_COVERAGE_CHILD_VAR_PREFIX)
        }
        env["HOME"] = str(home)
        # S603: argv is a fixed list (binary name + literal flags + caller-
        # supplied prompt text); no shell, no untrusted argv[0]. The prompt is
        # passed as a single argv element, never interpolated into a shell.
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return CliResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            session_id=None,
        )
