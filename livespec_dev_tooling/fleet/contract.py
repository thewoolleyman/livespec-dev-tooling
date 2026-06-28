"""The shared fleet-membership contract definition (manifest + obligation table).

ONE definition consumed by BOTH modes (livespec v108 §"Fleet
membership contract": "assert mode is CI; reconcile mode is wiring"):
`fleet_conformance` walks `OBLIGATION_ROWS` calling each row's
`assert_member`; `wire_fleet_member` walks the SAME rows calling
`reconcile` where the fix is machine-applicable (and surfacing
`manual_hint` where it is not — App installation, ci.yml authoring,
gitlink removal). The table is statically enumerated with explicit
typed imports so the type checker sees every dispatch target.

`parse_manifest` parses livespec core's `.livespec-fleet-manifest.jsonc` (the
committed member list, fetched from livespec master at run time).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._context import Adopter, FleetContext, FleetMember, RowOutcome
from livespec_dev_tooling.fleet._local_context import LocalContext
from livespec_dev_tooling.fleet._reconcile import (
    reconcile_branch_protection,
    reconcile_merge_settings,
    reconcile_secret_names,
    reconcile_shim_workflows,
    reconcile_topic,
)
from livespec_dev_tooling.fleet._rows_baseline import assert_baseline_harnesses
from livespec_dev_tooling.fleet._rows_beads import assert_tenant_connection_consistency
from livespec_dev_tooling.fleet._rows_files import (
    assert_bump_pin_workflow,
    assert_ci_workflow,
    assert_copier_answers,
    assert_dev_tooling_pin,
    assert_no_tracked_gitlinks,
    assert_pin_freshness_workflow,
    assert_release_dispatch_workflow,
)
from livespec_dev_tooling.fleet._rows_github import (
    assert_app_installation,
    assert_branch_protection,
    assert_merge_settings,
    assert_secret_names,
    assert_topic,
)
from livespec_dev_tooling.fleet._rows_instructions import (
    assert_agent_ai_references_resolve,
    assert_agent_instruction_surface,
)
from livespec_dev_tooling.fleet._rows_local import (
    assert_commit_refuse_hooks,
    assert_git_notes_refspec,
    assert_worktree_root_trust,
    reconcile_beads_dir_perms,
    reconcile_claude_plugins,
    reconcile_codex_plugins,
    reconcile_commit_refuse_hooks,
    reconcile_git_notes_refspec,
    reconcile_mise_trust_install,
    reconcile_uv_sync,
    reconcile_worktree_root_trust,
)
from livespec_dev_tooling.fleet._rows_local_beads import (
    reconcile_beads_bd_binary,
    reconcile_beads_config_committed,
    reconcile_beads_dolt_server,
    reconcile_beads_metadata_present,
    reconcile_beads_tenant_secret,
)
from livespec_dev_tooling.fleet._rows_local_jsonc import reconcile_livespec_jsonc_complete

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "ADOPTER_POSTURES",
    "LOCAL_OBLIGATION_ROWS",
    "OBLIGATION_ROWS",
    "PROFILE_LAYERS",
    "REPO_CLASSES",
    "Adopter",
    "LocalObligationRow",
    "Manifest",
    "ObligationRow",
    "parse_manifest",
    "rows_for",
]


REPO_CLASSES = ("core", "enforcement-suite", "impl-plugin", "driver-plugin", "library", "console")

# The ordered profile layers an adopter may declare (the cumulative
# conformance partition: each layer adds obligations atop the prior).
PROFILE_LAYERS = ("baseline", "fleet-infra", "orchestrator-plugin", "app")
# The adoption postures an adopter may hold toward the fleet pins.
ADOPTER_POSTURES = ("released", "pinned", "none")

_ALL_CLASSES: frozenset[str] = frozenset(REPO_CLASSES)
# The classes participating in the pin-and-bump web — i.e. carrying the
# three shim workflows (bump-pin-from-dispatch / pin-freshness /
# release-dispatch). Every class EXCEPT the Control-Plane console: the
# console (livespec-console-beads-fabro) is a non-pin-consuming fleet
# member that carries the dev-tooling pin (see _DEV_TOOLING_PIN_CLASSES)
# but ships none of the shims, so its pin freshness is monitored centrally
# by the dev-tooling-pin row's warning-severity staleness leg rather than
# auto-bumped (livespec-dev-tooling contracts.md §"Bump-pin policy").
_PIN_WEB_CLASSES = _ALL_CLASSES - {"console"}
_TEMPLATE_BORN_CLASSES = frozenset({"impl-plugin"})
# The dev-tooling-pin row excludes only the enforcement-suite class —
# dev-tooling cannot pin itself; every other class, the console included,
# carries a [tool.uv.sources] livespec-dev-tooling tag pin.
_DEV_TOOLING_PIN_CLASSES = _ALL_CLASSES - {"enforcement-suite"}


class RowFn(Protocol):
    """One obligation-row operation (assert or reconcile) over a member."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> RowOutcome: ...


