"""Beside-tests for the shared work-item liveness resolver.

The resolver is the mechanism `SPECIFICATION/spec.md` §"Non-goals" requires
("one shared mechanism, not per-gate hand-rolls") for the work-item-liveness
exception to the network-I/O prohibition. What these tests pin is the pair of
properties that make it non-vacuous:

- IT CAN ANSWER. A reachable store yields True for an open owner and False
  for a closed or absent one. Before this module every consuming gate's seam
  returned `None` unconditionally, so the convicting branch was unreachable
  and the gate passed by construction.
- IT CANNOT INVENT AN ANSWER. Every way the store can fail to answer — CLI
  absent, non-zero exit (the shape a missing credential projection takes),
  timeout, non-JSON output, unparseable JSON — collapses to `None`, which is
  distinct from the `{}` a reachable-but-empty store returns.

No test contacts a real tracker: `subprocess.run` and `shutil.which` are
monkeypatched, so nothing here spawns a process or opens a socket.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks._work_item_liveness import (
    NONEXISTENT,
    UNREACHABLE,
    bd_status_reader,
    resolve_liveness,
    resolved_status,
)

__all__: list[str] = []


_OWNER = "livespec-dev-tooling-d0er"
# The reader never touches the filesystem — `repo` only reaches `bd -C`, which is
# stubbed here — so any path serves as the query subject.
_REPO = Path()


def _stub_bd(
    *,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str = "",
    returncode: int = 0,
    wrapper: str | None = None,
) -> list[tuple[str, ...]]:
    """Replace the `bd` invocation with a canned answer; return the argv log.

    The log is what lets a test assert HOW the store was queried (the
    `--status all` widening, the credential wrapper) without a real CLI.
    """
    seen: list[tuple[str, ...]] = []

    def _fake_run(argv: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(tuple(argv))
        return subprocess.CompletedProcess(args=list(argv), returncode=returncode, stdout=stdout)

    def _fake_which(_name: str) -> str | None:
        return wrapper

    monkeypatch.setattr(shutil, "which", _fake_which)
    monkeypatch.setattr(subprocess, "run", _fake_run)
    return seen


def _stub_absent_wrapper(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the host as having no credential wrapper, for the non-answer cases."""

    def _fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", _fake_which)


def test_resolve_liveness_is_unverified_when_the_store_did_not_answer() -> None:
    """No snapshot → `None`, the honest degradation the ratified clause requires."""
    assert (
        resolve_liveness(work_item=_OWNER, snapshot=None) is None
    ), "an unanswered store must report UNVERIFIED, never a verdict it did not earn"


def test_resolve_liveness_convicts_a_closed_owner() -> None:
    """THE FAIL CAPABILITY: a closed owner resolves False so the gate can convict it."""
    assert (
        resolve_liveness(work_item=_OWNER, snapshot={_OWNER: "closed"}) is False
    ), "a closed owner must resolve False; a resolver that cannot say so is vacuous"


def test_resolve_liveness_convicts_an_owner_closed_under_the_native_spelling() -> None:
    """`done` is beads' own spelling of finished and must convict identically."""
    assert (
        resolve_liveness(work_item=_OWNER, snapshot={_OWNER: "done"}) is False
    ), "the closed set must cover both vocabularies, or one spelling silences the gate"


def test_resolve_liveness_convicts_an_owner_the_store_does_not_hold() -> None:
    """A reachable store that lacks the id makes the id NONEXISTENT, hence dead."""
    assert (
        resolve_liveness(work_item=_OWNER, snapshot={"livespec-dev-tooling-other": "ready"})
        is False
    ), "an id absent from a store that DID answer is nonexistent, not unverified"


def test_resolve_liveness_accepts_an_open_owner() -> None:
    """An open owner resolves True so a live stand-down stays quiet."""
    assert (
        resolve_liveness(work_item=_OWNER, snapshot={_OWNER: "ready"}) is True
    ), "an open owner must resolve True; convicting it would red every honest repo"


def test_resolved_status_names_the_unreachable_store() -> None:
    """The reportable word for a store that did not answer."""
    assert (
        resolved_status(work_item=_OWNER, snapshot=None) == UNREACHABLE
    ), "the diagnostic must be able to say the store never answered"


def test_resolved_status_names_a_missing_id() -> None:
    """The reportable word separating the two halves of `closed or nonexistent`."""
    assert (
        resolved_status(work_item=_OWNER, snapshot={}) == NONEXISTENT
    ), "a reader must be able to tell a closed owner from an invented id"


