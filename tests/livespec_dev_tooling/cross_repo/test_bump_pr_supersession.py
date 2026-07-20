"""Tests for bump PR supersession classification.

The fan-out may open several bump PRs for the same source repo and consumer over
time. The classifier decides which open PRs should be closed after a bump PR is
opened, without embedding that decision logic in workflow shell.
"""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling.cross_repo.bump_pr_supersession import (
    BumpKey,
    OpenBumpPullRequest,
    classify_superseded_prs,
    main,
    master_versions_from_records,
)


def _pr(*, number: int, source_repo: str, target_version: str) -> OpenBumpPullRequest:
    return OpenBumpPullRequest(
        number=number,
        branch=f"chore/bump-{source_repo}-{target_version}",
        key=BumpKey(
            source_repo=source_repo,
            target_version=target_version,
            consumer="livespec",
        ),
    )


def test_classifies_pr_superseded_by_consumer_master_pin() -> None:
    decisions = classify_superseded_prs(
        open_prs=[_pr(number=43, source_repo="livespec-runtime", target_version="v0.3.0")],
        master_versions={("livespec-runtime", "livespec"): "v0.4.0"},
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.number == 43
    assert decision.category == "master"
    assert decision.superseder == "v0.4.0"
    assert "master already carries livespec-runtime at v0.4.0" in decision.comment
    assert "target v0.3.0" in decision.comment


def test_classifies_older_pr_superseded_by_newer_open_sibling() -> None:
    decisions = classify_superseded_prs(
        open_prs=[
            _pr(number=206, source_repo="livespec-runtime", target_version="v0.3.0"),
            _pr(number=209, source_repo="livespec-runtime", target_version="v0.4.0"),
        ],
        master_versions={("livespec-runtime", "livespec"): "v0.2.0"},
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.number == 206
    assert decision.category == "open_sibling"
    assert decision.superseder == "#209"
    assert "newer open bump PR #209" in decision.comment
    assert "targeting v0.4.0" in decision.comment


def test_keeps_latest_open_pr_for_same_source_consumer_pair() -> None:
    decisions = classify_superseded_prs(
        open_prs=[
            _pr(number=206, source_repo="livespec-runtime", target_version="v0.3.0"),
            _pr(number=209, source_repo="livespec-runtime", target_version="v0.4.0"),
        ],
        master_versions={("livespec-runtime", "livespec"): "v0.2.0"},
    )

    assert [decision.number for decision in decisions] == [206]


def test_does_not_compare_different_source_repos_or_consumers() -> None:
    runtime = _pr(number=11, source_repo="livespec-runtime", target_version="v0.3.0")
    core = _pr(number=12, source_repo="livespec", target_version="v0.4.0")
    other_consumer = OpenBumpPullRequest(
        number=13,
        branch="chore/bump-livespec-runtime-v0.5.0",
        key=BumpKey(
            source_repo="livespec-runtime",
            target_version="v0.5.0",
            consumer="livespec-other",
        ),
    )

    assert (
        classify_superseded_prs(
            open_prs=[runtime, core, other_consumer],
            master_versions={("livespec-runtime", "livespec"): "v0.2.0"},
        )
        == []
    )


def test_master_floor_uses_the_lowest_discovered_pin_for_multi_pin_sources() -> None:
    records = [
        {
            "source_repo": "livespec-dev-tooling",
            "current_value": "python-v0.49.2",
        },
        {
            "source_repo": "livespec-dev-tooling",
            "current_value": "python-v0.43.2",
        },
    ]

    decisions = classify_superseded_prs(
        open_prs=[
            _pr(
                number=31,
                source_repo="livespec-dev-tooling",
                target_version="python-v0.49.2",
            )
        ],
        master_versions=master_versions_from_records(records=records, consumer="livespec"),
    )

    assert decisions == []


def test_main_emits_close_plan_from_github_pr_json(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    open_prs = [
        {
            "number": 206,
            "headRefName": "chore/bump-livespec-runtime-v0.3.0",
            "title": "chore(deps): bump livespec-runtime pin to v0.3.0",
        },
        {
            "number": 209,
            "headRefName": "chore/bump-livespec-runtime-v0.4.0",
            "title": "chore(deps): bump livespec-runtime pin to v0.4.0",
        },
    ]
    records = [{"source_repo": "livespec-runtime", "current_value": "v0.2.0"}]
    monkeypatch.setenv("OPEN_PRS", json.dumps(open_prs))
    monkeypatch.setenv("RECORDS", json.dumps(records))
    monkeypatch.setenv("CONSUMER", "livespec")

    assert main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "number": 206,
            "branch": "chore/bump-livespec-runtime-v0.3.0",
            "category": "open_sibling",
            "superseder": "#209",
            "comment": (
                "Closing this bump PR because it targets livespec-runtime v0.3.0 "
                "for livespec, and newer open bump PR #209 targets v0.4.0."
            ),
        }
    ]
