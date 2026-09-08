"""Whether this run is a DELEGATED GATE, and what a credential-less check owes when it is.

R4.S6 (`livespec-dev-tooling-ul61`), plan livespec `k3s-on-gmktec-for-vps-usage`
(epic `livespec-sab5gn`), design in that plan's `research/003` section H, which
prescribes "a check that FAILS, rather than warns, when a target that needs a
credential runs without one inside a gate pod".

THE DEFECT THIS EXISTS TO CLOSE. `check-branch-protection-alignment` and
`check-master-ci-green` shell out to `gh api` and exit 0 with a structured
warning when `gh` carries no usable credential. That is CORRECT on a developer
laptop, where the alternative would be an unrunnable gate for every contributor
without a forge token. It is WRONG in the job that authorises a push: an
unauthenticated gate pod would report the tree green having skipped exactly the
two checks the pushing host runs authenticated. That breaks "move WHERE the gate
runs, not WHAT it runs" while appearing to honour it, and it fails toward a
FALSE GREEN, which is the direction that costs the most.

THE RULING IS NOT NEW HERE. `livespec_dev_tooling/fleet/_credential_preflight.py`
already states it for the fleet-conformance lane: "a check that cannot see must
not report a pass", and escalating a blind row to error is recorded there as a
deliberate anti-vacuous-green ruling. This module carries the same disposition to
the two `gh api` checks, for the one context that needs it.

WHY AN EXPLICIT SIGNAL RATHER THAN DETECTION. The context is declared by whoever
runs the gate, never inferred from the environment. Guessing — "am I in a
container?", "is CI set?", "does this look like Kubernetes?" — is what makes a
rule like this fire where it was not meant to, and a false FAIL on a
contributor's machine would be paid for by every push. A caller that wants the
strict disposition says so.

SCOPE. This module decides a DISPOSITION and nothing else. It reads no
credential, probes no service, and names no check. Which targets consult it is
each target's own business; `credential-reading-targets.md` in this directory
enumerates the ones that do and what each degrades to without a credential.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__: list[str] = [
    "GATE_CONTEXT_ENV",
    "credential_skip_is_failure",
    "in_gate_context",
]

# Set by the gate Job template (`ci-runner/k3s/phase2/gates/gate-job-template.yaml`)
# and by nothing else in this repository. An operator reproducing a gate run by
# hand sets it deliberately, which is the point: the strict disposition is opted
# into, never stumbled into.
GATE_CONTEXT_ENV = "LIVESPEC_GATE_CONTEXT"


def in_gate_context(*, env: Mapping[str, str]) -> bool:
    """True when this run is a delegated gate that authorises a push.

    The environment is INJECTED rather than read from the process, so a test can
    never depend on the host's environment and a caller can never be surprised by
    a variable it did not consider. An empty value reads as unset, matching this
    repository's severity-lever idiom (see `no_todo_registry`).
    """
    return bool(env.get(GATE_CONTEXT_ENV, ""))


def credential_skip_is_failure(*, env: Mapping[str, str]) -> bool:
    """True when a check that could not read its credential must FAIL rather than skip.

    Named for the DECISION rather than for the context, so a caller reads the
    consequence at the call site instead of re-deriving it. Today the two
    coincide; keeping them separate means a future context that also demands the
    strict disposition does not have to be called a gate.
    """
    return in_gate_context(env=env)