def test_resolved_status_reports_the_stores_own_word() -> None:
    """A resolved id reports the status verbatim, as the ratified clause requires."""
    assert (
        resolved_status(work_item=_OWNER, snapshot={_OWNER: "acceptance"}) == "acceptance"
    ), "the finding must name the id AND its resolved status"


def test_bd_status_reader_snapshots_id_to_status(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable store yields an id → status map, and is queried with `--status all`."""
    payload = (
        '[{"id": "livespec-dev-tooling-d0er", "status": "active"}, '
        '{"id": "livespec-dev-tooling-old", "status": "closed"}, '
        '{"id": "livespec-dev-tooling-partial"}]'
    )
    seen = _stub_bd(monkeypatch=monkeypatch, stdout=payload)
    snapshot = bd_status_reader(repo=_REPO)
    assert snapshot == {
        "livespec-dev-tooling-d0er": "active",
        "livespec-dev-tooling-old": "closed",
    }, f"records lacking a status must be dropped rather than guessed; got {snapshot!r}"
    assert "--status" in seen[0] and "all" in seen[0], (
        f"`bd list` hides every closed item without `--status all`, so a closed owner "
        f"would be misread as nonexistent; argv={seen[0]!r}"
    )


def test_bd_status_reader_routes_through_the_credential_wrapper(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Where the host installs the projection wrapper, the query goes through it.

    A bare `bd` on a fleet host answers `Access denied`, which would leave the
    resolver permanently UNREACHABLE — as vacuous as the seam it replaces.
    """
    seen = _stub_bd(monkeypatch=monkeypatch, stdout="[]", wrapper="/usr/local/bin/wrapper.sh")
    _ = bd_status_reader(repo=_REPO)
    assert seen[0][:2] == (
        "/usr/local/bin/wrapper.sh",
        "--",
    ), f"the wrapper must front the query where the host has it; argv={seen[0]!r}"


def test_bd_status_reader_distinguishes_an_empty_store_from_no_answer(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reachable but empty store answers `{}` — never `None`."""
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="[]")
    assert bd_status_reader(repo=_REPO) == {}, (
        "an empty store ANSWERED; collapsing that onto `None` would make "
        "'I could not ask' indistinguishable from 'there is nothing there'"
    )


def test_bd_status_reader_is_unreachable_when_the_cli_is_absent(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `bd` on the host → `None`, never a fabricated empty population."""

    def _explode(_argv: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError(2, "No such file or directory: 'bd'")

    _stub_absent_wrapper(monkeypatch=monkeypatch)
    monkeypatch.setattr(subprocess, "run", _explode)
    assert (
        bd_status_reader(repo=_REPO) is None
    ), "a missing CLI must degrade to UNVERIFIED, not to an empty ledger"


def test_bd_status_reader_is_unreachable_on_timeout(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A store behind a stalled network hop must degrade, never wedge the gate."""

    def _stall(_argv: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="bd", timeout=1.0)

    _stub_absent_wrapper(monkeypatch=monkeypatch)
    monkeypatch.setattr(subprocess, "run", _stall)
    assert (
        bd_status_reader(repo=_REPO) is None
    ), "a timed-out query is a non-answer, not an empty ledger"


def test_bd_status_reader_is_unreachable_on_nonzero_exit(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `Access denied` shape: the CLI ran and refused → `None`."""
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="Error 1045 (28000)", returncode=1)
    assert (
        bd_status_reader(repo=_REPO) is None
    ), "a refused query must not be read as a store holding no work items"


def test_bd_status_reader_is_unreachable_when_output_carries_no_json(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output with no JSON delimiter parses as an EMPTY population — refuse it.

    Without this guard a `bd` shim printing a banner and exiting 0 would
    convict every owned id in the registry as nonexistent, on the strength of
    junk.
    """
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="bd: nothing to report\n")
    assert (
        bd_status_reader(repo=_REPO) is None
    ), "junk output must be a non-answer, never an empty population"


def test_bd_status_reader_is_unreachable_on_unparseable_json(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Truncated JSON is a non-answer too."""
    _ = _stub_bd(monkeypatch=monkeypatch, stdout='{"data": [{"id": "x"')
    assert (
        bd_status_reader(repo=_REPO) is None
    ), "a half-written record must degrade rather than snapshot a partial ledger"
