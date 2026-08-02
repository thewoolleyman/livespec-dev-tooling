"""Reconcile logic for the fleet-membership contract (`wire-fleet-member`).

The wiring side of the shared contract definition (livespec v108
section "Fleet membership contract", "assert mode is CI; reconcile mode is
wiring"): push the required secret NAMES from the operator's
1Password-wrapper-provided environment (values flow env→stdin, never
argv / logs / outcomes), set branch protection derived from the
member's own ci.yml matrix, apply the `livespec-sibling` topic, and
open one shim-workflow PR for any missing pin-and-bump shims. Every
operation is idempotent — re-running against an already-wired member
changes nothing. None of it depends on a dev-tooling release going
out (the no-circular-gating rule).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    GhOutcome,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    gh_answer,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._rows_github import (  # noqa: E402
    REQUIRED_MERGE_SETTINGS,
    REQUIRED_SECRET_NAMES,
    SIBLING_TOPIC,
    member_matrix_targets,
)

__all__: list[str] = [
    "reconcile_branch_protection",
    "reconcile_delete_branch_on_merge",
    "reconcile_merge_settings",
    "reconcile_secret_names",
    "reconcile_topic",
]


_SECRET_SOURCE_ENV_NAMES: dict[str, tuple[str, ...]] = {
    "APP_ID": ("GITHUB_APP_ID", "APP_ID"),
    "APP_PRIVATE_KEY": ("GITHUB_PRIVATE_KEY", "APP_PRIVATE_KEY"),
}


_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN ((?:[A-Z0-9]+ )*PRIVATE KEY)-----(.*?)-----END \1-----",
    re.DOTALL,
)


def _rewrap_pem(*, value: str) -> str:
    """Re-wrap a PEM private key to canonical 64-column lines (idempotent).

    The 1Password Environment stores the App key un-wrapped (single-line), and
    `op run` cannot be relied on to preserve interior newlines. A GitHub Actions
    secret set from that raw value fails to decode (`DECODER routines`). Extract
    the base64 body, strip all whitespace, and re-emit a canonical 64-column PEM
    so the minted-token step can parse it. A non-PEM value (e.g. APP_ID) has no
    match and passes through unchanged; an already-wrapped PEM re-wraps to itself.
    """
    match = _PEM_PRIVATE_KEY_RE.search(value)
    if match is None:
        return value
    label = match.group(1)
    body = re.sub(r"\s+", "", match.group(2))
    wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN {label}-----\n{wrapped}\n-----END {label}-----\n"


def _secret_value_from_env(*, destination_name: str) -> str | None:
    """Resolve the source env value for one destination Actions secret name."""
    for source_name in _SECRET_SOURCE_ENV_NAMES[destination_name]:
        value = os.environ.get(source_name)
        if value is not None:
            return value
    return None


def _gh_failed(*, outcome: GhOutcome, note: str) -> RowFinding | None:
    """The finding for a `gh` that never ran or ran and exited non-zero, else None.

    `note` describes the OPERATION that did not take effect, which is the
    right diagnostic only for a `gh` that ran and refused. A `gh` that never
    ran gets the seam's own reason instead: "applying the topic failed" is a
    claim about the member, and nothing was asked of the member at all.
    """
    answer = gh_answer(outcome=outcome)
    if isinstance(answer, InvocationNotPerformed):
        return RowFinding(message=answer.reason)
    return None if answer.returncode == 0 else RowFinding(message=note)


def reconcile_secret_names(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Push APP_ID + APP_PRIVATE_KEY from env via `gh secret set` (stdin only).

    The operator invokes wire-fleet-member under the 1Password
    environment wrapper, which projects the canonical values as
    GITHUB_APP_ID and GITHUB_PRIVATE_KEY. Those source env vars flow
    to GitHub via stdin under the destination secret names APP_ID and
    APP_PRIVATE_KEY, with the destination names also accepted as a
    back-compat fallback. Values are never echoed.
    """
    for name in REQUIRED_SECRET_NAMES:
        value = _secret_value_from_env(destination_name=name)
        if value is None:
            source_names = ", ".join(_SECRET_SOURCE_ENV_NAMES[name])
            return RowFinding(
                message=(
                    f"{member.repo}: env var(s) {source_names} absent — invoke under "
                    "with-livespec-env.sh so the 1Password projection provides them"
                )
            )
        value = _rewrap_pem(value=value)
        failure = _gh_failed(
            outcome=ctx.run_gh(
                args=["secret", "set", name, "--repo", f"{ctx.owner}/{member.repo}"],
                stdin=value,
            ),
            note=f"{member.repo}: gh secret set {name} failed",
        )
        if failure is not None:
            return failure
    return RowPass(note="secrets pushed from env (values via stdin, never logged)")


