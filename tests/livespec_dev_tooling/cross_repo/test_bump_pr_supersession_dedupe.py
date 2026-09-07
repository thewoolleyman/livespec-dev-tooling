"""Tests for the pre-create duplicate-bump-PR dedupe decision.

Per livespec-dev-tooling-dqfmjr the fan-out opened a redundant bump PR whenever a
second producer fired for a `(source_repo, target_version, consumer)` tuple that
already had an open bump PR: the dispatch path (`chore/bump-*`) and the
cron-freshness path (`chore/freshness-bump-*`) each opened one for the same
release, and neither looked before creating.

`classify_superseded_prs` provably cannot clean that pair up. Its `master`
category needs a master pin at or above the target — defeated in exactly the repo
whose bump has not landed yet — and its `open_sibling` category needs a STRICTLY
newer sibling, so an EQUAL-version pair sits outside the relation entirely. The
duplicate therefore has to be refused BEFORE `gh pr create`, which is what these
tests pin: supersession closes OLD siblings, dedupe refuses NEW duplicates, and
together they hold the invariant of at most one open bump PR per
`(source_repo, consumer)`.

The decision lives beside `classify_superseded_prs` in the same tested importable
classifier module, sharing its `BumpKey` identity and `parse_open_bump_prs`
parser, rather than in workflow shell.
"""

from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Any

from livespec_dev_tooling.cross_repo.bump_pr_supersession import (
    BumpKey,
    OpenBumpPullRequest,
    main,
)

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

_MODULE_NAME = "livespec_dev_tooling.cross_repo.bump_pr_supersession"


def _classifier() -> ModuleType:
    """Return the shared classifier module, asserting it carries the dedupe decision.

    The import is deliberately deferred into the test body and the presence of the
    new entry point asserted, so the pre-implementation failure is a genuine
    assertion about a missing decision rather than an unimportable module.
    """
    module = importlib.import_module(_MODULE_NAME)
    assert hasattr(module, "find_duplicate_bump_pr"), (
        f"{_MODULE_NAME} must export `find_duplicate_bump_pr` — the pre-create "
        "dedupe decision belongs beside `classify_superseded_prs` in the shared "
        "classifier module, never as new decision logic in workflow shell"
    )
    return module


def _find_duplicate(*, open_prs: list[OpenBumpPullRequest], key: BumpKey) -> Any:
    """Call the classifier's dedupe entry point."""
    return _classifier().find_duplicate_bump_pr(open_prs=open_prs, key=key)


def _open_pr_json(*, number: int, branch: str, source_repo: str, tag: str) -> dict[str, object]:
    """Return one `gh pr list --json number,headRefName,title` record."""
    return {
        "number": number,
        "headRefName": branch,
        "title": f"chore(deps): bump {source_repo} pin to {tag}",
    }


def _pr(*, number: int, branch: str, source_repo: str, target_version: str) -> OpenBumpPullRequest:
    return OpenBumpPullRequest(
        number=number,
        branch=branch,
        key=BumpKey(
            source_repo=source_repo,
            target_version=target_version,
            consumer="livespec-overseer",
        ),
    )


def _fan_out_dedupe_gate(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    open_prs: list[dict[str, object]],
    source_repo: str,
    tag: str,
) -> dict[str, object]:
    """Run one fan-out invocation's dedupe gate through the Action's env surface.

    This is the harness the acceptance names: the composite Action captures
    `gh pr list` JSON and dispatches this module in dedupe mode before
    `gh pr create`. An empty object means "no duplicate — open the PR".
    """
    monkeypatch.setenv("BUMP_MODE", "dedupe")
    monkeypatch.setenv("OPEN_PRS", json.dumps(open_prs))
    monkeypatch.setenv("SOURCE_REPO", source_repo)
    monkeypatch.setenv("TAG", tag)
    monkeypatch.setenv("CONSUMER", "livespec-overseer")

    assert main() == 0

    return json.loads(capsys.readouterr().out)


