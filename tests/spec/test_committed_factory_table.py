"""This repository's own committed factory table, from the Fabro factory registry
section of `SPECIFICATION/non-functional-requirements.md`.

The section's last paragraph, "Machines are bound only in the inventory", binds
this repository twice over. As the PROVISIONER it must render
`/etc/livespec/fabro-factories.json` from `fabro_factory_registry`, which the
sibling `tests.livespec_dev_tooling.test_fabro_factory_registry_role` asserts by
running the committed role. As a DISPATCHING REPOSITORY it is also subject to the
clause's prohibition — "no play, role or committed factory entry names the
machine" — and that half is a claim about the file in THIS tree, which no run of
the role can reach: the role renders the registry, and the registry is the thing
a committed entry is resolved BY, so a table that still carries its own address
resolves fine and never consults the file it was supposed to.

So the two properties asserted here are properties of the committed
`.livespec.jsonc` text, read the way the Dispatcher reads it:

- **Registry-backed entries, each named for the instance it addresses.** The
  table declares exactly `petri`, which declares
  `"registry": true` and carries NO `server`. `"registry": true` with an address beside it is the shape
  that fails silently in the direction of the defect: the Dispatcher has an
  address to use, so routing works, the registry is never read, and the machine
  stays bound in this file. Asserting the ABSENCE of `server` is therefore
  load-bearing in a way asserting the presence of the flag is not.
- **The default resolves through the registry too.** `default_factory` is
  `petri` since the cutover (coordinator ruling R668, mirroring
  livespec-orchestrator-beads-fabro bd-ib-iud52v), so a dispatch that names no factory takes the registry-backed entry
  rather than a second, address-carrying one. It is also the fallback a recorded
  item pin naming a retired factory lands on, which is why the table may not keep
  an address-carrying entry around for those pins to resolve against.

`petri` names an INSTANCE and not a role, per the same section's "A factory
name SHOULD name the Fabro server instance it addresses and SHOULD stay the same
for that instance's whole life", so this repository's default survives a move of
its instance between machines with no edit here.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import jsoncomment

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVESPEC_JSONC = _REPO_ROOT / ".livespec.jsonc"

# The implementation-plugin block the `dispatcher` settings live under.
_IMPL_PLUGIN = "livespec-orchestrator-beads-fabro"

# The factory names this repository declares, each resolved by name from the
# control node's rendered registry rather than from an address committed here.
_REGISTRY_FACTORIES = ["petri"]

# The factory a dispatch naming none takes.
_DEFAULT_FACTORY = "petri"


def _dispatcher_block() -> dict[str, object]:
    """The committed `dispatcher` settings, parsed from `.livespec.jsonc`."""
    document = cast(
        "dict[str, dict[str, dict[str, object]]]",
        jsoncomment.loads(_LIVESPEC_JSONC.read_text(encoding="utf-8")),
    )
    return document[_IMPL_PLUGIN]["dispatcher"]


def test_every_committed_factory_entry_is_registry_backed_with_no_address() -> None:
    """`dispatcher.factories` is exactly `petri`, registry-backed, with no address."""
    factories = cast("dict[str, dict[str, object]]", _dispatcher_block()["factories"])
    assert sorted(factories) == _REGISTRY_FACTORIES, (
        f"`dispatcher.factories` MUST declare exactly {_REGISTRY_FACTORIES}; "
        f"declared={sorted(factories)}"
    )
    for name, entry in factories.items():
        assert entry.get("registry") is True, (
            f'the `{name}` entry MUST declare `"registry": true` so the Dispatcher resolves '
            f"its address by name from `/etc/livespec/fabro-factories.json`; entry={entry}"
        )
        assert "server" not in entry, (
            f"the `{name}` entry MUST carry no `server`, so that no committed factory entry "
            f'names a machine (`SPECIFICATION/non-functional-requirements.md` §"Fabro factory '
            f'registry", "Machines are bound only in the inventory"): an address beside '
            f'`"registry": true` leaves the machine bound in this file and the registry unread, '
            f"with routing working either way; entry={entry}"
        )


def test_the_committed_default_factory_is_the_registry_backed_entry() -> None:
    """`dispatcher.default_factory` names a registry-backed entry, `petri`."""
    default_factory = _dispatcher_block()["default_factory"]
    assert default_factory == _DEFAULT_FACTORY, (
        f"`dispatcher.default_factory` MUST be `{_DEFAULT_FACTORY}`, a registry-backed entry, "
        f"so a dispatch naming no factory — and a recorded item pin naming a retired factory, "
        f"which falls back to the default — resolves through the control node's registry; "
        f"declared={default_factory!r}"
    )
