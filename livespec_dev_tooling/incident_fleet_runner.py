"""The incident fleet audit's one subprocess seam: fixed binaries and a scrubbed environment.

Every git, gh and systemctl call the audit makes decides which installed artifact counts
as serving evidence, so the caller's environment must not steer any of them:

- The binary is resolved by name from a fixed directory list (`/usr/bin`, then `/bin`),
  never from `PATH`, so a `systemctl` or `git` planted earlier on `PATH` is never run.
- The child's environment is a fixed minimal set: `PATH` (those directories, for the
  helpers git itself starts), `HOME` from the account database, `LANG`, and git's
  isolation switches. Every variable the caller set (`GIT_DIR`, `GIT_CONFIG_*`,
  `GH_HOST`, `SYSTEMD_*` and the rest) is dropped.
- `GIT_CONFIG_NOSYSTEM=1` and `GIT_CONFIG_GLOBAL=/dev/null` keep the system and global
  git configuration out, so no `url.<base>.insteadOf` can redirect a read.
- A call that names no working directory runs in `/`, so a repository the caller happens
  to stand in never contributes its local configuration.

A call whose binary is not in those directories, or cannot be started, is a failure
value: the reader that asked treats it as unverified.
"""

from __future__ import annotations

import os
import pwd
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import (  # noqa: E402
    CommandOutcome,
    CommandResult,
    CommandRunner,
)

__all__: list[str] = [
    "BINARY_DIRECTORIES",
    "make_scrubbed_runner",
    "resolve_binary",
    "scrubbed_environment",
    "scrubbed_runner",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
BINARY_DIRECTORIES: tuple[Path, ...] = (Path("/usr/bin"), Path("/bin"))
_NEUTRAL_CWD = Path("/")


def resolve_binary(*, name: str, directories: Sequence[Path]) -> Path | None:
    """The first executable file called `name` in `directories`; a path-like name is refused."""
    if not name or "/" in name:
        return None
    return next(
        (
            candidate
            for candidate in (directory / name for directory in directories)
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )


def scrubbed_environment(*, directories: Sequence[Path], home: Path) -> dict[str, str]:
    """The whole environment a child gets: nothing the caller set survives."""
    return {
        "PATH": os.pathsep.join(str(directory) for directory in directories),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def make_scrubbed_runner(*, directories: Sequence[Path]) -> CommandRunner:
    """A `CommandRunner` that resolves binaries only in `directories` and scrubs the env."""

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        argv = tuple(args)
        binary = resolve_binary(name=argv[0] if argv else "", directories=directories)
        if binary is None:
            return IOFailure(
                InvocationNotPerformed(
                    argv=argv,
                    kind=BINARY_ABSENT,
                    detail=f"not an executable in {', '.join(map(str, directories))}",
                )
            )
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        try:
            # The binary is an absolute path resolved from fixed directories, never PATH.
            completed = subprocess.run(  # noqa: S603
                [str(binary), *argv[1:]],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cwd or _NEUTRAL_CWD),
                env=scrubbed_environment(directories=directories, home=home),
            )
        except OSError as unspawnable:
            return IOFailure(
                InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=str(unspawnable))
            )
        return IOSuccess(
            CommandResult(
                returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
            )
        )

    return run


scrubbed_runner: CommandRunner = make_scrubbed_runner(directories=BINARY_DIRECTORIES)
