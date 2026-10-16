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

Stdlib only, for the reason the model module records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardOutcome
from livespec_dev_tooling.fleet._docker_engine_guard_state import record_phase

if TYPE_CHECKING:
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


def observe(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Claim the run, then sample the host across the whole observation window.

    The claim comes FIRST, before any sample, and that order is the
    whole of H2's singleton rule in fact rather than in unit naming: an
    observer that sampled first would leave a window in which the run
    still reads `started`, which is the one phase a second `observe` is
    admitted from.
    """
    record_phase(paths=env.paths, run=run, phase="observing")
    window_end = env.host.monotonic() + env.window_seconds
    while env.host.monotonic() < window_end:
        _ = env.host.sample()
        env.host.sleep(seconds=SAMPLE_INTERVAL_SECONDS)
    return GuardOutcome(
        operation="observe",
        run=run,
        verdict=decision.verdict,
        reason="every sample of the observation window passed",
    )