@dataclass(frozen=True, kw_only=True)
class ObligationRow:
    """One per-class obligation: assert logic plus its reconcile reference.

    `reconcile` is None where the fix is not machine-applicable from
    this vantage point; `manual_hint` then tells the operator what to
    do (the hint never gates anything the check itself gates — the
    no-circular-gating rule).
    """

    row_id: str
    obligation_type: str
    applies_to: frozenset[str]
    assert_member: RowFn
    reconcile: RowFn | None = None
    manual_hint: str = ""


OBLIGATION_ROWS: tuple[ObligationRow, ...] = (
    ObligationRow(
        row_id="workflow-ci",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_ci_workflow,
        manual_hint="author .github/workflows/ci.yml (no fleet-shipped template for this file)",
    ),
    ObligationRow(
        row_id="workflow-bump-pin-from-dispatch",
        obligation_type="committed-file",
        applies_to=_PIN_WEB_CLASSES,
        assert_member=assert_bump_pin_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-pin-freshness",
        obligation_type="committed-file",
        applies_to=_PIN_WEB_CLASSES,
        assert_member=assert_pin_freshness_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-release-dispatch",
        obligation_type="committed-file",
        applies_to=_PIN_WEB_CLASSES,
        assert_member=assert_release_dispatch_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="copier-answers",
        obligation_type="committed-file",
        applies_to=_TEMPLATE_BORN_CLASSES,
        assert_member=assert_copier_answers,
        manual_hint="re-scaffold from the copier template so .copier-answers.yml is committed",
    ),
    ObligationRow(
        row_id="dev-tooling-pin",
        obligation_type="committed-file",
        applies_to=_DEV_TOOLING_PIN_CLASSES,
        assert_member=assert_dev_tooling_pin,
        manual_hint=(
            "add a [tool.uv.sources] livespec-dev-tooling tag pin to pyproject.toml; "
            "the bump-pin automation maintains it thereafter"
        ),
    ),
    ObligationRow(
        row_id="no-tracked-gitlinks",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_no_tracked_gitlinks,
        manual_hint="remove the tracked gitlink (mode 160000) in a repo-local commit",
    ),
    ObligationRow(
        row_id="secret-names",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_secret_names,
        reconcile=reconcile_secret_names,
    ),
    ObligationRow(
        row_id="app-installation",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_app_installation,
        manual_hint="install the fleet GitHub App on the repo (owner settings → GitHub Apps)",
    ),
    ObligationRow(
        row_id="branch-protection",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_branch_protection,
        reconcile=reconcile_branch_protection,
    ),
    ObligationRow(
        row_id="merge-settings",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_merge_settings,
        reconcile=reconcile_merge_settings,
    ),
    ObligationRow(
        row_id="topic-livespec-sibling",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_topic,
        reconcile=reconcile_topic,
    ),
    ObligationRow(
        row_id="beads-tenant-connection-consistency",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_tenant_connection_consistency,
        manual_hint=(
            "reconcile .beads/config.yaml (dolt.* keys) and .livespec.jsonc's impl-plugin "
            "connection block so the five tenant-connection fields agree, in a repo-local commit"
        ),
    ),
    ObligationRow(
        row_id="agent-instruction-surface",
        obligation_type="committed-file",
        applies_to=_TEMPLATE_BORN_CLASSES,
        assert_member=assert_agent_instruction_surface,
        manual_hint=(
            "bring AGENTS.md up to the fleet-universal agent-instruction core and register the "
            "beads-access guard hook (.claude/hooks/beads-access-guard.sh) in "
            ".claude/settings.json, in a repo-local commit"
        ),
    ),
    ObligationRow(
        row_id="agent-ai-references-resolve",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_agent_ai_references_resolve,
        manual_hint=(
            "add the missing .ai/<topic>.md file(s) an AGENTS.md references, or remove the "
            "dangling reference, in a repo-local commit"
        ),
    ),
    ObligationRow(
        row_id="baseline-harnesses",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_baseline_harnesses,
        manual_hint=(
            "declare a non-empty `harnesses` object in .livespec.jsonc (Conformance "
            "Pattern concern #2 cross-harness plugin-resolution; zs22.7.7 M6)"
        ),
    ),
)


