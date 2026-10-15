"""The Docker engine install guard's value model: phases, operations and budgets.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" (this repository). Governing design:
`docs/docker-engine-guard-design.md`, revisions 5 to 8.

STDLIB ONLY, and that is a product constraint rather than a preference.
`docker_engine_guard.py` and the siblings beside it are copied onto a
factory host as `/usr/local/libexec/docker-engine-guard` and run there by
`systemd-run` transient units against the host's own interpreter — no
virtual environment, no vendored tree, no third-party package. So the
railway this repository otherwise rides (`dry-python/returns`) is not
importable where this code actually executes, and the module carries its
own refusal value (`GuardOutcome`, added as the operations land) instead:
an expected refusal is RETURNED, never raised, exactly as the Result rails
require — only the carrier differs. The package floor is Python 3.10, so
nothing here uses newer syntax.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

__all__: list[str] = [
    "INSTALL_PHASES",
    "OPERATIONS",
    "PHASES",
    "ROLLBACK_PHASES",
    "Operation",
    "Phase",
    "operation_budget_seconds",
]

Phase = Literal[
    "reserved",
    "publishing",
    "published",
    "armed",
    "started",
    "observing",
    "observed",
    "committed",
    "confirmed",
    "rolling-back",
    "rolled-back",
    "rollback-partial",
]

Operation = Literal[
    "reserve",
    "publish",
    "arm",
    "start",
    "observe",
    "confirm",
    "rollback",
    "recover",
    "verify",
    "reconfigure",
]

# Derived from the `Literal`s rather than restated beside them: a second
# hand-written tuple is a second place the vocabulary can drift, and the
# dispatch table below indexes both by name.
PHASES: Final[tuple[Phase, ...]] = get_args(Phase)
OPERATIONS: Final[tuple[Operation, ...]] = get_args(Operation)

ROLLBACK_PHASES: Final[tuple[Phase, ...]] = ("rolling-back", "rolled-back", "rollback-partial")
INSTALL_PHASES: Final[tuple[Phase, ...]] = tuple(
    phase for phase in PHASES if phase not in ROLLBACK_PHASES
)

# `TimeoutStartSec` per operation (design H6). `observe` is the one entry
# that is not a flat number: its unit must outlive the whole observation
# window, so the window is added to the 300 s recorded here.
_BASE_BUDGET_SECONDS: Final[dict[Operation, int]] = {
    "reserve": 60,
    "publish": 1800,
    "arm": 60,
    "start": 180,
    "observe": 300,
    "confirm": 120,
    "rollback": 900,
    "recover": 1800,
    "verify": 120,
    "reconfigure": 120,
}


def operation_budget_seconds(*, operation: Operation, window_seconds: int) -> int:
    """The `TimeoutStartSec` the role gives this operation's transient unit.

    `window_seconds` is the observation window the preflight derives from
    the host's effective k3s resync periods; every operation but `observe`
    ignores it.
    """
    window = window_seconds if operation == "observe" else 0
    return _BASE_BUDGET_SECONDS[operation] + window
