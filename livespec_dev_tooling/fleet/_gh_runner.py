"""The `gh` subprocess seam for the fleet-membership contract.

Split out of `_context` to keep that file under the 250-LLOC hard
ceiling the railway conversion pushed it past, and coherent with
`_snapshot.py` already owning the DOWNLOADER seam separately.
`_context` re-exports every name here, so no consumer import changes.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# `returns` is VENDORED, not installed; a bare import here would resolve
# only when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._read_failure import classify_gh_failure  # noqa: E402

__all__: list[str] = [
    "GhOutcome",
    "GhResult",
    "GhRunner",
    "PacedGhRunner",
    "default_gh_runner",
    "gh_answer",
]


@dataclass(frozen=True, kw_only=True)
class GhResult:
    """Answer of one `gh` invocation that RAN (exit code + captured streams)."""

    returncode: int
    stdout: str
    stderr: str


# The railway alias for this seam, matching `_local_context.CommandOutcome`
# and `_snapshot.DownloadResult`. The three subprocess seams share ONE
# failure type, so they cannot drift about what "did not run" means.
GhOutcome = IOResult[GhResult, InvocationNotPerformed]


class GhRunner(Protocol):
    """Callable seam for `gh` invocations; `args` excludes the leading `gh`.

    The failure track carries ONLY "the invocation did not happen". A `gh`
    that RAN is a success carrying its exit code as data, however that code
    reads — the seam does not adjudicate what GitHub said, and GitHub says
    404 and 422 as ordinary answers.
    """

    def __call__(self, *, args: list[str], stdin: str | None = None) -> GhOutcome: ...


def gh_answer(*, outcome: GhOutcome) -> GhResult | InvocationNotPerformed:
    """The answer of a `gh` that RAN, or the record of one that did not.

    The `_local_context.command_answer` shape, for the same reason: every
    consumer needs exactly this split, and eleven inline `isinstance` +
    `unsafe_perform_io` pairs would be the duplication shape one layer up.
    """
    if isinstance(outcome, IOFailure):
        return unsafe_perform_io(outcome.failure())
    return unsafe_perform_io(outcome.unwrap())


# The kinds worth asking again about. `_credential_preflight` retries a wider
# set for the ONE-SHOT credential probe; this seam carries every member read, so
# it retries only the two that mean "ask again later". `forbidden` and
# `not_found` are ANSWERS — retrying them spends the very budget that is scarce.
_RETRYABLE_KINDS = frozenset({"rate_limited", "server_error"})
# ⛔ SIZED FROM A MEASUREMENT, NOT A GUESS. The first schedule totalled 14s and
# was NOT enough: on PR #1222's job 91851854289 a `repo_metadata` read was
# refused at 23:58:23Z and a `contents` read was STILL refused at 23:58:39Z —
# 16 seconds later, across a different operation. A bound shorter than the one
# persistence actually observed is knowably short. Growth is required rather
# than cosmetic: a tight loop re-trips the same secondary limiter.
_BACKOFF_SECONDS: tuple[float, ...] = (2.0, 5.0, 10.0, 20.0, 25.0)
_MAX_ATTEMPTS = 6

# The ONE kind that is a statement about the SEQUENCE rather than about a single
# request. A `server_error` is GitHub failing to answer one question; it earns a
# per-call retry but must NOT pause the sweep, because nothing about it says the
# next row would be refused.
_PACING_KIND = "rate_limited"

# ⛔ INVARIANT: >= the longest single backoff. The cooldown is armed before a
# sleep, so a longer backoff would outlive it and the next row would start
# unpaced at exactly the moment the limiter was most active. Derived rather than
# hand-set so a future schedule change cannot silently break it.
_THROTTLE_COOLDOWN_SECONDS = max(20.0, *_BACKOFF_SECONDS)


def _invoke_once(*, argv: tuple[str, ...], stdin: str | None) -> GhOutcome:
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            input=stdin,
        )
    except OSError as unspawnable:
        # Previously UNCAUGHT, so it propagated out of the seam and killed
        # the whole nine-member sweep partway through one member rather
        # than failing that member.
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=str(unspawnable))
        )
    return IOSuccess(
        GhResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    )


class PacedGhRunner:
    """A `GhRunner` that carries one sweep's throttle state across its calls.

    ⛔ WHY AN OBJECT AND NOT A MODULE-LEVEL COOLDOWN. `check-global-writes` bans
    `global`/`nonlocal` outright — "state flows down via parameters, up via
    return values, never through scoped mutation" — and hiding the same state in
    a module-level mutable container would satisfy the checker while breaking
    the rule it enforces. `GhRunner` is a Protocol over `__call__`, so an
    instance satisfies it and every `FleetContext(run_gh=...)` call site is
    unchanged.

    ⚠️ WHY CROSS-CALL STATE IS THE POINT. Per-call retry cannot fix the measured
    failure at ANY schedule length: `contents` was thrown at GitHub 16s after
    `repo_metadata` had already been refused, and was refused in turn, because
    nothing carried the first refusal forward. The limiter's subject is the
    SEQUENCE.
    """

    def __init__(self) -> None:
        self._throttle_lifted_at: float = 0.0

    def _arm_cooldown(self) -> None:
        self._throttle_lifted_at = time.monotonic() + _THROTTLE_COOLDOWN_SECONDS

    def _wait_out_active_cooldown(self) -> None:
        remaining = self._throttle_lifted_at - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    def __call__(self, *, args: list[str], stdin: str | None = None) -> GhOutcome:
        """Run `gh <args>`, pacing the sweep and retrying a retryable rejection."""
        argv = ("gh", *args)
        if shutil.which("gh") is None:
            return IOFailure(
                InvocationNotPerformed(argv=argv, kind=BINARY_ABSENT, detail="gh CLI not on PATH")
            )
        self._wait_out_active_cooldown()
        attempt = 0
        while True:
            outcome = _invoke_once(argv=argv, stdin=stdin)
            attempt += 1
            if isinstance(outcome, IOFailure):
                # "Did not happen" — there is nothing to wait for, and a spawn
                # failure will not fix itself in twenty seconds.
                return outcome
            result = unsafe_perform_io(outcome.unwrap())
            if result.returncode == 0:
                return outcome
            kind = classify_gh_failure(stderr=result.stderr)
            if kind not in _RETRYABLE_KINDS:
                return outcome
            # Armed BEFORE the budget check, deliberately: being rate-limited is
            # a fact about the sweep whether or not THIS call has attempts left.
            # Arming only on the retrying path would let the last refusal go
            # unrecorded, and the next row would start unpaced at exactly the
            # moment the limiter was most active.
            if kind == _PACING_KIND:
                self._arm_cooldown()
            if attempt >= _MAX_ATTEMPTS:
                return outcome
            time.sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])


# The seam every `FleetContext` injects. ONE instance per process, so the nine
# members of a sweep share the cooldown one of them discovers.
default_gh_runner = PacedGhRunner()