def rows_for(*, repo_class: str) -> tuple[ObligationRow, ...]:
    """The obligation rows that apply to `repo_class`."""
    return tuple(row for row in OBLIGATION_ROWS if repo_class in row.applies_to)


class LocalRowFn(Protocol):
    """One LOCAL-vantage obligation-row operation (assert or reconcile) over a checkout."""

    def __call__(self, *, ctx: LocalContext) -> RowOutcome: ...


@dataclass(frozen=True, kw_only=True)
class LocalObligationRow:
    """One LOCAL-vantage first-touch obligation: a reconcile + an optional drift assert.

    `assert_local` is None for pure provisioning rows (toolchain install,
    dependency sync, plugin registration, beads-dir hardening) that carry
    no persistent committed state a drift sweep can re-check; the verb
    runs their idempotent `reconcile_local` unconditionally. A row that
    leaves persistent state (the commit-refuse hooks, the notes refspec,
    the worktree-root mise-trust entry) carries a real `assert_local`, so
    the assert/drift side gains the matching local check for free and the
    verb reconciles only an unmet row.

    These rows run from the LOCAL vantage only (per
    `livespec/SPECIFICATION/non-functional-requirements.md`
    §"Governed-repo lifecycle"); the central rows (`OBLIGATION_ROWS`) run
    against the manifest from the GitHub vantage, and no row needs both.
    """

    row_id: str
    assert_local: LocalRowFn | None
    reconcile_local: LocalRowFn


LOCAL_OBLIGATION_ROWS: tuple[LocalObligationRow, ...] = (
    LocalObligationRow(
        row_id="mise-trust-install",
        assert_local=None,
        reconcile_local=reconcile_mise_trust_install,
    ),
    LocalObligationRow(
        row_id="uv-sync",
        assert_local=None,
        reconcile_local=reconcile_uv_sync,
    ),
    LocalObligationRow(
        row_id="commit-refuse-hooks",
        assert_local=assert_commit_refuse_hooks,
        reconcile_local=reconcile_commit_refuse_hooks,
    ),
    LocalObligationRow(
        row_id="git-notes-refspec",
        assert_local=assert_git_notes_refspec,
        reconcile_local=reconcile_git_notes_refspec,
    ),
    LocalObligationRow(
        row_id="worktree-root-mise-trust",
        assert_local=assert_worktree_root_trust,
        reconcile_local=reconcile_worktree_root_trust,
    ),
    LocalObligationRow(
        row_id="beads-dir-perms",
        assert_local=None,
        reconcile_local=reconcile_beads_dir_perms,
    ),
    LocalObligationRow(
        row_id="claude-plugins",
        assert_local=None,
        reconcile_local=reconcile_claude_plugins,
    ),
    LocalObligationRow(
        row_id="codex-plugins",
        assert_local=None,
        reconcile_local=reconcile_codex_plugins,
    ),
    # Config-completeness row (livespec-zs22.8 M6): GUARANTEES a harnesses-bearing
    # .livespec.jsonc and MACHINE-FILLS the beads `connection` block from
    # .beads/config.yaml. It carries no `assert_local` — its reconcile both detects
    # (an absent / unparseable / harnesses-less config, or an existing connection's
    # drift → a warning the operator resolves by hand, the `harnesses` statuses being
    # a human-judgment seam never fabricated) and machine-fixes (the non-secret
    # connection block; the tenant password stays the beads-tenant-secret row).
    LocalObligationRow(
        row_id="livespec-jsonc-complete",
        assert_local=None,
        reconcile_local=reconcile_livespec_jsonc_complete,
    ),
    # Beads-runtime detect-and-guide rows (livespec-zs22.8 M4): each PROBES one
    # ledger-backend prerequisite and, when unmet, emits a WARNING-severity guided
    # TODO the verb surfaces rather than fails on. All are gated on a `.beads/`
    # directory (a non-beads repo skips). They carry no `assert_local` — the probe
    # IS the reconcile (it cannot machine-fix a host/secret/runtime seam).
    LocalObligationRow(
        row_id="beads-bd-binary",
        assert_local=None,
        reconcile_local=reconcile_beads_bd_binary,
    ),
    LocalObligationRow(
        row_id="beads-dolt-server",
        assert_local=None,
        reconcile_local=reconcile_beads_dolt_server,
    ),
    LocalObligationRow(
        row_id="beads-tenant-secret",
        assert_local=None,
        reconcile_local=reconcile_beads_tenant_secret,
    ),
    LocalObligationRow(
        row_id="beads-config-committed",
        assert_local=None,
        reconcile_local=reconcile_beads_config_committed,
    ),
    LocalObligationRow(
        row_id="beads-metadata-present",
        assert_local=None,
        reconcile_local=reconcile_beads_metadata_present,
    ),
)


