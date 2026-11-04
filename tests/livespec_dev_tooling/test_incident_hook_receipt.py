"""Unknown receipt lookups never authorize another local gate execution."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling.incident_hook_process import HookRefusalError
from livespec_dev_tooling.incident_hook_receipt import recover_receipt

_COMMITTED = "committed"
_CURRENT = "current"


def _identity() -> dict[str, str]:
    return dict(receipt_id="exact", tree="a" * 40, hook="pre-commit", mode="expedited-repair")


def _answer() -> dict[str, Any]:
    return dict(
        status="recorded",
        receipt_id="exact",
        committed_token_id=_COMMITTED,
        current_token_id=_CURRENT,
        checksum="sha256:" + "b" * 64,
        receipt=_identity()
        | dict(
            evidence_kind="expedited-local-partial",
            exit_status=3,
            results=[dict(name="failed gate")],
        ),
    )


def _recover(*, answer: dict[str, Any], root: Path) -> dict[str, Any] | None:
    return recover_receipt(
        repo=root,
        query={},
        reading=dict(committed_token_id=_COMMITTED, current_token_id=_CURRENT),
        identity=_identity(),
        invoke=lambda **_kw: answer,
    )


def test_exact_recorded_failure_returns_the_original_payload(tmp_path: Path) -> None:
    answer = _answer()
    before = deepcopy(answer)
    assert _recover(answer=answer, root=tmp_path) == answer["receipt"]
    assert answer == before


def test_only_canonical_absence_permits_initial_execution(tmp_path: Path) -> None:
    assert (
        _recover(
            answer=_answer() | dict(status="absent", receipt=None, checksum=None), root=tmp_path
        )
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"receipt_id": "other"},
        {"committed_token_id": "other"},
        {"current_token_id": "other"},
        {"status": "unknown"},
        {"status": "absent"},
        {"receipt": None},
        {"receipt": "wrong"},
        {"checksum": None},
        {"checksum": "not-a-checksum"},
    ],
)
def test_unbound_or_unknown_lookup_refuses(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(HookRefusalError):
        _recover(answer=_answer() | change, root=tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        {"receipt_id": "other"},
        {"tree": "other"},
        {"hook": "pre-push"},
        {"mode": "normal"},
        {"evidence_kind": "normal-proof"},
        {"exit_status": False},
        {"exit_status": -1},
        {"exit_status": 256},
    ],
)
def test_payload_must_bind_exact_invocation(tmp_path: Path, change: dict[str, Any]) -> None:
    answer = _answer()
    answer["receipt"] |= change
    with pytest.raises(HookRefusalError):
        _recover(answer=answer, root=tmp_path)
