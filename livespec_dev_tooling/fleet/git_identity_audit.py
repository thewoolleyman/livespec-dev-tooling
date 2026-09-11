"""Operator-invoked, future-state-only fleet Git author identity audit."""

from __future__ import annotations

import json
import os
import sys
from argparse import ArgumentParser
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402
from returns.result import Failure, Result, Success  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling.fleet._git_identity_audit_io import (  # noqa: E402
    AuditIOFailure,
    command_result,
    default_runner,
    read_object,
    source_pair,
)
from livespec_dev_tooling.fleet._git_identity_audit_model import (  # noqa: E402
    CANONICAL_EMAIL,
    CANONICAL_NAME,
    HOSTS,
    CommandOutcome,
    IdentityAuditCommandResult,
    IdentityAuditCommandRunner,
    host_findings,
    inventory_hosts,
    probe_args,
)
from livespec_dev_tooling.fleet._git_identity_audit_report import (  # noqa: E402
    base_report,
    observed_dispositions,
    valid_evidence,
)

CommandResult = IdentityAuditCommandResult

__all__: list[str] = ["CANONICAL_EMAIL", "CANONICAL_NAME", "CommandResult", "run_audit"]


def _report_write(*, path: Path, report: dict[str, object]) -> IOResult[None, AuditIOFailure]:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _ = temporary.replace(path)
    except OSError as error:  # pragma: no cover - follow-up Red cycle
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        return IOFailure(AuditIOFailure(operation="write-report", path=path, detail=str(error)))
    return IOSuccess(None)


def _parse_host_result(*, host: str, outcome: CommandOutcome) -> Result[dict[str, object], str]:
    command = command_result(outcome=outcome)
    if isinstance(command, Failure):  # pragma: no cover - second-cycle edge coverage
        return Failure(command.failure().reason)
    answer = command.unwrap()
    if answer.returncode != 0:  # pragma: no cover - second-cycle edge coverage
        return Failure(f"probe exited {answer.returncode}")
    try:
        parsed = json.loads(answer.stdout)
    except json.JSONDecodeError as error:  # pragma: no cover - second-cycle edge coverage
        return Failure(f"probe returned malformed JSON: {error}")
    record = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    if not record or record.get("host") != host:  # pragma: no cover - second-cycle edge coverage
        return Failure("probe report host/schema envelope is invalid")
    return Success(record)


def _fabro_evidence(
    *, evidence: dict[str, object] | None, runner: IdentityAuditCommandRunner, findings: list[str]
) -> dict[str, object]:
    if not valid_evidence(evidence=evidence):
        findings.append("Fabro evidence is missing or malformed")
        return {"verified": False}
    narrowed = cast("dict[str, object]", evidence)
    outcome = runner(
        args=(
            "git",
            "-C",
            cast("str", narrowed["repository"]),
            "show",
            "-s",
            "--format=%an%x00%ae",
            cast("str", narrowed["commit"]),
        )
    )
    command = command_result(outcome=outcome)
    if isinstance(command, Failure):  # pragma: no cover - follow-up Red cycle
        parts: list[str] = []
    else:
        answer = command.unwrap()
        parts = answer.stdout.rstrip("\n").split("\x00") if answer.returncode == 0 else []
    verified = parts == [CANONICAL_NAME, CANONICAL_EMAIL]
    if not verified:
        findings.append("Fabro commit author is absent, unverifiable, or noncanonical")
    result = dict(narrowed)
    result["verified"] = verified
    expected_parts = len(("name", "email"))
    result["verified_author"] = (
        {"name": parts[0], "email": parts[1]} if len(parts) == expected_parts else None
    )
    return result


