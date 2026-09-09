"""Tests for `release_lane_issue` — the pure transition table over the one issue.

The four transitions are the whole contract, and the asymmetry between them is
the point: three of the four keep the signal VISIBLE and only one retires it.
So the CLOSE row is tested for what it requires (an empty notice list) as much
as for what it produces, because the caller folds cannot-measure notices in
beside the failing ones precisely so that an unobserved lane cannot reach it.

No I/O, no fixtures, no forge: the notice lines replayed here are the sibling
`notice_text` renderings of the same RECORDED `thewoolleyman/livespec`
`release-tag.yml` window the `test_release_lane_watch` modules document.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.release_lane_issue import (
    ACTION_CLOSE,
    ACTION_NOOP,
    ACTION_OPEN,
    ACTION_UPDATE,
    ISSUE_LABEL,
    ISSUE_TITLE,
    issue_action,
    issue_body,
)

_RED_NOTICE = (
    "release-tag.yml: FAILING — 2 consecutive runs since 2026-08-19T15:53:59Z; "
    "last green 2026-08-12T01:04:02Z"
)
_UNMEASURED_NOTICE = (
    "release-please.yml: CANNOT MEASURE — forge unreachable, unauthorized, or unparsable"
)
_OPEN_ISSUE = 4127


def test_open_when_red_and_no_existing_issue() -> None:
    """The first red run writes the issue the needs-attention screen reads."""
    action = issue_action(red_notices=[_RED_NOTICE], open_issue_number=None)

    assert action.kind == ACTION_OPEN
    assert action.issue_number is None
    assert action.body is not None
    assert _RED_NOTICE in action.body


def test_update_when_red_and_an_issue_is_already_open() -> None:
    """A second red run keeps ONE issue current — it does not open a 123rd."""
    action = issue_action(red_notices=[_RED_NOTICE], open_issue_number=_OPEN_ISSUE)

    assert action.kind == ACTION_UPDATE
    assert action.issue_number == _OPEN_ISSUE
    assert action.body is not None
    assert _RED_NOTICE in action.body


def test_close_when_nothing_is_red_and_an_issue_is_open() -> None:
    """Recovery retires the signal, and carries no body: closing IS the message."""
    action = issue_action(red_notices=[], open_issue_number=_OPEN_ISSUE)

    assert action.kind == ACTION_CLOSE
    assert action.issue_number == _OPEN_ISSUE
    assert action.body is None


def test_noop_when_nothing_is_red_and_no_issue_is_open() -> None:
    """A healthy fleet is SILENT — the steady state writes nothing at all."""
    action = issue_action(red_notices=[], open_issue_number=None)

    assert action.kind == ACTION_NOOP
    assert action.issue_number is None
    assert action.body is None


def test_a_cannot_measure_notice_alone_still_blocks_the_close() -> None:
    """The load-bearing row: unobserved is not recovered, so this UPDATEs."""
    action = issue_action(red_notices=[_UNMEASURED_NOTICE], open_issue_number=_OPEN_ISSUE)

    assert action.kind == ACTION_UPDATE
    assert action.body is not None
    assert _UNMEASURED_NOTICE in action.body


def test_body_lists_every_red_lane_as_its_own_bullet() -> None:
    """A reader must be able to tell a failing lane from an unobserved one."""
    body = issue_body(red_notices=[_RED_NOTICE, _UNMEASURED_NOTICE])

    assert f"- {_RED_NOTICE}" in body
    assert f"- {_UNMEASURED_NOTICE}" in body


def test_body_explains_that_the_watcher_owns_the_lifecycle() -> None:
    """Hand-closing a watcher-owned issue is the obvious wrong move; say so."""
    body = issue_body(red_notices=[_RED_NOTICE])

    assert "closes by itself" in body
    assert "Closing it by hand" in body


def test_the_label_and_title_the_reader_joins_on_are_public_constants() -> None:
    """The label is the join with the needs-attention screen, not a local detail."""
    assert ISSUE_LABEL == "release-lane-red"
    assert ISSUE_TITLE
