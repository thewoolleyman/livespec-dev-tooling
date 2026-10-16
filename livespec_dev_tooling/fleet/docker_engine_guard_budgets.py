"""Every Docker engine install guard bound, read on the control node.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Dispatch table", "Deadline"
and "Arm and the dead-man". Governing design:
`docs/docker-engine-guard-design.md`, G1 and H6.

WHY A READER RATHER THAN A TABLE IN THE ROLE. Every guard operation runs
as its own transient oneshot unit whose `TimeoutStartSec` is that
operation's budget, and the role is what builds those units -- so
without this reader the role would carry a second copy of the budget
table in YAML. Both ways that copy goes wrong are SILENT. Too small and
systemd kills the operation mid-flight: a rollback killed before its
final postcondition check leaves a host nobody has verified, which is
the one state the rollback exists to rule out. Too large and the
dead-man can fire inside an operation that is still running. The
deadline is reported beside the budgets for the same reason: it is
derived from three of them plus a margin, and that arithmetic repeated
in YAML is the same restatement one layer up.

WHERE IT RUNS. On the CONTROL node, against the checkout the role
installs the guard from, so the numbers the units carry and the numbers
the guarded host's own code computes come from one file:

    python -m livespec_dev_tooling.fleet.docker_engine_guard_budgets \\
        --window-seconds <W>

It reads the guard's model and nothing else -- no host, no state root,
no run -- so it is safe to call at any point in a converge, including
before a reservation exists.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    DEFAULT_WINDOW_SECONDS,
    OPERATIONS,
    deadline_seconds,
    operation_budget_seconds,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: list[str] = [
    "LOGGER_NAME",
    "budget_report",
    "main",
]

LOGGER_NAME: Final[str] = "docker-engine-guard-budgets"

_PROG: Final[str] = "docker-engine-guard-budgets"
_DESCRIPTION: Final[str] = "Report every Docker engine install guard bound, as JSON."


def budget_report(*, window_seconds: int) -> dict[str, object]:
    """Every operation's `TimeoutStartSec` and the dead-man deadline for a window.

    The window is carried in the answer rather than left implicit,
    because two of the numbers depend on it -- `observe`'s budget and
    the deadline -- and a report that did not say which window produced
    it could be read against the wrong one.
    """
    return {
        "window_seconds": window_seconds,
        "budgets": {
            operation: operation_budget_seconds(operation=operation, window_seconds=window_seconds)
            for operation in OPERATIONS
        },
        "deadman_deadline_seconds": deadline_seconds(window_seconds=window_seconds),
    }


def main(*, argv: Sequence[str]) -> int:
    """Print the report the role reads, for the window its preflight derived.

    The window DEFAULTS to the one a guard invoked without it assumes,
    so a role whose preflight has not derived a window yet reads a
    table consistent with the guard's own behaviour rather than nothing
    at all.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(prog=_PROG, description=_DESCRIPTION)
    _ = parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS)
    args = parser.parse_args(list(argv))
    report = budget_report(window_seconds=args.window_seconds)
    logging.getLogger(LOGGER_NAME).info(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))