def _collect_hosts(
    *, runner: IdentityAuditCommandRunner, probe_source: str, findings: list[str]
) -> tuple[list[dict[str, object]], int, int, int, int]:
    reports: list[dict[str, object]] = []
    blind = repositories = worktrees = processes = 0
    for host in HOSTS:
        parsed_result = _parse_host_result(
            host=host, outcome=runner(args=probe_args(host=host), stdin=probe_source)
        )
        if isinstance(parsed_result, Failure):  # pragma: no cover - second-cycle edge coverage
            findings.append(f"{host}: sudo/ssh probe invocation was blind")
            blind += 1
            continue
        parsed = parsed_result.unwrap()
        reports.append(parsed)
        host_result = host_findings(host=host, report=parsed)
        findings.extend(host_result[0])
        blind += host_result[1]
        repositories += host_result[2]
        worktrees += host_result[3]
        processes += host_result[4]
    return reports, blind, repositories, worktrees, processes


def run_audit(
    *,
    inventory_path: Path,
    evidence_path: Path,
    output_path: Path,
    runner: IdentityAuditCommandRunner,
    allowed_output_root: Path,
) -> int:
    if not output_path.resolve().is_relative_to(allowed_output_root.resolve()):
        return 2
    findings: list[str] = []
    source_result = source_pair(inventory_path=inventory_path)
    if isinstance(source_result, IOFailure):  # pragma: no cover - second-cycle edge coverage
        source_failure = unsafe_perform_io(source_result.failure())
        findings.append(f"inventory/probe source could not be read: {source_failure.operation}")
        report_result = _report_write(
            path=output_path,
            report=base_report(inventory_path=inventory_path, findings=findings),
        )
        return 2 if isinstance(report_result, IOFailure) else 1
    inventory_source, probe_source = unsafe_perform_io(source_result.unwrap())
    if inventory_hosts(source=inventory_source) != HOSTS or not probe_source:
        findings.append("inventory/probe source is absent or not the exact four-host scope")
        report_result = _report_write(
            path=output_path, report=base_report(inventory_path=inventory_path, findings=findings)
        )
        return 2 if isinstance(report_result, IOFailure) else 1
    host_reports, blind, repositories, worktrees, processes = _collect_hosts(
        runner=runner, probe_source=probe_source, findings=findings
    )
    evidence_result = read_object(path=evidence_path)
    evidence = (
        None
        if isinstance(evidence_result, IOFailure)
        else unsafe_perform_io(evidence_result.unwrap())
    )
    fabro = _fabro_evidence(evidence=evidence, runner=runner, findings=findings)
    incomplete = (
        len(host_reports) != len(HOSTS) or repositories == 0 or worktrees == 0 or processes == 0
    )
    if incomplete:  # pragma: no cover - second-cycle edge coverage
        findings.append("audit scope is incomplete or vacuous")
    dispositions = observed_dispositions(host_reports=host_reports, findings=findings)
    summary = {
        "blind": blind,
        "failures": len(findings),
        "hosts": len(host_reports),
        "owned_repositories": repositories,
        "owned_worktrees": worktrees,
        "processes_audited": processes,
    }
    report = base_report(inventory_path=inventory_path, findings=findings)
    report.update(
        {
            "overall": "pass" if not findings and blind == 0 else "fail",
            "hosts": host_reports,
            "audit_source": {"sha256": sha256(probe_source.encode()).hexdigest()},
            "dispositions": dispositions,
            "fabro_evidence": fabro,
            "summary": summary,
        }
    )
    written = _report_write(path=output_path, report=report)
    if isinstance(written, IOFailure):  # pragma: no cover - second-cycle edge coverage
        return 2
    return 0 if report["overall"] == "pass" else 1


def main() -> int:  # pragma: no cover - operator CLI boundary
    parser = ArgumentParser(prog="git-identity-audit")
    _ = parser.add_argument("output", type=Path)
    _ = parser.add_argument("fabro_evidence", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    return run_audit(
        inventory_path=root / "ansible" / "inventory" / "legacy.yml",
        evidence_path=cast("Path", args.fabro_evidence),
        output_path=cast("Path", args.output),
        runner=default_runner,
        allowed_output_root=root / "tmp",
    )


if __name__ == "__main__":
    sys.exit(main())
