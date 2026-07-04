"""Committed-file obligation rows for the fleet-membership contract.

Each row asserts one committed-file fact about a member's `master`
tree from the central vantage point (livespec v108 §"Fleet membership
contract", obligation type "committed files"): the CI workflow, the
three pin-and-bump shim workflows, copier-answers for template-born
classes, the dev-tooling pin, and the no-tracked-gitlinks row. Every
assert distinguishes definitive absence (finding) from can't-read
(skip) so a permission-limited token never produces a false red.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import tomli  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "BUMP_PIN_WORKFLOW",
    "CI_WORKFLOW",
    "CLAUDE_SETTINGS",
    "COPIER_ANSWERS",
    "PIN_FRESHNESS_WORKFLOW",
    "RELEASE_DISPATCH_WORKFLOW",
    "assert_bump_pin_workflow",
    "assert_ci_workflow",
    "assert_claude_plugin_currency",
    "assert_copier_answers",
    "assert_dev_tooling_pin",
    "assert_no_tracked_gitlinks",
    "assert_pin_freshness_workflow",
    "assert_release_dispatch_workflow",
]


CI_WORKFLOW = ".github/workflows/ci.yml"
BUMP_PIN_WORKFLOW = ".github/workflows/bump-pin-from-dispatch.yml"
PIN_FRESHNESS_WORKFLOW = ".github/workflows/pin-freshness.yml"
RELEASE_DISPATCH_WORKFLOW = ".github/workflows/release-dispatch.yml"
COPIER_ANSWERS = ".copier-answers.yml"
CLAUDE_SETTINGS = ".claude/settings.json"

_DEV_TOOLING_REPO = "livespec-dev-tooling"


def _tree_path_outcome(*, ctx: FleetContext, member: FleetMember, path: str) -> RowOutcome:
    """Pass when `path` exists in the member's master tree; finding when absent."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if path in tree.paths:
        return RowPass()
    if tree.truncated:
        # A truncated recursive tree cannot prove absence; can't-read
        # (here: can't-read-completely) never produces a false red.
        return RowSkip(reason=f"{member.repo}: tree truncated; absence of {path} not definitive")
    return RowFinding(message=f"{member.repo}: required file {path} missing from master")


def assert_ci_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`ci.yml` present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=CI_WORKFLOW)


def assert_bump_pin_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`bump-pin-from-dispatch.yml` shim present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=BUMP_PIN_WORKFLOW)


def assert_pin_freshness_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`pin-freshness.yml` shim present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=PIN_FRESHNESS_WORKFLOW)


def assert_release_dispatch_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`release-dispatch.yml` shim present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=RELEASE_DISPATCH_WORKFLOW)


