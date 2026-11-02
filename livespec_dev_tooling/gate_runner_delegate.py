"""Venue selection for detached full-suite gate runs."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_delegate import delegated_gate_enabled

__all__: list[str] = ["GateVenue", "select_for_repository", "select_venue"]

_JUST_RECIPE_POSITION = 1
_JUST_COMMAND_MINIMUM_WORDS = 2


@dataclass(frozen=True, kw_only=True)
class GateVenue:
    """Where one detached gate command runs and, for local runs, why."""

    venue: str
    reason: str


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
    if command[:3] == ("mise", "exec", "--"):
        command = command[3:]
    if command[:1] == ("just",):
        return len(command) >= _JUST_COMMAND_MINIMUM_WORDS and (
            command[_JUST_RECIPE_POSITION] == "check"
            or (
                command[_JUST_RECIPE_POSITION].startswith("check-")
                and len(command[_JUST_RECIPE_POSITION]) > len("check-")
            )
        )
    return command[:1] == ("pytest",) or command[:3] == ("uv", "run", "pytest")


def _arguments() -> argparse.Namespace:
    """Parse the runner's selector request without reinterpreting its command."""
    parser = argparse.ArgumentParser(prog="gate-runner-venue")
    _ = parser.add_argument("--local", action="store_true", dest="force_local")
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    """Print the selected venue and reason as two newline-delimited fields."""
    arguments = _arguments()
    selected = select_for_repository(
        command=tuple(arguments.command), force_local=arguments.force_local, repo_root=Path.cwd()
    )
    _ = sys.stdout.write(f"{selected.venue}\n{selected.reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
