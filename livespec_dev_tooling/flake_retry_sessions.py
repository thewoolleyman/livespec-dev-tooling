"""Which pytest sessions of this process own the flake-retry plugin's state.

The plugin keeps its per-session state in module globals, and it is loaded into
every pytest session of the process. A session a test starts INSIDE a live one
(a consumer's own tests of its pytest configuration drive such sessions) would
clear and refill the OUTER session's withholding reason with the reason for its
own tmp directory, and the outer xdist worker would then forward that reason to
the controller: `FLAKE-RETRY-WITHHELD ... git fetch --deepen=1 origin ... exit
128` in 6 of 24 orchestrator coverage shards (livespec-dev-tooling-qawphe).

A session that starts while another is live in this process is therefore flagged
NESTED on its own config, and every plugin hook that reads or writes the state
returns first for it. The live list is the caller's, because the plugin's own
tests replace it.
"""

from __future__ import annotations

import pytest

__all__: list[str] = [
    "enter_session",
    "is_nested",
    "leave_session",
]

_NESTED_KEY = pytest.StashKey[bool]()


def is_nested(*, config: object) -> bool:
    """Report whether `config` belongs to a session started inside a live one."""
    stash = getattr(config, "stash", None)
    return isinstance(stash, pytest.Stash) and stash.get(_NESTED_KEY, False)


def enter_session(*, config: object, live: list[object]) -> None:
    """Record a starting session, flagging it nested when another is already live."""
    stash = getattr(config, "stash", None)
    if live and isinstance(stash, pytest.Stash):
        stash[_NESTED_KEY] = True
    live.append(config)


def leave_session(*, config: object, live: list[object]) -> None:
    """Forget a finished session."""
    if config in live:
        live.remove(config)
