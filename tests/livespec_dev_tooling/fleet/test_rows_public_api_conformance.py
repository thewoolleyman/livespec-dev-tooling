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
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from _gh_railway import lift_gh
from returns.io import IOSuccess

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
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome, DownloadResult

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

    def download(*, args: list[str], dest: Path) -> DownloadResult:
        repo = args[1].split("/")[2]
        if repo in unreachable:
            return IOSuccess(
                DownloadOutcome(returncode=1, stderr="HTTP 403: Resource not accessible")
            )
        _ = dest.write_bytes(archive_bytes(repo=repo, files=trees[repo]))
        return IOSuccess(DownloadOutcome(returncode=0, stderr=""))

    return FleetContext(
        owner="acme",
        run_gh=lift_gh(run),
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


_UNION_SOURCE = (
    "from dataclasses import dataclass\n"
    "\n"
    "\n"
    "@dataclass(frozen=True, kw_only=True)\n"
    "class Ok:\n"
    "    note: str = ''\n"
    "\n"
    "\n"
    "@dataclass(frozen=True, kw_only=True)\n"
    "class Bad:\n"
    "    message: str\n"
    "\n"
    "\n"
    "Outcome = Ok | Bad\n"
    "\n"
    "\n"
    "def render(*, flag: bool) -> Outcome:\n"
    "    return Ok() if flag else Bad(message='no')\n"
)
_VARIANTS_DECLARED = (
    "[tool.livespec_dev_tooling]\n"
    "single_meaning_variants = [\n"
    '  { file = "pkg/contract.py", union = "Outcome", variant = "Ok", meaning = "it holds" },\n'
    '  { file = "pkg/contract.py", union = "Outcome", variant = "Bad", meaning = "it does not" },\n'
    "]\n"
)


def test_v183_bound_four_reports_declared_unions_and_the_functions_they_relieve() -> None:
    """v183 BOUND 4 — the count is meaningless without the relief beside it.

    The ratified text says why in terms: "One union reads as negligible while
    relieving nineteen, and a count quoted without that denominator understates
    the carve-out by the ratio between them." So the row reports BOTH, and this
    test asserts both numbers rather than the union count alone.

    It is the only bound of v183 no repo-local check can supply, because no
    checkout can see the other eight.
    """
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _UNION_SOURCE, "pyproject.toml": _VARIANTS_DECLARED},
            "app": {"app/a.py": "X = 1\n"},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowPass)
    assert "single_meaning_variants declared: 1 union here, 1 fleet-wide" in outcome.note
    assert "relieving 1 function here" in outcome.note


