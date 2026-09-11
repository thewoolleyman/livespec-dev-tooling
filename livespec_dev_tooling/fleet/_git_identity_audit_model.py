"""Typed constants and validation for the fleet Git identity audit."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOResult  # noqa: E402

from livespec_dev_tooling.fleet import _git_identity_audit_report as audit_report  # noqa: E402
from livespec_dev_tooling.fleet._git_identity_audit_report import (  # noqa: E402
    CANONICAL_EMAIL,
    CANONICAL_NAME,
    OWNER,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)

__all__: list[str] = []

HOSTS = ("gmktec-xubuntu", "hp-xubuntu", "poweredge-xubuntu", "vps")
HOST_USERS = {"vps": "ubuntu", **{host: "cwoolley" for host in HOSTS if host != "vps"}}
HOST_ROOTS = {
    "vps": ("/data/projects", "/home/ubuntu/workspace", "/home/ubuntu/.worktrees"),
    **{host: ("/home/cwoolley/workspace",) for host in HOSTS if host != "vps"},
}


@dataclass(frozen=True, kw_only=True)
class IdentityAuditCommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandOutcome = (
    IdentityAuditCommandResult | IOResult[IdentityAuditCommandResult, InvocationNotPerformed]
)


class IdentityAuditCommandRunner(Protocol):
    def __call__(self, *, args: tuple[str, ...], stdin: str | None = None) -> CommandOutcome: ...


def inventory_hosts(*, source: str) -> tuple[str, ...]:
    hosts: set[str] = set()
    host_indent: int | None = None
    for line in source.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "hosts:":
            host_indent = indent
        elif host_indent is not None and stripped and indent <= host_indent:
            host_indent = None
        elif host_indent is not None and stripped.endswith(":") and indent == host_indent + 2:
            hosts.add(stripped[:-1])
    return tuple(sorted(hosts))


def valid_evidence(*, evidence: dict[str, object] | None) -> bool:
    return audit_report.valid_evidence(evidence=evidence)


def base_report(*, inventory_path: Path, findings: list[str]) -> dict[str, object]:
    return audit_report.base_report(inventory_path=inventory_path, findings=findings)


def host_roots(*, host: str) -> tuple[str, ...]:
    return HOST_ROOTS[host]


def probe_args(*, host: str) -> tuple[str, ...]:
    user = HOST_USERS[host]
    home = f"/home/{user}"
    suffix = (
        "sudo",
        "-n",
        "env",
        f"HOME={home}",
        f"USER={user}",
        f"LOGNAME={user}",
        "python3",
        "-",
        host,
        OWNER,
        CANONICAL_NAME,
        CANONICAL_EMAIL,
        json.dumps(host_roots(host=host)),
    )
    if host == "vps":
        return suffix
    return ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", f"{user}@{host}", *suffix)


def worktree_passes(*, worktree: dict[str, object]) -> bool:
    if (
        worktree.get("passed") is not True
        or worktree.get("effective_name") != CANONICAL_NAME
        or worktree.get("effective_email") != CANONICAL_EMAIL
    ):
        return False
    pairs = (
        ("local_names", CANONICAL_NAME),
        ("local_emails", CANONICAL_EMAIL),
        ("worktree_names", CANONICAL_NAME),
        ("worktree_emails", CANONICAL_EMAIL),
    )
    return all(
        isinstance(worktree.get(key), list)
        and all(value == expected for value in cast("list[object]", worktree[key]))
        for key, expected in pairs
    )


def environment_findings(
    *, host: str, label: str, value: object, findings: list[str]
) -> tuple[int, int]:
    if not isinstance(value, dict):  # pragma: no cover - second-cycle edge coverage
        findings.append(f"{host}: {label} environment report is malformed")
        return 0, 1
    record = cast("dict[str, object]", value)
    audited = record.get("audited") if label == "process" else record.get("servers")
    violations, blind = record.get("violations"), record.get("blind")
    valid = isinstance(audited, int) and audited >= 0 and isinstance(blind, int) and blind >= 0
    if not valid:  # pragma: no cover - second-cycle edge coverage
        findings.append(f"{host}: {label} environment counts are malformed")
        return 0, 1
    if not isinstance(violations, list):  # pragma: no cover - second-cycle edge coverage
        findings.append(f"{host}: {label} environment violations are malformed")
        return cast("int", audited), cast("int", blind) + 1
    if violations:
        findings.append(f"{host}: {label} author environment contains violations")
    if label == "process":
        total, unreadable = record.get("total"), record.get("unreadable")
        unreadable_rows = cast("list[object]", unreadable) if isinstance(unreadable, list) else []
        complete = (
            isinstance(total, int)
            and isinstance(unreadable, list)
            and total == cast("int", audited) + len(unreadable_rows)
            and cast("int", blind) == len(unreadable_rows)
        )
        if not complete:
            findings.append(f"{host}: process environment completeness counts are inconsistent")
            blind = max(cast("int", blind), len(unreadable_rows) if unreadable_rows else 1)
        if unreadable_rows:
            findings.append(f"{host}: process environment has unreadable processes")
            blind = max(cast("int", blind), len(unreadable_rows))
    elif record.get("scope") != "default-user-socket-supplemental":
        findings.append(f"{host}: tmux environment scope is malformed")
        blind = max(cast("int", blind), 1)
    if blind:
        findings.append(f"{host}: {label} environment has {blind} blind observations")
    return cast("int", audited), cast("int", blind)


def canaries_pass(*, canaries: object) -> bool:
    if not isinstance(canaries, dict):  # pragma: no cover - second-cycle edge coverage
        return False
    record = cast("dict[str, object]", canaries)
    positive = record.get("positive")
    missing = record.get("missing_identity")
    invalid = record.get("invalid_identity")
    positive_record = cast("dict[str, object]", positive) if isinstance(positive, dict) else {}
    missing_record = cast("dict[str, object]", missing) if isinstance(missing, dict) else {}
    invalid_record = cast("dict[str, object]", invalid) if isinstance(invalid, dict) else {}
    return (
        bool(positive_record)
        and positive_record.get("passed") is True
        and positive_record.get("author_name") == CANONICAL_NAME
        and positive_record.get("author_email") == CANONICAL_EMAIL
        and bool(missing_record)
        and missing_record.get("passed") is True
        and bool(invalid_record)
        and invalid_record.get("passed") is True
    )


def repository_findings(
    *, host: str, repositories: object, roots: object, findings: list[str]
) -> tuple[int, int, int]:
    if (  # pragma: no cover - second-cycle edge coverage
        not isinstance(repositories, list) or not isinstance(roots, list) or not roots
    ):
        findings.append(f"{host}: owned clone/root scope is incomplete")
        return 0, 0, 1
    root_rows = cast("list[object]", roots)
    observed_roots: dict[str, object] = {}
    for item in root_rows:
        row = cast("dict[str, object]", item) if isinstance(item, dict) else {}
        path = row.get("path")
        if isinstance(path, str):
            observed_roots[path] = row.get("state")
    expected_roots = set(host_roots(host=host))
    root_blind = 0
    if set(observed_roots) != expected_roots or any(
        observed_roots.get(path) != "present" for path in expected_roots
    ):
        findings.append(f"{host}: required repository root scope is absent or incomplete")
        root_blind = 1
    worktrees = 0
    repository_rows = cast("list[object]", repositories)
    for repository in repository_rows:
        record = cast("dict[str, object]", repository) if isinstance(repository, dict) else {}
        rows = record.get("worktrees")
        if not isinstance(rows, list):  # pragma: no cover - second-cycle edge coverage
            findings.append(f"{host}: malformed owned repository result")
            continue
        worktree_rows = cast("list[object]", rows)
        worktrees += len(worktree_rows)
        if not worktree_rows or any(
            not isinstance(row, dict)
            or not worktree_passes(worktree=cast("dict[str, object]", row))
            for row in worktree_rows
        ):
            findings.append(f"{host}: worktree identity or override is noncanonical")
    return len(repository_rows), worktrees, root_blind


def host_findings(*, host: str, report: dict[str, object]) -> tuple[list[str], int, int, int, int]:
    findings: list[str] = []
    if (  # pragma: no cover - second-cycle edge coverage
        report.get("schema_version") != 1 or report.get("host") != host
    ):
        return [f"{host}: invalid host report schema or identity"], 1, 0, 0, 0
    expected_global = {
        "name": CANONICAL_NAME,
        "email": CANONICAL_EMAIL,
        "use_config_only": True,
        "passed": True,
    }
    if report.get("global_config") != expected_global:
        findings.append(f"{host}: global_config is not canonical and fail-closed")
    repositories, worktrees, root_blind = repository_findings(
        host=host,
        repositories=report.get("owned_repositories"),
        roots=report.get("roots"),
        findings=findings,
    )
    process_count, process_blind = environment_findings(
        host=host,
        label="process",
        value=report.get("process_author_environment"),
        findings=findings,
    )
    _, tmux_blind = environment_findings(
        host=host,
        label="tmux",
        value=report.get("tmux_author_environment"),
        findings=findings,
    )
    if not canaries_pass(canaries=report.get("commit_canaries")):
        findings.append(f"{host}: positive/missing/invalid commit canary failed")
    declared_failures, declared_blind = report.get("failures"), report.get("blind")
    if (  # pragma: no cover - second-cycle edge coverage
        isinstance(declared_failures, list) and declared_failures
    ):
        findings.append(f"{host}: probe reported failures")
    host_blind = (
        len(cast("list[object]", declared_blind)) if isinstance(declared_blind, list) else 1
    )
    if host_blind:  # pragma: no cover - second-cycle edge coverage
        findings.append(f"{host}: probe reported blind observations")
    return (
        findings,
        host_blind + root_blind + process_blind + tmux_blind,
        repositories,
        worktrees,
        process_count,
    )
