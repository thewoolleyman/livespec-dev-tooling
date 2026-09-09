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
  timeout, non-JSON output, unparseable JSON — rides the `IOResult` FAILURE
  track, which is distinct from the `IOSuccess({})` a reachable-but-empty
  store returns.

And, since livespec-dev-tooling-qndn put both public answers on the railway,
a third property the sentinel could not express:

- IT SAYS WHICH NON-ANSWER OCCURRED. The four failure modes carry four
  distinct `reason` words. Collapsed onto one `None`, "there is no `bd` on
  this host" and "`bd` ran and was refused because the tenant password is not
  projected" were the same word — and only the second is a repair the reader
  can make in one command.

No test contacts a real tracker: `subprocess.run` and `shutil.which` are
monkeypatched, so nothing here spawns a process or opens a socket.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks._work_item_liveness import (
    NONEXISTENT,
    UNREACHABLE,
    LedgerUnreachable,
    bd_status_reader,
    resolve_liveness,
    resolved_status,
)

_VENDOR_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


_OWNER = "livespec-dev-tooling-d0er"
# The reader never touches the filesystem — `repo` only reaches `bd -C`, which is
# stubbed here — so any path serves as the query subject.
_REPO = Path()
# The two names `checks/public_api_result_typed` accepts as railway-typed, and
# the terminal-name reduction it applies before comparing. Restated here rather
# than imported so this test pins the PROPERTY the shipped detector reads,
# independently of that module continuing to exist in its current shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})


def _terminal_return_name(*, rendered: str) -> str:
    """`IOResult[dict[str, str], LedgerUnreachable]` → `IOResult`.

    Mirrors `public_api_result_typed._annotation_head_name`: drop the
    subscript, then drop any dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _stub_bd(
    *,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str = "",
    stderr: str = "",
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
        return subprocess.CompletedProcess(
            args=list(argv), returncode=returncode, stdout=stdout, stderr=stderr
        )

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


def _unanswered(*, monkeypatch: pytest.MonkeyPatch) -> IOResult[dict[str, str], LedgerUnreachable]:
    """A REAL failure-track snapshot, produced by the reader rather than forged.

    Building it through `bd_status_reader` keeps the pure-resolver tests
    below honest about what a failed read actually looks like: a hand-rolled
    `IOFailure` would still pass if the reader stopped producing one.
    """
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="bd: nothing to report\n")
    return bd_status_reader(repo=_REPO)


def test_both_public_answers_are_railway_typed() -> None:
    """THE CONVERSION ITSELF: neither public answer may be a bare value.

    `checks/public_api_result_typed` reads a function as on the railway when
    its return annotation's terminal name is `Result` or `IOResult` (or it
    carries a `safe` / `impure_safe` decorator). That check is a NO-OP in this
    repository — `pure_trees` is declared `not_applicable` — so nothing else
    here would notice a regression to `dict[str, str] | None` / `bool | None`.
    This is the arming that stands in for it until the scan universe is.
    """
    for func in (bd_status_reader, resolve_liveness):
        rendered = str(func.__annotations__["return"])
        assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, (
            f"{func.__name__} must return a Result/IOResult so its failure track is "
            f"expressible; got the bare annotation {rendered!r}"
        )


def test_resolve_liveness_is_unverified_when_the_store_did_not_answer(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No snapshot → the FAILURE track, the honest degradation the clause requires."""
    live = resolve_liveness(work_item=_OWNER, snapshot=_unanswered(monkeypatch=monkeypatch))
    assert isinstance(
        live, IOFailure
    ), f"an unanswered store must report UNVERIFIED, never a verdict it did not earn; got {live!r}"


