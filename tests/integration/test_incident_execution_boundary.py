"""Exercise the shared resolver at a real process and gate-selection boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    ExecutionContext,
    ExecutionMode,
    Invocation,
    OperationIdentity,
)
from livespec_dev_tooling.incident_transport import (
    CONTEXT_ENV,
    child_environment,
    decode_execution_context,
)

__all__: list[str] = []
pytestmark = pytest.mark.integration

# The child represents an authenticated caller, not an installed fleet hook.
# Its trusted event and receipt fixture arrive through explicit test argv.
_CHILD = """
import os,sys
from livespec_dev_tooling.incident_execution import (
    OperationIdentity, resolve_execution_context,
)
from livespec_dev_tooling.incident_transport import (
    child_environment, decode_execution_context, encode_execution_context,
)
assert "COVERAGE_PROCESS_START" not in os.environ
assert not any(key.startswith("COV_CORE_") for key in os.environ)
invocation, phase, merge = sys.argv[1:]
identity = OperationIdentity(incident_item_id="incident-123", attempt_id="attempt-1",
    phase=phase, repository="owner/repo", base_sha="a"*40, head_sha="b"*40,
    operation_id="operation-1", recorded_incident_merge_sha=merge or None)
resolved = resolve_execution_context(environ=os.environ, invocation=invocation, identity=identity)
if not resolved.is_successful:
    print(resolved.failure().code)
    sys.exit(78)
context = resolved.unwrap()
transport = encode_execution_context(context=context).unwrap()
assert decode_execution_context(payload=transport, trusted_context=context).unwrap() == context
environment = child_environment(context=context, environ=os.environ).unwrap()
if context.mode == "normal":
    assert "EXPEDITED_INCIDENT_RESPONSE" not in environment
    assert "EXPEDITED_INCIDENT_RESPONSE_REVERT" not in environment
    assert "LIVESPEC_INCIDENT_CONTEXT" not in environment
# This observable is deliberately after both resolution and transport checking.
print("selected:" + context.mode)
"""


@pytest.mark.parametrize(
    ("invocation", "phase", "merge", "repair", "revert", "expected", "code"),
    [
        ("ordinary", "repair", "", "", "", "selected:normal", 0),
        ("ordinary", "repair", "", "1", "", "selected:expedited-repair", 0),
        ("ordinary", "reverting", "c" * 40, "1", "1", "selected:emergency-revert", 0),
        ("ordinary", "reverting", "", "1", "1", "missing-recorded-incident-merge", 78),
        ("ordinary", "repair", "", "malformed", "", "invalid-incident-flag", 78),
        ("normal-master", "repair", "", "malformed", "malformed", "selected:normal", 0),
        ("normal-factory-follow-up", "repair", "", "malformed", "malformed", "selected:normal", 0),
    ],
)
def test_process_boundary_resolves_before_gate_selection(
    *,
    invocation: str,
    phase: str,
    merge: str,
    repair: str,
    revert: str,
    expected: str,
    code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COVERAGE_PROCESS_START", "unexpected-child-coverage")
    monkeypatch.setenv("COV_CORE_SOURCE", "unexpected-child-source")
    result = subprocess.run(
        [sys.executable, "-c", _CHILD, invocation, phase, merge],
        env={
            **_process_environment(),
            "EXPEDITED_INCIDENT_RESPONSE": repair,
            "EXPEDITED_INCIDENT_RESPONSE_REVERT": revert,
            "LIVESPEC_INCIDENT_CONTEXT": "stale",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == code, result.stderr
    assert result.stdout.strip() == expected


def _process_environment() -> dict[str, str]:
    """Keep real child boundaries independent of parallel coverage writers."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }


def _context(*, mode: str = ExecutionMode.EXPEDITED_REPAIR) -> ExecutionContext:
    """Model context independently authenticated by the receiving caller."""
    identity = OperationIdentity(
        incident_item_id="incident-123",
        attempt_id="attempt-1",
        phase="repair",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="operation-1",
    )
    if mode == ExecutionMode.EMERGENCY_REVERT:
        identity = replace(identity, phase="reverting", recorded_incident_merge_sha="c" * 40)
    return ExecutionContext(
        mode=mode,
        invocation=Invocation.ORDINARY,
        identity=None if mode == ExecutionMode.NORMAL else identity,
    )


@pytest.mark.parametrize(
    ("mode", "flag"),
    [
        (ExecutionMode.EXPEDITED_REPAIR, EXPEDITED_INCIDENT_RESPONSE),
        (ExecutionMode.EMERGENCY_REVERT, EXPEDITED_INCIDENT_RESPONSE_REVERT),
    ],
)
def test_explicit_inner_environment_survives_a_real_scrubbing_process(
    *, mode: str, flag: str
) -> None:
    context = _context(mode=mode)
    projected = child_environment(
        context=context,
        environ={
            EXPEDITED_INCIDENT_RESPONSE: "bad",
            EXPEDITED_INCIDENT_RESPONSE_REVERT: "bad",
            CONTEXT_ENV: "bad",
        },
    ).unwrap()
    assert set(projected) == {flag, CONTEXT_ENV}
    # env -i is a real process boundary that removes every outer value;
    # explicit inner argv recreates only this operation's nonsecret transport.
    result = subprocess.run(
        [
            "env",
            "-i",
            *[f"{key}={value}" for key, value in projected.items()],
            sys.executable,
            "-c",
            "import os,json; print(json.dumps(dict(os.environ)))",
        ],
        env={**_process_environment(), EXPEDITED_INCIDENT_RESPONSE: "foreign"},
        text=True,
        capture_output=True,
        check=True,
    )
    received = json.loads(result.stdout)
    assert received[flag] == "1"
    assert (
        decode_execution_context(payload=received[CONTEXT_ENV], trusted_context=context).unwrap()
        == context
    )


def test_transport_imports_in_a_fresh_process_without_preimported_resolver() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from livespec_dev_tooling.incident_transport import CONTEXT_ENV; assert CONTEXT_ENV == 'LIVESPEC_INCIDENT_CONTEXT'",
        ],
        env=_process_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