@dataclass(frozen=True, kw_only=True)
class Manifest:
    """The parsed fleet manifest: owner + the fleet member list + the adopters."""

    owner: str
    members: tuple[FleetMember, ...]
    adopters: tuple[Adopter, ...]

    def member_names(self) -> frozenset[str]:
        """The set of member repo names (for the discovery sweep)."""
        return frozenset(member.repo for member in self.members)


def _parse_member(*, entry: object) -> FleetMember | None:
    """One manifest member entry, or None when malformed."""
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    repo = record.get("repo")
    repo_class = record.get("class")
    if not isinstance(repo, str) or repo_class not in REPO_CLASSES:
        return None
    return FleetMember(repo=repo, repo_class=cast("str", repo_class))


def _parse_members(*, raw: object) -> tuple[FleetMember, ...] | None:
    """Parse the fleet member array; None when non-list, malformed, or duplicated."""
    if not isinstance(raw, list):
        return None
    members: list[FleetMember] = []
    for entry in cast("list[object]", raw):
        member = _parse_member(entry=entry)
        if member is None:
            return None
        members.append(member)
    if len({member.repo for member in members}) != len(members):
        return None
    return tuple(members)


def _parse_adopter(*, entry: object) -> Adopter | None:
    """One manifest adopter entry, or None when malformed."""
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    repo = record.get("repo")
    profile = record.get("profile")
    posture = record.get("posture")
    if not isinstance(repo, str) or not repo:
        return None
    if not isinstance(profile, list) or not profile:
        return None
    for layer in cast("list[object]", profile):
        if not isinstance(layer, str) or layer not in PROFILE_LAYERS:
            return None
    if not isinstance(posture, str) or posture not in ADOPTER_POSTURES:
        return None
    return Adopter(repo=repo, profile=tuple(cast("list[str]", profile)), posture=posture)


def _parse_adopters(*, raw: object) -> tuple[Adopter, ...] | None:
    """Parse the optional adopters array; () when absent, None when malformed."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return None
    adopters: list[Adopter] = []
    for entry in cast("list[object]", raw):
        adopter = _parse_adopter(entry=entry)
        if adopter is None:
            return None
        adopters.append(adopter)
    return tuple(adopters)


def parse_manifest(*, source: str) -> Manifest | None:
    """Parse `.livespec-fleet-manifest.jsonc` text; None when malformed.

    The fleet member array is read from the `fleet` key, falling back to
    the legacy `members` key when `fleet` is absent (the required-key
    migration seam: this parser accepts both before livespec core renames
    the manifest key). The optional `adopters` array, when present, parses
    into `Adopter` records; an absent `adopters` key yields an empty tuple.

    Malformed means: invalid JSONC, a non-object root, a non-string
    `owner`, a non-list fleet array (under either `fleet` or `members`),
    any malformed member entry (missing `repo`, unknown `class`),
    duplicate member repos, a present-but-non-list `adopters` value, or
    any malformed adopter entry (missing/empty `repo`, a `profile` that
    is not a non-empty list of known layers, or an unknown `posture`).
    """
    parser = jsoncomment.JsonComment()
    try:
        data = cast("object", parser.loads(source))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    mapping = cast("dict[str, object]", data)
    owner = mapping.get("owner")
    members_raw = mapping.get("fleet")
    if members_raw is None:
        members_raw = mapping.get("members")
    members = _parse_members(raw=members_raw)
    adopters = _parse_adopters(raw=mapping.get("adopters"))
    if not isinstance(owner, str) or members is None or adopters is None:
        return None
    return Manifest(owner=owner, members=members, adopters=adopters)
