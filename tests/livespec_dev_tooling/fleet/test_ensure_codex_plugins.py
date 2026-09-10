"""Tests for `livespec_dev_tooling.fleet.ensure_codex_plugins`, the Codex twin.

The property under test is the one the collapse exists to buy: the Codex
registration commands are DERIVED from a committed per-repo manifest, so a
fifth plugin needs no recipe edit in any governed repo. The representative
fixture is this repo's own live Codex plugin set — the three marketplaces the
hand-written `scripts/just/ensure-codex-plugins.sh` body registers — so a
regression shows up as a difference from the commands that body actually runs
rather than as a difference from an invented example.

The modules are reached through `importlib` with a file-existence assertion
first, the pattern this repo's other extract-to-a-new-module slices use: at Red
the module does not exist and the FIRST assertion fails genuinely, rather than
the whole file dying at collection on a top-level import.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Protocol, cast

from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet._ensure_plugin_commands import (
    PluginCommandOutcome,
    PluginCommandResult,
)
from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    InvocationNotPerformed,
)

__all__: list[str] = []

_FLEET_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet"

# This repo's live Codex plugin set, transcribed from the hand-written recipe
# body the shared module replaces: livespec CORE, the Codex Driver, and the
# orchestrator. Note what it is NOT — the Claude settings enable
# `livespec@livespec-driver-claude`, and the Codex set names
# `livespec@livespec-driver-codex` instead. That single difference is the
# measured reason the Codex manifest cannot be the Claude settings file.
_MANIFEST: dict[str, object] = {
    "extraKnownMarketplaces": {
        "livespec": {
            "source": {"source": "github", "repo": "thewoolleyman/livespec", "ref": "release"}
        },
        "livespec-driver-codex": {
            "source": {
                "source": "github",
                "repo": "thewoolleyman/livespec-driver-codex",
                "ref": "release",
            }
        },
        "livespec-orchestrator-beads-fabro": {
            "source": {
                "source": "github",
                "repo": "thewoolleyman/livespec-orchestrator-beads-fabro",
                "ref": "release",
            }
        },
    },
    "enabledPlugins": {
        "livespec@livespec": True,
        "livespec@livespec-driver-codex": True,
        "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro": True,
    },
}

# The exact command sequence the hand-written body runs, in its order: every
# marketplace added, then every marketplace upgraded, then every plugin added.
_EXPECTED: tuple[tuple[str, ...], ...] = (
    ("codex", "plugin", "marketplace", "add", "thewoolleyman/livespec", "--ref", "release"),
    (
        "codex",
        "plugin",
        "marketplace",
        "add",
        "thewoolleyman/livespec-driver-codex",
        "--ref",
        "release",
    ),
    (
        "codex",
        "plugin",
        "marketplace",
        "add",
        "thewoolleyman/livespec-orchestrator-beads-fabro",
        "--ref",
        "release",
    ),
    ("codex", "plugin", "marketplace", "upgrade", "livespec"),
    ("codex", "plugin", "marketplace", "upgrade", "livespec-driver-codex"),
    ("codex", "plugin", "marketplace", "upgrade", "livespec-orchestrator-beads-fabro"),
    ("codex", "plugin", "add", "livespec@livespec"),
    ("codex", "plugin", "add", "livespec@livespec-driver-codex"),
    (
        "codex",
        "plugin",
        "add",
        "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro",
    ),
)


class PlannedCommands(Protocol):
    """The derive-from-manifest planner under test."""

    def __call__(self, *, settings_text: str) -> tuple[tuple[str, ...], ...]: ...


class SettingsFindings(Protocol):
    """The manifest vacuity gate under test."""

    def __call__(self, *, settings_text: str) -> tuple[str, ...]: ...


class Ensure(Protocol):
    """The gate-then-run provisioning entry point under test."""

    def __call__(self, *, settings_text: str, runner: object) -> tuple[str, ...]: ...


class Recorder:
    """A canned runner recording every argv it was handed."""

    def __init__(self, *, returncode: int = 0) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._returncode = returncode

    def __call__(self, *, args: tuple[str, ...]) -> PluginCommandOutcome:
        self.calls.append(args)
        return IOSuccess(PluginCommandResult(returncode=self._returncode))


def _codex_module() -> object:
    """The Codex provisioner, asserted present before it is imported."""
    assert (_FLEET_DIR / "ensure_codex_plugins.py").is_file(), (
        "the Codex twin of ensure_plugins.py must exist at "
        "livespec_dev_tooling/fleet/ensure_codex_plugins.py"
    )
    return importlib.import_module("livespec_dev_tooling.fleet.ensure_codex_plugins")


def _shared_module() -> object:
    """The shared derive-from-settings reader, asserted present before import."""
    assert (_FLEET_DIR / "_plugin_settings.py").is_file(), (
        "the vacuity reader both provisioners share must exist at "
        "livespec_dev_tooling/fleet/_plugin_settings.py"
    )
    return importlib.import_module("livespec_dev_tooling.fleet._plugin_settings")


def _planned(*, module: object) -> PlannedCommands:
    return cast("PlannedCommands", module.planned_commands)


def _findings(*, module: object) -> SettingsFindings:
    return cast("SettingsFindings", module.settings_findings)


def _ensure(*, module: object) -> Ensure:
    return cast("Ensure", module.ensure)


def test_commands_derive_from_the_representative_manifest() -> None:
    """The planner reproduces the hand-written body's exact command sequence.

    This is acceptance criterion 1 stated as a test: the marketplace/add/upgrade
    operations are COMPUTED from the committed manifest, and the computation
    lands on the same commands the hard-coded bash body issues today.
    """
    module = _codex_module()

    commands = _planned(module=module)(settings_text=json.dumps(_MANIFEST))

    assert commands == _EXPECTED, (
        f"the derived sequence must match the hand-written recipe body it "
        f"replaces; got {commands!r}"
    )


def test_a_fifth_plugin_needs_no_code_change() -> None:
    """Declaring one more marketplace+plugin grows the plan by exactly three commands.

    The property the work-item names: adding a fifth plugin is a manifest edit,
    not a recipe edit and not a code edit here either.
    """
    module = _codex_module()
    markets = cast("dict[str, object]", _MANIFEST["extraKnownMarketplaces"])
    plugins = cast("dict[str, object]", _MANIFEST["enabledPlugins"])
    grown = {
        "extraKnownMarketplaces": {
            **markets,
            "livespec-overseer": {
                "source": {
                    "source": "github",
                    "repo": "thewoolleyman/livespec-overseer",
                    "ref": "release",
                }
            },
        },
        "enabledPlugins": {**plugins, "livespec-overseer@livespec-overseer": True},
    }

    commands = _planned(module=module)(settings_text=json.dumps(grown))

    assert set(commands) - set(_EXPECTED) == {
        (
            "codex",
            "plugin",
            "marketplace",
            "add",
            "thewoolleyman/livespec-overseer",
            "--ref",
            "release",
        ),
        ("codex", "plugin", "marketplace", "upgrade", "livespec-overseer"),
        ("codex", "plugin", "add", "livespec-overseer@livespec-overseer"),
    }, f"a fifth plugin must add exactly its add/upgrade/add triple; got {commands!r}"


def test_a_marketplace_without_a_ref_omits_the_flag() -> None:
    """Codex takes the ref as a `--ref` FLAG, and an absent ref emits no flag.

    The shape difference from Claude, which fuses the ref into a single
    `<repo>@<ref>` argument — the renderers cannot be shared even though the
    manifest key they read is.
    """
    module = _codex_module()
    manifest = {
        "extraKnownMarketplaces": {"livespec": {"source": {"repo": "thewoolleyman/livespec"}}},
        "enabledPlugins": {"livespec@livespec": True},
    }

    commands = _planned(module=module)(settings_text=json.dumps(manifest))

    assert commands[0] == ("codex", "plugin", "marketplace", "add", "thewoolleyman/livespec")


def test_a_manifest_entry_with_no_readable_source_is_skipped() -> None:
    """An entry carrying no usable `source.repo` contributes no marketplace command."""
    module = _codex_module()
    manifest = {
        "extraKnownMarketplaces": {
            "broken": {"source": {"repo": 7}},
            "sourceless": {"nope": True},
            "not-an-object": "string",
        },
        "enabledPlugins": {"livespec@broken": True},
    }

    commands = _planned(module=module)(settings_text=json.dumps(manifest))

    assert commands == (("codex", "plugin", "add", "livespec@broken"),)


def test_a_non_object_manifest_plans_nothing() -> None:
    """A manifest that is not a JSON object derives zero commands."""
    module = _codex_module()

    assert _planned(module=module)(settings_text=json.dumps(["not", "an", "object"])) == ()


def test_a_manifest_declaring_no_marketplace_plans_only_plugin_adds() -> None:
    """A manifest with no `extraKnownMarketplaces` still registers its plugins.

    Legitimate rather than vacuous, and a state host-wide enablement actively
    produces: once ANY repo on the host has added a marketplace it stays added,
    so a later repo may declare only the plugins it draws from it. The vacuity
    gate admits that manifest — it refuses a DECLARED marketplace with nothing
    enabled, not an enabled plugin with no declaration.
    """
    module = _codex_module()
    manifest = {"enabledPlugins": {"livespec@livespec": True}}

    assert _findings(module=module)(settings_text=json.dumps(manifest)) == ()
    assert _planned(module=module)(settings_text=json.dumps(manifest)) == (
        ("codex", "plugin", "add", "livespec@livespec"),
    )


def test_an_unreadable_enablement_plans_no_plugin_command() -> None:
    """A shape nobody can read contributes marketplace commands and NO install.

    The Claude twin's rule preserved: planning an install from a value nobody
    could read is the one thing this arm must not do. The shipped path never
    reaches it, because `ensure` gates on the vacuity findings first.
    """
    module = _codex_module()
    manifest = {
        "extraKnownMarketplaces": {
            "livespec": {"source": {"repo": "thewoolleyman/livespec", "ref": "release"}}
        },
        "enabledPlugins": "not a list or mapping",
    }

    commands = _planned(module=module)(settings_text=json.dumps(manifest))

    assert commands == (
        ("codex", "plugin", "marketplace", "add", "thewoolleyman/livespec", "--ref", "release"),
        ("codex", "plugin", "marketplace", "upgrade", "livespec"),
    )


def test_a_vacuous_manifest_is_refused_before_any_command_runs() -> None:
    """An all-false manifest reports the vacuity and runs NOTHING.

    A vacuous manifest derives zero commands, so a provisioner that ran it would
    exit 0 having done nothing — the shape indistinguishable from success.
    """
    module = _codex_module()
    markets = cast("dict[str, object]", _MANIFEST["extraKnownMarketplaces"])
    manifest = {
        "extraKnownMarketplaces": markets,
        "enabledPlugins": {"livespec@livespec": False},
    }
    recorder = Recorder()

    findings = _ensure(module=module)(settings_text=json.dumps(manifest), runner=recorder)

    assert findings == ("no plugin is enabled; enabledPlugins is empty, absent, or all-false",)
    assert recorder.calls == [], "a refused manifest must not reach the Codex CLI"


def test_findings_name_the_codex_manifest_not_the_claude_one() -> None:
    """The operator is sent to `.codex/settings.json`, never to the Claude file.

    The label is the whole reason the shared reader takes it as a parameter: a
    finding naming the wrong harness's file sends the reader to a file that is
    already correct, which is worse than naming no file at all.
    """
    module = _codex_module()

    findings = _findings(module=module)(settings_text=json.dumps(["not", "an", "object"]))

    assert findings == (".codex/settings.json must contain a JSON object",)


def test_a_marketplace_with_nothing_enabled_from_it_is_reported() -> None:
    """A declared marketplace no plugin draws from is a partially stripped manifest."""
    module = _codex_module()
    manifest = {
        "extraKnownMarketplaces": {
            "livespec": {"source": {"repo": "thewoolleyman/livespec", "ref": "release"}},
            "livespec-driver-codex": {
                "source": {"repo": "thewoolleyman/livespec-driver-codex", "ref": "release"}
            },
        },
        "enabledPlugins": {"livespec@livespec": True},
    }

    findings = _findings(module=module)(settings_text=json.dumps(manifest))

    assert findings == ("marketplace 'livespec-driver-codex' declared but nothing enabled from it",)


def test_a_well_formed_manifest_runs_every_planned_command() -> None:
    """The happy path issues the full sequence and reports no finding."""
    module = _codex_module()
    recorder = Recorder()

    findings = _ensure(module=module)(settings_text=json.dumps(_MANIFEST), runner=recorder)

    assert findings == ()
    assert tuple(recorder.calls) == _EXPECTED


def test_a_command_that_refused_is_reported_with_its_exit_code() -> None:
    """A Codex CLI that RAN and said no is reported as the CLI's own verdict."""
    module = _codex_module()
    recorder = Recorder(returncode=2)

    findings = _ensure(module=module)(settings_text=json.dumps(_MANIFEST), runner=recorder)

    assert findings == (
        "command failed with exit 2: codex plugin marketplace add "
        "thewoolleyman/livespec --ref release",
    )
    assert len(recorder.calls) == 1, "provisioning must stop at the first refusal"


