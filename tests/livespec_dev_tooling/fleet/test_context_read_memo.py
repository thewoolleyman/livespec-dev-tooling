"""`FleetContext` reads each sibling file and API object at most once per run.

`livespec-dev-tooling-bcwf2z`: one fleet-conformance sweep MEASURED 521 core
requests on the livespec-ai org App installation (5,000/h), 405 of them
per-file `contents/` reads, and 53% of the sweep repeated a read the same run
had already made, although every sibling's tarball was already on disk.

Every runner here is a canned fake that RECORDS its calls, so each test counts
the requests a read actually issued. Hermetic: no `gh` runs, and the "tarball"
is a directory under `tmp_path` placed in `snapshot_cache` the way
`member_tree_snapshot` leaves a successful fetch.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zq2i4c
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from _gh_railway import lift_gh
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet._context import FleetContext, GhResult, GhRunner
from livespec_dev_tooling.fleet._snapshot import SnapshotUnavailable, TreeSnapshot

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


_CONTENTS = ("api", "repos/acme/widget/contents/justfile?ref=master")
_RAW = ("-H", "Accept: application/vnd.github.raw")
_CONTENTS_ARGS = (*_CONTENTS, *_RAW)
_REPO_ARGS = ("api", "repos/acme/widget")
_NOT_FOUND = GhResult(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")


def _context(
    *, table: dict[tuple[str, ...], GhResult], calls: list[tuple[str, ...]]
) -> FleetContext:
    """A context for owner `acme` whose `widget` canonical ref is `master`."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        _ = stdin
        calls.append(tuple(args))
        return table.get(tuple(args), _NOT_FOUND)

    runner: GhRunner = lift_gh(run)
    ctx = FleetContext(owner="acme", run_gh=runner)
    ctx.ref_cache["widget"] = "master"
    return ctx


def _snapshot(*, root: Path, ref: str = "master") -> IOSuccess[TreeSnapshot]:
    """A successful already-fetched `widget` snapshot extracted at `root`."""
    return IOSuccess(TreeSnapshot(repo="widget", ref=ref, root=root, file_count=1))


def test_a_repeated_file_read_issues_no_second_contents_call() -> None:
    calls: list[tuple[str, ...]] = []
    ctx = _context(
        table={_CONTENTS_ARGS: GhResult(returncode=0, stdout="check:\n", stderr="")}, calls=calls
    )
    first = ctx.file_text(repo="widget", path="justfile")
    second = ctx.file_text(repo="widget", path="justfile")
    facts = [first == "check:\n", second == "check:\n", calls == [_CONTENTS_ARGS]]
    assert all(facts), (first, second, calls)


