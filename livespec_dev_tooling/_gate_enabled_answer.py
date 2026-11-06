"""The `enabled` answer of the delegated pre-push gate: delegate, gate locally, or refuse.

`check-pre-push.sh` branches on this exit code and on nothing else: the delegated
pre-push gate's host-eligibility rule, and the developer-host rule that a
non-Linux host gates through the cluster or not at all. Three answers, and the
third is why this lives on its own:

- 0, delegate: this push gates on the cluster, possibly under the credential's
  owning group (`gate_group_repair`).
- 1, gate locally: the repository opted in but this LINUX host cannot read the
  gates kubeconfig, so the full local aggregate is the fall-through. It says so,
  because a locally-gated push and a cluster-gated one look identical afterwards.
- 78, refuse: the same, but on a non-Linux host (macOS). The Linux-only members of
  the suites cannot produce a verdict there, so the local aggregate is no fallback;
  the push is refused naming the missing gates-client enrollment.
"""

from __future__ import annotations

import platform

import structlog

from livespec_dev_tooling.gate_credential import gates_kubeconfig_path
from livespec_dev_tooling.gate_group_repair import GATE_RUNS_UNDER_GROUP, group_repair_group

__all__: list[str] = [
    "GATED_LOCALLY",
    "REFUSED_UNENROLLED_HOST",
    "UNENROLLED_NON_LINUX_HOST",
    "enabled_answer",
]

GATED_LOCALLY = (
    "delegated gate is switched on for this repository, but this host cannot read the "
    "gates kubeconfig, so this push is gating locally on the full just check aggregate"
)
UNENROLLED_NON_LINUX_HOST = (
    "delegated gate is switched on for this repository, and this non-Linux host is "
    "missing its gates-client enrollment: the pushing user cannot read the gates "
    "kubeconfig, and the local just check aggregate cannot produce a verdict here, "
    "so this push is refused rather than gated locally"
)
# The pre-push recipe's refusal status, distinct from the fall-through's 1.
REFUSED_UNENROLLED_HOST = 78


def enabled_answer(*, selected: bool, opted_in: bool, log: structlog.stdlib.BoundLogger) -> int:
    """The `enabled` exit code for a push whose selection and opt-in are already read."""
    if selected:
        return 0
    group = group_repair_group(opted_in=opted_in)
    if group is not None:
        log.warning(GATE_RUNS_UNDER_GROUP, group=group)
        return 0
    if opted_in and platform.system() != "Linux":
        log.error(
            UNENROLLED_NON_LINUX_HOST,
            platform=platform.system(),
            kubeconfig=str(gates_kubeconfig_path()),
        )
        return REFUSED_UNENROLLED_HOST
    if opted_in:
        log.warning(GATED_LOCALLY, kubeconfig=str(gates_kubeconfig_path()))
    return 1
