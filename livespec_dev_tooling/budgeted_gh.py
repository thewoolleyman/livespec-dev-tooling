"""The ONE budgeted `gh` read boundary for this package's first-party code.

Every first-party GitHub read in `livespec_dev_tooling` goes through
`GithubBudgetedClient` rather than spawning `gh` at the call site, so the
conditional-read, pacing, backoff and reserved-floor policies that client
implements apply uniformly rather than to whichever caller remembered to
ask (livespec core epic livespec-httc; retrofit livespec-dev-tooling-z69s).

The client is VENDORED from livespec-runtime under `_vendor/`, the same
source-copy pattern `returns`, `structlog` and `tomli` already use here,
rather than added as a runtime dependency: this package is installed into
every governed sibling repo, and a dependency edge onto a second
first-party distribution would have to be satisfied in all of them.
Direction is fine either way — livespec-dev-tooling is canonical upstream
and depending on a client livespec-runtime supplies is an ordinary
downstream dependency; what stays banned is this repo reading INTO a
downstream consumer.

⚠️ WHAT ROUTING BUYS HERE, AND WHAT IT DOES NOT. The policies are applied
by the client, but the two that read NUMBERS — the conditional-read cache
and the reserved floor — can only act on response headers the transport
actually surfaced, and `gh` surfaces them only under `GH_DEBUG=api` (on
stderr) or `--include` (on stdout). `_spawn_gh` sets NEITHER, and that is
deliberate: every caller here classifies `gh`'s stderr — the canonical
"Branch not protected" 404 marker, the `No commit found for SHA` marker,
the `HTTP 401` credential rejection, the `no pull requests found`
answer — and several of them log `stderr.strip()[:200]` as the operator's
hint. Turning on the debug stream would bury each of those hints under a
header dump. So these reads are UNMEASURED, exactly as livespec-runtime's
own `hygiene_scan_context` retrofit leaves its reads, and the floor
preflight — which issues the `--include` form against `/rate_limit` and
IS measurable — is the path that carries a floor when a caller declares
one. None of this package's five sites is a bulk or deferrable sequence,
so none declares one.

⚠️ THE CLIENT IS BUILT PER CALL, AND WITH `max_attempts=1`. Per call
because `cwd` and `timeout` are per call and the transport binds them at
construction; the cost is a cache that starts empty, which costs these
callers nothing, since each check process issues each read exactly once.
`max_attempts=1` because retry policy belongs to the caller: the
enforcement checks turn a read they could not take into a structured skip
or a named failure, and a backoff loop inside the transport would sleep
on a schedule none of them asked for.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

# `returns` and `livespec_runtime` are VENDORED, not installed; a bare
# import here would resolve only when some earlier import in the process
# happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_runtime.github_budget import (  # noqa: E402  — vendor-path-aware import.
    GhInvocation,
    GithubBudgetedClient,
    gh_invocation,
    gh_transport,
)
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GhRead",
    "gh_read",
]

# `gh` never ran — the binary is absent, the working directory is gone, or
# the call outlived its timeout. Reported as the shell's own
# command-not-found code so it cannot be confused with an exit code GitHub
# caused, and so every caller's existing `returncode != 0` branch — each
# one already the "this run did not see" path — keeps its meaning.
_UNSPAWNED_RETURNCODE = 127
# The budget client refused the read rather than issuing it: a rate limit
# it could measure, or a reserved floor a caller declared. Also a read
# that did not happen, and also non-zero for the same reason.
_UNANSWERED_RETURNCODE = 1


@dataclass(frozen=True, kw_only=True)
class GhRead:
    """What one budgeted `gh` read reported, in `CompletedProcess` vocabulary.

    Deliberately the shape the call sites already read — `returncode`,
    `stdout`, `stderr` — so routing a site through the budgeted client
    changes WHERE its bytes come from and nothing about how it classifies
    them. In particular a `gh` that RAN and answered "no" (a 404 on a
    branch nobody protected, a `no pull requests found`) stays an ANSWER
    on the ordinary track, carrying the exit code and the stderr its
    caller matches against.
    """

    returncode: int
    stdout: str
    stderr: str


def _spawn_gh(*, argv: list[str], cwd: Path | None, timeout: float | None) -> GhInvocation:
    """Spawn one `gh` argv, reporting what it printed or why it never ran.

    The two failure shapes the callers care about collapse into
    `unspawnable`, which is what `GhInvocation` records: a binary that is
    not there and a call that outlived its timeout are both "this run did
    not see", and neither is an exit code GitHub produced.
    """
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=None if cwd is None else str(cwd),
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as unusable:
        return GhInvocation(argv=shlex.join(argv), unspawnable=str(unusable))
    return GhInvocation(
        argv=shlex.join(argv),
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def gh_read(
    *,
    args: list[str],
    cwd: Path | None = None,
    timeout: float | None = None,
) -> GhRead:
    """One budgeted GitHub read, in the shape its callers already read.

    `args` is the `gh` ARGUMENT TAIL, excluding the leading `gh`: the
    transport builds the argv, so a call site names WHAT it wants to read
    and never HOW to invoke `gh`. It is shlex-joined into the client's
    `resource`, which doubles as the conditional-read cache key, and
    `gh_argv` inverts that join exactly — so the argv `gh` receives is the
    one the call site named, unchanged.
    """
    client = GithubBudgetedClient(
        transport=gh_transport(execute=partial(_spawn_gh, cwd=cwd, timeout=timeout)),
        max_attempts=1,
    )
    outcome = client.request(method="GET", resource=shlex.join(args))
    if isinstance(outcome, IOFailure):
        refused = unsafe_perform_io(outcome.failure())
        return GhRead(returncode=_UNANSWERED_RETURNCODE, stdout="", stderr=str(refused))
    invocation = gh_invocation(value=outcome.unwrap().value)
    if invocation.unspawnable is not None:
        return GhRead(returncode=_UNSPAWNED_RETURNCODE, stdout="", stderr=invocation.unspawnable)
    return GhRead(
        returncode=invocation.returncode,
        stdout=invocation.stdout,
        stderr=invocation.stderr,
    )
