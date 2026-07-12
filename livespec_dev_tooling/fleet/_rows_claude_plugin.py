"""Claude-plugin session-start currency obligation row for the fleet contract.

The `claude-plugin-currency` committed-file obligation (livespec v108
§"Fleet membership contract"): a member's `.claude/settings.json`
SessionStart must wire `mise exec -- just ensure-plugins` and the
justfile must carry the standard shared ensure-plugins wrapper, OR the
settings must explicitly declare a documented `livespecPluginCurrencySuccessor`
mechanism. Each leg distinguishes definitive absence (finding) from
can't-read (skip) so a permission-limited token never produces a false
red. Extracted from `_rows_files.py` (its own cohesive cluster); the
other committed-file rows stay there.
"""

from __future__ import annotations

import json
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

__all__: list[str] = [
    "CLAUDE_SETTINGS",
    "assert_claude_plugin_currency",
]


CLAUDE_SETTINGS = ".claude/settings.json"

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


def _claude_settings_presence_outcome(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Pass when `.claude/settings.json` is definitively present and readable."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if CLAUDE_SETTINGS in tree.paths:
        return RowPass()
    if tree.truncated:
        return RowSkip(reason=f"{member.repo}: tree truncated; {CLAUDE_SETTINGS} not definitive")
    return RowFinding(message=f"{member.repo}: required file {CLAUDE_SETTINGS} missing")


def _settings_currency_outcome(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Pass when settings carry either the hook or an explicit successor."""
    settings_text = ctx.file_text(repo=member.repo, path=CLAUDE_SETTINGS)
    if settings_text is None:
        return RowSkip(reason=f"{member.repo}: {CLAUDE_SETTINGS} unreadable")
    settings = _settings_payload(settings_text=settings_text)
    if settings is None:
        return RowFinding(message=f"{member.repo}: {CLAUDE_SETTINGS} is not parseable JSON object")
    if _has_documented_currency_successor(settings=settings):
        return RowPass()
    if _has_ensure_plugins_session_start(settings=settings):
        return RowSkip(reason=_WRAPPER_VERIFICATION_REQUIRED)
    return RowFinding(
        message=(
            f"{member.repo}: SessionStart does not invoke "
            "`mise exec -- just ensure-plugins` and no documented successor is declared"
        )
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
            )
        )
    if tree.truncated:
        return RowSkip(reason=f"{member.repo}: tree truncated; justfile not definitive")
    return RowFinding(message=f"{member.repo}: justfile missing; ensure-plugins wrapper absent")


def assert_claude_plugin_currency(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """SessionStart wires plugin currency, or settings document its successor."""
    return _claude_plugin_currency_outcome(ctx=ctx, member=member)


def _claude_plugin_currency_outcome(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The undemoted row outcome: settings hook or successor, then wrapper."""
    presence = _claude_settings_presence_outcome(ctx=ctx, member=member)
    if not isinstance(presence, RowPass):
        return presence
    settings = _settings_currency_outcome(ctx=ctx, member=member)
    if isinstance(settings, RowSkip) and settings.reason == _WRAPPER_VERIFICATION_REQUIRED:
        return _justfile_currency_outcome(ctx=ctx, member=member)
    return settings
