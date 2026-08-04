"""Shared types + GitHub-access seam for the fleet-membership contract.

Carries the value types every fleet module exchanges (member, row
outcomes, gh results) plus `FleetContext` — the single seam through
which all GitHub state flows. Row functions receive a context and
return outcome VALUES; they never log and never touch `subprocess`
directly, so the obligation table stays hermetically testable with a
canned-response runner. The default runner shells out to the `gh`
CLI (the fleet precedent for GitHub reads — see
`checks/branch_protection_alignment.py`).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

# `returns` is VENDORED, not installed, so a bare import resolves only if
# some EARLIER import in the same process already put `_vendor/` on
# `sys.path` — the latent form of the bare import that broke the fleet's
# release fan-out for seven hours (`vzwa`'s `89296e0`). This module reached
# `returns` purely through the `_snapshot` import below, whose own preamble
# ran first. The preamble is declared HERE regardless of which sibling
# currently owns the `returns` import, because this module is the fleet
# package's front door and the hazard is an ordering dependency no reader
# can see, not a property of any one import line.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_dev_tooling.fleet._gh_runner import (  # noqa: E402
    GhOutcome,
    GhResult,
    GhRunner,
    default_gh_runner,
    gh_answer,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._origin_remote import (  # noqa: E402
    OriginRemoteUnresolved,
    owner_or_origin,
    resolve_owner,
    resolve_repo_name,
)
from livespec_dev_tooling.fleet._public_api_graph import FleetConsumption  # noqa: E402
from livespec_dev_tooling.fleet._read_failure import (  # noqa: E402
    ReadFailure,
    classify_gh_failure,
    sanitize_detail,
)
from livespec_dev_tooling.fleet._snapshot import (  # noqa: E402
    GhDownloader,
    SnapshotResult,
    default_gh_downloader,
    memoized_snapshot,
)
from livespec_dev_tooling.fleet._tree_state import TreeState, parse_tree_payload  # noqa: E402

__all__: list[str] = [
    "EXCLUDED_NOTE_PREFIX",
    "Adopter",
    "FleetContext",
    "FleetMember",
    "GhDownloader",
    "GhOutcome",
    "GhResult",
    "GhRunner",
    "OriginRemoteUnresolved",
    "ReadFailure",
    "RowFinding",
    "RowOutcome",
    "RowPass",
    "RowSkip",
    "SnapshotResult",
    "TreeState",
    "default_gh_downloader",
    "default_gh_runner",
    "gh_answer",
    "owner_or_origin",
    "resolve_owner",
    "resolve_repo_name",
    "row_excluded",
]


@dataclass(frozen=True, kw_only=True)
class FleetMember:
    """One manifest entry: a fleet repo and its repo class."""

    repo: str
    repo_class: str


@dataclass(frozen=True, kw_only=True)
class Adopter:
    """One manifest adopter entry: a repo, its profile layers, and its posture."""

    repo: str
    profile: tuple[str, ...]
    posture: str


@dataclass(frozen=True, kw_only=True)
class RowPass:
    """The member satisfies the obligation row."""

    note: str = ""


@dataclass(frozen=True, kw_only=True)
class RowFinding:
    """The member definitively violates the obligation row."""

    message: str
    severity: str = "error"


@dataclass(frozen=True, kw_only=True)
class RowSkip:
    """The row could not be definitively evaluated (can't-read is not absent)."""

    reason: str


RowOutcome = RowPass | RowFinding | RowSkip

# The note prefix that marks a RowPass as INAPPLICABLE rather than satisfied.
# It lives here, beside the union, rather than privately in `_lanes.py`: a row
# module cannot import `_lanes` (that is an import cycle through
# `_contract_rows`), and both engines must render the same value the same way.
EXCLUDED_NOTE_PREFIX = "excluded-with-reason: "


def row_excluded(*, reason: str) -> RowPass:
    """The row does not APPLY to this member — a definitive non-obligation.

    ⛔ NOT `RowSkip`. `RowSkip` means the row could not be EVALUATED, and the
    central lane feeds every one of them into `blind_rows`, which fails the run
    with no lever and no opt-out. Spelling inapplicability as a skip therefore
    reds master fleet-wide the moment the applicable population reaches zero —
    for a condition that is not a failure at all.

    A constructor rather than a bare prefix so the correct spelling is a NAME
    both engines share, not a string concatenation each call site re-derives.
    """
    return RowPass(note=f"{EXCLUDED_NOTE_PREFIX}{reason}")


# Fallback ref when a repo's default branch cannot be resolved. The single
# source of truth for a repo's canonical ref is `FleetContext.canonical_ref`,
# resolved and memoized PER REPO: `file_text` and `tree` BOTH route through it
# so the genuine-absence guard — which reads a member's file (file_text) and
# then its tree (tree) to tell genuine absence from transient unreadability —
# can never evaluate the two against divergent branches. Resolving per repo
# (rather than pinning one global branch) is what lets a governed repo whose
# default branch is not `master` be evaluated at all instead of skipping every
# row; memoizing the FALLBACK too keeps the two reads together even when the
# lookup fails mid-run.
_CANONICAL_REF = "master"


@dataclass(frozen=True, kw_only=True)
class FleetContext:
    """Owner + gh seam + per-run memo caches shared by every row function."""

    owner: str
    run_gh: GhRunner
    # True when this run emits per-member verdicts — i.e. it is the fan-out
    # preflight, whose findings the livespec-f73t dispatch-matrix filter
    # consumes as per-member exclusions rather than as a halt. Rows use it to
    # scope severity by CONTEXT: a persisting pin gap is an error HERE (the
    # filter excludes that member and propagation continues) and a warning in
    # ordinary per-PR CI, where a sibling's stall would otherwise red this
    # repo's unrelated and repair PRs alike. Derived from the existing
    # `--emit-member-verdicts` invocation, never from a lever or env var.
    # Defaults False so every other construction site keeps warning behavior.
    filter_consuming_preflight: bool = False
    download_gh: GhDownloader = default_gh_downloader
    # The manifest roster, populated by the central engine once the manifest
    # resolves. A FLEET-vantage row is called once per MEMBER but must answer a
    # question about every member at once ("does any sibling consume this?"),
    # and the row protocol hands it one member. Defaulting to EMPTY is the
    # fail-closed spelling: a construction site that does not populate it makes
    # such a row SKIP naming the roster, and a row that skips for every
    # applicable member is BLIND, which this repo already treats as an error.
    members: tuple[FleetMember, ...] = ()
    # The LOCAL vantage, and the guardrail that keeps it sound. `local_repo` is
    # the member this run is executing INSIDE — derived from the origin remote,
    # never configured — and `local_root` is that checkout's git toplevel. When
    # both are set, and ONLY for the member whose name matches, the consumption
    # graph reads that member's tree from disk instead of downloading its
    # canonical ref.
    #
    # ⛔ SELF ONLY. Every SIBLING keeps its forge ref, and that asymmetry is
    # what makes the row mean anything: the CONSUMPTION half of the verdict
    # comes from other members' trees, so a PR cannot manufacture "no sibling
    # consumes this". It can change only what it declares and what it defines,
    # which is exactly the state that lands on master. Generalize the local read
    # to siblings and the consumption side becomes forgeable.
    #
    # BOTH default to None, which is the fail-closed spelling: a construction
    # site that does not opt in keeps the forge vantage unchanged.
    local_repo: str | None = None
    local_root: Path | None = None
    snapshot_cache: dict[str, SnapshotResult] = field(default_factory=dict)
    consumption_cache: dict[str, FleetConsumption] = field(default_factory=dict)
    tree_cache: dict[str, TreeState] = field(default_factory=dict)
    installed_cache: dict[str, frozenset[str] | None] = field(default_factory=dict)
    marker_cache: dict[str, bool] = field(default_factory=dict)
    ref_cache: dict[str, str] = field(default_factory=dict)
    # Diagnostics sink, mutated in place like the memo caches above. Reads
    # keep returning None on failure — the fail-closed contract is unchanged —
    # and the CAUSE is appended here so a consumer can report it instead of
    # collapsing every failure to "unavailable".
    read_failures: list[ReadFailure] = field(default_factory=list)

    def api(self, *, path: str, method: str = "GET", body: str | None = None) -> GhOutcome:
        """Issue one `gh api` call; non-GET methods stream `body` via stdin."""
        args = ["api", path]
        if method != "GET":
            args.extend(["--method", method, "--input", "-"])
        return self.run_gh(args=args, stdin=body)

    def record_not_performed(
        self, *, operation: str, path: str, failure: InvocationNotPerformed
    ) -> None:
        """Preserve a `gh` that never ran, kept apart from a `gh` that answered.

        `returncode=0` beside a `kind` naming the cause, matching
        `_snapshot`'s spelling for the same condition: there is no exit code
        to report when nothing ran, and reusing the fabricated 127 here would
        put the sentinel back one layer up.
        """
        self.record_read_failure(
            operation=operation,
            path=path,
            returncode=0,
            kind=failure.kind,
            detail=failure.reason,
        )

    def record_read_failure(
        self, *, operation: str, path: str, returncode: int, kind: str, detail: str
    ) -> None:
        """Append one preserved cause; never raises and never alters a verdict."""
        self.read_failures.append(
            ReadFailure(
                operation=operation,
                path=path,
                returncode=returncode,
                kind=kind,
                detail=sanitize_detail(text=detail),
            )
        )

    def api_object(self, *, path: str, operation: str = "api") -> object | None:
        """GET `path` and parse the JSON payload; None on any failure.

        Returns None exactly as before — callers are unchanged — while the
        cause is preserved on `read_failures`. A transport/HTTP failure and a
        200 carrying unparseable JSON are recorded as DIFFERENT kinds, because
        "never reached the API" and "the API answered with nonsense" call for
        different responses.
        """
        result = gh_answer(outcome=self.api(path=path))
        if isinstance(result, InvocationNotPerformed):
            # This used to reach `classify_gh_failure(stderr=...)` carrying
            # the seam's own invented string, so a `gh` that never ran was
            # recorded as one that had spoken and been understood.
            self.record_not_performed(operation=operation, path=path, failure=result)
            return None
        if result.returncode != 0:
            self.record_read_failure(
                operation=operation,
                path=path,
                returncode=result.returncode,
                kind=classify_gh_failure(stderr=result.stderr),
                detail=result.stderr,
            )
            return None
        try:
            return cast("object", json.loads(result.stdout))
        except json.JSONDecodeError as exc:
            self.record_read_failure(
                operation=operation,
                path=path,
                returncode=result.returncode,
                kind="malformed_payload",
                detail=str(exc),
            )
            return None

    def canonical_ref(self, *, repo: str) -> str:
        """Memoized default branch of `repo`; the `master` fallback when unresolvable.

        Resolving the ref per repo is what lets a governed repo whose default
        branch is not `master` be evaluated at all — reading it on the wrong
        branch makes every row skip. The result (fallback included) is memoized
        so `file_text` and `tree` always agree on one ref for a given repo
        within a run. Falling back rather than failing preserves the historical
        behavior: an unresolvable lookup yields a can't-read skip downstream,
        never a false pass.
        """
        cached = self.ref_cache.get(repo)
        if cached is not None:
            return cached
        payload = self.api_object(path=f"repos/{self.owner}/{repo}", operation="repo_metadata")
        resolved = _CANONICAL_REF
        if isinstance(payload, dict):
            branch = cast("dict[str, object]", payload).get("default_branch")
            if isinstance(branch, str) and branch:
                resolved = branch
        self.ref_cache[repo] = resolved
        return resolved

    def file_text(self, *, repo: str, path: str) -> str | None:
        """Raw file content at `repo`'s canonical ref via the contents API.

        The ref is pinned EXPLICITLY (`?ref=<canonical_ref>`) to match `tree`'s
        pin, so a guard that reads a file and then the tree never resolves the
        two against divergent branches. None on failure.
        """
        result = gh_answer(
            outcome=self.run_gh(
                args=[
                    "api",
                    f"repos/{self.owner}/{repo}/contents/{path}?ref={self.canonical_ref(repo=repo)}",
                    "-H",
                    "Accept: application/vnd.github.raw",
                ]
            )
        )
        if isinstance(result, InvocationNotPerformed):
            # A file this run never managed to ASK about is not an absent
            # file, and the genuine-absence guard downstream reads this.
            self.record_not_performed(operation="contents", path=f"{repo}:{path}", failure=result)
            return None
        if result.returncode != 0:
            self.record_read_failure(
                operation="contents",
                path=f"{repo}:{path}",
                returncode=result.returncode,
                kind=classify_gh_failure(stderr=result.stderr),
                detail=result.stderr,
            )
            return None
        return result.stdout

    def tree(self, *, repo: str) -> TreeState:
        """Memoized recursive canonical-ref tree for `repo` (one API call per run)."""
        cached = self.tree_cache.get(repo)
        if cached is not None:
            return cached
        ref = self.canonical_ref(repo=repo)
        payload = self.api_object(
            path=f"repos/{self.owner}/{repo}/git/trees/{ref}?recursive=1", operation="tree"
        )
        state = (
            TreeState(readable=False) if payload is None else parse_tree_payload(payload=payload)
        )
        self.tree_cache[repo] = state
        return state

    def member_tree_snapshot(self, *, repo: str) -> SnapshotResult:
        """`repo`'s whole tree at its canonical ref, materialized once per run.

        ONE API call where a per-file `file_text` walk costs one per file —
        the difference `livespec-dev-tooling-k76y` measured at ~653 reads per
        run against a pool shared by all nine repos' automation.

        Pinned through `canonical_ref` for the same reason `file_text` and
        `tree` are: a row that reads the archive and then the tree must never
        resolve the two against divergent branches.
        """
        return memoized_snapshot(
            cache=self.snapshot_cache,
            download=self.download_gh,
            owner=self.owner,
            repo=repo,
            ref=self.canonical_ref(repo=repo),
            record=self.record_read_failure,
        )

    def installed_repos(self) -> frozenset[str] | None:
        """Repos visible to the current App installation token; None = can't read.

        `GET /installation/repositories` only answers under a GitHub App
        installation token (the scheduled fleet workflow and the release
        fan-out preflight mint one); under a user PAT it fails and the
        app-installation row skips rather than guessing.
        """
        cached = self.installed_cache.get("installation")
        if "installation" in self.installed_cache:
            return cached
        payload = self.api_object(path="installation/repositories?per_page=100")
        names: frozenset[str] | None = None
        if isinstance(payload, dict):
            repositories = cast("dict[str, object]", payload).get("repositories")
            if isinstance(repositories, list):
                names = frozenset(
                    cast("str", cast("dict[str, object]", entry).get("name"))
                    for entry in cast("list[object]", repositories)
                    if isinstance(entry, dict)
                    and isinstance(cast("dict[str, object]", entry).get("name"), str)
                )
        self.installed_cache["installation"] = names
        return names

    def once(self, *, key: str) -> bool:
        """True exactly once per run for `key` (dedupes multi-row side effects)."""
        if self.marker_cache.get(key):
            return False
        self.marker_cache[key] = True
        return True
