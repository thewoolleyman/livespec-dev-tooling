"""Forge reads and writes the recovery principal performs as the recovery App.

Scope is derived, never accepted: the landed chain comes from the forge's own
record of the armed pull request plus the independent reference clone's
immutable objects. Publication is three steps with one effect. The inverse tree
and its commit are created as objects first, and the created tree must be
byte-identical to the tree the principal computed locally; only then does a
non-forced ref update move master. A non-forced update succeeds only when the
new commit fast-forwards master, and the commit's single parent is the expected
head, so a master that moved refuses the update with no effect (master's
protection forbids rewinding it to an ancestor).
"""

from __future__ import annotations

import base64
import hashlib
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_inverse_git import scope_matches_git  # noqa: E402
from livespec_dev_tooling._incident_inverse_types import (  # noqa: E402
    InversePlan,
    LandedIncident,
)
from livespec_dev_tooling._incident_observer_types import RecoveryIntent  # noqa: E402
from livespec_dev_tooling._incident_recovery_git import LandedGit  # noqa: E402
from livespec_dev_tooling._incident_recovery_publication import (  # noqa: E402
    Publication,
    PublicationAttempt,
)
from livespec_dev_tooling.incident_inverse import plan_incident_inverse  # noqa: E402
from livespec_dev_tooling.incident_recovery_app import RecoveryForge  # noqa: E402

__all__: list[str] = ["RecoveryEffects"]

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_SUBMODULE = "160000"
# GitHub lists at most 250 commits of a pull, one hundred to a page.
_COMMIT_PAGE_SIZE = 100
_COMMIT_LISTING_PAGES = 3


