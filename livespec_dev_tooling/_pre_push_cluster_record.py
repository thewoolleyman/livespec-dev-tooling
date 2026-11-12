"""The cluster-owned record that confirms reusable delegated pre-push evidence."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, cast

from livespec_dev_tooling._gate_member_report import parse_member_report, passed_members
from livespec_dev_tooling.gate_credential import with_gates_kubeconfig
from livespec_dev_tooling.gate_remote_invocation import GateCommandRunner

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

__all__: list[str] = ["cluster_record_confirms", "confirmation"]

_GATE_NAMESPACE = "gates"
_TREE_HASH_LABEL = "livespec.gate/tree-hash"
_COMPLETE = "Complete"
_FAILED = "Failed"
_ASSERTED = "True"


class Evidence(NamedTuple):
    """The evidence fields the retained Job record must independently confirm."""

    tree_hash: str
    gate_job: str
    members_passed: tuple[str, ...]


class Confirmation(NamedTuple):
    """Whether a retained Job confirms evidence, rather than merely existing."""

    matches: bool
    missing: bool
    disagreements: tuple[tuple[str, str, str], ...]


def _cluster_command(*, arguments: list[str]) -> list[str]:
    """Build one credential-wrapped read of the gates namespace."""
    return with_gates_kubeconfig(argv=["kubectl", "--namespace", _GATE_NAMESPACE, *arguments])


def _read_cluster(*, argv: list[str], cwd: Path, runner: GateCommandRunner) -> str | None:
    """Return one successful cluster reply, or ``None`` when no record is readable."""
    from returns.pipeline import is_successful

    outcome = runner(argv=argv, cwd=cwd)
    if not is_successful(outcome):
        return None
    completed = outcome.unwrap()
    return completed.stdout if completed.returncode == 0 else None


def _payload(*, output: str) -> Mapping[str, object] | None:
    """Decode a Kubernetes response only when it is a JSON object."""
    try:
        decoded: object = json.loads(output)
    except json.JSONDecodeError:
        return None
    return cast("Mapping[str, object]", decoded) if isinstance(decoded, Mapping) else None


def _job_conditions(*, payload: Mapping[str, object]) -> tuple[tuple[object, object], ...]:
    """Return the ``(type, status)`` pairs the Job's status conditions carried."""
    status = payload.get("status")
    empty: Mapping[str, object] = {}
    typed_status: Mapping[str, object] = (
        cast("Mapping[str, object]", status) if isinstance(status, Mapping) else empty
    )
    conditions: object | None = typed_status.get("conditions")
    typed_conditions = (
        cast("Sequence[object]", conditions)
        if isinstance(conditions, Sequence) and not isinstance(conditions, str)
        else ()
    )
    pairs: list[tuple[object, object]] = []
    for condition in typed_conditions:
        typed: Mapping[str, object] = (
            cast("Mapping[str, object]", condition) if isinstance(condition, Mapping) else empty
        )
        pairs.append((typed.get("type"), typed.get("status")))
    return tuple(pairs)


def _job_succeeded(*, conditions: tuple[tuple[object, object], ...]) -> bool:
    """Whether the Job carries Complete=True and never Failed=True."""
    complete = (_COMPLETE, _ASSERTED) in conditions
    failed = (_FAILED, _ASSERTED) in conditions
    return complete and not failed


def _carried_conditions(*, conditions: tuple[tuple[object, object], ...]) -> str:
    """Render the conditions the cluster carried, or say it carried none."""
    if not conditions:
        return "no conditions"
    return ",".join(f"{kind}={asserted}" for kind, asserted in conditions)


def _tree_hash(*, payload: Mapping[str, object]) -> str:
    """Return the retained Job's tree label, or an empty absent value."""
    metadata = payload.get("metadata")
    empty: Mapping[str, object] = {}
    typed_metadata: Mapping[str, object] = (
        cast("Mapping[str, object]", metadata) if isinstance(metadata, Mapping) else empty
    )
    labels: object | None = typed_metadata.get("labels")
    typed_labels: Mapping[str, object] = (
        cast("Mapping[str, object]", labels) if isinstance(labels, Mapping) else empty
    )
    value: object | None = typed_labels.get(_TREE_HASH_LABEL)
    return value if isinstance(value, str) else ""


def _pod_name(*, output: str) -> str | None:
    """Return the sole pod retained for a Job, or no name for an incomplete record."""
    payload = _payload(output=output)
    items = payload.get("items") if payload is not None else None
    typed_items = cast("list[object]", items) if isinstance(items, list) else []
    item: object = typed_items[0] if len(typed_items) == 1 else {}
    empty: Mapping[str, object] = {}
    record: Mapping[str, object] = (
        cast("Mapping[str, object]", item) if isinstance(item, Mapping) else empty
    )
    metadata: object | None = record.get("metadata")
    typed_metadata: Mapping[str, object] = (
        cast("Mapping[str, object]", metadata) if isinstance(metadata, Mapping) else empty
    )
    name: object | None = typed_metadata.get("name")
    return name if isinstance(name, str) and name else None


def confirmation(*, evidence: Evidence, cwd: Path, runner: GateCommandRunner) -> Confirmation:
    """Read the retained Job, pod and member report that can confirm an evidence file."""
    job_argv = _cluster_command(arguments=["get", "job", evidence.gate_job, "--output", "json"])
    job_output = _read_cluster(argv=job_argv, cwd=cwd, runner=runner)
    payload = _payload(output=job_output) if job_output is not None else None
    if payload is None:
        return Confirmation(matches=False, missing=True, disagreements=())
    pods_argv = _cluster_command(
        arguments=["get", "pods", "--selector", f"job-name={evidence.gate_job}", "--output", "json"]
    )
    pods_output = _read_cluster(argv=pods_argv, cwd=cwd, runner=runner)
    pod = _pod_name(output=pods_output) if pods_output is not None else None
    if pod is None:
        return Confirmation(matches=False, missing=True, disagreements=())
    logs_argv = _cluster_command(arguments=["logs", pod])
    logs_output = _read_cluster(argv=logs_argv, cwd=cwd, runner=runner)
    report = parse_member_report(output=logs_output) if logs_output is not None else None
    if report is None:
        return Confirmation(matches=False, missing=True, disagreements=())
    disagreements: list[tuple[str, str, str]] = []
    conditions = _job_conditions(payload=payload)
    if not _job_succeeded(conditions=conditions):
        disagreements.append(
            (
                "outcome",
                "Complete=True and Failed!=True",
                _carried_conditions(conditions=conditions),
            )
        )
    reported_tree = _tree_hash(payload=payload)
    if reported_tree != evidence.tree_hash:
        disagreements.append(("tree", evidence.tree_hash, reported_tree))
    reported_members = passed_members(report=report)
    if reported_members != evidence.members_passed:
        disagreements.append(
            ("member list", ",".join(evidence.members_passed), ",".join(reported_members))
        )
    return Confirmation(
        matches=not disagreements,
        missing=False,
        disagreements=tuple(disagreements),
    )


def cluster_record_confirms(*, evidence: Evidence, cwd: Path, runner: GateCommandRunner) -> bool:
    """Return whether the retained record confirms every reusable-evidence field."""
    return confirmation(evidence=evidence, cwd=cwd, runner=runner).matches
