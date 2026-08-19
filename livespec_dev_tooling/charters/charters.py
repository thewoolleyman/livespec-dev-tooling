"""Public charter detector API.

The module is intentionally outside `livespec_dev_tooling/checks/`: membership
of `checks/` is the canonical-check inventory, and these detectors are an
importable library surface rather than a fleet-wide mandatory check slug.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# `returns` is VENDORED, not installed, so this module puts `_vendor/` on the
# path ITSELF rather than relying on its importer having done so — a property
# of the callers, not of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.

from livespec_dev_tooling.charters._detectors import (  # noqa: E402
    bare_targets,
    bash_pipestatus_in_zsh_fleet,
    busy_test_matches_idle_pane,
    fixed_cap_marker_read,
    history_fed_capture,
    local_time_labelled_utc,
    regex_session_existence_test,
    supervisor_trusted_by_name,
    unguarded_marker_binding,
    unguarded_path_resolution,
    wrapper_less_ledger_read,
)
from livespec_dev_tooling.charters._document_rules import (  # noqa: E402
    adoptable_runtime_contract,
    unattended_charter_missing_perform_the_unblock,
)
from livespec_dev_tooling.charters._seed_rules import empty_prev_watcher_init  # noqa: E402

__all__: list[str] = [
    "CHARTER_GLOBS",
    "DETECTORS",
    "charters_in",
    "defects_in",
]

Detector = Callable[..., list[str]]


@dataclass(frozen=True, kw_only=True)
class CharterReadFailure:
    """A charter root the walk could not read."""

    path: str
    detail: str


CHARTER_GLOBS: tuple[str, ...] = (
    ".ai/supervisor-protocol.md",
    "plan/**/supervisor-handoff.md",
)

DETECTORS: tuple[tuple[str, Detector], ...] = (
    ("a-bare-tmux-target", bare_targets),
    ("b-unguarded-path-resolution", unguarded_path_resolution),
    ("c-history-fed-capture", history_fed_capture),
    ("d-empty-prev-watcher-init", empty_prev_watcher_init),
    ("e-supervisor-trusted-by-name", supervisor_trusted_by_name),
    ("f-regex-session-existence-test", regex_session_existence_test),
    ("g-bash-pipestatus-under-zsh", bash_pipestatus_in_zsh_fleet),
    ("h-wrapper-less-ledger-read", wrapper_less_ledger_read),
    ("i-fixed-cap-marker-read", fixed_cap_marker_read),
    ("j-unguarded-marker-binding", unguarded_marker_binding),
    ("k-local-time-labelled-utc", local_time_labelled_utc),
    ("l-busy-test-matches-idle-pane", busy_test_matches_idle_pane),
    ("m-adoptable-runtime-contract", adoptable_runtime_contract),
    (
        "n-unattended-charter-missing-perform-the-unblock",
        unattended_charter_missing_perform_the_unblock,
    ),
)


def defects_in(*, text: str) -> list[str]:
    """Every defect in one charter, as `<class>: <offending line>` strings."""
    results: list[tuple[str, list[str]]] = [
        ("a-bare-tmux-target", bare_targets(text=text)),
        ("b-unguarded-path-resolution", unguarded_path_resolution(text=text)),
        ("c-history-fed-capture", history_fed_capture(text=text)),
        ("d-empty-prev-watcher-init", empty_prev_watcher_init(text=text)),
        ("e-supervisor-trusted-by-name", supervisor_trusted_by_name(text=text)),
        ("f-regex-session-existence-test", regex_session_existence_test(text=text)),
        ("g-bash-pipestatus-under-zsh", bash_pipestatus_in_zsh_fleet(text=text)),
        ("h-wrapper-less-ledger-read", wrapper_less_ledger_read(text=text)),
        ("i-fixed-cap-marker-read", fixed_cap_marker_read(text=text)),
        ("j-unguarded-marker-binding", unguarded_marker_binding(text=text)),
        ("k-local-time-labelled-utc", local_time_labelled_utc(text=text)),
        ("l-busy-test-matches-idle-pane", busy_test_matches_idle_pane(text=text)),
        ("m-adoptable-runtime-contract", adoptable_runtime_contract(text=text)),
        (
            "n-unattended-charter-missing-perform-the-unblock",
            unattended_charter_missing_perform_the_unblock(text=text),
        ),
    ]
    return [f"{name}: {line}" for name, lines in results for line in lines]


def charters_in(*, root: Path) -> IOResult[list[Path], CharterReadFailure]:
    """Every charter path under `root` reached by the declared charter globs."""
    try:
        found: list[Path] = []
        for glob in CHARTER_GLOBS:
            found.extend(root.glob(glob))
    except OSError as err:
        return IOFailure(CharterReadFailure(path=str(root), detail=str(err)))

    return IOSuccess(
        sorted(
            found,
            key=lambda path: (
                len(path.relative_to(root).parts),
                path.relative_to(root).as_posix(),
            ),
        )
    )
