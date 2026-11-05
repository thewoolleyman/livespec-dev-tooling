"""Venue selection for detached full-suite gate runs."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_dev_tooling.gate_command import is_full_suite_command, pytest_command
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_delegate import (
    delegated_gate_enabled,
    gate_remote_request,
    resolve_renderer,
)
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner
from livespec_dev_tooling.gate_remote_verdict import (
    GATE_FAILED,
    GATE_PASSED,
    run_gated_push,
)
from livespec_dev_tooling.incident_gate_entry import entrance_refusal, resolve_entrance

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "ClusterGateResult",
    "GateVenue",
    "run_cluster_gate",
    "select_for_repository",
    "select_venue",
]


@dataclass(frozen=True, kw_only=True)
class GateVenue:
    """Where one detached gate command runs and, for local runs, why."""

    venue: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class ClusterGateResult:
    """The remote gate's terminal status and evidence for one detached run."""

    exit_status: int
    tree_hash: str
    job_name: str
    detail: str = ""


def select_venue(
    *,
    command: tuple[str, ...],
    force_local: bool,
    delegated: bool,
    credential_readable: bool,
) -> GateVenue:
    """Select the venue for a direct or ``mise exec`` full-suite command."""
    if force_local:
        return GateVenue(venue="host_local", reason="--local")
    if not delegated:
        return GateVenue(venue="host_local", reason="undelegated repository")
    if not _is_full_suite(command=command):
        return GateVenue(venue="host_local", reason="command outside full-suite set")
    if not credential_readable:
        return GateVenue(venue="host_local", reason="ineligible host")
    return GateVenue(venue="cluster_job", reason="eligible full-suite command")


def select_for_repository(
    *, command: tuple[str, ...], force_local: bool, repo_root: Path
) -> GateVenue:
    """Select a venue from the launching repository's opt-in and host eligibility."""
    return select_venue(
        command=command,
        force_local=force_local,
        delegated=delegated_gate_enabled(repo_root=repo_root),
        credential_readable=gates_kubeconfig_readable(),
    )


def _is_full_suite(*, command: tuple[str, ...]) -> bool:
    """Recognise the ratified direct and ``mise exec`` full-suite spellings."""
    return is_full_suite_command(command=command)


def _working_tree_source(*, repo_root: Path) -> tuple[str, str] | None:
    """Commit a worktree-only tree through a temporary index for the mirror push."""
    with tempfile.TemporaryDirectory(prefix="livespec-gate-index-") as temporary:
        index_path = str(Path(temporary) / "index")
        original_index = os.environ.get("GIT_INDEX_FILE")
        os.environ["GIT_INDEX_FILE"] = index_path
        try:
            return _temporary_index_source(repo_root=repo_root)
        finally:
            if original_index is None:
                _ = os.environ.pop("GIT_INDEX_FILE", None)
            else:
                os.environ["GIT_INDEX_FILE"] = original_index


def _temporary_index_source(*, repo_root: Path) -> tuple[str, str] | None:
    """Build a commit object from the temporary index selected by the caller."""
    commands = (
        ["git", "read-tree", "HEAD"],
        ["git", "add", "--all"],
        ["git", "write-tree"],
    )
    output = ""
    for argv in commands:
        ran = default_gate_command_runner(argv=argv, cwd=repo_root)
        if isinstance(ran, Failure) or ran.unwrap().returncode != 0:
            return None
        output = ran.unwrap().stdout
    tree_hash = output.strip()
    if not tree_hash:
        return None
    committed = default_gate_command_runner(
        argv=[
            "git",
            "-c",
            "user.name=livespec-gate",
            "-c",
            "user.email=gate@livespec.invalid",
            "commit-tree",
            tree_hash,
            "-p",
            "HEAD",
            "-m",
            "detached gate worktree tree",
        ],
        cwd=repo_root,
    )
    if isinstance(committed, Failure) or committed.unwrap().returncode != 0:
        return None
    source_ref = committed.unwrap().stdout.strip()
    if not source_ref:
        return None
    return tree_hash, source_ref


