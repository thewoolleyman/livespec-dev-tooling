"""Consumer-tier: `SPECIFICATION/scenarios.md` §"an unarmed-until payload naming a closed work item is a conformance failure".

    Given a consumer declares a union role key as `unarmed_until` whose payload
    names a work item that is closed
    When the conformance verifier runs
    Then it MUST report a failure identifying the consumer, the key, and the item
    And the failure MUST state that the declaration claims pending work that is
    already complete

`public_api_result_typed` is the verifier driven here rather than the announcer
called directly, because the check IS the conformance verifier from a
consumer's side: it is the shipped gate whose disarming by a switched-off role
key was measured across nine fleet repositories, and its stderr is where a
consumer reads the verdict. What the scenario calls a failure is an
ERROR-severity structured record — `role_absence_exit_code` returns 0 for every
declared-absent variant by ratified design, so severity, not exit code, is the
observable the clause names.

The work-item store is a DOUBLE. `_role_key_gate.bd_status_reader` is read off
the module at call time exactly so it can be, and every status below is
synthetic: a test whose verdict depended on some production work item staying
closed would decay into a false green the day someone reopened it.

The three-way distinction is asserted together, because the defect this scenario
closes was a verifier that could not make it: CLOSED must convict, OPEN must
not, and a store that did not ANSWER must do neither. A skip that renders like a
pass and a pass that renders like a skip are the same bug from two sides.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import _role_key_gate, public_api_result_typed
from livespec_dev_tooling.checks._work_item_liveness import LedgerUnreachable
from tests.consumer.role_key_fixture import (
    ROLE_KEY_SPELLING_FIELD,
    records_from,
    union_key_block,
    write_consumer,
)

_VENDOR_DIR = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []

pytestmark = pytest.mark.consumer

# The union role key the declaration hangs on, and the synthetic item it names.
_UNION_KEY = "pure_trees"
_LEDGER_ID = "acme-widget-4211"
_COMMENT = "# switched off pending the named work"
# The clause a reader ACTS on. Asserted as a phrase rather than as the whole
# ratified sentence, so a wording revision that keeps the meaning does not fail
# the test while a revision that drops the clause does.
_ALREADY_COMPLETE = "already complete"


def _drive(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: dict[str, str] | None,
) -> dict[str, object]:
    """Run the verifier over an `unarmed_until` declaration; return its announcement.

    `snapshot` is what the consumer's configured work-item store answers —
    `None` meaning it did not answer at all. Nothing here opens a socket,
    spawns a process, or reads a real tenant.
    """
    answer: IOResult[dict[str, str], LedgerUnreachable] = (
        IOFailure(
            LedgerUnreachable(
                repo=".",
                argv="bd -C . list --status all --json",
                reason="query-unrunnable",
                detail="test double: no store configured",
            )
        )
        if snapshot is None
        else IOSuccess(snapshot)
    )

    def _read(*, repo: Path) -> IOResult[dict[str, str], LedgerUnreachable]:
        del repo  # The double answers for whatever repo it is handed.
        return answer

    monkeypatch.setattr(_role_key_gate, "bd_status_reader", _read)
    root = write_consumer(
        root=tmp_path / "consumer",
        block=union_key_block(
            key=_UNION_KEY, value=f'{{ unarmed_until = "{_LEDGER_ID}" }}', comment=_COMMENT
        ),
    )
    monkeypatch.chdir(root)

    code = public_api_result_typed.main()

    captured = capsys.readouterr()
    records = records_from(captured=captured.out + captured.err)
    assert code == 0, (
        f"the verdict is ANNOUNCED, not enforced by exit code — every declared-absent "
        f"variant exits 0 by ratified design; got exit={code} records={records!r}"
    )
    announced = [
        record for record in records if record.get(ROLE_KEY_SPELLING_FIELD) == "unarmed_until"
    ]
    assert len(announced) == 1, (
        f"the verifier must report the `unarmed_until` declaration by name, exactly once; "
        f"got {announced!r} from {records!r}"
    )
    return announced[0]


def test_a_closed_work_item_is_reported_as_a_conformance_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLOSED convicts, and the report identifies the consumer, the key and the item."""
    announced = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        snapshot={_LEDGER_ID: "closed"},
    )

    assert announced.get("level") == "error", (
        f"a declaration naming work that is already complete MUST be reported as a "
        f"FAILURE — reporting it at the same severity as a genuinely-pending deferral "
        f"is what let a key stay switched off forever; got {announced!r}"
    )
    identified = {
        "consumer": announced.get("consumer"),
        "key": announced.get("role"),
        "item": announced.get("ledger_id"),
    }
    assert identified["key"] == _UNION_KEY and identified["item"] == _LEDGER_ID, (
        f"the failure MUST identify the consumer, the key, and the item — a report that "
        f"names only the severity leaves a reader with nothing to fix; got {identified!r}"
    )
    consumer = identified["consumer"]
    assert isinstance(consumer, str) and consumer.endswith("consumer"), (
        f"the failure must name the CONSUMER whose declaration it convicts, which is the "
        f"tree the check ran over; got {consumer!r}"
    )
    assert _ALREADY_COMPLETE in json.dumps(announced), (
        f"the failure MUST state that the declaration claims pending work that is already "
        f"complete — the resolved status alone leaves the reader to infer the consequence, "
        f"and that clause is the one they act on; got {announced!r}"
    )


def test_an_open_item_and_an_unanswering_store_are_both_distinguishable_from_the_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other two arms, so the conviction above is a verdict rather than a constant."""
    still_open = _drive(
        tmp_path=tmp_path / "open",
        monkeypatch=monkeypatch,
        capsys=capsys,
        snapshot={_LEDGER_ID: "ready"},
    )
    no_answer = _drive(
        tmp_path=tmp_path / "unreachable", monkeypatch=monkeypatch, capsys=capsys, snapshot=None
    )

    assert still_open.get("level") != "error", (
        f"work that is genuinely still open is the state `unarmed_until` EXISTS to "
        f"declare, so it must not be convicted; got {still_open!r}"
    )
    assert _ALREADY_COMPLETE not in json.dumps(still_open), (
        f"the already-complete clause must be earned by a closed item, not emitted on "
        f"every `unarmed_until` declaration; got {still_open!r}"
    )
    assert no_answer.get("level") != "error" and no_answer.get("liveness_unverified") is True, (
        f"a store that did not answer establishes NOTHING, so it must render as an "
        f"explicit UNVERIFIED skip rather than as either a conviction or a silent pass; "
        f"got {no_answer!r}"
    )
