"""Validate a moving expedited pull-request base in the controller's object view."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from livespec_dev_tooling._incident_inverse_git import IsolatedGit
from livespec_dev_tooling.incident_git import IncidentGitError

__all__: list[str] = ["base_freshness_refusal"]

_SHA = re.compile(r"[0-9a-f]{40}")


def base_freshness_refusal(
    *,
    root: Path,
    genesis_base: str,
    event_base: str,
    max_commits: int,
    max_minutes: int,
) -> str | None:
    """Return the named refusal for a stale base, or ``None`` when it is fresh.

    The protected reference clone supplies every object and timestamp. Candidate
    workflow inputs only select object IDs already present in that clone.
    """
    if (
        _SHA.fullmatch(genesis_base) is None
        or _SHA.fullmatch(event_base) is None
        or type(max_commits) is not int
        or max_commits < 0
        or type(max_minutes) is not int
        or max_minutes < 0
    ):
        return _refusal(
            genesis_base=genesis_base,
            event_base=event_base,
            exceeded="controller freshness configuration is invalid",
        )
    try:
        with IsolatedGit.view(root=root) as (administration, objects):
            ancestor = (
                IsolatedGit.run(
                    root=root,
                    args=("merge-base", genesis_base, event_base),
                    administration=administration,
                    objects=objects,
                )
                .decode()
                .strip()
            )
            if ancestor != genesis_base:
                return _refusal(
                    genesis_base=genesis_base,
                    event_base=event_base,
                    exceeded="genesis base is not an ancestor",
                )
            commits = int(
                IsolatedGit.run(
                    root=root,
                    args=("rev-list", "--count", f"{genesis_base}..{event_base}"),
                    administration=administration,
                    objects=objects,
                )
                .decode()
                .strip()
            )
            timestamps = tuple(
                int(
                    IsolatedGit.run(
                        root=root,
                        args=("show", "-s", "--format=%ct", commit),
                        administration=administration,
                        objects=objects,
                    )
                    .decode()
                    .strip()
                )
                for commit in (genesis_base, event_base)
            )
    except (IncidentGitError, OSError, UnicodeDecodeError, ValueError, subprocess.SubprocessError):
        return _refusal(
            genesis_base=genesis_base,
            event_base=event_base,
            exceeded="ancestry or freshness could not be determined",
        )
    minutes = max(0, timestamps[1] - timestamps[0]) // 60
    exceeded = tuple(
        item
        for item in (
            f"commits {commits}>{max_commits}" if commits > max_commits else None,
            f"minutes {minutes}>{max_minutes}" if minutes > max_minutes else None,
        )
        if item is not None
    )
    return (
        _refusal(genesis_base=genesis_base, event_base=event_base, exceeded=", ".join(exceeded))
        if exceeded
        else None
    )


def _refusal(*, genesis_base: str, event_base: str, exceeded: str) -> str:
    return (
        "expedited base freshness refused: genesis base "
        + genesis_base
        + "; event base "
        + event_base
        + "; bound exceeded: "
        + exceeded
    )