def _remote_command(*, command: tuple[str, ...]) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    """Translate the selector's accepted command spellings for the gate renderer."""
    normalized = command[3:] if command[:3] == ("mise", "exec", "--") else command
    if normalized[:1] == ("just",):
        return None, tuple(normalized[1:])
    pytest_argv = pytest_command(command=normalized)
    return pytest_argv, ()


def run_cluster_gate(*, repo_root: Path, command: tuple[str, ...]) -> ClusterGateResult:
    """Publish and run the current worktree tree without falling back to the host."""
    source = _working_tree_source(repo_root=repo_root)
    if source is None:
        return ClusterGateResult(exit_status=75, tree_hash="", job_name="")
    tree_hash, source_ref = source
    pytest_argv, check_suite = _remote_command(command=command)
    built = gate_remote_request(
        repo_root=repo_root,
        renderer=resolve_renderer(repo_root=repo_root),
        runner=default_gate_command_runner,
        tree_hash=tree_hash,
        pytest_argv=pytest_argv,
        check_suite=check_suite,
    )
    if isinstance(built, Failure):
        return ClusterGateResult(
            exit_status=75,
            tree_hash=tree_hash,
            job_name="",
            detail=built.failure().detail,
        )
    request = replace(
        built.unwrap(),
        source_ref=source_ref,
        tree_hash=tree_hash,
        capture_output=False,
    )
    verdict = run_gated_push(request=request, runner=default_gate_command_runner)
    status = 0 if verdict.state == GATE_PASSED else 1 if verdict.state == GATE_FAILED else 75
    return ClusterGateResult(
        exit_status=status,
        tree_hash=tree_hash,
        job_name=verdict.job_name or "",
        detail=verdict.detail,
    )


def _arguments() -> argparse.Namespace:
    """Parse the runner's selector request without reinterpreting its command."""
    parser = argparse.ArgumentParser(prog="gate-runner-venue")
    _ = parser.add_argument("--local", action="store_true", dest="force_local")
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def _run_arguments() -> argparse.Namespace:
    """Parse the detached runner's cluster execution request."""
    parser = argparse.ArgumentParser(prog="gate-runner-venue run")
    _ = parser.add_argument("--run-dir", type=Path, required=True)
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(sys.argv[2:])


def _run_main() -> int:
    """Persist remote evidence beside the shell runner's durable run record."""
    arguments = _run_arguments()
    command = tuple(arguments.command[1:]) if arguments.command[:1] == ["--"] else ()
    result = run_cluster_gate(repo_root=Path.cwd(), command=command)
    if result.tree_hash:
        _ = (arguments.run_dir / "tree_hash").write_text(f"{result.tree_hash}\n", encoding="utf-8")
    if result.job_name:
        _ = (arguments.run_dir / "job_name").write_text(f"{result.job_name}\n", encoding="utf-8")
    if result.detail:
        _ = sys.stderr.write(f"{result.detail}\n")
    return result.exit_status


def main() -> int:
    """Print the selected venue and reason as two newline-delimited fields.

    Incident mode resolves first. A cluster submission has no incident mode, so
    `run` refuses a trusted incident too; venue selection is a launcher, so a
    trusted incident continues on the LOCAL venue, where the child's own
    hook entrance resolves again.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        refused = entrance_refusal(surface="gate-runner")
        return _run_main() if refused is None else refused
    decision = resolve_entrance(surface="gate-runner", launcher=True)
    if decision.mode == "refused":
        return decision.status
    arguments = _arguments()
    command = (
        tuple(arguments.command[1:])
        if arguments.command[:1] == ["--"]
        else tuple(arguments.command)
    )
    selected = select_for_repository(
        command=command,
        force_local=arguments.force_local or decision.mode == "incident",
        repo_root=Path.cwd(),
    )
    _ = sys.stdout.write(f"{selected.venue}\n{selected.reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
