"""The Red-Green-Replay protocol text emitted by every rejection branch.

Split out of `_red_green_replay_modes.py` so the leg handlers and the suite-green
helper can share it without an import cycle. Private sibling module.
"""

from __future__ import annotations

__all__: list[str] = ["RED_GREEN_REPLAY_PROTOCOL"]


# The full 2-step Red-Green-Replay protocol, emitted verbatim by EVERY
# rejection branch (here AND in the parent `red_green_replay.py`) so a
# developer or fresh agent recovers the correct authoring sequence from
# the hook output alone, without spelunking the check source
# (work-item li-rgr-docs-wi2). Each reject's mode-specific `hint` says
# what is locally wrong; this `protocol` field says what the correct
# full sequence is.
RED_GREEN_REPLAY_PROTOCOL: str = (
    "Red-Green-Replay protocol (single-commit TDD ritual). "
    "Step 1 — Red commit: stage the test file ALONE (no impl) and commit. The hook runs pytest "
    "on the staged tree; the new test MUST fail meaningfully (an assertion failure, NOT an "
    "ImportError / collection error). ANY subject prefix may author a Red — fix:/feat: declares "
    "the behavior change, and a behavior-changing chore Reds the same way. The hook records "
    "TDD-Red-* trailers (test path, failure reason, test-file checksum, output checksum, "
    "captured-at). "
    "Step 2 — Green amend: stage the impl and run `git commit --amend`. The hook sees the "
    "TDD-Red-* trailers + staged impl, re-runs the SAME test (now passing), and records "
    "TDD-Green-* trailers. The final SINGLE commit carries both files + both trailer sets. The "
    "test file bytes MUST be byte-identical across the Red->Green pair; to change the test, "
    "author a new Red commit. "
    "Behavior-PRESERVING product changes (no new failing test) instead take the green-verified "
    "leg: the FULL pytest suite must pass against the staged tree, and TDD-Suite-Green-* "
    "trailers are recorded as the evidence shape. "
    "RECONCILIATION WITH livespec's `.ai/ci-gate-discipline.md`, which this protocol does NOT "
    "override and is not overridden by: when master CI is red and local commits are themselves "
    "blocked by that red, that directive mandates creating the revert SERVER-SIDE, through the "
    "forge's own revert API, precisely because no local hook mediates it. This ritual is the "
    "local hook, so it cannot stamp such a commit and must not refuse it either — the commit-RANGE "
    "gate therefore exempts a revert that verifies against GitHub's pinned web-flow signing key "
    "AND is byte-identical to the reverted commit's parent at every product impl .py path it "
    "touches. That exemption is keyed on evidence an agent cannot fabricate, never on a subject "
    "line, and it is the ONLY one: adding a flag, a skip, or a severity knob to this protocol "
    "remains forbidden without exception (work-item livespec-dev-tooling-j2qa)."
)
