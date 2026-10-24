"""The host-wide local-gate slot limit — at most N pytest sessions, the rest queue.

Governed by `SPECIFICATION/non-functional-requirements.md` section "Local gate
concurrency limit" and the four `SPECIFICATION/scenarios.md` scenarios beneath
it. Nothing here reads the host's own `/etc/livespec/local-gate-slots` or its
`/run` slot store: every assertion is taken against `tmp_path`, so the suite
answers the same on the dev VPS, which carries a limit, as in a factory sandbox,
which never will.

THE LOCKS ARE REAL, and that is the point rather than an accident of
convenience. `flock` is owned by the OPEN FILE DESCRIPTION, not by the process,
so two descriptors opened separately in ONE process contend exactly as two
sessions on the host do — measured, not assumed, and it is what lets the
at-most-N and queueing properties be proved without a second interpreter. The
two properties that genuinely need a second process — a slot holder dying by
SIGKILL, and a nested session inheriting the marker — fork one, because what
they assert IS process death and environment inheritance.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "local_gate_slots.py"
_SYNTHETIC_NAME = "local_gate_slots_under_test"


def _load_module() -> ModuleType:
    """Import the slot module fresh from its file path.

    Loaded BY PATH rather than as `livespec_dev_tooling.local_gate_slots` so the
    assertions read the on-disk module the Red→Green hook inspects, and so this
    file's first assertion can be a genuine one about the module's existence
    instead of a collection error.
    """
    spec = importlib.util.spec_from_file_location(_SYNTHETIC_NAME, str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _limit_file(*, root: Path, text: str) -> Path:
    """One host limit file carrying `text`."""
    path = root / "local-gate-slots"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.integration
def test_a_hosts_limit_of_n_admits_n_slot_holders_and_queues_the_next(*, tmp_path: Path) -> None:
    """SCENARIO: a host at its local-gate slot limit queues the next pytest session.

    The at-most-N half of the ratified clause, proved against real `flock`
    holds: with the limit set to 2, two takes succeed, the third finds nothing
    free, and releasing ONE frees exactly one — not the store.
    """
    assert _MODULE_PATH.is_file(), (
        f"{_MODULE_PATH.relative_to(_REPO_ROOT)} must exist: it is the pytest "
        f"plugin that bounds how many fleet gate test runs execute at once on "
        f"one host, per SPECIFICATION/non-functional-requirements.md "
        f'section "Local gate concurrency limit"'
    )
    module = _load_module()
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir()

    limit = module.configured_limit(limit_file=_limit_file(root=tmp_path, text="2\n"))
    assert limit == 2

    first = module.take_slot(slot_dir=slot_dir, limit=limit)
    second = module.take_slot(slot_dir=slot_dir, limit=limit)
    assert first is not None
    assert second is not None
    assert (
        module.take_slot(slot_dir=slot_dir, limit=limit) is None
    ), "a third session must find no free slot on a host whose limit is 2"

    os.close(first)
    third = module.take_slot(slot_dir=slot_dir, limit=limit)
    assert third is not None, "the slot the first holder released must be takeable"
    assert (
        module.take_slot(slot_dir=slot_dir, limit=limit) is None
    ), "releasing one slot must free exactly one, never the whole store"
    os.close(second)
    os.close(third)


@pytest.mark.integration
def test_the_limit_is_read_from_one_host_file_and_every_absence_is_unlimited(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SCENARIO: a host with no local-gate slot limit runs pytest sessions unchanged.

    The limit lives in ONE host file, and every way of not carrying a usable one
    collapses to the same unlimited answer. That collapse is deliberate and is
    the fail-OPEN direction: a throttle that cannot read its own setting must
    not be able to stop a gate, so an absent file, a value that will not parse,
    a negative, an explicit zero and an unreadable file all read as no limit.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()

    assert module.configured_limit(limit_file=tmp_path / "absent") is None
    assert module.configured_limit(limit_file=tmp_path) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="lots")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="-1")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="0\n")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text=" 3 \n")) == 3

    unreadable = _limit_file(root=tmp_path, text="3\n")

    def _refuse(*_args: object, **_kwargs: object) -> str:
        raise OSError(5, "simulated I/O error reading the host limit file")

    monkeypatch.setattr(Path, "read_text", _refuse)
    assert module.configured_limit(limit_file=unreadable) is None, (
        "a limit file that cannot be read must leave the host unthrottled "
        "rather than fail a gate that has nothing to do with it"
    )


@pytest.mark.integration
def test_a_slot_file_that_cannot_be_opened_is_not_handed_out(*, tmp_path: Path) -> None:
    """A slot whose file will not open is never reported as taken.

    The slot store is provisioned by the same converge that sets the limit, so
    this is the broken-host edge rather than an expected state. It is asserted
    because the alternative — handing back a descriptor for a path no lock was
    taken on — would let two sessions believe they each held the same slot.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir()
    (slot_dir / "slot-1").mkdir()

    assert module.take_slot(slot_dir=slot_dir, limit=1) is None
