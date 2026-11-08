"""Route installed git hooks before ordinary prechecks, caches or delegation."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    ExecutionContext,
    parse_incident_truth_value,
)
from livespec_dev_tooling.incident_gate_inventory import inventory_gates
from livespec_dev_tooling.incident_hook_process import (
    HookRefusalError,
    canonical,
    exact_tree,
    git_text,
    invoke_authority,
    parse_query,
    resolve_current,
)
from livespec_dev_tooling.incident_hook_receipt import recover_receipt
from livespec_dev_tooling.incident_hook_scope import HookCall, validate_scope
from livespec_dev_tooling.incident_local_gates import GateResult, route_resolved_gates
from livespec_dev_tooling.incident_transport import normal_child_environment

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import impure_safe  # noqa: E402 — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = ["main"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
QUERY_ENV = "LIVESPEC_INCIDENT_AUTHORITY_QUERY"
LOCAL_OPERATION_ENV = "LIVESPEC_INCIDENT_LOCAL_OPERATION"
_REFUSED = 78
_NORMAL = 75
_MAX_STDIN = 16384
_INDEX_ARGUMENTS = 2


def _refuse(*, reason: str) -> int:
    _ = sys.stderr.write("incident-hook-refused: " + reason + "\n")
    return _REFUSED


def _active() -> bool:
    flags = [
        parse_incident_truth_value(name=name, value=os.environ.get(name))
        for name in (EXPEDITED_INCIDENT_RESPONSE, EXPEDITED_INCIDENT_RESPONSE_REVERT)
    ]
    if any(not is_successful(value) for value in flags):
        message = "malformed incident flag"
        raise HookRefusalError(message)
    return any(value.unwrap() for value in flags)


def _persist(
    *, repo: Path, query: dict[str, Any], reading: dict[str, Any], receipt: dict[str, Any]
) -> None:
    saved = invoke_authority(
        repo=repo, query=query, action="record-local-gates", receipt=canonical(value=receipt)
    )
    expected = dict(
        receipt_id=receipt["receipt_id"],
        committed_token_id=reading["committed_token_id"],
        current_token_id=reading["current_token_id"],
    )
    checksum = saved.get("checksum")
    if (
        any(saved.get(key) != value for key, value in expected.items())
        or not isinstance(checksum, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", checksum) is None
    ):
        message = "partial receipt readback does not bind this invocation"
        raise HookRefusalError(message)
    current = invoke_authority(repo=repo, query=query, action="read-current")
    if current != reading:
        message = "current authority changed before hook admission"
        raise HookRefusalError(message)


def _finish(
    *,
    repo: Path,
    query: dict[str, Any],
    reading: dict[str, Any],
    receipt: dict[str, Any],
    context: ExecutionContext,
    recovered: bool = False,
) -> int:
    if recovered:
        current = invoke_authority(repo=repo, query=query, action="read-current")
        if current != reading:
            message = "current authority changed before hook receipt recovery"
            raise HookRefusalError(message)
    else:
        _persist(repo=repo, query=query, reading=reading, receipt=receipt)
    if exact_tree(repo=repo, context=context, hook=receipt["hook"]) != receipt["tree"]:
        return _refuse(reason="local tree changed during incident gates; partial receipt retained")
    _ = sys.stdout.write(
        canonical(value=dict(schema=1, receipt=receipt, normal_factory_proof=False)) + "\n"
    )
    return receipt["exit_status"]


@impure_safe
def _run(*, hook: str, extra: list[str], actual_index: str = "") -> int:
    if not _active():
        return _NORMAL
    if (
        actual_index
        and Path(actual_index).resolve()
        != Path(git_text(repo=Path.cwd(), args=["rev-parse", "--git-path", "index"])).resolve()
    ):
        return _refuse(reason="alternate Git operation index is unsupported for incident commits")
    stdin = sys.stdin.read(_MAX_STDIN + 1) if hook == "pre-push" else ""
    query = parse_query(text=os.environ.get(QUERY_ENV, "{}"))
    local_operation = os.environ.get(LOCAL_OPERATION_ENV, "")
    if query is None or not local_operation.strip() or local_operation != local_operation.strip():
        return _refuse(
            reason="exact canonical query and distinct local operation identity required"
        )
    repo = Path.cwd()
    reading = invoke_authority(repo=repo, query=query, action="read-current")
    context = resolve_current(reading=reading, query=query)
    started = time.monotonic()
    tree = exact_tree(repo=repo, context=context, hook=hook)
    scope = validate_scope(
        repo=repo,
        context=context,
        reading=reading,
        query=query,
        tree=tree,
        call=HookCall(hook=hook, extra=tuple(extra), stdin=stdin or ""),
    )
    # The scope row times the scope check alone: the receipt lookup below is an authority
    # read whose latency grows with the chain, and a "passed" row must stay under 60 s.
    scope_seconds = time.monotonic() - started
    receipt_id = hashlib.sha256(
        canonical(
            value=[
                local_operation,
                reading["committed_token_id"],
                reading["current_token_id"],
                hook,
                tree,
                scope,
            ]
        ).encode()
    ).hexdigest()
    prior = recover_receipt(
        repo=repo,
        query=query,
        reading=reading,
        identity=dict(receipt_id=receipt_id, hook=hook, tree=tree, mode=context.mode),
        invoke=invoke_authority,
    )
    if prior is not None:
        return _finish(
            repo=repo, query=query, reading=reading, receipt=prior, context=context, recovered=True
        )
    inventory = inventory_gates(inventory=(repo / "check-targets.txt").read_text())
    child = normal_child_environment(environ=os.environ)
    _ = child.pop(QUERY_ENV, None)
    _ = child.pop(LOCAL_OPERATION_ENV, None)
    scope_result = GateResult(
        name="incident-carrier-scope",
        status="passed",
        reason="exact canonical repair carrier verified",
        returncode=0,
        duration_seconds=scope_seconds,
        output=canonical(value=scope),
    )
    report = route_resolved_gates(context=context, gates=inventory, cwd=repo, environment=child)
    if report is None:
        return _refuse(reason="incident request did not resolve incident context")
    empty = (
        ()
        if inventory
        else (
            GateResult(
                name="incident-inventory", status="deferred", reason="no applicable gates declared"
            ),
        )
    )
    report = replace(report, results=(scope_result, *report.results, *empty))
    receipt = dict(receipt_id=receipt_id, hook=hook, tree=tree, mode=context.mode, **asdict(report))
    return _finish(repo=repo, query=query, reading=reading, receipt=receipt, context=context)


def main(*, argv: list[str] | None = None) -> int:
    """Exit 75 only for ordinary work; every incident result is terminal."""
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in {"pre-commit", "commit-msg", "pre-push"}:
        return _refuse(reason="unknown hook entrance")
    extra = args[1:]
    actual_index = ""
    if extra[:1] == ["--git-index-file"]:
        if len(extra) < _INDEX_ARGUMENTS:
            return _refuse(reason="missing actual Git index argument")
        actual_index, extra = extra[1], extra[2:]
    result = _run(hook=args[0], extra=extra, actual_index=actual_index)
    return (
        unsafe_perform_io(result.unwrap())
        if is_successful(result)
        else _refuse(reason=str(unsafe_perform_io(result.failure())))
    )


if __name__ == "__main__":
    raise SystemExit(main())
