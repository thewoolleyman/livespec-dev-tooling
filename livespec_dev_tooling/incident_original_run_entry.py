"""Operator entrance: collect a reverted incident's original run, then propose its correction.

Run it as the independent controller account, so the evidence lands in the
observer's private state directory beside the registration it reads. `--repo`
is the governed primary checkout; the incident item is reached through the
credential wrapper and the project's registered orchestrator build:

    python -m livespec_dev_tooling.incident_original_run_entry collect \\
        --state-dir DIR --repository OWNER/REPO --repo PRIMARY \\
        --revert-sha SHA --expected-graph GRAPH.json

    python -m livespec_dev_tooling.incident_original_run_entry propose-correction \\
        --state-dir DIR --repository OWNER/REPO --repo PRIMARY \\
        --evidence-digest DIGEST --next-head-sha SHA --target-ref REF \\
        --current-attempt ID --current-owner PRINCIPAL --current-generation N \\
        [--resolved JOB=RECEIPT ...]

`collect` refuses until the registered original master run has completed.
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
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_original_run_canonical import CanonicalPorts
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, ExpectedJob, RunEvidence
from livespec_dev_tooling.flake_retry_filer import registered_plugin_root
from livespec_dev_tooling.incident_original_run_flows import (
    Collection,
    Correction,
    EntryPorts,
    collect,
    propose,
)
from livespec_dev_tooling.incident_run_evidence import evidence_digest
from livespec_dev_tooling.incident_run_forge import ForgeRunReader

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["main", "parse_graph", "registered_ports"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zvntys
_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
_REFUSED = 78
_TIMEOUT = 120
_UNVERIFIED = "registered incident authority refused or returned an invalid reply"
_INVALID_GRAPH = "expected graph must list jobs as {name, needs}"


def _run(*, argv: Sequence[str], cwd: Path, stdin: bytes = b"") -> bytes:
    return subprocess.run(  # noqa: S603 -- fixed git, bd and registered authority argv.
        list(argv), cwd=cwd, input=stdin, capture_output=True, timeout=_TIMEOUT, check=True
    ).stdout


def _flags(*, values: Mapping[str, object]) -> list[str]:
    return [part for name, value in values.items() for part in ("--" + name, str(value))]


@dataclass(frozen=True, kw_only=True)
class _Git:
    repo: Path

    def __call__(self, args: Sequence[str], stdin: bytes) -> bytes:
        return _run(argv=["git", *args], cwd=self.repo, stdin=stdin)


@dataclass(frozen=True, kw_only=True)
class _Ledger:
    """`bd` through the credential wrapper, so the incident item is reachable."""

    repo: Path

    def __call__(self, args: Sequence[str]) -> str:
        return _run(argv=[_WRAPPER, "--", "bd", *args], cwd=self.repo).decode()


@dataclass(frozen=True, kw_only=True)
class _Authority:
    """The project's registered orchestrator `incident_authority.py`, never caller JSON."""

    repo: Path

    def __call__(
        self, action: str, query: Mapping[str, object], payload: Mapping[str, str]
    ) -> dict[str, Any]:
        plugin = registered_plugin_root(
            repo_root=self.repo, registry=Path.home() / ".claude/plugins/installed_plugins.json"
        )
        script = str(plugin / "scripts/bin/incident_authority.py")
        argv = [_WRAPPER, "--", "python3", script, action, "--repo", str(self.repo)]
        argv += _flags(values={**query, **payload})
        reply = cast("object", json.loads(_run(argv=argv, cwd=self.repo)))
        body = cast("dict[str, Any]", reply) if isinstance(reply, dict) else {}
        result = body.get("result")
        if (
            body.get("schema") != 1
            or body.get("status") != "verified"
            or body.get("normal_factory_proof") is not False
            or not isinstance(result, dict)
        ):
            raise ValueError(_UNVERIFIED)
        return cast("dict[str, Any]", result)


def registered_ports(*, repo: Path) -> EntryPorts:
    """Git in the primary, bd through the wrapper, and the registered authority."""
    return EntryPorts(
        canonical=CanonicalPorts(authority=_Authority(repo=repo), ledger=_Ledger(repo=repo)),
        git=_Git(repo=repo),
        read=ForgeRunReader(),
    )


def _parse(*, argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="incident-original-run")
    actions = parser.add_subparsers(dest="action", required=True)
    gather = actions.add_parser("collect")
    correct = actions.add_parser("propose-correction")
    for sub in (gather, correct):
        _ = sub.add_argument("--state-dir", required=True, type=Path)
        _ = sub.add_argument("--repository", required=True)
        _ = sub.add_argument("--repo", required=True, type=Path)
    _ = gather.add_argument("--revert-sha", required=True)
    _ = gather.add_argument("--expected-graph", required=True, type=Path)
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


def _collect(*, args: argparse.Namespace, ports: EntryPorts) -> int:
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
            state_dir=args.state_dir,
            repository=args.repository,
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


def _propose(*, args: argparse.Namespace, ports: EntryPorts) -> int:
    pairs = [cast("str", text).partition("=") for text in args.resolved]
    if any(not job or not sep or not receipt for job, sep, receipt in pairs):
        return _refused(
            refusal=EvidenceRefusal(
                code="incident-original-run-invalid-request", detail="--resolved is JOB=RECEIPT"
            )
        )
    result = propose(
        request=Correction(
            state_dir=args.state_dir,
            repository=args.repository,
            evidence_digest=args.evidence_digest,
            next_head_sha=args.next_head_sha,
            target_ref=args.target_ref,
            current_attempt=args.current_attempt,
            current_owner=args.current_owner,
            current_generation=args.current_generation,
            resolved_jobs=tuple((job, receipt) for job, _sep, receipt in pairs),
            base_ref=args.base_ref,
        ),
        ports=ports,
    )
    if isinstance(result, EvidenceRefusal):
        return _refused(refusal=result)
    return _reply(body={"status": "proposed", "receipt": result})


def main(*, argv: Sequence[str] | None = None, ports: EntryPorts | None = None) -> int:
    """Collect or propose for one registered original run; refusals exit 78."""
    args = _parse(argv=sys.argv[1:] if argv is None else argv)
    bound = registered_ports(repo=args.repo) if ports is None else ports
    if args.action == "collect":
        return _collect(args=args, ports=bound)
    return _propose(args=args, ports=bound)


if __name__ == "__main__":
    raise SystemExit(main())
