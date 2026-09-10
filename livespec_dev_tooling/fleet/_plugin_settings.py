"""The derive-from-settings reader both harness provisioners share.

`ensure_plugins` (Claude) and `ensure_codex_plugins` (Codex) read DIFFERENT
committed files and emit DIFFERENT argv, but the half in between is one thing:
both read the same two keys — `extraKnownMarketplaces` and `enabledPlugins` —
and both reject the same three vacuity levels. That half lives here so the
Codex twin mirrors the Claude contract STRUCTURALLY rather than by a copied
body, which is the whole point of the collapse: a fifth vacuity level, or a
fourth enablement spelling, is then one edit rather than two that can drift.

The operator-facing label is a PARAMETER rather than a constant because the
only thing that differs between the two callers' findings is which committed
file the operator has to go edit. A finding that names the wrong harness's
settings file does not merely read oddly — it sends the reader to a file that
is already correct, which is worse than naming no file at all.

Every name here is PUBLIC despite the module being package-private: both
callers live in sibling modules, and a `_`-prefixed name crossing a module
boundary is refused by pyright strict (`reportPrivateUsage`) and by
`checks/private_calls` alike.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`.
# Both callers establish it, but neither is guaranteed to be the first import
# in a process that reaches this module, so it establishes the path itself.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_commands import (  # noqa: E402
    enabled_plugin_names,
)

__all__: list[str] = [
    "marketplace_of",
    "split_enablement",
    "vacuity_findings",
]


def marketplace_of(*, plugin: str) -> str:
    """The marketplace half of a `<plugin>@<marketplace>` key.

    Both harnesses spell an enablement key the same way, so the coverage
    question ("is anything from this marketplace enabled?") is answered
    identically for each.
    """
    _, _, marketplace = plugin.partition("@")
    return marketplace or plugin


def split_enablement(*, raw: object) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
    """(enabled, explicitly-disabled, shape-finding) from an enabledPlugins value.

    The legacy LIST spelling delegates to `enabled_plugin_names` and reads its
    failure TRACK, so an unreadable list can no longer arrive here as an empty
    name set. The mapping spelling is parsed here rather than delegated because
    this caller needs the split the seam deliberately does not make: an
    explicitly-`false` plugin is a DISABLE the vacuity findings below report on,
    and the seam answers only with what is enabled.
    """
    if raw is None:
        return ((), (), None)
    if isinstance(raw, list):
        names = enabled_plugin_names(raw=cast("list[object]", raw))
        if isinstance(names, Failure):
            return ((), (), names.failure().finding)
        return (names.unwrap(), (), None)
    if not isinstance(raw, dict):
        return ((), (), "enabledPlugins must be a JSON object")
    on: list[str] = []
    off: list[str] = []
    for key, value in cast("dict[str, object]", raw).items():
        if not isinstance(value, bool):
            return ((), (), f"enabledPlugins values must be JSON booleans; {key!r} is not")
        (on if value else off).append(key)
    return (tuple(on), tuple(off), None)


def vacuity_findings(*, settings_text: str, settings_label: str) -> tuple[str, ...]:
    """Findings for one committed settings file alone. Empty means well-formed.

    Rejects all three vacuity levels: an empty enablement set, an all-false one
    (a `false` value is an explicit disable, not an enablement), and a partially
    stripped one where a declared marketplace has no enabled plugin left. A
    vacuous file derives ZERO commands, so a provisioner that ran it would exit
    0 having done nothing — indistinguishable from a provisioned host.
    """
    parsed = json.loads(settings_text)
    if not isinstance(parsed, dict):
        return (f"{settings_label} must contain a JSON object",)
    settings = cast("dict[str, object]", parsed)
    marketplaces = settings.get("extraKnownMarketplaces")
    if marketplaces is not None and not isinstance(marketplaces, dict):
        return ("extraKnownMarketplaces must be a JSON object",)
    enabled, disabled, shape = split_enablement(raw=settings.get("enabledPlugins"))
    if shape is not None:
        return (shape,)
    declared = tuple(cast("dict[str, object]", marketplaces or {}))
    if declared and not enabled:
        return ("no plugin is enabled; enabledPlugins is empty, absent, or all-false",)
    covered = {marketplace_of(plugin=name) for name in enabled}
    off_markets = {marketplace_of(plugin=name) for name in disabled}
    findings: list[str] = []
    for market in declared:
        if market in covered:
            continue
        if market in off_markets:
            findings.append(f"marketplace {market!r} has only explicitly disabled plugins")
        else:
            findings.append(f"marketplace {market!r} declared but nothing enabled from it")
    return tuple(findings)
