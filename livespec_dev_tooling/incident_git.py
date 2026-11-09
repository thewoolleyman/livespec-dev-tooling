"""The one Git entrance for the expedited-incident path.

Six private wrappers used to answer this: a 30 s text reader, a reader with no
timeout, a 15 s isolated-view runner, a 120 s port, a returncode reader with no
guard against a missing program, and a path probe that re-derived the common
directory. Each chose its own bound and its own failure shape, so one hung Git
process was a refusal in one entrance and a raw traceback in another.

Every incident Git call now rides `run_git`: one timeout, and one failure type
(`IncidentGitError`) whose message is the one reason a caller reports, whether
the process exited non-zero, outlived its ceiling, or could not start. What
legitimately differs between callers is a parameter: the environment (the
isolated object view scrubs `GIT_*`; the controller's ports pass a fixed
account), the stdin payload, and whether a non-zero exit is an answer
(`check=False`, as in an ancestry probe) rather than a failure.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

__all__: list[str] = ["INCIDENT_GIT_TIMEOUT_SECONDS", "IncidentGitError", "git_text", "run_git"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gwzviw
# A hang guard for one Git process, never a verdict. It is the longest bound any of
# the retired wrappers carried (the controller's reference-clone fetch), so no call
# that completed under its old bound is cut off by the shared one.
INCIDENT_GIT_TIMEOUT_SECONDS = 120


class IncidentGitError(Exception):
    """An incident Git call that did not produce an answer; `str(error)` is its one reason.

    Not a `SubprocessError` (the no-inheritance allowlist closes that base), so a caller
    that refuses on subprocess failures names this type beside them. `returncode` is
    None unless the process exited, and `cmd` / `stderr` let the inverse planner tell a
    patch conflict from an unavailable Git.
    """

    def __init__(
        self, *, reason: str, cmd: tuple[str, ...], returncode: int | None, stderr: bytes
    ) -> None:
        super().__init__(reason)
        self.returncode = returncode
        self.cmd = cmd
        self.stderr = stderr


def run_git(
    *,
    repo: Path,
    args: Sequence[str],
    env: Mapping[str, str] | None = None,
    data: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run `git <args>` in `repo` under the one timeout; raise `IncidentGitError` on failure.

    With `check=False` a non-zero exit is returned for the caller to read, because it
    is the answer (for example `merge-base --is-ancestor`). A timeout or a program
    that cannot start is never an answer and raises either way.
    """
    argv = ["git", *args]
    command = tuple(argv)
    name = args[0]
    try:
        done = subprocess.run(  # noqa: S603 — fixed git executable; argv is never shell evaluated.
            argv,
            cwd=repo,
            env=env,
            input=data,
            capture_output=True,
            timeout=INCIDENT_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise IncidentGitError(
            reason=f"incident git {name} exceeded its {INCIDENT_GIT_TIMEOUT_SECONDS} s ceiling",
            cmd=command,
            returncode=None,
            stderr=b"",
        ) from error
    except OSError as error:
        raise IncidentGitError(
            reason=f"incident git {name} could not run: {error}",
            cmd=command,
            returncode=None,
            stderr=b"",
        ) from error
    if check and done.returncode != 0:
        detail = done.stderr.decode(errors="replace").strip()
        raise IncidentGitError(
            reason=f"incident git {name} exited {done.returncode}"
            + (f": {detail}" if detail else ""),
            cmd=command,
            returncode=done.returncode,
            stderr=done.stderr,
        )
    return done


def git_text(*, repo: Path, args: Sequence[str]) -> str:
    """The stripped text a checked `git <args>` printed in `repo`."""
    return run_git(repo=repo, args=args).stdout.decode().strip()
