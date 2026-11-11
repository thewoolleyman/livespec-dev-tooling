"""Read a failed gate pod's own account of why it stopped.

EVIDENCE, NEVER A VERDICT, which is why every unreadable shape answers the
empty string rather than a failure. The gate has already reported a real
terminal condition by the time this runs; a pod that has been collected, a
read the API server declines, or a container that wrote nothing must not be
able to turn that red verdict into a no-verdict — the push is refused either
way, and losing the explanation is strictly better than losing the verdict
that carries it.

The Job object does not carry either reading — only its pod does — so each is
a separate read, taken only when there is a failure to explain.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_dev_tooling.gate_remote_invocation import GateCommandRunner

__all__: list[str] = ["FailedPod", "read_failed_pod"]

# The failed pod's own last words. `containerStatuses` rather than
# `initContainerStatuses`: the aggregate container is the one whose refusal an
# operator has to act on, and the initContainer's own fatal paths already name
# themselves in the log.
_TERMINATION_MESSAGE_JSONPATH = "{.items[*].status.containerStatuses[*].state.terminated.message}"
# Why the failed pod stopped, in the kubelet's word rather than the container's:
# an evicted pod's own reason reads `Evicted`, and a container killed for
# memory reads `OOMKilled` as its terminated reason.
_STOP_REASONS_JSONPATH = (
    "{.items[*].status.reason} {.items[*].status.containerStatuses[*].state.terminated.reason}"
)
_RESOURCE_KILL_REASONS = frozenset({"OOMKilled", "Evicted"})


@dataclass(frozen=True, kw_only=True)
class FailedPod:
    """What a failed gate pod said about its own end.

    `message` is the termination message, verbatim. `resource_kill` is
    `OOMKilled` or `Evicted` when a resource kill ended the pod. Each is the
    empty string when the pod said nothing of the kind or could not be read.
    """

    message: str = ""
    resource_kill: str = ""


def read_failed_pod(
    *, kubectl: Sequence[str], runner: GateCommandRunner, cwd: Path, job_name: str
) -> FailedPod:
    """Read the failed pod's termination message and any resource kill that ended it."""
    read = partial(_read_pods, kubectl=kubectl, runner=runner, cwd=cwd, job_name=job_name)
    message = read(jsonpath=_TERMINATION_MESSAGE_JSONPATH)
    reasons = read(jsonpath=_STOP_REASONS_JSONPATH).split()
    kill = next((reason for reason in reasons if reason in _RESOURCE_KILL_REASONS), "")
    return FailedPod(message=message, resource_kill=kill)


def _read_pods(
    *,
    kubectl: Sequence[str],
    runner: GateCommandRunner,
    cwd: Path,
    job_name: str,
    jsonpath: str,
) -> str:
    """One jsonpath read over the Job's pods, or the empty string when it cannot be read."""
    argv = [
        *kubectl,
        "get",
        "pods",
        "--selector",
        f"job-name={job_name}",
        "--output",
        f"jsonpath={jsonpath}",
    ]
    read = runner(argv=argv, cwd=cwd)
    return read.map(lambda ran: ran.stdout.strip()).value_or("")
