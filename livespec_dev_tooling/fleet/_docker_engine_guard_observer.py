"""The Docker engine install guard's observer: claim the run, then watch the host.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Observe and the challenge"
(this repository). Governing design: `docs/docker-engine-guard-design.md`,
G4 and H2.

Reached only through `docker_engine_guard.run_operation`, so the lock is
held, the run is the current reservation, and the dispatch table has
already admitted the invocation from `started` with an unexpired
deadline. Nothing here re-decides admission.

WHAT IS AND IS NOT BEHIND THE `sample` SEAM. The observer decides the
SHAPE of the window -- when it claims the run, how often it samples,
what it does with a failure -- and nothing about what a sample looks at.
The probe set, the canary, and R8's rule that a failed probe is re-run
once and counts only if it fails twice all live behind `HostOps.sample`,
which answers one record per sample. So a sample that reaches this
module has already been retried: the observer treats the first failed
SAMPLE as the window's failure, exactly as the specification states it.

THE LOCK, AND WHERE THIS STOPS SHORT OF H2. H2 refines the observer to
hold the lock only BETWEEN samples, never across a Docker API request.
`run_operation` holds the guard's one lock for the whole handler and
offers no seam to release and retake it, so each between-sample phase
read here IS a lock-held read, and the window is covered by the lock
rather than punctuated by it. That is why the sampling seam is a single
bounded `HostOps.sample` call and not a long-lived API session: the
refinement that releases the lock between samples needs a seam in
`run_operation` that child 1a did not ship, and adding one is not this
child's to do.

Stdlib only, for the reason the model module records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardOutcome, rollback_argv
from livespec_dev_tooling.fleet._docker_engine_guard_records import (
    Challenge,
    Evidence,
    fresh_nonce,
    owned_keys_digest,
    write_challenge,
    write_evidence,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import read_phase, record_phase

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "SAMPLE_INTERVAL_SECONDS",
    "observe",
]

# The specification's sampling interval: every sample over the window has
# to pass, and the window is derived from the host's own effective k3s
# resync periods, so this is the resolution at which a regression inside
# one resync period is still seen.
SAMPLE_INTERVAL_SECONDS: Final[int] = 15

# The one phase this window belongs to. Read back between samples rather
# than remembered, because a rollback records `rolling-back` before it
# does anything else, and from that moment nothing about this run may be
# carried forward.
_CLAIMED: Final[str] = "observing"

# The one key a sample's own record has to carry for the window to go on.
# Read fail-closed: anything that is not exactly `True` -- a `False`, a
# missing key, a truthy string -- is a failed sample.
_PASSED: Final[str] = "passed"


def _record_window(
    *,
    run: str,
    env: GuardEnv,
    window_start: float,
    samples: Sequence[Mapping[str, object]],
    failure: str,
) -> None:
    """Write this window's evidence record, pass or fail.

    The record carries the run, the boot it ran on, the configuration
    digest and the window's two ends as well as the samples, because a
    `confirm` arriving later has to be able to tell this window from one
    that ran on another boot or against another configuration.
    """
    write_evidence(
        paths=env.paths,
        run=run,
        evidence=Evidence(
            run=run,
            boot_id=env.host.boot_id(),
            digest=owned_keys_digest(paths=env.paths, run=run),
            window_start=window_start,
            window_end=env.host.monotonic(),
            samples=tuple(samples),
            passed=not failure,
            failure=failure,
        ),
    )


def _failed_sample(
    *,
    run: str,
    env: GuardEnv,
    window_start: float,
    samples: Sequence[Mapping[str, object]],
) -> GuardOutcome:
    """Record the failure, start the rollback as its own unit, and exit.

    The rollback cannot be called in process: this invocation holds the
    guard's one lock and the rollback entry takes that same lock. It is
    started as its own transient unit instead, and NOT waited for
    (design H2) -- the observer has nothing left to submit, so
    rollback's own stop of the observer unit is a no-op and neither
    waits on the other.
    """
    failure = f"sample {len(samples)} of the observation window failed: {dict(samples[-1])}"
    _record_window(run=run, env=env, window_start=window_start, samples=samples, failure=failure)
    env.host.systemd_run(argv=rollback_argv(run=run))
    return GuardOutcome(operation="observe", run=run, verdict="refuse", reason=failure)


def _passing_window(
    *,
    run: str,
    env: GuardEnv,
    window_start: float,
    samples: Sequence[Mapping[str, object]],
    decision: Decision,
) -> GuardOutcome:
    """Record the window, issue the challenge, and only then reach `observed`.

    The ORDER of the last two is load-bearing. `observed` is the one
    phase a `confirm` is admitted from, so reaching it before the
    challenge exists would admit a `confirm` with nothing to answer --
    and a `confirm` that found no challenge would refuse a run whose
    window had in fact passed.
    """
    _record_window(run=run, env=env, window_start=window_start, samples=samples, failure="")
    write_challenge(
        paths=env.paths,
        challenge=Challenge(
            run=run,
            boot_id=env.host.boot_id(),
            nonce=fresh_nonce(),
            issued_monotonic=env.host.monotonic(),
        ),
    )
    record_phase(paths=env.paths, run=run, phase="observed")
    return GuardOutcome(
        operation="observe",
        run=run,
        verdict=decision.verdict,
        reason="every sample of the observation window passed; the challenge is issued",
    )


def observe(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Claim the run, then sample the host across the whole observation window.

    The claim comes FIRST, before any sample, and that order is the
    whole of H2's singleton rule in fact rather than in unit naming: an
    observer that sampled first would leave a window in which the run
    still reads `started`, which is the one phase a second `observe` is
    admitted from.
    """
    record_phase(paths=env.paths, run=run, phase="observing")
    window_start = env.host.monotonic()
    window_end = window_start + env.window_seconds
    samples: list[Mapping[str, object]] = []
    while env.host.monotonic() < window_end:
        if read_phase(paths=env.paths, run=run) != _CLAIMED:
            return GuardOutcome(
                operation="observe",
                run=run,
                verdict="refuse",
                reason="the run is no longer observing, so this window is not its window",
            )
        samples.append(env.host.sample())
        if samples[-1].get(_PASSED) is not True:
            return _failed_sample(run=run, env=env, window_start=window_start, samples=samples)
        env.host.sleep(seconds=SAMPLE_INTERVAL_SECONDS)
    return _passing_window(
        run=run, env=env, window_start=window_start, samples=samples, decision=decision
    )
