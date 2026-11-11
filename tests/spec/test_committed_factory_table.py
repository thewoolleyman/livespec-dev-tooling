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
  table declares exactly `petri`, `candidate` (gmktec's fabro-server-candidate,
  reached only by an explicit per-dispatch `--factory candidate`) and
  `homelab-worker-arm64` (gmktec's fabro-server-homelab-worker-arm64, the arm64
  container workers' factory, likewise reached only per dispatch), each of which
  declares `"registry": true` and carries NO `server`. `"registry": true` with an address beside it is the shape
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

import json
from pathlib import Path
from typing import cast

import jsoncomment
import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVESPEC_JSONC = _REPO_ROOT / ".livespec.jsonc"

# The implementation-plugin block the `dispatcher` settings live under.
_IMPL_PLUGIN = "livespec-orchestrator-beads-fabro"


def _dispatcher_block(*, path: Path = _LIVESPEC_JSONC) -> dict[str, object]:
    """One `dispatcher` block, parsed from a committed or fixture JSONC file."""
    document = cast(
        "dict[str, dict[str, dict[str, object]]]",
        jsoncomment.loads(path.read_text(encoding="utf-8")),
    )
    return document[_IMPL_PLUGIN]["dispatcher"]


def _assert_factory_table(*, dispatcher: dict[str, object]) -> None:
    """Require registry-only entries and a default that the table declares."""
    factories = cast("dict[str, dict[str, object]]", dispatcher["factories"])
    assert factories, "`dispatcher.factories` must declare at least one registry-backed factory"
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
    default_factory = dispatcher["default_factory"]
    assert isinstance(default_factory, str) and default_factory in factories, (
        "`dispatcher.default_factory` must name an entry declared by "
        f"`dispatcher.factories`; declared={default_factory!r} factories={sorted(factories)}"
    )


def _write_dispatcher_fixture(
    *, tmp_path: Path, factories: dict[str, dict[str, object]], default_factory: str
) -> dict[str, object]:
    """Write and re-read one dispatcher table, as the live-file reader does."""
    path = tmp_path / ".livespec.jsonc"
    payload = {
        _IMPL_PLUGIN: {"dispatcher": {"factories": factories, "default_factory": default_factory}}
    }
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    return _dispatcher_block(path=path)


def test_every_committed_factory_entry_is_registry_backed_with_no_address() -> None:
    """Every committed factory is registry-backed; names and table size are free values."""
    _assert_factory_table(dispatcher=_dispatcher_block())


@pytest.mark.parametrize(
    ("factories", "default_factory", "message"),
    [
        ({"missing-registry": {}}, "missing-registry", "registry"),
        (
            {"address-carrying": {"registry": True, "server": "example.invalid"}},
            "address-carrying",
            "server",
        ),
        ({"declared": {"registry": True}}, "undeclared", "default_factory"),
    ],
)
def test_factory_table_refuses_invalid_registry_shapes(
    *,
    tmp_path: Path,
    factories: dict[str, dict[str, object]],
    default_factory: str,
    message: str,
) -> None:
    """Fixture-written violations prove the invariant without pinning live names."""
    dispatcher = _write_dispatcher_fixture(
        tmp_path=tmp_path,
        factories=factories,
        default_factory=default_factory,
    )
    with pytest.raises(AssertionError, match=message):
        _assert_factory_table(dispatcher=dispatcher)