def _object(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _merged_pull(*, pull: dict[str, Any], intent: RecoveryIntent, branch: str) -> int | None:
    """The landed commit count of an armed pull the forge merged at the registered SHA."""
    arm, base, head = intent.observer_arm, _object(value=pull.get("base")), pull.get("head")
    count = pull.get("commits")
    if (
        arm is None
        or pull.get("merged") is not True
        or pull.get("merge_commit_sha") != intent.registration.head_sha
        or base.get("ref") != branch
        or _object(value=head).get("sha") != arm.head_sha
        or type(count) is not int
        or count < 1
    ):
        return None
    return count


@dataclass(frozen=True, kw_only=True)
class RecoveryEffects:
    """The recovery App's forge access joined to the independent reference clone."""

    forge: RecoveryForge
    root: Path
    branch: str = "master"

    def head(self) -> str | None:
        """Master's authoritative head as the forge reports it, fetched locally."""
        status, value = self.forge.request(method="GET", path=f"git/ref/heads/{self.branch}")
        sha = _object(value=_object(value=value).get("object")).get("sha")
        if status != _HTTP_OK or not isinstance(sha, str):
            return None
        LandedGit.fetch(root=self.root, branch=self.branch)
        return sha

    def landed(self, *, intent: RecoveryIntent) -> LandedIncident | None:
        """The complete landed scope of the armed pull, or None when it cannot be proven."""
        arm = intent.observer_arm
        if arm is None:
            return None
        status, pull = self.forge.request(method="GET", path=f"pulls/{arm.pr_number}")
        count = _merged_pull(pull=_object(value=pull), intent=intent, branch=self.branch)
        if status != _HTTP_OK or count is None:
            return None
        LandedGit.fetch(root=self.root, branch=self.branch)
        merge = intent.registration.head_sha
        facts = LandedGit.facts(root=self.root, merge_sha=merge, count=count)
        if self._pull_messages(number=arm.pr_number) != facts.messages:
            return None
        scope = LandedIncident(
            repository=intent.registration.repository,
            pr_number=arm.pr_number,
            original_base_sha=arm.base_sha,
            original_head_sha=arm.head_sha,
            before_sha=facts.before_sha,
            merge_sha=merge,
            landed_commits=facts.landed_commits,
            landed_trees=facts.landed_trees,
            patch_sha256=facts.patch_sha256,
            changed_paths=facts.changed_paths,
            authority_sha256=hashlib.sha256(intent.registration.authority_receipt).hexdigest(),
        )
        return (
            scope if scope_matches_git(root=self.root, scope=scope, expected_head=merge) else None
        )

    def _pull_messages(self, *, number: int) -> tuple[str, ...] | None:
        """The armed pull's own commit messages; a rebase merge lands each one in order.

        The listing answers at most one hundred commits a page, so every page is read until
        a short one. The forge lists no more than `_COMMIT_LISTING_PAGES` pages for a pull;
        a longer pull reads as incomplete and cannot match its landed chain.
        """
        messages: list[str] = []
        for page in range(1, _COMMIT_LISTING_PAGES + 1):
            suffix = "" if page == 1 else f"&page={page}"
            status, listed = self.forge.request(
                method="GET", path=f"pulls/{number}/commits?per_page={_COMMIT_PAGE_SIZE}{suffix}"
            )
            if status != _HTTP_OK or not isinstance(listed, list):
                return None
            rows = cast("list[object]", listed)
            texts = [_object(value=_object(value=row).get("commit")).get("message") for row in rows]
            if not all(isinstance(text, str) for text in texts):
                return None
            messages.extend(cast("str", text).strip() for text in texts)
            if len(rows) < _COMMIT_PAGE_SIZE:
                break
        return tuple(messages)

    def landed_on(self, *, commit: str) -> bool | None:
        """Whether `commit` is on master: True, False, or None when unobserved."""
        status, value = self.forge.request(method="GET", path=f"compare/{commit}...{self.branch}")
        relation = _object(value=value).get("status")
        if status == _HTTP_NOT_FOUND:
            return False
        if status != _HTTP_OK or relation not in {"identical", "ahead", "behind", "diverged"}:
            return None
        return relation in {"identical", "ahead"}

    def settle(self, *, publication: Publication) -> Publication:
        """Resolve a prepared attempt from forge facts: landed, provably inert, or still open."""
        attempt = cast("PublicationAttempt", publication.open_attempt)
        commit = cast("str", attempt.commit)
        landed = self.landed_on(commit=commit)
        if landed:
            return publication.committed(merge_sha=commit, tree_sha=attempt.tree_sha)
        head = None if landed is None else self.head()
        if head is None or head == attempt.expected_head:
            return publication
        return publication.with_attempt(attempt=replace(attempt, status="head-moved"))

    def overlaps(self, *, scope: LandedIncident, head: str) -> bool:
        """True only when the complete inverse genuinely conflicts with work at `head`."""
        planned = plan_incident_inverse(repo_root=self.root, scope=scope, expected_head=head)
        return not is_successful(planned) and (
            unsafe_perform_io(planned.failure()).code == "rollback-conflict"
        )

    def prepare(self, *, plan: InversePlan, message: str) -> str | None:
        """Create the verified inverse tree and its commit; master does not move."""
        status, parent = self.forge.request(method="GET", path=f"git/commits/{plan.expected_head}")
        base_tree = _object(value=_object(value=parent).get("tree")).get("sha")
        entries = [
            self._entry(path=change.path, mode=change.mode, sha=change.sha)
            for change in LandedGit.changes(
                root=self.root, base=plan.expected_head, tree=plan.tree_sha
            )
        ]
        if status != _HTTP_OK or not isinstance(base_tree, str) or None in entries:
            return None
        status, tree = self.forge.request(
            method="POST", path="git/trees", value={"base_tree": base_tree, "tree": entries}
        )
        if status != _HTTP_CREATED or _object(value=tree).get("sha") != plan.tree_sha:
            return None
        status, commit = self.forge.request(
            method="POST",
            path="git/commits",
            value={"message": message, "tree": plan.tree_sha, "parents": [plan.expected_head]},
        )
        sha = _object(value=commit).get("sha")
        return sha if status == _HTTP_CREATED and isinstance(sha, str) else None

    def advance(self, *, commit: str) -> Literal["moved", "rejected", "unknown"]:
        """Move master to `commit` only as a fast-forward; never forced."""
        status, _ = self.forge.request(
            method="PATCH",
            path=f"git/refs/heads/{self.branch}",
            value={"sha": commit, "force": False},
        )
        if status == _HTTP_OK:
            return "moved"
        return "rejected" if status == _HTTP_UNPROCESSABLE else "unknown"

    def _entry(self, *, path: str, mode: str, sha: str | None) -> dict[str, object] | None:
        if sha is None or mode == _SUBMODULE:
            kind = "commit" if mode == _SUBMODULE else "blob"
            return {"path": path, "mode": mode, "type": kind, "sha": sha}
        data = LandedGit.blob(root=self.root, sha=sha)
        try:
            return {"path": path, "mode": mode, "type": "blob", "content": data.decode("utf-8")}
        except UnicodeDecodeError:
            status, created = self.forge.request(
                method="POST",
                path="git/blobs",
                value={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
            )
        if status != _HTTP_CREATED or _object(value=created).get("sha") != sha:
            return None
        return {"path": path, "mode": mode, "type": "blob", "sha": sha}