def test_resolve_liveness_forwards_the_stores_own_failure_unchanged(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resolver adds no failure mode, so the reader's payload reaches the caller.

    Re-wrapping would make a caller distinguish two error types for one
    condition, and would strand the `reason` the operator acts on.
    """
    snapshot = _unanswered(monkeypatch=monkeypatch)
    live = resolve_liveness(work_item=_OWNER, snapshot=snapshot)
    assert isinstance(live, IOFailure), f"expected the failure track; got {live!r}"
    assert unsafe_perform_io(live.failure()) is unsafe_perform_io(
        snapshot.failure()
    ), "the resolver must forward the reader's LedgerUnreachable, not mint a second one"


def test_resolve_liveness_convicts_a_closed_owner() -> None:
    """THE FAIL CAPABILITY: a closed owner resolves False so the gate can convict it."""
    live = resolve_liveness(work_item=_OWNER, snapshot=IOSuccess({_OWNER: "closed"}))
    assert (
        unsafe_perform_io(live.unwrap()) is False
    ), "a closed owner must resolve False; a resolver that cannot say so is vacuous"


def test_resolve_liveness_convicts_an_owner_closed_under_the_native_spelling() -> None:
    """`done` is beads' own spelling of finished and must convict identically."""
    live = resolve_liveness(work_item=_OWNER, snapshot=IOSuccess({_OWNER: "done"}))
    assert (
        unsafe_perform_io(live.unwrap()) is False
    ), "the closed set must cover both vocabularies, or one spelling silences the gate"


def test_resolve_liveness_convicts_an_owner_the_store_does_not_hold() -> None:
    """A reachable store that lacks the id makes the id NONEXISTENT, hence dead."""
    live = resolve_liveness(
        work_item=_OWNER, snapshot=IOSuccess({"livespec-dev-tooling-other": "ready"})
    )
    assert (
        unsafe_perform_io(live.unwrap()) is False
    ), "an id absent from a store that DID answer is nonexistent, not unverified"


def test_resolve_liveness_accepts_an_open_owner() -> None:
    """An open owner resolves True so a live stand-down stays quiet."""
    live = resolve_liveness(work_item=_OWNER, snapshot=IOSuccess({_OWNER: "ready"}))
    assert (
        unsafe_perform_io(live.unwrap()) is True
    ), "an open owner must resolve True; convicting it would red every honest repo"


def test_resolved_status_names_the_unreachable_store(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The reportable word for a store that did not answer."""
    assert (
        resolved_status(work_item=_OWNER, snapshot=_unanswered(monkeypatch=monkeypatch))
        == UNREACHABLE
    ), "the diagnostic must be able to say the store never answered"


def test_resolved_status_names_a_missing_id() -> None:
    """The reportable word separating the two halves of `closed or nonexistent`."""
    assert (
        resolved_status(work_item=_OWNER, snapshot=IOSuccess({})) == NONEXISTENT
    ), "a reader must be able to tell a closed owner from an invented id"


def test_resolved_status_reports_the_stores_own_word() -> None:
    """A resolved id reports the status verbatim, as the ratified clause requires."""
    assert (
        resolved_status(work_item=_OWNER, snapshot=IOSuccess({_OWNER: "acceptance"}))
        == "acceptance"
    ), "the finding must name the id AND its resolved status"


def test_bd_status_reader_snapshots_id_to_status(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable store yields an id → status map, and is queried with `--status all`."""
    payload = (
        '[{"id": "livespec-dev-tooling-d0er", "status": "active"}, '
        '{"id": "livespec-dev-tooling-old", "status": "closed"}, '
        '{"id": "livespec-dev-tooling-partial"}]'
    )
    seen = _stub_bd(monkeypatch=monkeypatch, stdout=payload)
    read = bd_status_reader(repo=_REPO)
    assert isinstance(read, IOSuccess), f"a reachable store must succeed; got {read!r}"
    snapshot = unsafe_perform_io(read.unwrap())
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
    """A reachable but empty store answers `IOSuccess({})` — never the failure track."""
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="[]")
    read = bd_status_reader(repo=_REPO)
    assert isinstance(read, IOSuccess) and unsafe_perform_io(read.unwrap()) == {}, (
        "an empty store ANSWERED; collapsing that onto the failure track would make "
        "'I could not ask' indistinguishable from 'there is nothing there'"
    )


def test_bd_status_reader_is_unreachable_when_the_cli_is_absent(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `bd` on the host → the failure track, never a fabricated empty population."""

    def _explode(_argv: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError(2, "No such file or directory: 'bd'")

    _stub_absent_wrapper(monkeypatch=monkeypatch)
    monkeypatch.setattr(subprocess, "run", _explode)
    read = bd_status_reader(repo=_REPO)
    assert isinstance(
        read, IOFailure
    ), f"a missing CLI must degrade to UNVERIFIED, not to an empty ledger; got {read!r}"
    unreachable = unsafe_perform_io(read.failure())
    assert unreachable.argv.startswith("bd "), (
        f"the failure must name the invocation an operator would re-run; "
        f"got argv={unreachable.argv!r}"
    )


def test_bd_status_reader_is_unreachable_on_timeout(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A store behind a stalled network hop must degrade, never wedge the gate."""

    def _stall(_argv: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="bd", timeout=1.0)

    _stub_absent_wrapper(monkeypatch=monkeypatch)
    monkeypatch.setattr(subprocess, "run", _stall)
    assert isinstance(
        bd_status_reader(repo=_REPO), IOFailure
    ), "a timed-out query is a non-answer, not an empty ledger"


def test_bd_status_reader_is_unreachable_on_nonzero_exit(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `Access denied` shape: the CLI ran and refused → the failure track."""
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="Error 1045 (28000)", returncode=1)
    read = bd_status_reader(repo=_REPO)
    assert isinstance(
        read, IOFailure
    ), "a refused query must not be read as a store holding no work items"
    assert "exit 1" in unsafe_perform_io(read.failure()).detail, (
        "the refusal must carry the exit code: it is what tells an operator the CLI "
        "ran at all, which is the difference between a credential fix and an install"
    )


def test_bd_status_reader_is_unreachable_when_output_carries_no_json(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output with no JSON delimiter parses as an EMPTY population — refuse it.

    Without this guard a `bd` shim printing a banner and exiting 0 would
    convict every owned id in the registry as nonexistent, on the strength of
    junk.
    """
    _ = _stub_bd(monkeypatch=monkeypatch, stdout="bd: nothing to report\n")
    assert isinstance(
        bd_status_reader(repo=_REPO), IOFailure
    ), "junk output must be a non-answer, never an empty population"


def test_bd_status_reader_is_unreachable_on_unparseable_json(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Truncated JSON is a non-answer too."""
    _ = _stub_bd(monkeypatch=monkeypatch, stdout='{"data": [{"id": "x"')
    assert isinstance(
        bd_status_reader(repo=_REPO), IOFailure
    ), "a half-written record must degrade rather than snapshot a partial ledger"


def test_the_four_non_answers_are_told_apart(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ THE LOAD-BEARING TEST OF THE CONVERSION: the collapse is undone.

    The pre-railway reader answered `None` for all four, so a stand-down
    diagnostic could not tell an operator whether to install `bd`, project the
    tenant password, or go look at what their `bd` is printing. Four distinct
    reasons is the property that makes the failure track worth having; three
    would mean two modes had been merged again.
    """

    def _explode(_argv: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError(2, "No such file or directory: 'bd'")

    _stub_absent_wrapper(monkeypatch=monkeypatch)
    monkeypatch.setattr(subprocess, "run", _explode)
    unrunnable = bd_status_reader(repo=_REPO)
    reasons = {unsafe_perform_io(unrunnable.failure()).reason}
    for stdout, returncode in (("Error 1045", 1), ("banner\n", 0), ('{"data": [{"id"', 0)):
        _ = _stub_bd(monkeypatch=monkeypatch, stdout=stdout, returncode=returncode)
        read = bd_status_reader(repo=_REPO)
        assert isinstance(read, IOFailure), f"expected a non-answer for {stdout!r}; got {read!r}"
        reasons.add(unsafe_perform_io(read.failure()).reason)
    assert len(reasons) == 4, (
        f"each of the four non-answers must carry its own reason, or the collapse the "
        f"railway conversion removed has been reintroduced; got {sorted(reasons)}"
    )
