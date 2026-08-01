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

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file. The module that broke the fleet's release fan-out for seven hours on
# 2026-07-30 was in exactly that state until it became a process entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._context import FleetContext
    from livespec_dev_tooling.fleet._read_failure import ReadFailure

__all__: list[str] = [
    "CredentialUnusable",
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
class CredentialUnusable:
    """The credential was probed and did not answer, and WHAT the probe learned.

    `reason` is the discriminator: `rejected` carries a CLASSIFIED cause off
    `ctx.read_failures`, `unclassified` is the probe failing with no cause
    recorded at all. They were the same `PreflightOutcome(usable=False)` before,
    separated only by a `cause is None` ternary that BOTH callers had to spell
    out, so "rejected for a reason we can name" and "rejected and we cannot say
    why" reached the operator as one shape.

    `attempts` rides on the failure because the callers log it there: how many
    times a credential was retried before the verdict is part of the verdict.
    """

    reason: Literal["rejected", "unclassified"]
    attempts: int
    cause: ReadFailure | None = None

    def as_log_fields(self) -> dict[str, object]:
        """Every field BOTH lanes log about an unusable credential, in ONE place.

        The two sites each carried `attempts=`, and `None if preflight.cause is
        None else preflight.cause.as_dict()` — a rule with two copies, which is
        the shape `livespec-i04f` is about, and the two lanes are REQUIRED to
        diagnose the same credential identically. `cause` is `None` here as a
        LOG value meaning "no classified cause"; `reason` already says that
        structurally, which is what the old shape could not.
        """
        return {
            "attempts": self.attempts,
            "reason": self.reason,
            "cause": None if self.cause is None else self.cause.as_dict(),
        }


def preflight_credential(
    *, ctx: FleetContext, sleep: Sleeper = time.sleep
) -> Result[int, CredentialUnusable]:
    """Probe the credential, retrying bounded times on a retryable cause.

    Returns the ATTEMPT COUNT that reached a usable credential, or WHY it never
    did. `Result` rather than `IOResult` because every effect here goes through
    an INJECTED SEAM — `ctx.api_object` and `sleep` are both parameters — the
    same direct-call-versus-injected-seam reading that keeps `fetch_manifest`
    on `Result` while `_origin_remote` is on `IOResult`.

    Reads the cause from `ctx.read_failures`, which is exactly what
    `livespec-dev-tooling-s22c5z` preserved it for: without a classified cause
    this could only retry blindly or not at all, and retrying a 404 is as wrong
    as not retrying a rate limit.

    ⛔ WHY THIS IS A CONVERSION AND NOT AN ACQUITTAL — `livespec-dev-tooling-8o8e.9`,
    triage §4b. The check convicts this function via ONE basis: the bare call
    to `sleep`, an INJECTED PARAMETER, which `_no_expected_failure_mode` cannot
    resolve and so treats as doubt. That looks like a false positive, because
    the same module rules that an injected seam is NOT a boundary — and
    acquitting it would have been a FALSE ACQUITTAL. The old
    `PreflightOutcome(usable=bool, cause=ReadFailure | None)` is a HAND-ROLLED
    failure track, and member 1's clause (e) only recognises `X | None` as the
    function's OWN return annotation, so it cannot see one nested a field deep
    in a returned dataclass. The conservative doubt was the only thing holding
    a genuine offender in scope.
    """
    attempt = 0
    # Every exit is a `return` from INSIDE the loop, deliberately. The previous
    # shape ended with a post-loop `ctx.read_failures[-1] if ... else None`
    # whose `None` arm was UNREACHABLE — exhausting the retries requires a
    # RETRYABLE cause, and a retryable cause is one `api_object` recorded — so
    # it was a defensive arm no test could reach and the 100% per-file bar
    # would have had to be bought with a monkeypatch. Folding the exhaustion
    # into the same return as the non-retryable one leaves five arms and all
    # five are reachable from a scripted `gh`.
    while True:
        before = len(ctx.read_failures)
        payload = ctx.api_object(path=_PROBE_PATH, operation="credential_probe")
        attempt += 1
        if payload is not None:
            return Success(attempt)
        # `api_object` records a cause on every FAILING call — but a 200 whose
        # body is a JSON `null` parses to `None` with nothing recorded, which
        # is neither a usable credential nor a rejection anyone can name. That
        # is the `unclassified` arm, and it is reachable without a stub.
        cause = ctx.read_failures[before] if len(ctx.read_failures) > before else None
        if cause is None:
            return Failure(CredentialUnusable(reason="unclassified", attempts=attempt))
        if cause.kind not in _RETRYABLE_KINDS or attempt >= _MAX_ATTEMPTS:
            return Failure(CredentialUnusable(reason="rejected", attempts=attempt, cause=cause))
        sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
