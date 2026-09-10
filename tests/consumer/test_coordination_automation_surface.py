"""Consumer-tier: the `SPECIFICATION/contracts.md` §"Cross-repo coordination automation surface".

This section is the canonical implementation specification for the pin-and-bump
policy: the reusable workflow INVENTORY every consumer delegates to, the
`repository_dispatch` event types the surface fires, and — under §"Self-hosting"
— the shims by which this library is a consumer of its own automation. Each is
consumer-observable and each rots in a different way.

- **The inventory ships whole, with its declared wire.** All four workflows the
  §"Reusable workflow inventory" enumerates must exist and declare the inputs
  and secrets their callers pass. `release_url` is asserted required on the
  dispatcher and OPTIONAL on the bump-pin handler, because the section states
  exactly that asymmetry and a caller reading it backwards fails at run time.
  The two threshold defaults (`staleness_threshold_releases` `1`,
  `park_threshold_hours` `24`) are asserted for the reason every default is: a
  consumer that omits the input never sees the number it got.
- **Only the two declared event types are fired.** "These two are the only event
  types the coordination surface fires." A third `repository_dispatch` type
  appearing anywhere in the surface is a coordination event no consumer's
  handler is wired for, and it fails SILENTLY — GitHub accepts any event type
  and simply matches no workflow.
- **Self-hosting: this library carries all three consumer shims, delegating.**
  It is a FULL participant in the §"Bump-pin policy" sense — it both receives
  (`bump-pin-from-dispatch.yml` on `repository_dispatch: sibling-released`, plus
  `pin-freshness.yml` on a schedule) and produces (`release-dispatch.yml` on
  `release: published`). Each shim must be a THIN delegation: the section's DRY
  discipline says "no coordination logic duplicated across consumers", so a shim
  is asserted to `uses:` the matching reusable workflow of this repository. A
  shim that inlined the logic would still pass an existence check while becoming
  the fork the discipline exists to prevent.

The workflow files are read as TEXT rather than parsed: this library declares
zero runtime dependencies (`constraints.md` §"Dependencies") and ships no YAML
parser.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"

# The reusable workflow inventory, each mapped to the `workflow_call` inputs and
# secrets its callers pass, with the documented default where one exists.
_REQUIRED_WIRE: dict[str, tuple[str, ...]] = {
    "reusable-release-dispatch.yml": ("source_repo", "tag", "release_url"),
    "reusable-bump-pin-from-dispatch.yml": ("source_repo", "tag"),
    "reusable-pin-freshness.yml": (),
    "reusable-release-park.yml": (),
}
_OPTIONAL_DEFAULTS: dict[str, dict[str, str]] = {
    "reusable-release-dispatch.yml": {},
    "reusable-bump-pin-from-dispatch.yml": {"release_url": ""},
    "reusable-pin-freshness.yml": {"staleness_threshold_releases": "1"},
    "reusable-release-park.yml": {"park_threshold_hours": "24"},
}
# The App-token secrets `secrets: inherit` threads from each consumer shim. The
# park backstop authenticates with the read-only `github.token` and needs none.
_INHERITED_SECRETS: dict[str, tuple[str, ...]] = {
    "reusable-release-dispatch.yml": ("APP_ID", "APP_PRIVATE_KEY"),
    "reusable-bump-pin-from-dispatch.yml": ("APP_ID", "APP_PRIVATE_KEY"),
    "reusable-pin-freshness.yml": ("APP_ID", "APP_PRIVATE_KEY"),
    "reusable-release-park.yml": (),
}

# The three consumer shims §"Self-hosting" requires, each mapped to the reusable
# workflow it must delegate to.
_SELF_HOSTED_SHIMS: dict[str, str] = {
    "release-dispatch.yml": "reusable-release-dispatch.yml",
    "bump-pin-from-dispatch.yml": "reusable-bump-pin-from-dispatch.yml",
    "pin-freshness.yml": "reusable-pin-freshness.yml",
}

# The only two `repository_dispatch` event types the surface fires.
_DECLARED_EVENT_TYPES = frozenset({"sibling-released", "codex-acp-golden-master"})
_EVENT_TYPE = re.compile(r"event_type[=:]\s*'?\"?(?P<name>[a-z][a-z0-9-]*)")

# One `workflow_call` input / secret entry: six-space name, eight-space fields.
_ENTRY = "^      {name}:\n(?P<body>(?:        .*\n)+)"
_FIELD = re.compile(r"^        (?P<field>[a-z-]+): ?(?P<value>.*)$", re.MULTILINE)


def _workflow(*, name: str) -> str:
    """The text of a shipped workflow file."""
    path = _WORKFLOWS_DIR / name
    assert path.is_file(), f"the coordination surface must ship `{name}` at {path}"
    return path.read_text(encoding="utf-8")


def _entry_fields(*, source: str, name: str) -> dict[str, str]:
    """The declared fields of the `workflow_call` entry `name`, or `{}` when absent."""
    matched = re.search(_ENTRY.format(name=re.escape(name)), source, re.MULTILINE)
    body = "" if matched is None else matched.group("body")
    return {
        field.group("field"): field.group("value").strip().strip('"')
        for field in _FIELD.finditer(body)
    }


def test_the_reusable_workflow_inventory_declares_the_wire_its_callers_pass() -> None:
    """Every inventory member ships with its required inputs, defaults, and secrets."""
    sources = {name: _workflow(name=name) for name in sorted(_REQUIRED_WIRE)}

    unrequired = {
        name: sorted(
            declared
            for declared in _REQUIRED_WIRE[name]
            if _entry_fields(source=source, name=declared).get("required") != "true"
        )
        for name, source in sources.items()
    }
    relaxed = {name: names for name, names in unrequired.items() if names}
    assert not relaxed, (
        f"an input the contract marks required must stay required — a caller omitting it "
        f"otherwise reaches the job body with an empty value; relaxed={relaxed}"
    )

    drifted = {
        f"{name}.{declared}": (fields.get("default"), expected, fields.get("required"))
        for name, source in sources.items()
        for declared, expected in _OPTIONAL_DEFAULTS[name].items()
        for fields in [_entry_fields(source=source, name=declared)]
        if fields.get("default") != expected or fields.get("required") != "false"
    }
    assert not drifted, (
        f"each of these inputs is optional with a documented default, and a consumer that "
        f"omits it never sees the value it got; drifted={drifted}"
    )

    unthreaded = {
        name: sorted(
            secret
            for secret in _INHERITED_SECRETS[name]
            if _entry_fields(source=source, name=secret).get("required") != "true"
        )
        for name, source in sources.items()
    }
    missing_secrets = {name: names for name, names in unthreaded.items() if names}
    assert not missing_secrets, (
        f"the coordination surface authenticates via a GitHub App installation token, "
        f"threaded from each consumer shim by `secrets: inherit`; missing={missing_secrets}"
    )


def test_the_surface_fires_only_the_two_declared_repository_dispatch_event_types() -> None:
    """No third coordination event type has crept into the shipped surface."""
    fired = {
        name: sorted(
            {
                match.group("name")
                for match in _EVENT_TYPE.finditer(path.read_text(encoding="utf-8"))
            }
            - _DECLARED_EVENT_TYPES
        )
        for path in sorted(_WORKFLOWS_DIR.glob("*.yml"))
        for name in [path.name]
    }
    undeclared = {name: names for name, names in fired.items() if names}
    assert not undeclared, (
        f"GitHub accepts any `repository_dispatch` event type and simply matches no "
        f"workflow, so an undeclared type fires into silence rather than erroring; "
        f"undeclared={undeclared} declared={sorted(_DECLARED_EVENT_TYPES)}"
    )


def test_this_library_self_hosts_all_three_consumer_shims_by_delegation() -> None:
    """Each shim ships and delegates to the matching reusable workflow, adding no logic."""
    shims = {name: _workflow(name=name) for name in sorted(_SELF_HOSTED_SHIMS)}

    undelegated = sorted(
        name
        for name, source in shims.items()
        if f".github/workflows/{_SELF_HOSTED_SHIMS[name]}@" not in source
    )
    assert not undelegated, (
        f"a consumer's coordination footprint is the THIN shim that delegates to the "
        f"reusable workflow — no coordination logic duplicated across consumers — so a "
        f"shim that stopped delegating is the fork that discipline forbids; "
        f"undelegated={undelegated}"
    )
    assert "on:\n  release:\n    types: [published]" in shims["release-dispatch.yml"], (
        "the PRODUCING half of participation is `release-dispatch.yml` firing on this "
        "repository's own published release; without that trigger no sibling is told to bump"
    )
    assert (
        "on:\n  repository_dispatch:\n    types: [sibling-released]"
        in shims["bump-pin-from-dispatch.yml"]
    ), (
        "the RECEIVING half is the `sibling-released` handler; a shim listening on any "
        "other event receives no dispatch and its pins go stale silently"
    )
