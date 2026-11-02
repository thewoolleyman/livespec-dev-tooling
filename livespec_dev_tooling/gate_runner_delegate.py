"""Venue selection for detached full-suite gate runs."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["GateVenue", "select_venue"]

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
    if not credential_readable:
        return GateVenue(venue="host_local", reason="ineligible host")
    if not _is_full_suite(command=command):
        return GateVenue(venue="host_local", reason="command outside full-suite set")
    return GateVenue(venue="cluster_job", reason="eligible full-suite command")


def _is_full_suite(*, command: tuple[str, ...]) -> bool:
    """Recognise the ratified direct and ``mise exec`` full-suite spellings."""
    if command[:3] == ("mise", "exec", "--"):
        command = command[3:]
    if command[:1] == ("just",):
        return len(command) >= _JUST_COMMAND_MINIMUM_WORDS and (
            command[_JUST_RECIPE_POSITION] == "check"
            or command[_JUST_RECIPE_POSITION].startswith("check-")
        )
    return command[:1] == ("pytest",) or command[:3] == ("uv", "run", "pytest")
