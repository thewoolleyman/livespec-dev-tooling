"""Operator entrance: collect a reverted incident's original run, then propose its correction.

Run it as the independent controller account with the installation's isolated
interpreter, so the evidence lands in the observer's private state directory beside
the registration it reads. `--config` is the protected `controller.json`; everything
else comes from the installation it verifies: the state directory, the repository,
the reference clone and the manifest's canonical reader. The tenant credential is
`reader.env` beside it, and forge reads use the recovery App's read-only token from
`recovery-app.json` beside it. That account has no plugin registry, no credential
wrapper and no `gh`, and needs none of them:

    sudo -u livespec-incident -H /opt/livespec-incident/venv/bin/python -I \\
        -m livespec_dev_tooling.incident_original_run_entry collect \\
        --config /etc/livespec-incident/controller.json \\
        --revert-sha SHA [--expected-graph GRAPH.json]

    sudo -u livespec-incident -H /opt/livespec-incident/venv/bin/python -I \\
        -m livespec_dev_tooling.incident_original_run_entry propose-correction \\
        --config /etc/livespec-incident/controller.json \\
        --evidence-digest DIGEST --next-head-sha SHA --target-ref REF \\
        --current-attempt ID --current-owner PRINCIPAL --current-generation N \\
        [--staged-tree TREE] [--resolved JOB=RECEIPT ...]

`collect` refuses until the registered original master run has completed and
the canonical chain records the merge, through its `record-merge` action. The
expected jobs come from the workflow at the merge revision, matrix legs
expanded; `--expected-graph` is optional and, when given, must agree with that
workflow or it is refused by name. The running controller also collects by
itself after a revert lands, so this command is the operator's manual retry.
`propose-correction` hands a correction to the canonical `correct-attempt`
action against the attempt a recorded revert receipt moved to
`collecting-failures`: the `recovery-<digest>` attempt reopen-regression
recorded, owned by the incident principal, at generation N. REF is the
corrected attempt's reserved branch.

Each prints one schema-1 JSON reply. A refusal exits 78 and names its reason.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_original_run_ports import installed_ports, refresh_reference
from livespec_dev_tooling._incident_run_types import (
    EvidenceRefusal,
    ExpectedJob,
    RunEvidence,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_original_run_flows import (
    Collection,
    Correction,
    EntryPorts,
    collect,
    propose,
)
from livespec_dev_tooling.incident_run_evidence import evidence_digest

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["installed_ports", "main", "parse_graph"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zvntys
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-jvfb7x
_REFUSED = 78
_INVALID_GRAPH = "expected graph must list jobs as {name, needs}"
_NO_INSTALLATION = (
    "the configuration is not a protected installation for this account: run as the"
    " controller account with the installation's interpreter under -I"
)


def _parse(*, argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="incident-original-run")
    actions = parser.add_subparsers(dest="action", required=True)
    gather = actions.add_parser("collect")
    correct = actions.add_parser("propose-correction")
    for sub in (gather, correct):
        _ = sub.add_argument("--config", required=True, type=Path)
    _ = gather.add_argument("--revert-sha", required=True)
    _ = gather.add_argument("--expected-graph", type=Path)
    _ = gather.add_argument("--run-attempt", type=int, default=1)
    _ = gather.add_argument("--workflow", default=".github/workflows/ci.yml")
    for name in (
        "--evidence-digest",
        "--next-head-sha",
        "--target-ref",
        "--current-attempt",
        "--current-owner",
    ):
        _ = correct.add_argument(name, required=True)
    _ = correct.add_argument("--current-generation", required=True, type=int)
    _ = correct.add_argument("--resolved", action="append", default=[])
    _ = correct.add_argument("--base-ref", default="origin/master")
    _ = correct.add_argument("--staged-tree", default="")
    return parser.parse_args(list(argv))


def _reply(*, body: dict[str, object]) -> int:
    _ = sys.stdout.write(json.dumps({"schema": 1, **body}, sort_keys=True) + "\n")
    return _REFUSED if body["status"] == "refused" else 0


def _refused(*, refusal: EvidenceRefusal) -> int:
    return _reply(body={"status": "refused", "code": refusal.code, "detail": refusal.detail})


def _collected(*, evidence: RunEvidence) -> int:
    return _reply(
        body={
            "status": "collected",
            "evidence_digest": evidence_digest(evidence=evidence),
            "run_id": evidence.original.run_id,
            "terminal": evidence.terminal,
            "jobs": [[job.name, job.state, job.conclusion] for job in evidence.jobs],
            "debts": [debt.job_name for debt in evidence.debts],
        }
    )


def parse_graph(*, value: object) -> tuple[ExpectedJob, ...]:
    """An operator's expected jobs, spelled as the forge names them; acyclicity is checked later."""
    if not isinstance(value, list):
        raise TypeError(_INVALID_GRAPH)
    jobs: list[ExpectedJob] = []
    for row in cast("list[object]", value):
        record = cast("dict[str, object]", row) if isinstance(row, dict) else {}
        name, needs = record.get("name"), record.get("needs", [])
        if (
            set(record) - {"name", "needs"}
            or not isinstance(name, str)
            or not isinstance(needs, list)
            or not all(isinstance(need, str) for need in cast("list[object]", needs))
        ):
            raise TypeError(_INVALID_GRAPH)
        jobs.append(ExpectedJob(name=name, needs=tuple(cast("list[str]", needs))))
    return tuple(jobs)


