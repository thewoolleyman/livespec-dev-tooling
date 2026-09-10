"""§"Test-Driven Development discipline" — the gates it names, at the stage it names.

The section is three bullets, and every one of them ends in a NAMED
enforcement surface rather than in an exhortation. What makes those names
load-bearing is that each gate can be removed from the surface it is named on
while every OTHER signal stays green:

- `red_green_replay` is named "at commit-msg time". It can only run there: the
  `TDD-Red-*` / `TDD-Green-*` trailers it reads and writes live in the COMMIT
  MESSAGE, which does not exist at pre-commit. And lefthook passes the message
  file positionally — `{1}` — so a wiring that drops the argument leaves the
  gate in its OTHER mode (the `origin/master..HEAD` range validator), which
  exits 0 on a branch whose commits already carry trailers. The gate would
  still run, still pass, and stop judging the pending commit entirely.
- `commit_pairs_source_and_test` is named "at pre-commit time", and the hook
  is the ONLY place it decides anything: its own docstring records that inside
  the `just check` aggregate it passes VACUOUSLY, because a clean tree stages
  nothing and `git diff --cached` is empty. Dropped from lefthook, the
  aggregate keeps reporting it green while the pairing goes unenforced.
- `per_file_coverage`'s 100% per-file gate is named "at `just check`", which
  is where its enforcement lives — a per-file floor is measured over a whole
  suite run, not over a staged diff.

So this file asserts the STAGE each gate is wired at, which is the part of the
section no single check can defend (a check cannot observe whether it was
invoked). That every shipped slug is also a `just check` target is asserted
once, for all of them, by `tests.spec.test_definition_of_done_gates`; the
Red→Green pair's own trailer semantics are covered by the unit suite at
`tests/livespec_dev_tooling/checks/test_red_green_replay*.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# The two lefthook stages the section names its gates at. The third gate it
# names, `per_file_coverage`, is a `just check` member rather than a hook —
# a per-file floor is measured over a suite run, not over a staged diff.
_COMMIT_MSG_STAGE = "commit-msg"
_PRE_COMMIT_STAGE = "pre-commit"

_RED_GREEN_RECIPE = "just check-red-green-replay"
_PAIRING_RECIPE = "just check-commit-pairs-source-and-test"

# lefthook's positional argument for the commit-message file. The commit-msg
# hook receives it as argv[1]; without it the gate judges a branch range
# instead of the pending commit.
_MESSAGE_FILE_ARG = "{1}"

_STAGE_BLOCK = re.compile(
    r"^(?P<stage>[a-z-]+):\n(?P<body>(?:[ \t].*\n|\n)*)",
    re.MULTILINE,
)


def _stage_bodies() -> dict[str, str]:
    """Each top-level lefthook stage mapped to its raw block text."""
    source = _LEFTHOOK.read_text(encoding="utf-8")
    return {
        matched.group("stage"): matched.group("body") for matched in _STAGE_BLOCK.finditer(source)
    }


def test_the_red_green_gate_is_wired_at_commit_msg_and_receives_the_message_file() -> None:
    """`red_green_replay` runs where the trailers exist, and is handed the message."""
    stages = _stage_bodies()
    assert _COMMIT_MSG_STAGE in stages, (
        f"the section enforces the Red -> Green pair at commit-msg time, so lefthook must "
        f"declare a `{_COMMIT_MSG_STAGE}` stage at all; stages={sorted(stages)}"
    )

    commit_msg = stages[_COMMIT_MSG_STAGE]
    assert _RED_GREEN_RECIPE in commit_msg, (
        f"`{_RED_GREEN_RECIPE}` must be a `{_COMMIT_MSG_STAGE}` command — it reads and "
        f"writes the `TDD-Red-*` / `TDD-Green-*` trailers, which live in the commit "
        f"message and do not exist at any earlier stage; body={commit_msg!r}"
    )

    invocation = next(line.strip() for line in commit_msg.splitlines() if _RED_GREEN_RECIPE in line)
    assert _MESSAGE_FILE_ARG in invocation, (
        f"the commit-msg wiring must pass lefthook's `{_MESSAGE_FILE_ARG}` message-file "
        f"argument: with it the gate judges the PENDING commit against the staged diff, "
        f"without it it silently falls back to validating `origin/master..HEAD` — which "
        f"passes on a branch whose landed commits already carry trailers, so the gate "
        f"stays green while judging nothing; invocation={invocation!r}"
    )

    pre_commit = stages[_PRE_COMMIT_STAGE]
    assert _RED_GREEN_RECIPE not in pre_commit, (
        f"`{_RED_GREEN_RECIPE}` must NOT be a `{_PRE_COMMIT_STAGE}` command: the message "
        f"it judges does not exist yet there, so the gate could only pass vacuously"
    )


def test_the_source_and_test_pairing_gate_is_wired_at_pre_commit() -> None:
    """`commit_pairs_source_and_test` runs at the one stage where it decides anything."""
    stages = _stage_bodies()
    pre_commit = stages[_PRE_COMMIT_STAGE]
    assert _PAIRING_RECIPE in pre_commit, (
        f"the section enforces the source/test pairing with `commit_pairs_source_and_test` "
        f"at pre-commit, and that hook is its ONLY deciding invocation — inside `just "
        f"check` it passes VACUOUSLY (a clean tree stages nothing, so its `git diff "
        f"--cached` universe is empty). Dropped from lefthook, the aggregate keeps "
        f"reporting the gate green while nothing enforces the pairing; body={pre_commit!r}"
    )
