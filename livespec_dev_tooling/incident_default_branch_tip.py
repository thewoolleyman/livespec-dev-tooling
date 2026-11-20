"""Establish that an expedited event base lies on the protected default branch."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling._incident_inverse_git import IsolatedGit
from livespec_dev_tooling._incident_recovery_git import LandedGit
from livespec_dev_tooling.incident_git import IncidentGitError

__all__: list[str] = ["default_branch_refusal"]


def default_branch_refusal(*, root: Path, branch: str, event_base: str) -> str | None:
    """Return the named refusal for an event base off the default branch, else ``None``.

    The forge-reported event base is candidate-controlled input: a pull request
    retargeted to a branch descending from the attempt's genesis base reports a
    base that is fresh against that genesis yet is not the default branch. The
    controller therefore refreshes the protected branch in its own reference
    clone and admits only an event base that lies on that branch's history. The caller
    has already validated the event base as a 40-hex object name.
    """
    try:
        LandedGit.fetch(root=root, branch=branch)
        tip = (
            IsolatedGit.run(
                root=root,
                args=("rev-parse", "--verify", f"refs/remotes/origin/{branch}^{{commit}}"),
            )
            .decode()
            .strip()
        )
        with IsolatedGit.view(root=root) as (administration, objects):
            ancestor = (
                IsolatedGit.run(
                    root=root,
                    args=("merge-base", event_base, tip),
                    administration=administration,
                    objects=objects,
                )
                .decode()
                .strip()
            )
    except (IncidentGitError, OSError, UnicodeDecodeError, ValueError, subprocess.SubprocessError):
        return _refusal(
            branch=branch, event_base=event_base, exceeded="default branch history unreadable"
        )
    if ancestor != event_base:
        return _refusal(
            branch=branch, event_base=event_base, exceeded="event base is not on the default branch"
        )
    return None


def _refusal(*, branch: str, event_base: str, exceeded: str) -> str:
    return (
        "expedited event base refused: event base " + event_base + " on " + branch + ": " + exceeded
    )