@impure_safe
def _graph(*, path: Path) -> tuple[ExpectedJob, ...]:
    return parse_graph(value=json.loads(path.read_text()))


def _collect(
    *, args: argparse.Namespace, ports: EntryPorts, installation: ControllerInstallation
) -> int:
    expected = None
    if args.expected_graph is not None:
        graph = _graph(path=args.expected_graph)
        if not is_successful(graph):
            return _refused(
                refusal=EvidenceRefusal(
                    code="incident-original-run-graph-invalid", detail="unreadable expected graph"
                )
            )
        expected = unsafe_perform_io(graph.unwrap())
    result = collect(
        request=Collection(
            state_dir=installation.state,
            repository=installation.repository,
            revert_sha=args.revert_sha,
            expected=expected,
            run_attempt=args.run_attempt,
            workflow_path=args.workflow,
        ),
        ports=ports,
    )
    if isinstance(result, EvidenceRefusal):
        return _refused(refusal=result)
    return _collected(evidence=result)


def _propose(
    *, args: argparse.Namespace, ports: EntryPorts, installation: ControllerInstallation
) -> int:
    pairs = [cast("str", text).partition("=") for text in args.resolved]
    if any(not job or not sep or not receipt for job, sep, receipt in pairs):
        return _refused(
            refusal=EvidenceRefusal(
                code="incident-original-run-invalid-request", detail="--resolved is JOB=RECEIPT"
            )
        )
    result = propose(
        request=Correction(
            state_dir=installation.state,
            repository=installation.repository,
            evidence_digest=args.evidence_digest,
            next_head_sha=args.next_head_sha,
            target_ref=args.target_ref,
            current_attempt=args.current_attempt,
            current_owner=args.current_owner,
            current_generation=args.current_generation,
            resolved_jobs=tuple((job, receipt) for job, _sep, receipt in pairs),
            base_ref=args.base_ref,
            staged_tree=args.staged_tree,
        ),
        ports=ports,
    )
    if isinstance(result, EvidenceRefusal):
        return _refused(refusal=result)
    return _reply(body={"status": "proposed", "receipt": result})


def _bound(*, installation: ControllerInstallation) -> EntryPorts | None:
    """The installed ports with a current reference clone, or None without the credential."""
    try:
        ports = installed_ports(installation=installation)
    except OSError:
        return None
    refresh_reference(installation=installation)
    return ports


def main(*, argv: Sequence[str] | None = None, ports: EntryPorts | None = None) -> int:
    """Collect or propose for one registered original run; refusals exit 78."""
    args = _parse(argv=sys.argv[1:] if argv is None else argv)
    # The service unit's UMask: this writes the same private state the observer reads.
    _ = os.umask(0o077)
    installation = ControllerInstallation.load(config=args.config)
    bound = ports
    if installation is not None and bound is None:
        bound = _bound(installation=installation)
    if installation is None or bound is None:
        return _refused(
            refusal=EvidenceRefusal(
                code="incident-original-run-installation-unavailable", detail=_NO_INSTALLATION
            )
        )
    if args.action == "collect":
        return _collect(args=args, ports=bound, installation=installation)
    return _propose(args=args, ports=bound, installation=installation)


if __name__ == "__main__":
    raise SystemExit(main())
