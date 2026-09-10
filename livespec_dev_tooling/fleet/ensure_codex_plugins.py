"""Shared Codex plugin provisioner derived from a committed per-repo manifest.

The Codex twin of `ensure_plugins`. The invoking repo's committed
`.codex/settings.json` is the single source of truth: this module reads its
marketplaces and enabled plugins at runtime and executes the matching Codex CLI
registration commands, so enabling another plugin needs no recipe edit anywhere.

## THE OPEN DESIGN QUESTION, AND WHY THE ANSWER IS NOT THE CLAUDE ANSWER

Claude derives from `.claude/settings.json` and enables PER PROJECT. Codex
plugin enablement is HOST-WIDE (`~/.codex/config.toml`), so derive-from-settings
does not carry over unchanged, and the work-item that commissioned this module
required the choice be made explicitly rather than silently. Four candidates
were considered; the chosen one is a DEDICATED COMMITTED PER-REPO MANIFEST,
provisioned ADDITIVELY.

**Reusing `.claude/settings.json` directly is FALSIFIED BY MEASUREMENT, not
merely disfavoured.** This repo's committed Claude settings enable
`livespec@livespec-driver-claude`; the Codex registration it actually needs is
`livespec@livespec-driver-codex`. The Driver plugin is harness-specific BY
CONSTRUCTION — that is what a Driver is — so reading the Claude file for Codex
would register a plugin Codex cannot use and omit the one it needs, unless the
module carried a hard-coded claude→codex translation table. That table is
exactly the hard-coding this collapse exists to delete, re-introduced one layer
down and shared across every repo instead of copied into each.

**Union-across-governed-repos is not implementable from here.** It matches how
the host behaves, but this module runs inside ONE checkout and has no
enumerable, trustworthy list of the host's other governed repos; and computing
it would let one repo's declaration rewrite another repo's runtime.

**Last-writer is rejected for the reason it is usually rejected.** It requires
PRUNING host-wide state, and pruning silently unregisters plugins a sibling repo
declared. Silent is the operative word: nothing errors.

**So: a dedicated committed manifest, plus additive-only provisioning.** The
manifest is honest about the host-wide/per-repo mismatch and costs a second
source of truth — but the two files differ ONLY where the harnesses genuinely
differ, and no mechanical sync could exist without the translation table above.
ADDITIVE-ONLY is what makes a per-repo declaration safe against a shared config:
this module emits `marketplace add`, `marketplace upgrade` and `plugin add` and
NEVER a remove, so each repo contributes its declarations and retracts nobody
else's. The union candidate 1 wanted therefore emerges as a property OF THE HOST
rather than as something one repo computes on the others' behalf.

⛔ DO NOT ADD A PRUNE ARM. A remove verb here is not a feature; it is candidate
2 arriving by increment, and its damage is invisible until another repo's
session fails to resolve a plugin it never declared to this one.

## WHAT THIS MODULE DELIBERATELY DOES NOT DO YET

It does NOT verify that a registered plugin RESOLVES. The Claude twin does — it
reads the installed-plugins registry and probes the artifact each record names,
because REGISTRATION IS NOT INSTALLATION. The Codex equivalent would read
`codex plugin list --json`, and that surface's JSON shape has NOT been measured
on a host with the Codex CLI present. Writing a parser against a guessed shape
would produce a verifier that reads green for the wrong reason, which is worse
than an absent one.

⛔ AND THE SUBSTITUTE IS BANNED, NOT MERELY WEAK: a `~/.codex/config.toml` that
CONTAINS the right strings while nothing resolves is NOT evidence of anything.
Whoever adds the verification arm measures `codex plugin list --json` first and
reads THAT; a config-file string match must never stand in for it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import cast

# `returns` is VENDORED, not installed; this module reads the command seam's
# railway track directly, so it establishes the path itself rather than relying
# on whichever sibling import happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_commands import (  # noqa: E402
    PluginCommandRunner,
    enabled_plugin_names,
    plugin_command_answer,
    subprocess_runner,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed  # noqa: E402
from livespec_dev_tooling.fleet._plugin_settings import vacuity_findings  # noqa: E402

__all__: list[str] = [
    "CODEX_PROGRAM",
    "CODEX_SETTINGS",
    "ensure",
    "main",
    "planned_commands",
    "settings_findings",
]

# The committed per-repo Codex manifest, repo-root-relative. Spelled to mirror
# `.claude/settings.json` key-for-key so the two files read as twins; kept clear
# of `.codex-plugin/`, which is a PLUGIN-PACKAGING directory inside a Driver
# repo and means something else entirely.
CODEX_SETTINGS = ".codex/settings.json"

# The Codex CLI program name, named once so the PATH probe and the emitted argv
# cannot drift apart.
CODEX_PROGRAM = "codex"


def settings_findings(*, settings_text: str) -> tuple[str, ...]:
    """Findings for the committed Codex manifest alone. Empty means well-formed.

    The Claude twin's vacuity contract, applied to the Codex manifest: an empty
    enablement set, an all-false one, and a declared marketplace with no enabled
    plugin left are all refusals, because each derives zero commands and would
    otherwise provision nothing at exit 0.
    """
    return vacuity_findings(settings_text=settings_text, settings_label=CODEX_SETTINGS)


def _marketplace_add(*, entry: object) -> tuple[str, ...] | None:
    """The `codex plugin marketplace add` argv for one manifest entry.

    Codex takes the ref as its own `--ref` FLAG where Claude takes a fused
    `<repo>@<ref>` argument, so the two harnesses cannot share the renderer even
    though they share the manifest key it reads. An entry that declares no `ref`
    registers the marketplace's default branch, which is the form the host-wide
    install instructions already document.
    """
    if not isinstance(entry, dict):
        return None
    source = cast("dict[str, object]", entry).get("source")
    if not isinstance(source, dict):
        return None
    source_map = cast("dict[str, object]", source)
    repo = source_map.get("repo")
    ref = source_map.get("ref")
    if not isinstance(repo, str):
        return None
    if isinstance(ref, str):
        return (CODEX_PROGRAM, "plugin", "marketplace", "add", repo, "--ref", ref)
    return (CODEX_PROGRAM, "plugin", "marketplace", "add", repo)


def planned_commands(*, settings_text: str) -> tuple[tuple[str, ...], ...]:
    """Return Codex plugin commands derived from the committed manifest.

    Emitted in three GROUPS — every `marketplace add`, then every `marketplace
    upgrade`, then every `plugin add` — which is the ordering the hand-written
    recipe bodies this replaces already used. The grouping is load-bearing at
    one seam only: an `upgrade` names a marketplace by the manifest KEY, so
    every marketplace must be added before any is upgraded.

    An unreadable enablement value contributes NO plugin command, matching the
    Claude twin: the shipped path reaches here only through `ensure`, which
    gates on `settings_findings` first and so REPORTS the unreadable shape
    before any command is planned. Planning an install from a value nobody could
    read is the one thing this arm must not do.
    """
    parsed = json.loads(settings_text)
    if not isinstance(parsed, dict):
        return ()
    settings = cast("dict[str, object]", parsed)
    adds: list[tuple[str, ...]] = []
    upgrades: list[tuple[str, ...]] = []
    marketplaces = settings.get("extraKnownMarketplaces")
    if isinstance(marketplaces, dict):
        for name, entry in cast("dict[str, object]", marketplaces).items():
            add = _marketplace_add(entry=entry)
            if add is None:
                continue
            adds.append(add)
            upgrades.append((CODEX_PROGRAM, "plugin", "marketplace", "upgrade", name))
    plugins = enabled_plugin_names(raw=settings.get("enabledPlugins"))
    if isinstance(plugins, Failure):
        return (*adds, *upgrades)
    installs = [(CODEX_PROGRAM, "plugin", "add", plugin) for plugin in plugins.unwrap()]
    return (*adds, *upgrades, *installs)


def ensure(*, settings_text: str, runner: PluginCommandRunner) -> tuple[str, ...]:
    """Provision from the manifest. Empty means every planned command exited 0.

    Gates BEFORE running anything, for the reason the Claude twin does: a
    vacuous or malformed manifest derives zero commands, so running it would
    exit 0 having done nothing.

    The two command failures are kept APART because they call for opposite
    operator responses: a command that RAN and refused is the Codex CLI's own
    verdict, while a command that never ran at all is an install or permissions
    problem on the host and says nothing about the plugin.
    """
    pre = settings_findings(settings_text=settings_text)
    if pre:
        return pre
    for command in planned_commands(settings_text=settings_text):
        answer = plugin_command_answer(outcome=runner(args=command))
        if isinstance(answer, InvocationNotPerformed):
            return (f"command did not run: {answer.reason}",)
        if answer.returncode != 0:
            return (f"command failed with exit {answer.returncode}: {' '.join(command)}",)
    return ()


def main() -> int:  # pragma: no cover
    """CLI entry point for `python -m livespec_dev_tooling.fleet.ensure_codex_plugins`.

    Exit codes follow `livespec-dev-tooling`'s `SPECIFICATION/contracts.md`
    section "Exit-code table": `3` when the committed manifest cannot support
    provisioning (a precondition the project state does not meet), `4` when a
    planned command refused or never ran.

    An ABSENT Codex CLI is a sanctioned no-op at exit `0`, not a failure — Codex
    is an optional dogfooding runtime, and this preserves the `command -v codex`
    guard the hand-written recipe bodies carried. An absent MANIFEST is likewise
    exit `0`: a repo that has not opted into Codex dogfooding declares nothing,
    and a repo that HAS declared something is held to the vacuity gate.
    """
    root = Path.cwd()
    if shutil.which(CODEX_PROGRAM) is None:
        skipped = "host-wide Codex plugin provisioning skipped"
        _ = sys.stderr.write(f"ensure_codex_plugins: {CODEX_PROGRAM} not on PATH; {skipped}\n")
        return 0
    settings_path = root / CODEX_SETTINGS
    if not settings_path.is_file():
        _ = sys.stderr.write(f"ensure_codex_plugins: no {CODEX_SETTINGS}; nothing declared\n")
        return 0
    settings_text = settings_path.read_text(encoding="utf-8")
    precondition = settings_findings(settings_text=settings_text)
    for finding in precondition:
        _ = sys.stderr.write(f"ensure_codex_plugins: {finding}\n")
    if precondition:
        return 3
    findings = ensure(settings_text=settings_text, runner=subprocess_runner)
    for finding in findings:
        _ = sys.stderr.write(f"ensure_codex_plugins: {finding}\n")
    return 4 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