def test_a_repeated_api_object_read_issues_no_second_call() -> None:
    calls: list[tuple[str, ...]] = []
    payload = {"default_branch": "master", "topics": ["livespec"]}
    ctx = _context(
        table={_REPO_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")},
        calls=calls,
    )
    first = ctx.api_object(path="repos/acme/widget")
    second = ctx.api_object(path="repos/acme/widget")
    facts = [first == payload, second == payload, calls == [_REPO_ARGS]]
    assert all(facts), (first, second, calls)


def test_a_file_in_the_fetched_tarball_is_served_with_no_contents_call(tmp_path: Path) -> None:
    _ = (tmp_path / "justfile").write_text("check:\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    ctx = _context(table={}, calls=calls)
    ctx.snapshot_cache["widget"] = _snapshot(root=tmp_path)
    text = ctx.file_text(repo="widget", path="justfile")
    facts = [text == "check:\n", calls == [], ctx.read_failures == []]
    assert all(facts), (text, calls, ctx.read_failures)


def test_a_tarball_at_another_ref_is_not_served(tmp_path: Path) -> None:
    _ = (tmp_path / "justfile").write_text("stale:\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    ctx = _context(
        table={_CONTENTS_ARGS: GhResult(returncode=0, stdout="check:\n", stderr="")}, calls=calls
    )
    ctx.snapshot_cache["widget"] = _snapshot(root=tmp_path, ref="main")
    text = ctx.file_text(repo="widget", path="justfile")
    facts = [text == "check:\n", calls == [_CONTENTS_ARGS]]
    assert all(facts), (text, calls)


def test_a_path_the_tarball_lacks_is_still_asked_of_github(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    ctx = _context(table={}, calls=calls)
    ctx.snapshot_cache["widget"] = _snapshot(root=tmp_path)
    text = ctx.file_text(repo="widget", path="justfile")
    kinds = [failure.kind for failure in ctx.read_failures]
    facts = [text is None, calls == [_CONTENTS_ARGS], kinds == ["not_found"]]
    assert all(facts), (text, calls, kinds)


def test_non_utf8_tarball_bytes_fall_back_to_the_contents_api(tmp_path: Path) -> None:
    _ = (tmp_path / "justfile").write_bytes(b"\xff\xfe\x00")
    calls: list[tuple[str, ...]] = []
    ctx = _context(
        table={_CONTENTS_ARGS: GhResult(returncode=0, stdout="check:\n", stderr="")}, calls=calls
    )
    ctx.snapshot_cache["widget"] = _snapshot(root=tmp_path)
    text = ctx.file_text(repo="widget", path="justfile")
    facts = [text == "check:\n", calls == [_CONTENTS_ARGS]]
    assert all(facts), (text, calls)


def test_a_failed_tarball_fetch_falls_back_to_the_contents_api() -> None:
    calls: list[tuple[str, ...]] = []
    ctx = _context(
        table={_CONTENTS_ARGS: GhResult(returncode=0, stdout="check:\n", stderr="")}, calls=calls
    )
    ctx.snapshot_cache["widget"] = IOFailure(
        SnapshotUnavailable(
            repo="widget", ref="master", returncode=1, kind="rate_limited", detail="limit"
        )
    )
    text = ctx.file_text(repo="widget", path="justfile")
    facts = [text == "check:\n", calls == [_CONTENTS_ARGS]]
    assert all(facts), (text, calls)


def test_a_failed_read_is_not_memoized_and_records_each_cause() -> None:
    calls: list[tuple[str, ...]] = []
    ctx = _context(table={}, calls=calls)
    first = ctx.file_text(repo="widget", path="justfile")
    second = ctx.file_text(repo="widget", path="justfile")
    kinds = [failure.kind for failure in ctx.read_failures]
    facts = [
        first is None,
        second is None,
        calls == [_CONTENTS_ARGS, _CONTENTS_ARGS],
        kinds == ["not_found", "not_found"],
    ]
    assert all(facts), (first, second, calls, kinds)


def test_a_json_null_payload_is_not_memoized() -> None:
    calls: list[tuple[str, ...]] = []
    ctx = _context(
        table={_REPO_ARGS: GhResult(returncode=0, stdout="null", stderr="")}, calls=calls
    )
    first = ctx.api_object(path="repos/acme/widget")
    second = ctx.api_object(path="repos/acme/widget")
    facts = [first is None, second is None, calls == [_REPO_ARGS, _REPO_ARGS]]
    assert all(facts), (first, second, calls)


def test_a_write_clears_the_read_memos() -> None:
    calls: list[tuple[str, ...]] = []
    ctx = _context(
        table={
            _CONTENTS_ARGS: GhResult(returncode=0, stdout="check:\n", stderr=""),
            _REPO_ARGS: GhResult(returncode=0, stdout="{}", stderr=""),
        },
        calls=calls,
    )
    _ = ctx.file_text(repo="widget", path="justfile")
    _ = ctx.api_object(path="repos/acme/widget")
    _ = ctx.api(path="repos/acme/widget", method="PATCH", body="{}")
    _ = ctx.file_text(repo="widget", path="justfile")
    _ = ctx.api_object(path="repos/acme/widget")
    reads = [call for call in calls if "--method" not in call]
    expected = [_CONTENTS_ARGS, _REPO_ARGS, _CONTENTS_ARGS, _REPO_ARGS]
    assert reads == expected, calls
