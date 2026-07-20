"""Edge coverage for bump PR supersession parsing and version comparisons."""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling.cross_repo.bump_pr_supersession import (
    BumpKey,
    OpenBumpPullRequest,
    classify_superseded_prs,
    main,
    master_versions_from_records,
    parse_open_bump_prs,
)


def _pr(*, number: int, target_version: str) -> OpenBumpPullRequest:
    return OpenBumpPullRequest(
        number=number,
        branch=f"chore/bump-livespec-runtime-{target_version}",
        key=BumpKey(
            source_repo="livespec-runtime",
            target_version=target_version,
            consumer="livespec",
        ),
    )


def test_exact_master_version_supersedes_matching_target() -> None:
    decisions = classify_superseded_prs(
        open_prs=[_pr(number=44, target_version="v0.4.0")],
        master_versions={("livespec-runtime", "livespec"): "v0.4.0"},
    )

    assert [decision.number for decision in decisions] == [44]


def test_unparseable_versions_do_not_compare_as_newer_or_at_master() -> None:
    decisions = classify_superseded_prs(
        open_prs=[
            _pr(number=44, target_version="sha-old"),
            _pr(number=45, target_version="sha-new"),
        ],
        master_versions={("livespec-runtime", "livespec"): "sha-master"},
    )

    assert decisions == []


def test_parse_open_bump_prs_skips_non_lists_and_malformed_items() -> None:
    assert parse_open_bump_prs(payload={"number": 1}, consumer="livespec") == []

    parsed = parse_open_bump_prs(
        payload=[
            "not a mapping",
            {"number": 1, "headRefName": "branch"},
            {"number": 2, "headRefName": "branch", "title": "docs: update"},
            {
                "number": 3,
                "headRefName": "chore/bump-livespec-runtime-v0.4.0",
                "title": "chore(deps): bump livespec-runtime pin to v0.4.0",
            },
        ],
        consumer="livespec",
    )

    assert [pr.number for pr in parsed] == [3]


def test_master_versions_from_records_skips_malformed_and_keeps_existing_floor() -> None:
    records = [
        {"source_repo": "livespec-runtime"},
        {"current_value": "v0.3.0"},
        {"source_repo": "livespec-runtime", "current_value": "sha-old"},
        {"source_repo": "livespec-runtime", "current_value": "v0.3.0"},
    ]

    assert master_versions_from_records(records=records, consumer="livespec") == {
        ("livespec-runtime", "livespec"): "sha-old"
    }


def test_main_uses_github_repository_as_consumer_fallback(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CONSUMER", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "thewoolleyman/livespec")
    monkeypatch.setenv(
        "OPEN_PRS",
        json.dumps(
            [
                {
                    "number": 44,
                    "headRefName": "chore/bump-livespec-runtime-v0.4.0",
                    "title": "chore(deps): bump livespec-runtime pin to v0.4.0",
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "RECORDS", json.dumps([{"source_repo": "livespec-runtime", "current_value": "v0.4.0"}])
    )

    assert main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["category"] == "master"
    assert "for livespec" in payload[0]["comment"]
