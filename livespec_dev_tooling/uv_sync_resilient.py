"""uv_sync_resilient — the dependency-install step, self-healing at its source.

## What this replaces, and why a retry knob was not the answer

The fleet's `Install Python dev deps via uv` step fails transiently often
enough to leave MASTER branches red, and until now the only remedy was a human
noticing and re-running by hand (`livespec-dev-tooling-el7g`). That is the
"easiest fix" the agent instructions forbid for a recurring failure mode: a
NORMAL, RECURRING failure mode must be handled AUTOMATICALLY AT ITS SOURCE.

TWO DISTINCT MECHANISMS are recorded, across five repositories, and telling
them apart is what selected this remedy over the alternatives:

1. A PyPI package download that times out —
   ``Failed to download `<pkg>` / Request failed after 5 retries / operation
   timed out``. Five distinct packages were recorded with an identical shape,
   so the cause is the download PATH, not any one index entry.
2. A `git+https` fetch of the cross-repo pin that fails TLS trust —
   ``Git operation failed / failed to clone into: .../git-v0/db/... / server
   certificate verification failed. CAfile: none``.

Mechanism 2 is the one that decides the design. It exits IMMEDIATELY rather
than exhausting `UV_HTTP_RETRIES`, so raising that count — or raising
`UV_HTTP_TIMEOUT`, or capping `UV_CONCURRENT_DOWNLOADS`, both of which the
`self_hosted_uv_lane` check already enforces fleet-wide for mechanism 1 —
cannot reach it. Nor can a warm cache: the failure IS the attempt to populate
the cache. Every knob that bounds the network leaves mechanism 2 exactly where
it was, which is why the remedy is at the level of the STEP: a fresh `uv`
process, after a backoff, re-derives the trust store and re-opens the
connection that the previous process could not.

## Why this is not the forbidden retry-the-whole-job wrapper

The work item is explicit that no gate may be weakened, and that a wrapper
which "masks a genuine failure as a transient" is not an acceptable remedy.
Three properties keep this on the right side of that line:

* It wraps ONLY the dependency-install step. The check command that follows it
  is untouched, so a genuine check failure is never re-run and never masked.
* It re-attempts ONLY on a RECORDED signature. A failure that does not match
  propagates on the FIRST attempt carrying uv's own exit code. A resolution
  error, a lock that cannot be satisfied, a missing package — all fail
  immediately, exactly as before.
* A signature is a marker AND a corroborating transport symptom, never the
  marker alone. `Failed to download` on its own is NOT transient: uv prints it
  for a package that is genuinely absent from the index too. Requiring the
  corroborator is what stops the classifier from widening into "retry any
  install failure".

The attempt budget is bounded and small. A transient that survives three
attempts across roughly half a minute of backoff is reported as a failure with
uv's own exit code, because at that point it is no longer distinguishable from
a real outage and a red gate is the honest answer.

## The log is the record

Every attempt emits one structured event on stderr under `check_id`
`uv_sync_resilient`, carrying the classified `family`, the attempt number, and
uv's combined output. That is deliberate: the step healing itself silently
would trade one invisible failure mode for another, and the work item's
acceptance measure is a QUERY over run logs for install-step failures. The
`uv-sync-transient` event is the greppable marker that query counts, so a
transient that is being absorbed stays countable instead of disappearing.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. Diagnostics flow through the
vendored structlog (JSON to stderr), which is importable with no installed
dependencies — load-bearing, since this module runs BEFORE `uv sync` has
populated the environment.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CHECK_ID = "uv_sync_resilient"

# The step's actual work, unchanged. `--all-groups` matches the step this
# module replaces; the wrapper adds resilience, never a different install.
_COMMAND = ("uv", "sync", "--all-groups")

# Three attempts total, so a transient gets two re-attempts. Small on purpose:
# the point is to absorb a blip, not to outlast an outage.
_MAX_ATTEMPTS = 3

# One delay per re-attempt, so this tuple MUST carry `_MAX_ATTEMPTS - 1`
# entries. Lengthening rather than uniform: a CDN or trust-store blip clears in
# seconds, while a congested uplink benefits from the longer second wait.
_BACKOFF_SECONDS = (5.0, 20.0)


@dataclass(frozen=True, kw_only=True)
class _Signature:
    """One recorded transient mechanism.

    `marker` names the failure; `corroborators` are the transport symptoms that
    distinguish a transient from a genuine one carrying the same marker. BOTH
    must appear, which is the whole guard against masking a real failure.
    """

    family: str
    marker: str
    corroborators: tuple[str, ...]


_SIGNATURES = (
    _Signature(
        family="package-fetch-timeout",
        marker="Failed to download",
        corroborators=(
            "Request failed after",
            "operation timed out",
            "error sending request",
            "Broken pipe",
            "connection closed",
        ),
    ),
    _Signature(
        family="git-fetch-transport",
        marker="Git operation failed",
        corroborators=(
            "failed to clone into",
            "failed to fetch commit",
            "server certificate verification failed",
            "Could not resolve host",
            "unable to access",
        ),
    ),
)


def _classify(*, output: str) -> str | None:
    """Return the transient family `output` matches, or `None` when it is genuine."""
    for signature in _SIGNATURES:
        if signature.marker not in output:
            continue
        if any(symptom in output for symptom in signature.corroborators):
            return signature.family
    return None


def _run_uv_sync() -> tuple[int, str]:
    """Run the install command, returning its exit code and combined output."""
    completed = subprocess.run(
        list(_COMMAND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return (completed.returncode, completed.stdout)


def _configure_logging() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def main(
    *,
    run: Callable[[], tuple[int, str]] = _run_uv_sync,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    log = _configure_logging()
    attempt = 1
    while True:
        code, output = run()
        if code == 0:
            log.info(
                "dependency install succeeded",
                check_id=_CHECK_ID,
                attempt=attempt,
                output=output,
            )
            return 0
        family = _classify(output=output)
        if family is None:
            log.error(
                "dependency install failed on a genuine error; not re-attempting",
                check_id=_CHECK_ID,
                attempt=attempt,
                exit_code=code,
                output=output,
            )
            return code
        if attempt >= _MAX_ATTEMPTS:
            log.error(
                "uv-sync-transient exhausted its re-attempts",
                check_id=_CHECK_ID,
                family=family,
                attempts=attempt,
                exit_code=code,
                output=output,
            )
            return code
        delay = _BACKOFF_SECONDS[attempt - 1]
        log.warning(
            "uv-sync-transient absorbed; re-attempting the dependency install",
            check_id=_CHECK_ID,
            family=family,
            attempt=attempt,
            delay_seconds=delay,
            exit_code=code,
            output=output,
        )
        sleep(delay)
        attempt += 1


if __name__ == "__main__":
    raise SystemExit(main())