def reconcile_topic(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Apply the `livespec-sibling` topic, preserving existing topics."""
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}/topics")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: topics unreadable; cannot reconcile")
    names_raw = cast("dict[str, object]", payload).get("names")
    if not isinstance(names_raw, list):
        return RowSkip(reason=f"{member.repo}: topics payload shape unexpected")
    names = [entry for entry in cast("list[object]", names_raw) if isinstance(entry, str)]
    if SIBLING_TOPIC in names:
        return RowPass(note="topic already present")
    body = json.dumps({"names": [*names, SIBLING_TOPIC]})
    failure = _gh_failed(
        outcome=ctx.api(path=f"repos/{ctx.owner}/{member.repo}/topics", method="PUT", body=body),
        note=f"{member.repo}: applying {SIBLING_TOPIC} topic failed",
    )
    if failure is not None:
        return failure
    return RowPass(note=f"applied {SIBLING_TOPIC} topic")


def reconcile_branch_protection(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Set default-branch protection from the member's own ci.yml matrix.

    The PUT targets the member's resolved default branch via the same
    memoized `FleetContext.canonical_ref` the read path uses, so reads
    and writes can never diverge for a repo (livespec-dev-tooling-17o):
    a hardcoded `master` PUT against a main-default repo would configure
    protection for a branch that does not exist, leaving the real
    default branch wide open.
    """
    targets = member_matrix_targets(ctx=ctx, member=member)
    if isinstance(targets, IOFailure):
        # A can't-read is not a member defect, and telling the operator to
        # hand-configure branch protection because ONE read failed sends
        # them to do manual work a re-run would make unnecessary.
        return RowSkip(
            reason=(
                f"{member.repo}: cannot derive required checks "
                f"({unsafe_perform_io(targets.failure()).detail})"
            )
        )
    matrix = unsafe_perform_io(targets.unwrap())
    if not matrix:
        return RowFinding(
            message=(
                f"{member.repo}: cannot derive required checks (ci.yml declares no "
                "matrix targets); set branch protection manually"
            )
        )
    body = json.dumps(
        {
            "required_status_checks": {"strict": False, "contexts": sorted(matrix)},
            "enforce_admins": True,
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
    )
    failure = _gh_failed(
        outcome=ctx.api(
            path=(
                f"repos/{ctx.owner}/{member.repo}/branches/"
                f"{ctx.canonical_ref(repo=member.repo)}/protection"
            ),
            method="PUT",
            body=body,
        ),
        note=f"{member.repo}: setting branch protection failed",
    )
    if failure is not None:
        return failure
    return RowPass(note="branch protection set (strict=off + enforce_admins + ci matrix checks)")


def reconcile_merge_settings(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Set repo-level merge settings to rebase-only (+ auto-merge enabled).

    PATCHes the repo object with the fleet-mandated merge-strategy
    flags (livespec NFR section "Commit and merge discipline"): merge-commit
    and squash-merge OFF, rebase-merge ON, auto-merge ON. Idempotent —
    re-PATCHing an already-rebase-only repo changes nothing.
    """
    body = json.dumps(dict(REQUIRED_MERGE_SETTINGS))
    failure = _gh_failed(
        outcome=ctx.api(path=f"repos/{ctx.owner}/{member.repo}", method="PATCH", body=body),
        note=f"{member.repo}: setting merge settings failed",
    )
    if failure is not None:
        return failure
    return RowPass(note="merge settings set (rebase-only + auto-merge)")


def reconcile_delete_branch_on_merge(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Enable automatic deletion of merged PR head branches for the member repo."""
    body = json.dumps({"delete_branch_on_merge": True})
    answer = gh_answer(
        outcome=ctx.api(path=f"repos/{ctx.owner}/{member.repo}", method="PATCH", body=body)
    )
    if isinstance(answer, InvocationNotPerformed):
        return RowFinding(message=answer.reason)
    if answer.returncode != 0:
        command = (
            f"gh api repos/{ctx.owner}/{member.repo} --method PATCH "
            "--input - <<< '{\"delete_branch_on_merge\":true}'"
        )
        return RowFinding(
            message=(
                f"{member.repo}: setting delete_branch_on_merge failed; re-run "
                "wire-fleet-member with a token that has GitHub repository "
                "Administration permission, or run: "
                f"{command}"
            )
        )
    return RowPass(note="delete_branch_on_merge enabled")
