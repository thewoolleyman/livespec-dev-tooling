"""Tests for `livespec_dev_tooling/fleet/_rows_public_api_conformance.py`.

END-TO-END through the real stack: each fake member is a real `.tar.gz` served
by a canned downloader, so the row runs through `member_tree_snapshot` ->
`read_member_sources` -> `cross_member_consumption` exactly as it will against
the forge. Only the network is faked. A test that injected a pre-built graph
would pin the row's arithmetic and none of the wiring, and the wiring is where
`livespec-dev-tooling-oitd` and Phase 3 both showed the failures live.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_public_api_conformance import (
    assert_cross_repo_public_api_declared,
)
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome

if TYPE_CHECKING:
    pass

__all__: list[str] = []


_LIBRARY_SOURCE = "def parse_manifest(*, text: str) -> str:\n    return text\n"
_CONSUMER_SOURCE = "from pkg.contract import parse_manifest\n\nparse_manifest(text='x')\n"


def archive_bytes(*, repo: str, files: dict[str, str | bytes]) -> bytes:
    """A real gzip tarball shaped like GitHub's, with the single root component.

    A `bytes` value is written verbatim, so a member carrying a source that is
    not valid UTF-8 can be built — the one input that reads as a healthy TREE
    and an unreadable SOURCE.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name, text in files.items():
            payload = text.encode("utf-8") if isinstance(text, str) else text
            entry = tarfile.TarInfo(name=f"acme-{repo}-abc123/{name}")
            entry.size = len(payload)
            bundle.addfile(entry, io.BytesIO(payload))
    return buffer.getvalue()


def make_context(
    *, trees: dict[str, dict[str, str | bytes]], unreachable: frozenset[str] = frozenset()
) -> FleetContext:
    """A context whose downloader serves each member's tarball from `trees`."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        repo = args[1].split("/")[2]
        return (
            GhResult(returncode=0, stdout=json.dumps({"default_branch": "master"}), stderr="")
            if repo in trees
            else GhResult(returncode=1, stdout="", stderr="HTTP 404")
        )

    def download(*, args: list[str], dest: Path) -> DownloadOutcome:
        repo = args[1].split("/")[2]
        if repo in unreachable:
            return DownloadOutcome(returncode=1, stderr="HTTP 403: Resource not accessible")
        _ = dest.write_bytes(archive_bytes(repo=repo, files=trees[repo]))
        return DownloadOutcome(returncode=0, stderr="")

    return FleetContext(
        owner="acme",
        run_gh=run,
        download_gh=download,
        members=tuple(FleetMember(repo=repo, repo_class="library") for repo in trees),
    )


def outcome_for(
    *,
    trees: dict[str, dict[str, str | bytes]],
    repo: str,
    unreachable: frozenset[str] = frozenset(),
) -> RowPass | RowFinding | RowSkip:
    """Run the row for `repo` over a fake fleet."""
    ctx = make_context(trees=trees, unreachable=unreachable)
    return assert_cross_repo_public_api_declared(
        ctx=ctx, member=FleetMember(repo=repo, repo_class="library")
    )


def test_an_undeclared_sibling_consumption_is_a_finding_naming_every_site() -> None:
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowFinding)
    assert "cross_repo_public_api omits 1 function(s)" in outcome.message
    assert "pkg/contract.py::parse_manifest <- app:app/use.py" in outcome.message
    assert outcome.severity == "error"


def test_a_declared_consumption_passes() -> None:
    """The declaration is what the row checks; carrying it is the whole remedy."""
    declaration = (
        "[tool.livespec_dev_tooling]\n"
        'cross_repo_public_api = [{ file = "pkg/contract.py", function = "parse_manifest", '
        'reason = "consumed by app" }]\n'
    )
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE, "pyproject.toml": declaration},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowPass)


def test_a_name_already_public_repo_locally_needs_no_declaration() -> None:
    """Clause 3. Without it the row would demand declarations the local check already scopes."""
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE, "pkg/local.py": _CONSUMER_SOURCE},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowPass)


def test_a_member_no_sibling_consumes_passes_and_still_reports_bound_four() -> None:
    outcome = outcome_for(
        trees={"lib": {"pkg/contract.py": _LIBRARY_SOURCE}, "app": {"app/other.py": "X = 1\n"}},
        repo="lib",
    )
    assert isinstance(outcome, RowPass)
    assert "total_absence_returns declared: 0 here, 0 fleet-wide" in outcome.note
    assert "STATIC BLIND SPOT" in outcome.note


def test_the_finding_carries_the_guard_warning_and_the_blind_spot_in_its_own_output() -> None:
    """k76y: both belong in the OUTPUT, because an operator reads the finding."""
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowFinding)
    assert "FINDING THE IMPORT IS NOT FINDING THE GUARD" in outcome.message
    assert "STATIC BLIND SPOT" in outcome.message
    assert "total_absence_returns declared:" in outcome.message


def test_bound_four_counts_this_repo_and_the_fleet_separately() -> None:
    absence = (
        "[tool.livespec_dev_tooling]\n"
        'total_absence_returns = [{ file = "pkg/contract.py", function = "find", '
        'reason = "absence not failure" }]\n'
    )
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": "def find() -> int | None:\n    return None\n"},
            "app": {"app/a.py": "X = 1\n", "pyproject.toml": absence},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowPass)
    assert "total_absence_returns declared: 0 here, 1 fleet-wide" in outcome.note


def test_an_unreadable_member_skips_naming_the_cause_rather_than_passing() -> None:
    """A can't-read is not an absence; a member measured as empty would PASS."""
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
        unreachable=frozenset({"lib"}),
    )
    assert isinstance(outcome, RowSkip)
    assert "tree unreadable (forbidden)" in outcome.reason


