"""Git commit-message trailer I/O for `red_green_replay` — HEAD-state + trailer writer.

Extracted from `_red_green_replay_modes.py` so that module stays under
the file-LLOC ceiling (fleet-check-coverage). This sibling carries the
low-level git commit-message read/write surface the Red/Green/suite-green
handlers and the parent supervisor share: the HEAD-state resolver
(`head_red_awaiting_green`), the two HEAD readers (`head_trailer_value`,
`current_head_sha`), and the trailer writer (`write_trailers`).

`red_green_replay.py` imports `head_red_awaiting_green`;
`_red_green_replay_modes.py` imports the other three — both via the
`checks/` bare-sibling path after their own `sys.path` insert. The
leading underscore in the filename marks this a private helper rather
than a check entry point.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = [
    "current_head_sha",
    "head_red_awaiting_green",
    "head_trailer_value",
    "write_trailers",
]


def head_red_awaiting_green() -> bool:
    """Return True iff HEAD carries `TDD-Red-*` trailers WITHOUT `TDD-Green-*`.

    The genuine amend-in-progress signature (work-item
    livespec-dev-tooling-xn0): a COMPLETED Red+Green commit at HEAD
    also carries Red trailers — the normal state of real history —
    so keying Branch-4 routing on Red-trailer presence alone
    misrouted every fresh product commit atop a completed pair into
    the Green-amend leg, stamping bare `TDD-Green-*` trailers that
    the commit-range validator then rejected. Only a Red awaiting
    its Green may take the amend leg; everything else falls through
    to the suite-green leg.
    """
    result = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        capture_output=True,
        text=True,
        check=False,
    )
    message = result.stdout
    return "TDD-Red-Test-File-Checksum:" in message and "TDD-Green-Verified-At:" not in message


def head_trailer_value(*, key: str) -> str:
    """Return the value of HEAD~0's named trailer, or empty if absent."""
    result = subprocess.run(
        ["git", "log", "-1", f"--pretty=%(trailers:key={key},valueonly)"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def current_head_sha() -> str:
    """Return the current HEAD SHA via `git rev-parse HEAD`, or empty on failure."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def write_trailers(*, msg_path: Path, trailers: tuple[tuple[str, str], ...]) -> None:
    # Two-step write to handle the v034 D2-D3 Red re-amend case
    # (surfaced concretely 2026-05-04 during v039 D3 authoring):
    # three Red re-amends produced three sets of `TDD-Red-*`
    # trailers in the commit message, after which
    # `head_trailer_value` returned a newline-joined string of
    # three identical paths and the Green-mode handler raised
    # FileNotFoundError on Path.read_bytes().
    #
    # Step 1: pre-strip any line in the existing message whose
    # leading token matches one of the keys we're about to write.
    # We CANNOT use `git interpret-trailers --if-exists=replace`
    # here because git's `replace` matching uses prefix-aliasing
    # (treats `TDD-Red-Test` and `TDD-Red-Test-File-Checksum` as
    # the same trailer when one is a prefix of the other) and
    # silently DROPS the longer-keyed trailer when a shorter
    # prefix is present. The Red trailer schema has exactly
    # this collision (`TDD-Red-Test` is a strict prefix of
    # `TDD-Red-Test-File-Checksum` and `TDD-Red-Output-Checksum`'s
    # base form), so prefix-matching corrupts the trailer set
    # rather than fixing the duplicate-append bug.
    #
    # Step 2: invoke `git interpret-trailers --in-place` to add
    # the new trailers. Git's trailer-block-formatting rules
    # (blank-line separator between body and trailer block,
    # `Key: value` formatting, etc.) are preserved.
    keys_to_replace = {key for key, _ in trailers}
    original_text = msg_path.read_text(encoding="utf-8")
    stripped_lines: list[str] = []
    for line in original_text.splitlines(keepends=True):
        head = line.split(":", 1)[0]
        if head in keys_to_replace:
            continue
        stripped_lines.append(line)
    _ = msg_path.write_text("".join(stripped_lines), encoding="utf-8")

    args: list[str] = []
    for key, value in trailers:
        args.extend(["--trailer", f"{key}: {value}"])
    _ = subprocess.run(
        ["git", "interpret-trailers", "--in-place", *args, str(msg_path)],
        capture_output=True,
        text=True,
        check=False,
    )
