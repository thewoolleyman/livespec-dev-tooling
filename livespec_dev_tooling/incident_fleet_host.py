"""The host the incident fleet audit reads its serving evidence from.

Every location is fixed by this code or by the account database: where the fleet's
clones live, which account's plugin caches are read, and where the process table is.
None of them is taken from an environment variable, a working directory or an
argument, because each one decides which installed artifact counts as serving
evidence, and a caller who can move it can write the evidence.
"""

from __future__ import annotations

import os
import pwd
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandRunner, command_answer

__all__: list[str] = ["FLEET_OWNER", "HostProbe", "production_probe"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
FLEET_OWNER = "thewoolleyman"
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, kw_only=True)
class HostProbe:
    """Where the audit reads installed state, plus the one command seam it runs through."""

    clones_root: Path | None
    proc_root: Path
    home: Path
    run: CommandRunner


def _clones_root(*, run: CommandRunner) -> Path | None:
    answer = command_answer(
        outcome=run(
            args=[
                "git",
                "-C",
                str(_PACKAGE_ROOT),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ]
        )
    )
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    common = Path(answer.stdout.strip())
    return common.parent.parent if common.name == ".git" else None


def production_probe(*, run: CommandRunner) -> HostProbe:
    """The fleet's clones are siblings of this code's primary checkout."""
    return HostProbe(
        clones_root=_clones_root(run=run),
        proc_root=Path("/proc"),
        home=Path(pwd.getpwuid(os.getuid()).pw_dir),
        run=run,
    )
