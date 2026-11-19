"""The operator reproduction route: one diagnosed gate Job on a named lane.

livespec-dev-tooling-pkmxgu, the reproduction route for
livespec-dev-tooling-ddy5xu. An operator on a delegating host runs

    python -m livespec_dev_tooling.gate_repro --repo-root <checkout> \\
        --renderer <render-gate-job.sh>

and this submits ONE gate Job for that checkout's committed tree through the
normal gate client: the mirror push, a `kubectl create` of the rendered Job, the
admission and terminal waits, and the delete of a Job it stops waiting for. It
is never a hand `kubectl create`, which fleet_host_guard refuses.

Two things differ from a pre-push gate, and both are render flags:

- `--queue` puts the Job on the LocalQueue the operator names, `gates-repro-lq`
  by default: livespec-dev-tooling's
  `ci-runner/k3s/phase2/kueue/cluster-queue-repro-gates.yaml`, one gate unit on
  gamingpc-xubuntu, so a held gates-cq lane stays held for every other gate;
- `--repro-stack-interval` switches on the renderer's stack diagnostics, so the
  pod's log carries the process tree and each live Python process's latest stack
  every N seconds without a `kubectl exec`, which the gates credential lacks.

Two optional parameters name WHERE and WHAT it reproduces on (livespec-dev-tooling-cwrg3v):
`--image NAME@sha256:DIGEST` runs the Job in that exact ARC runner or factory
sandbox image instead of the repository's pin, and `--node <node>` pins it to
poweredge, gmktec, hp or gamingpc, through that node's flavor on the repro
queue. Both are render flags the renderer validates; nothing is pushed from
the pod, which holds no credential and mounts no ServiceAccount token.

AND ONE THING IS LEFT OUT ON PURPOSE: the green token. A pre-push gate that
passes writes one into the checkout, and a later push of that tree may spend it.
A reproduction is a measurement of a node, so this reports how the Job ended and
writes nothing into the checkout it gated. The host-authority half of a
pre-push gate is left out for the same reason: it decides a push, and nothing
here is pushed anywhere but the gates mirror.

The pre-push client is not changed at all: the repro flags reach the renderer
through `gate_remote_request`'s existing `resources` argv, appended after the
repository's own declared size.

`--renderer` is REQUIRED rather than resolved: the checkout under test is
usually another repository, whose own installed livespec-dev-tooling carries an
older packaged renderer than the one this route needs.
"""

from __future__ import annotations

import argparse
import base64
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling._gate_lane_capacity import repro_lane_refusal
from livespec_dev_tooling._gate_remote_assembly import declared_gate_job_resources
from livespec_dev_tooling.config import ConfigParseError, load_gate_job_resources
from livespec_dev_tooling.gate_credential import with_wrapper_notices
from livespec_dev_tooling.gate_remote_client import GateRunOutcome, run_gate
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandRunner,
    GateStepFailed,
    Sleeper,
    default_gate_command_runner,
    default_sleeper,
)
from livespec_dev_tooling.gate_remote_job_status import COMPLETE_CONDITION

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "REPRO_ENDED_COMPLETE",
    "REPRO_ENDED_FAILED",
    "REPRO_ENDED_NO_TERMINAL_CONDITION",
    "REPRO_QUEUE",
    "REPRO_STACK_INTERVAL_SECONDS",
    "ReproOutcome",
    "main",
    "repro_render_argv",
    "run_repro_gate",
]

REPRO_QUEUE = "gates-repro-lq"
# Five minutes: the pkmxgu Definition of Done's "at least once every five
# minutes", and long enough that an ordinary member never dumps at all.
REPRO_STACK_INTERVAL_SECONDS = 300

# The three ways a reproduction ends. The first two are the Job's own terminal
# condition: either one means the hang did NOT reproduce this run. The third is
# everything else, a step that could not be completed, including the client
# giving up on an admitted Job that reached no terminal condition within its
# poll budget; its detail names the step and the client's own reason.
REPRO_ENDED_COMPLETE = "complete"
REPRO_ENDED_FAILED = "failed"
REPRO_ENDED_NO_TERMINAL_CONDITION = "no-terminal-condition"
REPRO_ENDED_REFUSED = "refused"

_ENDED_BY_CONDITION = {COMPLETE_CONDITION: REPRO_ENDED_COMPLETE}
_EXIT_BY_ENDING = {
    REPRO_ENDED_COMPLETE: 0,
    REPRO_ENDED_NO_TERMINAL_CONDITION: 3,
    REPRO_ENDED_REFUSED: 4,
}
_EXIT_FAILED = 1


@dataclass(frozen=True, kw_only=True)
class ReproOutcome:
    """How one reproduction Job ended, the Job it was, and the reason given."""

    ended: str
    job_name: str
    detail: str


def repro_render_argv(
    *,
    queue: str,
    stack_interval_seconds: int,
    image: str | None = None,
    node: str | None = None,
    command: Sequence[str] = (),
) -> tuple[str, ...]:
    """The renderer flags that make a gate Job a reproduction Job.

    `--image` (a reference by digest) and `--node` (one gate node) are rendered
    only when the operator names them; the renderer refuses a tag or an unknown
    node, so this does not re-validate either (livespec-dev-tooling-cwrg3v).

    `command` is the words the operator gave after `--`. They are quoted into one
    shell line and base64-encoded into a single `--repro-command` flag, so no
    quoting has to survive the renderer, its placeholder substitution or the Job
    script; an empty command renders no flag and the Job runs the repository's
    whole gate (livespec-dev-tooling-z66x7t).
    """
    base = ("--queue", queue, "--repro-stack-interval", str(stack_interval_seconds))
    image_flags = ("--image", image) if image is not None else ()
    node_flags = ("--node", node) if node is not None else ()
    encoded = base64.b64encode(shlex.join(command).encode("utf-8")).decode("ascii")
    command_flags = ("--repro-command", encoded) if command else ()
    return (*base, *image_flags, *node_flags, *command_flags)