def test_a_command_that_never_ran_is_reported_as_such() -> None:
    """An absent Codex binary is an install problem, kept apart from a refusal.

    The two failures call for opposite operator responses, so they must not
    collapse into one message — the distinction the shared invocation seam's
    failure track exists to carry.
    """
    module = _codex_module()

    def absent(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        return IOFailure(
            InvocationNotPerformed(argv=args, kind=BINARY_ABSENT, detail="codex not on PATH")
        )

    findings = _ensure(module=module)(settings_text=json.dumps(_MANIFEST), runner=absent)

    assert findings == ("command did not run: binary_absent: codex (codex not on PATH)",)


def test_the_provisioner_never_plans_a_removal() -> None:
    """ADDITIVE-ONLY: no planned command can retract another repo's registration.

    Codex enablement is HOST-WIDE, so a prune arm here would silently
    unregister plugins a sibling repo declared. This pins the property that
    makes a per-repo manifest safe against a shared config file.
    """
    module = _codex_module()

    commands = _planned(module=module)(settings_text=json.dumps(_MANIFEST))

    banned = {"remove", "rm", "delete", "uninstall", "disable"}
    assert all(
        banned.isdisjoint(command) for command in commands
    ), f"host-wide provisioning must never retract a registration; got {commands!r}"


def test_both_provisioners_share_one_vacuity_reader() -> None:
    """The Claude module's private vacuity helpers are GONE, not copied.

    Mirroring the Claude derive-from-settings contract by a copied body would
    re-create the drift the collapse exists to remove, one layer down. The
    shared reader is the structural form of the mirror.
    """
    shared = _shared_module()
    claude_source = (_FLEET_DIR / "ensure_plugins.py").read_text(encoding="utf-8")

    assert hasattr(shared, "split_enablement")
    assert hasattr(shared, "vacuity_findings")
    assert hasattr(shared, "marketplace_of")
    assert (
        "_split_enablement" not in claude_source
    ), "ensure_plugins.py must consume the shared reader, not keep its own copy"
    assert "def _marketplace_of" not in claude_source
