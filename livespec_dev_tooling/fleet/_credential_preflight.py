"""One deliberate credential probe before any obligation row is evaluated.

`livespec-dev-tooling-z4qi`: a transient App-token rejection made EVERY
conformance row blind at once, which escalated to error and reddened master on
a commit that changed nothing. Nine rows reading unrelated things — repo
topics, `.beads/config.yaml`, the master tree, installation repositories — all
went blind in the same run, so the common cause was one credential fault, not
nine independent ones.

The token was not missing. The failing run's log shows
`actions/create-github-app-token` completing and exporting it, and the reads
returned in ~a third of the passing re-run's time: the calls were being
REJECTED essentially immediately, not stalling. A GitHub App installation
token minted at T and used at T+11s can be rejected outright while the
identical flow minutes later works.

WHAT THIS CHANGES: the "cannot see" verdict is reached ONCE, on a cheap
authenticated probe, with bounded backoff on the retryable causes — instead of
as N downstream symptoms of a single miss.

WHAT THIS DOES NOT CHANGE, and must not: a genuinely unavailable credential
still FAILS. No obligation row is demoted to a warning and there is no skip
lever. Escalating a blind row to error is a deliberate anti-vacuous-green
ruling — a check that cannot see must not report a pass — and livespec
`.ai/ci-gate-discipline.md` forbids relaxing a merge-blocking gate to make a
repair land. The defect was that a transient rejection was INDISTINGUISHABLE
from a real blind spot, not that blind spots fail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._context import FleetContext
    from livespec_dev_tooling.fleet._read_failure import ReadFailure

__all__: list[str] = [
    "PreflightOutcome",
    "preflight_credential",
]

# `rate_limit` is authenticated, cheap, un-throttled, and touches no repository
# — so a rejection is unambiguously about the CREDENTIAL rather than about
# whether some particular repo or path exists.
_PROBE_PATH = "rate_limit"

# The causes worth a second attempt. `forbidden` is here because it is the
# OBSERVED shape of the z4qi failure — a freshly-minted token rejected outright
# — and excluding it would leave the actual defect unfixed. `not_found` is
# deliberately absent: it carries real information (the thing is absent), so
# retrying burns the budget on a question already answered.
_RETRYABLE_KINDS = frozenset({"forbidden", "rate_limited", "server_error", "transport"})

# Three attempts, ~2s then ~4s. Bounded so a real outage reaches its verdict
# promptly rather than spinning: the failure path costs at most ~6s, and the
# happy path costs one API call and no delay at all.
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS: tuple[float, ...] = (2.0, 4.0)


class Sleeper(Protocol):
    """Callable seam for the backoff delay; injected so tests never really sleep."""

    def __call__(self, seconds: float, /) -> None: ...


@dataclass(frozen=True, kw_only=True)
class PreflightOutcome:
    """Whether the credential answered, and the cause when it did not."""

    usable: bool
    cause: ReadFailure | None = None
    attempts: int = 1


def preflight_credential(*, ctx: FleetContext, sleep: Sleeper = time.sleep) -> PreflightOutcome:
    """Probe the credential, retrying bounded times on a retryable cause.

    Reads the cause from `ctx.read_failures`, which is exactly what
    `livespec-dev-tooling-s22c5z` preserved it for: without a classified cause
    this could only retry blindly or not at all, and retrying a 404 is as wrong
    as not retrying a rate limit.
    """
    attempt = 0
    while attempt < _MAX_ATTEMPTS:
        before = len(ctx.read_failures)
        payload = ctx.api_object(path=_PROBE_PATH, operation="credential_probe")
        attempt += 1
        if payload is not None:
            return PreflightOutcome(usable=True, attempts=attempt)
        # `api_object` appends exactly one cause per failed call.
        cause = ctx.read_failures[before] if len(ctx.read_failures) > before else None
        if cause is None or cause.kind not in _RETRYABLE_KINDS:
            return PreflightOutcome(usable=False, cause=cause, attempts=attempt)
        if attempt < _MAX_ATTEMPTS:
            sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
    last = ctx.read_failures[-1] if ctx.read_failures else None
    return PreflightOutcome(usable=False, cause=last, attempts=attempt)