def _ended(*, outcome: GateRunOutcome) -> ReproOutcome:
    """A Job that reached a terminal condition, named by that condition."""
    return ReproOutcome(
        ended=_ENDED_BY_CONDITION.get(outcome.terminal_state, REPRO_ENDED_FAILED),
        job_name=outcome.job_name,
        detail=outcome.failure_message,
    )


def _unended(*, failure: GateStepFailed) -> ReproOutcome:
    """A run that reached no terminal condition, with the step and reason it stopped at."""
    return ReproOutcome(
        ended=REPRO_ENDED_NO_TERMINAL_CONDITION,
        job_name="",
        detail=f"{failure.step}: {failure.detail}",
    )


def _unadmittable(*, repo_root: Path, renderer: Path, node: str | None) -> str | None:
    """Why this repro could never be admitted by its node's committed flavor, or None.

    The repro queue is read from the tooling checkout the renderer belongs to
    (`<phase2>/kueue/`, a sibling of `<phase2>/gates/`). A declaration that
    cannot be read owes no comparison here; `gate_remote_request` refuses it.
    """
    try:
        declared = load_gate_job_resources(repo_root=repo_root)
    except ConfigParseError:
        return None
    return repro_lane_refusal(
        repo_root=repo_root,
        declared=declared,
        node=node,
        queue=renderer.parent.parent / "kueue" / "cluster-queue-repro-gates.yaml",
        renderer=renderer,
    )


def run_repro_gate(  # noqa: PLR0913 — every keyword is an independent input of the one reproduction Job.
    *,
    repo_root: Path,
    renderer: Path,
    queue: str,
    stack_interval_seconds: int,
    image: str | None = None,
    node: str | None = None,
    command: Sequence[str] = (),
    runner: GateCommandRunner = default_gate_command_runner,
    sleeper: Sleeper = default_sleeper,
) -> ReproOutcome:
    """Submit one reproduction Job for `repo_root`'s committed tree and report its ending."""
    runner = with_wrapper_notices(runner=runner)
    # `resources` is appended to the renderer argv verbatim IN PLACE OF the
    # repository's declared size, so it carries that declared size unchanged
    # and then the two reproduction flags: the Job is sized exactly as the
    # repository's own gate is. An unreadable declaration contributes nothing
    # here, and `gate_remote_request` refuses it on its own read.
    declared = declared_gate_job_resources(repo_root=repo_root).value_or(())
    refusal = _unadmittable(repo_root=repo_root, renderer=renderer, node=node)
    if refusal is not None:
        return ReproOutcome(ended=REPRO_ENDED_REFUSED, job_name="", detail=refusal)
    built = gate_remote_request(
        repo_root=repo_root,
        renderer=renderer,
        runner=runner,
        resources=(
            *declared,
            *repro_render_argv(
                queue=queue,
                stack_interval_seconds=stack_interval_seconds,
                image=image,
                node=node,
                command=command,
            ),
        ),
    )
    if isinstance(built, Failure):
        return _unended(failure=built.failure())
    ran = run_gate(request=built.unwrap(), runner=runner, sleeper=sleeper)
    if isinstance(ran, Failure):
        return _unended(failure=ran.failure())
    return _ended(outcome=ran.unwrap())


def main(
    *,
    argv: Sequence[str] | None = None,
    runner: GateCommandRunner = default_gate_command_runner,
    sleeper: Sleeper = default_sleeper,
) -> int:
    """Run one reproduction and print its ending.

    Exit 0 when the Job reached Complete, 1 when it reached Failed, and 3 when it
    reached no terminal condition (the ending a hang produces).
    """
    parser = argparse.ArgumentParser(
        description="Submit one diagnosed reproduction gate Job and report how it ended.",
    )
    _ = parser.add_argument("--repo-root", type=Path, required=True)
    _ = parser.add_argument("--renderer", type=Path, required=True)
    _ = parser.add_argument("--queue", default=REPRO_QUEUE)
    _ = parser.add_argument("--stack-interval", type=int, default=REPRO_STACK_INTERVAL_SECONDS)
    _ = parser.add_argument("--image", default=None)
    _ = parser.add_argument("--node", default=None)
    _ = parser.add_argument("command", nargs="*")
    parsed = parser.parse_args(argv)
    outcome = run_repro_gate(
        repo_root=parsed.repo_root,
        renderer=parsed.renderer,
        queue=parsed.queue,
        stack_interval_seconds=parsed.stack_interval,
        image=parsed.image,
        node=parsed.node,
        command=parsed.command,
        runner=runner,
        sleeper=sleeper,
    )
    print(  # noqa: T201 — this line IS the CLI's answer; the recipe records it as the ending.
        f"gate-repro: ended={outcome.ended} job={outcome.job_name} detail={outcome.detail}",
        flush=True,
    )
    return _EXIT_BY_ENDING.get(outcome.ended, _EXIT_FAILED)


if __name__ == "__main__":
    raise SystemExit(main())