def test_fan_out_opens_the_first_bump_pr_and_refuses_the_second(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invoking the fan-out twice for one release opens exactly one PR.

    The discriminating pair, in both directions. The first invocation sees no
    open bump PR for the tuple and MUST still open one; the second — modelled by
    feeding back the PR the first invocation opened — MUST no-op. A dedupe that
    suppressed both would be worse than the duplicate it replaces.
    """
    first = _fan_out_dedupe_gate(
        monkeypatch=monkeypatch,
        capsys=capsys,
        open_prs=[],
        source_repo="livespec",
        tag="v0.20.1",
    )

    assert first == {}, "a tuple with no open bump PR must still get one opened"

    opened = _open_pr_json(
        number=6,
        branch="chore/bump-livespec-v0.20.1",
        source_repo="livespec",
        tag="v0.20.1",
    )
    second = _fan_out_dedupe_gate(
        monkeypatch=monkeypatch,
        capsys=capsys,
        open_prs=[opened],
        source_repo="livespec",
        tag="v0.20.1",
    )

    assert second["number"] == 6
    assert second["branch"] == "chore/bump-livespec-v0.20.1"
    assert "#6" in str(second["notice"])
    assert "livespec v0.20.1" in str(second["notice"])
    assert "livespec-overseer" in str(second["notice"])


def test_dedupe_matches_the_incumbent_across_the_two_producer_branch_prefixes(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The freshness producer refuses a duplicate of the dispatch producer's PR.

    The live reproduction: `livespec-overseer` #6 (`chore/bump-livespec-v0.20.1`)
    and #8 (`chore/freshness-bump-livespec-v0.20.1`) are the same bump identity
    on different branches. Keying on `BumpKey` rather than the branch name is
    what makes the cross-producer pair visible.
    """
    decision = _fan_out_dedupe_gate(
        monkeypatch=monkeypatch,
        capsys=capsys,
        open_prs=[
            _open_pr_json(
                number=6,
                branch="chore/bump-livespec-v0.20.1",
                source_repo="livespec",
                tag="v0.20.1",
            )
        ],
        source_repo="livespec",
        tag="v0.20.1",
    )

    assert decision["number"] == 6
    assert decision["branch"] == "chore/bump-livespec-v0.20.1"


def test_dedupe_does_not_refuse_a_bump_to_a_different_target_version() -> None:
    """An open OLDER sibling is supersession's concern, not dedupe's.

    Refusing here would suppress the legitimate newer bump and freeze the
    consumer at the older target — the failure mode that makes an over-eager
    dedupe worse than the duplicate.
    """
    duplicate = _find_duplicate(
        open_prs=[
            _pr(
                number=6,
                branch="chore/bump-livespec-v0.20.1",
                source_repo="livespec",
                target_version="v0.20.1",
            )
        ],
        key=BumpKey(
            source_repo="livespec",
            target_version="v0.21.0",
            consumer="livespec-overseer",
        ),
    )

    assert duplicate is None


def test_dedupe_does_not_refuse_across_source_repos_or_consumers() -> None:
    """Only the exact `(source_repo, target_version, consumer)` tuple deduplicates."""
    other_source = _pr(
        number=7,
        branch="chore/bump-livespec-dev-tooling-v0.20.1",
        source_repo="livespec-dev-tooling",
        target_version="v0.20.1",
    )
    other_consumer = OpenBumpPullRequest(
        number=8,
        branch="chore/bump-livespec-v0.20.1",
        key=BumpKey(
            source_repo="livespec",
            target_version="v0.20.1",
            consumer="livespec-runtime",
        ),
    )

    duplicate = _find_duplicate(
        open_prs=[other_source, other_consumer],
        key=BumpKey(
            source_repo="livespec",
            target_version="v0.20.1",
            consumer="livespec-overseer",
        ),
    )

    assert duplicate is None


def test_dedupe_names_the_oldest_open_pr_when_duplicates_already_accumulated() -> None:
    """With a duplicate pair already open, the incumbent named is the oldest.

    The supersession sweep cannot close an equal-version pair, so a backlog of
    them can exist. Naming the lowest-numbered PR keeps the notice stable across
    repeated fan-outs instead of pointing at whichever duplicate landed last.
    """
    duplicate = _find_duplicate(
        open_prs=[
            _pr(
                number=8,
                branch="chore/freshness-bump-livespec-v0.20.1",
                source_repo="livespec",
                target_version="v0.20.1",
            ),
            _pr(
                number=6,
                branch="chore/bump-livespec-v0.20.1",
                source_repo="livespec",
                target_version="v0.20.1",
            ),
        ],
        key=BumpKey(
            source_repo="livespec",
            target_version="v0.20.1",
            consumer="livespec-overseer",
        ),
    )

    assert duplicate is not None
    assert duplicate.number == 6
    assert duplicate.branch == "chore/bump-livespec-v0.20.1"


def test_supersession_mode_is_unchanged_when_dedupe_mode_is_not_requested(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without `BUMP_MODE=dedupe` the entry point still emits the close plan.

    The dedupe gate is a second mode on the same module, not a replacement: the
    post-create supersession sweep keeps reading the same stdout contract.
    """
    monkeypatch.delenv("BUMP_MODE", raising=False)
    monkeypatch.setenv(
        "OPEN_PRS",
        json.dumps(
            [
                _open_pr_json(
                    number=6,
                    branch="chore/bump-livespec-v0.20.1",
                    source_repo="livespec",
                    tag="v0.20.1",
                )
            ]
        ),
    )
    monkeypatch.setenv(
        "RECORDS", json.dumps([{"source_repo": "livespec", "current_value": "v0.21.0"}])
    )
    monkeypatch.setenv("CONSUMER", "livespec-overseer")

    assert main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert [decision["category"] for decision in payload] == ["master"]
