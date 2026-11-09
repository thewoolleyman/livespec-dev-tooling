"""An expedited gate receipt fits the one argument it travels in.

The hook hands its receipt to the registered incident authority as a single
`--receipt-json` argument, and Linux refuses any one argument over 128 KiB
(E2BIG). With 75 fast gates each carrying its whole output, attempt 4 of
livespec-dev-tooling-e62ss6 was refused at commit with "[Errno 7] Argument list
too long" (gate run 20261109T121109Z-3825892). The limit is asserted on the
argv strings handed to exec, not on the receipt record.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_process as module
from livespec_dev_tooling._check_target_runner import (
    BLOCKED,
    COMPLETED,
    TIMED_OUT,
    TargetOutcome,
)
from livespec_dev_tooling.incident_local_gates import GateReport, _gate_result

__all__: list[str] = []

_ARGUMENT_CAP = 131072
_EVERY_GATE = 85
_QUERY = {
    "repository": "owner/repo",
    "item": "incident",
    "attempt": "attempt",
    "phase": "repair",
    "operation": "operation",
    "generation": 1,
    "owner": "operator",
}
# Worst-case escaping: a control byte becomes six characters, an astral one twelve.
_WORST = ("\x01\U0001f600─" * 40_000) + "the failing line"
_STATUSES = ((COMPLETED, 0), (COMPLETED, 1), (BLOCKED, None), (TIMED_OUT, None))


def _results() -> tuple[Any, ...]:
    return tuple(
        _gate_result(
            outcome=TargetOutcome(
                name=f"check-{index}",
                status=_STATUSES[index % len(_STATUSES)][0],
                returncode=_STATUSES[index % len(_STATUSES)][1],
                wall_time_s=61.0 if _STATUSES[index % len(_STATUSES)][0] == TIMED_OUT else 1.0,
                output=_WORST,
            ),
            concurrency=4,
        )
        for index in range(_EVERY_GATE)
    )


def test_every_argv_element_of_a_worst_case_receipt_call_stays_under_the_cap(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(module, "_governed_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(module, "registered_plugin_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(module.subprocess, "run", run)
    results = _results()
    receipt = dict(
        receipt_id="receipt",
        hook="pre-commit",
        tree="0" * 40,
        mode="expedited-repair",
        **asdict(GateReport(results=results, exit_status=1)),
    )
    with pytest.raises(module.HookRefusalError):
        _ = module.invoke_authority(
            repo=tmp_path,
            query=_QUERY,
            action="record-local-gates",
            receipt=module.canonical(value=receipt),
        )
    sizes = [len(os.fsencode(element)) for element in calls[0]]
    digest = hashlib.sha256(_WORST.encode("utf-8")).hexdigest()
    texts = [row.output or row.reason for row in results]
    facts = [
        max(sizes) < _ARGUMENT_CAP // 2,
        sum(sizes) < _ARGUMENT_CAP,
        all(text.endswith("the failing line") for text in texts),
        all(digest in text and str(len(_WORST)) in text for text in texts),
    ]
    assert all(facts), (max(sizes), sum(sizes), facts)


def test_a_small_gate_output_is_kept_whole() -> None:
    result = _gate_result(
        outcome=TargetOutcome(name="check-a", status=COMPLETED, returncode=0, output="ok\n"),
        concurrency=4,
    )
    assert result.output == "ok\n"