def assert_copier_answers(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`.copier-answers.yml` present on master (template-born classes)."""
    return _tree_path_outcome(ctx=ctx, member=member, path=COPIER_ANSWERS)


_STANDARD_ENSURE_PLUGINS_COMMAND = (
    "mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins"
)
_WRAPPER_VERIFICATION_REQUIRED = "settings require justfile wrapper verification"


def _settings_payload(*, settings_text: str) -> dict[str, object] | None:
    """Parsed `.claude/settings.json`, or None when it is not an object."""
    try:
        parsed = json.loads(settings_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _has_documented_currency_successor(*, settings: dict[str, object]) -> bool:
    """True when settings explicitly document the successor currency mechanism."""
    successor = settings.get("livespecPluginCurrencySuccessor")
    if not isinstance(successor, dict):
        return False
    successor_map = cast("dict[str, object]", successor)
    mechanism = successor_map.get("mechanism")
    documented_in = successor_map.get("documentedIn")
    return (
        isinstance(mechanism, str)
        and bool(mechanism.strip())
        and isinstance(documented_in, str)
        and bool(documented_in.strip())
    )


def _session_start_commands(*, settings: dict[str, object]) -> tuple[str, ...]:
    """Command hooks registered for SessionStart in `.claude/settings.json`."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return ()
    session_start = cast("dict[str, object]", hooks).get("SessionStart")
    if not isinstance(session_start, list):
        return ()
    commands: list[str] = []
    for entry in cast("list[object]", session_start):
        if not isinstance(entry, dict):
            continue
        nested = cast("dict[str, object]", entry).get("hooks")
        if not isinstance(nested, list):
            continue
        for hook in cast("list[object]", nested):
            if not isinstance(hook, dict):
                continue
            command = cast("dict[str, object]", hook).get("command")
            if isinstance(command, str):
                commands.append(command)
    return tuple(commands)


def _has_ensure_plugins_session_start(*, settings: dict[str, object]) -> bool:
    """True when SessionStart invokes the project ensure-plugins recipe."""
    return "mise exec -- just ensure-plugins" in _session_start_commands(settings=settings)


def _has_standard_ensure_plugins_recipe(*, justfile_text: str) -> bool:
    """True when `ensure-plugins` is the standard shared-wrapper recipe."""
    lines = justfile_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "ensure-plugins:" or line.startswith((" ", "\t")):
            continue
        body: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate and not candidate.startswith((" ", "\t")):
                break
            stripped = candidate.strip()
            if stripped and not stripped.startswith("#"):
                body.append(stripped)
        return body == [_STANDARD_ENSURE_PLUGINS_COMMAND]
    return False


# Currency findings are WARNING severity until the fleet-plugin-currency
# wiring fan-out lands the standard wrapper in every member;
# livespec-dev-tooling-h7z flips this back to "error".
_CURRENCY_SEVERITY = "warning"


def _claude_settings_presence_outcome(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Pass when `.claude/settings.json` is definitively present and readable."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if CLAUDE_SETTINGS in tree.paths:
        return RowPass()
    if tree.truncated:
        return RowSkip(reason=f"{member.repo}: tree truncated; {CLAUDE_SETTINGS} not definitive")
    return RowFinding(
        message=f"{member.repo}: required file {CLAUDE_SETTINGS} missing",
        severity=_CURRENCY_SEVERITY,
    )


def _settings_currency_outcome(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Pass when settings carry either the hook or an explicit successor."""
    settings_text = ctx.file_text(repo=member.repo, path=CLAUDE_SETTINGS)
    if settings_text is None:
        return RowSkip(reason=f"{member.repo}: {CLAUDE_SETTINGS} unreadable")
    settings = _settings_payload(settings_text=settings_text)
    if settings is None:
        return RowFinding(
            message=f"{member.repo}: {CLAUDE_SETTINGS} is not parseable JSON object",
            severity=_CURRENCY_SEVERITY,
        )
    if _has_documented_currency_successor(settings=settings):
        return RowPass()
    if _has_ensure_plugins_session_start(settings=settings):
        return RowSkip(reason=_WRAPPER_VERIFICATION_REQUIRED)
    return RowFinding(
        message=(
            f"{member.repo}: SessionStart does not invoke "
            "`mise exec -- just ensure-plugins` and no documented successor is declared"
        ),
        severity=_CURRENCY_SEVERITY,
    )


def _justfile_currency_outcome(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Pass when justfile carries the standard shared ensure-plugins wrapper."""
    tree = ctx.tree(repo=member.repo)
    if "justfile" in tree.paths:
        justfile_text = ctx.file_text(repo=member.repo, path="justfile")
        if justfile_text is None:
            return RowSkip(reason=f"{member.repo}: justfile unreadable")
        if _has_standard_ensure_plugins_recipe(justfile_text=justfile_text):
            return RowPass()
        return RowFinding(
            message=(
                f"{member.repo}: ensure-plugins recipe is not the standard wrapper "
                f"`{_STANDARD_ENSURE_PLUGINS_COMMAND}`"
            ),
            severity=_CURRENCY_SEVERITY,
        )
    if tree.truncated:
        return RowSkip(reason=f"{member.repo}: tree truncated; justfile not definitive")
    return RowFinding(
        message=f"{member.repo}: justfile missing; ensure-plugins wrapper absent",
        severity=_CURRENCY_SEVERITY,
    )


def assert_claude_plugin_currency(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """SessionStart wires plugin currency, or settings document its successor."""
    presence = _claude_settings_presence_outcome(ctx=ctx, member=member)
    if not isinstance(presence, RowPass):
        return presence
    settings = _settings_currency_outcome(ctx=ctx, member=member)
    if isinstance(settings, RowSkip) and settings.reason == _WRAPPER_VERIFICATION_REQUIRED:
        return _justfile_currency_outcome(ctx=ctx, member=member)
    return settings


def assert_no_tracked_gitlinks(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """No mode-160000 (gitlink) entries on master — the fleet uses no submodules."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if tree.gitlink_paths:
        joined = ", ".join(tree.gitlink_paths)
        return RowFinding(message=f"{member.repo}: tracked gitlink(s) on master: {joined}")
    if tree.truncated:
        return RowSkip(reason=f"{member.repo}: tree truncated; gitlink absence not definitive")
    return RowPass()


def _pinned_tag(*, pyproject_text: str) -> str | None:
    """The `[tool.uv.sources].livespec-dev-tooling.tag` value, or None."""
    try:
        data: dict[str, object] = tomli.loads(pyproject_text)
    except tomli.TOMLDecodeError:
        return None
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    uv = cast("dict[str, object]", tool).get("uv")
    if not isinstance(uv, dict):
        return None
    sources = cast("dict[str, object]", uv).get("sources")
    if not isinstance(sources, dict):
        return None
    entry = cast("dict[str, object]", sources).get(_DEV_TOOLING_REPO)
    if not isinstance(entry, dict):
        return None
    tag = cast("dict[str, object]", entry).get("tag")
    return tag if isinstance(tag, str) else None


def _locked_tag(*, uv_lock_text: str) -> str | None:
    """The committed `uv.lock` git tag locked for livespec-dev-tooling, or None.

    `uv.lock` is TOML: a `[[package]]` array where the dev-tooling entry
    carries `source = { git = "…/livespec-dev-tooling.git?tag=vX.Y.Z#<sha>" }`.
    Returns the `tag=` query value, or None when the lock is unparseable,
    carries no such package, or the package is not a git-tag source.
    """
    try:
        data: dict[str, object] = tomli.loads(uv_lock_text)
    except tomli.TOMLDecodeError:
        return None
    packages = data.get("package")
    if not isinstance(packages, list):
        return None
    for pkg in cast("list[object]", packages):
        if not isinstance(pkg, dict):
            continue
        if cast("dict[str, object]", pkg).get("name") != _DEV_TOOLING_REPO:
            continue
        source = cast("dict[str, object]", pkg).get("source")
        if not isinstance(source, dict):
            return None
        git = cast("dict[str, object]", source).get("git")
        if not isinstance(git, str):
            return None
        match = re.search(r"[?&]tag=([^#&]+)", git)
        return match.group(1) if match else None
    return None


def _latest_dev_tooling_tag(*, ctx: FleetContext) -> str | None:
    """`livespec-dev-tooling`'s latest release tag, or None when unreadable."""
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{_DEV_TOOLING_REPO}/releases/latest")
    if not isinstance(payload, dict):
        return None
    tag = cast("dict[str, object]", payload).get("tag_name")
    return tag if isinstance(tag, str) else None


def _freshness_outcome(*, ctx: FleetContext, member: FleetMember, tag: str) -> RowOutcome:
    """Staleness leg of the pin row — WARNING severity only.

    Freshness has its own dedicated repo-local mechanism
    (`pin-freshness.yml` + bump-PR automation); failing the fleet on a
    not-yet-merged bump PR would gate the release fan-out on its own
    downstream effect, so a stale pin warns rather than reds the fleet.
    """
    latest = _latest_dev_tooling_tag(ctx=ctx)
    if latest is None:
        return RowPass(note="pin present; freshness unverified (latest release unreadable)")
    if tag != latest:
        return RowFinding(
            message=f"{member.repo}: dev-tooling pin {tag} is stale (latest release {latest})",
            severity="warning",
        )
    return RowPass()


def _lock_outcome(*, ctx: FleetContext, member: FleetMember, tag: str) -> RowFinding | None:
    """Lock-lockstep leg — ERROR severity on a definitive committed uv.lock<->pin mismatch.

    The committed `uv.lock` MUST pin the same livespec-dev-tooling tag as
    `pyproject.toml`'s `[tool.uv.sources]` entry. The automated bump path's
    pre-rewrite `uv sync` re-locks against the OLD pin, so without a
    post-rewrite re-lock the committed lock lags the pin by one release
    (livespec-glv6). Returns a finding ONLY on a definitive mismatch;
    returns None — deferring to the freshness leg — when the lock is
    absent, unreadable, or carries no git-tag source (never a false red).
    """
    tree = ctx.tree(repo=member.repo)
    if "uv.lock" not in tree.paths:
        return None
    text = ctx.file_text(repo=member.repo, path="uv.lock")
    if text is None:
        return None
    locked = _locked_tag(uv_lock_text=text)
    if locked is None:
        return None
    if locked != tag:
        return RowFinding(
            message=(
                f"{member.repo}: committed uv.lock pins dev-tooling {locked} but "
                f"pyproject pins {tag} — run "
                f"'uv lock --refresh-package {_DEV_TOOLING_REPO}' and commit the lock"
            )
        )
    return None


def assert_dev_tooling_pin(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """A `[tool.uv.sources]` pin on livespec-dev-tooling exists; lock matches; staleness warns.

    Presence is the hard obligation (error severity); the committed
    `uv.lock` MUST lock the same tag the pin names (`_lock_outcome`,
    error severity, livespec-glv6); the staleness leg is delegated to
    `_freshness_outcome` (warning severity).
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if "pyproject.toml" not in tree.paths:
        if tree.truncated:
            return RowSkip(reason=f"{member.repo}: tree truncated; pyproject.toml not definitive")
        return RowFinding(message=f"{member.repo}: no pyproject.toml — dev-tooling pin missing")
    text = ctx.file_text(repo=member.repo, path="pyproject.toml")
    if text is None:
        return RowSkip(reason=f"{member.repo}: pyproject.toml unreadable")
    tag = _pinned_tag(pyproject_text=text)
    if tag is None:
        return RowFinding(
            message=(
                f"{member.repo}: no [tool.uv.sources] {_DEV_TOOLING_REPO} tag pin in pyproject.toml"
            )
        )
    # Lock-lockstep leg (error) takes precedence over the freshness leg
    # (warning); a single tail return keeps the function within the
    # max-returns budget.
    lock_finding = _lock_outcome(ctx=ctx, member=member, tag=tag)
    return (
        lock_finding
        if lock_finding is not None
        else _freshness_outcome(ctx=ctx, member=member, tag=tag)
    )