def test_a_member_whose_pyproject_will_not_parse_skips_naming_it() -> None:
    outcome = outcome_for(
        trees={
            "lib": {
                "pkg/contract.py": _LIBRARY_SOURCE,
                "pyproject.toml": "[tool.livespec_dev_tooling]\ncross_repo_public_api = 17\n",
            },
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowSkip)
    assert "pyproject unparseable" in outcome.reason


def test_an_unparseable_source_is_named_in_the_output_not_silently_measured_as_empty() -> None:
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE, "pkg/broken.py": "def (:\n"},
            "app": {"app/other.py": "X = 1\n"},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowPass)
    assert "UNPARSED (measured as holding nothing): pkg/broken.py" in outcome.note


def test_an_absent_roster_skips_rather_than_reporting_a_clean_fleet() -> None:
    """Fail-closed: a fleet-vantage row given one member must not answer at all.

    An empty roster measures nothing, and "nothing consumed this" is exactly
    what a clean fleet looks like — the manufactured-confidence failure this
    whole epic exists to remove.
    """

    ctx = make_context(trees={})
    outcome = assert_cross_repo_public_api_declared(
        ctx=ctx, member=FleetMember(repo="lib", repo_class="library")
    )
    assert isinstance(outcome, RowSkip)
    assert "fleet roster absent" in outcome.reason


def test_a_member_outside_the_roster_skips_rather_than_passing_vacuously() -> None:
    ctx = make_context(trees={"lib": {"pkg/contract.py": _LIBRARY_SOURCE}})
    outcome = assert_cross_repo_public_api_declared(
        ctx=ctx, member=FleetMember(repo="stranger", repo_class="library")
    )
    assert isinstance(outcome, RowSkip)
    assert "not present in this run's fleet roster" in outcome.reason


def test_the_fleet_graph_is_built_once_per_run_not_once_per_member() -> None:
    """Nine members would otherwise read the whole fleet nine times (k76y)."""
    downloads: list[str] = []
    trees = {
        "lib": {"pkg/contract.py": _LIBRARY_SOURCE},
        "app": {"app/use.py": _CONSUMER_SOURCE},
    }

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin, args
        return GhResult(returncode=0, stdout=json.dumps({"default_branch": "master"}), stderr="")

    def download(*, args: list[str], dest: Path) -> DownloadOutcome:
        repo = args[1].split("/")[2]
        downloads.append(repo)
        _ = dest.write_bytes(archive_bytes(repo=repo, files=trees[repo]))
        return DownloadOutcome(returncode=0, stderr="")

    ctx = FleetContext(
        owner="acme",
        run_gh=run,
        download_gh=download,
        members=tuple(FleetMember(repo=repo, repo_class="library") for repo in trees),
    )
    for repo in trees:
        _ = assert_cross_repo_public_api_declared(
            ctx=ctx, member=FleetMember(repo=repo, repo_class="library")
        )
    assert sorted(downloads) == ["app", "lib"]


def test_a_member_whose_source_is_not_utf8_skips_naming_the_file() -> None:
    """A healthy TREE with an unreadable SOURCE is its own outcome.

    The archive extracts fine, so the snapshot succeeds and only the source
    read fails — the arm that would otherwise be reachable solely in
    production, where a member is measured as holding nothing and passes.
    """
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": b"VALUE = '\xff\xfe not utf-8'\n"},
            "app": {"app/other.py": "X = 1\n"},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowSkip)
    assert "sources unreadable" in outcome.reason
    assert "contract.py" in outcome.reason
