"""An append whose reply was lost is recovered before local gates run again."""

from __future__ import annotations

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_entry as module
from livespec_dev_tooling.incident_hook_process import HookRefusalError
from tests.livespec_dev_tooling.test_incident_hook_entry_edges import _wired


def test_lost_canonical_append_reply_reuses_exact_payload_without_gate_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reading, _unused = _wired(root=tmp_path, monkeypatch=monkeypatch)
    records: dict[str, dict[str, Any]] = {}
    gate_calls: list[None] = []
    original = module.route_resolved_gates

    def gates(**kwargs: Any) -> Any:
        gate_calls.append(None)
        return original(**kwargs)

    def invoke(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "read-current":
            return reading
        bindings = dict(
            committed_token_id=reading["committed_token_id"],
            current_token_id=reading["current_token_id"],
        )
        if kwargs["action"] == "read-local-gates":
            identity = kwargs["receipt_id"]
            receipt = records.get(identity)
            return dict(
                status="recorded" if receipt else "absent",
                receipt_id=identity,
                checksum="sha256:" + "a" * 64 if receipt else None,
                receipt=deepcopy(receipt),
                **bindings,
            )
        receipt = json.loads(kwargs["receipt"])
        records[receipt["receipt_id"]] = receipt
        message = "append landed; reply was lost"
        raise HookRefusalError(message)

    monkeypatch.setattr(module, "route_resolved_gates", gates)
    monkeypatch.setattr(module, "invoke_authority", invoke)
    assert module.main(argv=["pre-commit"]) == 78
    assert len(records) == len(gate_calls) == 1
    original_receipt = deepcopy(next(iter(records.values())))
    assert module.main(argv=["pre-commit"]) == 0
    assert len(gate_calls) == len(records) == 1
    assert next(iter(records.values())) == original_receipt