def test_v183_bound_four_counts_a_siblings_declaration_in_the_fleet_total() -> None:
    """The fleet total spans members, which is the whole reason the bound is central."""
    outcome = outcome_for(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE},
            "app": {"pkg/contract.py": _UNION_SOURCE, "pyproject.toml": _VARIANTS_DECLARED},
        },
        repo="lib",
    )
    assert isinstance(outcome, RowPass)
    assert "single_meaning_variants declared: 0 unions here, 1 fleet-wide" in outcome.note
    assert "relieving 0 functions here" in outcome.note


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

    def download(*, args: list[str], dest: Path) -> DownloadResult:
        repo = args[1].split("/")[2]
        downloads.append(repo)
        _ = dest.write_bytes(archive_bytes(repo=repo, files=trees[repo]))
        return IOSuccess(DownloadOutcome(returncode=0, stderr=""))

    ctx = FleetContext(
        owner="acme",
        run_gh=lift_gh(run),
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


_DECLARATION = (
    "[tool.livespec_dev_tooling]\n"
    'cross_repo_public_api = [{ file = "pkg/contract.py", function = "parse_manifest", '
    'reason = "consumed by app" }]\n'
)
_DECLARATION_REMOVED = "[tool.livespec_dev_tooling]\n"


def _checkout(*, root: Path, files: dict[str, str]) -> Path:
    """Materialize a real on-disk checkout, the shape a local vantage reads."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
    return root


def _local_outcome(
    *,
    trees: dict[str, dict[str, str | bytes]],
    repo: str,
    local_repo: str,
    local_root: Path,
) -> RowPass | RowFinding | RowSkip:
    """Run the row with a local vantage bound to `local_repo` only."""
    ctx = replace(make_context(trees=trees), local_repo=local_repo, local_root=local_root)
    return assert_cross_repo_public_api_declared(
        ctx=ctx, member=FleetMember(repo=repo, repo_class="library")
    )


def test_the_self_member_is_read_from_the_local_checkout_not_the_forge(*, tmp_path: Path) -> None:
    """A PR that REMOVES a still-needed declaration must be convicted.

    This is the case the forge vantage cannot see and the whole reason the row
    moves. The forge tarball CARRIES the declaration; the local checkout has had
    it removed, which is exactly what a PR deleting the entry looks like. Read
    from the forge the row passes, because it is grading a tree the PR has not
    changed. Read from the local checkout it convicts.

    So this is STRICTLY STRICTER, not a loosening dressed as a fix: it catches a
    removal the previous vantage let through.

    ⛔ IT IS ALSO THE SELF-ONLY GUARDRAIL, which is why it is one test and not
    two. The consumption edge comes from `app`, and `app` exists ONLY in the
    forge trees — there is no local copy of it. An implementation that read the
    local root for EVERY member would find no consumer at all, no edge, and pass.
    Convicting here is only possible when the self member is local and the
    sibling is not.
    """
    local = _checkout(
        root=tmp_path,
        files={"pkg/contract.py": _LIBRARY_SOURCE, "pyproject.toml": _DECLARATION_REMOVED},
    )

    outcome = _local_outcome(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE, "pyproject.toml": _DECLARATION},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
        local_repo="lib",
        local_root=local,
    )

    assert isinstance(outcome, RowFinding), (
        f"the self member must be graded from its LOCAL checkout, where the "
        f"declaration was removed; got {outcome!r}"
    )
    assert "pkg/contract.py::parse_manifest <- app:app/use.py" in outcome.message


def test_the_local_self_member_passes_when_its_own_tree_conforms(*, tmp_path: Path) -> None:
    """The other direction: the local checkout is authoritative when it CONFORMS.

    Here the forge tarball is the one missing the declaration and the local
    checkout carries it — a PR that ADDS the entry. A row that convicted here
    would be reading the forge and would make the deadlock permanent, since the
    remedy could never be seen by the check demanding it.
    """
    local = _checkout(
        root=tmp_path,
        files={"pkg/contract.py": _LIBRARY_SOURCE, "pyproject.toml": _DECLARATION},
    )

    outcome = _local_outcome(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE, "pyproject.toml": _DECLARATION_REMOVED},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
        local_repo="lib",
        local_root=local,
    )

    assert isinstance(
        outcome, RowPass
    ), f"the local checkout conforms, so the row must pass on it; got {outcome!r}"


def test_a_sibling_is_never_read_from_the_local_checkout(*, tmp_path: Path) -> None:
    """ONLY the self member reads locally; every sibling keeps its forge ref.

    The local vantage is bound to `app`, and the row is evaluated for `lib`.
    `lib` is a SIBLING of the running repo here, so it must still be read from
    the forge — where it defines `parse_manifest` and declares nothing.

    If a sibling were read locally, `lib` would be graded against `app`'s
    checkout, which contains no `pkg/contract.py` at all: no defining file, no
    edge, and a vacuous pass. Generalizing the local read is what makes the
    consumption side forgeable, and this is the test that fails when someone
    does.
    """
    local = _checkout(root=tmp_path, files={"app/use.py": _CONSUMER_SOURCE})

    outcome = _local_outcome(
        trees={
            "lib": {"pkg/contract.py": _LIBRARY_SOURCE},
            "app": {"app/use.py": _CONSUMER_SOURCE},
        },
        repo="lib",
        local_repo="app",
        local_root=local,
    )

    assert isinstance(outcome, RowFinding), (
        f"a sibling must still be read from the forge, where it defines the "
        f"consumed function; got {outcome!r}"
    )
    assert "pkg/contract.py::parse_manifest <- app:app/use.py" in outcome.message
