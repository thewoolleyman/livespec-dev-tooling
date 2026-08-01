"""Mirror-paired test for `livespec_dev_tooling/agent_hooks/_subagent_stop_guard_transcript.py`.

The private sibling module carries the transcript worktree-path
parsing extracted from `subagent_stop_guard.py` at the
fleet-check-coverage LLOC-reduction split. The parser's end-to-end
coverage lives in `test_subagent_stop_guard.py` (the created-path
chain is exercised outside-in through the hook's `_gather_worktrees`
tests); THIS file unit-tests the extracted parsers directly, pinning
the module boundary — the worktree-path regex and the public
`git worktree add`-command entry point.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling.agent_hooks._subagent_stop_guard_transcript import (
    _extract_worktree_paths,
    extract_created_worktree_paths,
)

__all__: list[str] = []


def test_extract_worktree_paths_matches_both_layouts_and_dedupes() -> None:
    text = (
        "cd /data/projects/x/worktrees/slug-1 && ls\n"
        '"/data/projects/y/.claude/worktrees/s2"\n'
        "again /data/projects/x/worktrees/slug-1/deeper/file.py\n"
        "no worktree mention here\n"
    )
    paths = _extract_worktree_paths(transcript_text=text)
    assert paths == [
        Path("/data/projects/x/worktrees/slug-1"),
        Path("/data/projects/y/.claude/worktrees/s2"),
    ]


def test_extract_worktree_paths_matches_new_root_through_branch_segment() -> None:
    # The fleet-wide worktree root is ~/.worktrees/<repo>/<branch> (a
    # leading-dot `.worktrees` dir with TWO path segments). The match
    # MUST capture through <branch> so the downstream `git -C <match>`
    # probes target the real worktree dir, not just ~/.worktrees/<repo>.
    text = (
        "cd /home/ubuntu/.worktrees/somerepo/some-branch && git status\n"
        "deeper /home/ubuntu/.worktrees/somerepo/some-branch/pkg/file.py\n"
        "no worktree mention here\n"
    )
    paths = _extract_worktree_paths(transcript_text=text)
    assert paths == [Path("/home/ubuntu/.worktrees/somerepo/some-branch")]


def test_extract_worktree_paths_empty_on_plain_text() -> None:
    assert _extract_worktree_paths(transcript_text="nothing relevant") == []


def test_extract_created_worktree_paths_from_git_worktree_add_command() -> None:
    """The public entry derives the created path from a `git worktree add -b` command."""
    text = (
        "mise exec -- git -C /data/projects/somerepo worktree add "
        "-b some-branch /home/ubuntu/.worktrees/somerepo/some-branch master\n"
        "unrelated line with no worktree add\n"
    )
    assert extract_created_worktree_paths(transcript_text=text) == [
        Path("/home/ubuntu/.worktrees/somerepo/some-branch")
    ]


def test_extract_created_worktree_paths_none_without_branch_flag() -> None:
    """A `git worktree add` with no `-b`/`-B` branch flag creates no tracked target."""
    text = "git worktree add /home/ubuntu/.worktrees/somerepo/some-branch\n"
    assert extract_created_worktree_paths(transcript_text=text) == []


_CREATED = Path("/home/ubuntu/.worktrees/somerepo/some-branch")
_ADD_COMMAND = f"git worktree add -b some-branch {_CREATED}"


def test_an_apostrophe_does_not_hide_the_created_worktree() -> None:
    """`livespec-dev-tooling-dno1` — a single apostrophe used to blind the guard.

    `shlex.split` raises `ValueError: No closing quotation` on ANY unbalanced
    quote, and the old fallback returned `[]`, discarding the whole segment.
    `subagent_stop_guard` reads an empty list as "this sub-agent created no
    worktree", so a worktree narrated in ordinary prose — which almost always
    contains an apostrophe — was left unreaped with the guard reporting
    nothing.

    The pair below IS the measurement: the two inputs differ only by the
    prefix, so the recovered path is credible exactly because the
    apostrophe-free control returns the same path.
    """
    control = extract_created_worktree_paths(transcript_text=_ADD_COMMAND)
    prosaic = extract_created_worktree_paths(transcript_text=f"it's done: {_ADD_COMMAND}")

    assert control == [_CREATED], f"the control must find the path; got {control!r}"
    assert prosaic == [_CREATED], f"an apostrophe must not hide a created worktree; got {prosaic!r}"


def test_an_apostrophe_does_not_hide_the_created_worktree_inside_jsonl() -> None:
    """The same, through the JSONL transcript shape the hook actually reads.

    The segment reaching `_tokenize` is a JSON string VALUE rather than the raw
    line, so this pins that the recovery survives the `json.loads` path as well
    as the raw-line one — the two arms `_transcript_line_segments` chooses
    between.
    """
    line = json.dumps({"type": "assistant", "text": f"it's done: {_ADD_COMMAND}"})

    assert extract_created_worktree_paths(transcript_text=line) == [_CREATED]


def test_a_quoted_target_containing_whitespace_is_still_refused() -> None:
    """The degraded fallback cannot MANUFACTURE a path, only recover a real one.

    A whitespace split loses quote grouping, so a target with a space in it
    tokenizes apart. `_worktree_add_target` validates its candidate against the
    worktree-path regex, which forbids whitespace inside a path, so the
    mis-split candidate is refused rather than reported — the same answer the
    discard-everything fallback gave, and the reason the degradation is safe.
    """
    text = "it's here: git worktree add -b b '/home/ubuntu/.worktrees/repo/two words'"

    assert extract_created_worktree_paths(transcript_text=text) == []
