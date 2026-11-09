"""Name the trusted normal origins whose inherited incident flags are inert.

A gate or hook entrance runs inside a process whose environment may carry
`EXPEDITED_INCIDENT_RESPONSE` or `EXPEDITED_INCIDENT_RESPONSE_REVERT` that the
entrance never asked for: a runner, a wrapper or a parent shell leaked them.
`SPECIFICATION/contracts.md` (section "Expedited incident execution") requires
two origins to force both flags absent BEFORE parsing them, malformed values
included:

- a master-push CI job, named by the Actions runner's own `GITHUB_ACTIONS=true`
  with `GITHUB_EVENT_NAME=push` (the repository's CI triggers a push only on
  master, and `incident_ci_process` already keys its normal-master projection on
  the same event name);
- a normal factory follow-up, named by the `livespec.sandboxExempt=true` git
  marker that identifies a factory sandbox checkout.

Both are read from ambient state, which is sound here because the answer can only
ever select the COMPLETE normal body. A forged signal makes an entrance ignore an
incident flag and apply full policy; it never grants an incident exception, which
still requires the registered canonical authority's receipt.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    Invocation,
)
from livespec_dev_tooling.incident_hook_process import git_text

__all__: list[str] = ["factory_sandbox", "trusted_invocation"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wtsntu


def factory_sandbox(*, repo: Path) -> bool:
    """Whether the checkout at `repo` declares itself a factory sandbox."""
    try:
        marker = git_text(repo=repo, args=["config", "--get", "livespec.sandboxExempt"])
    except (OSError, subprocess.SubprocessError):
        return False
    return marker == "true"


def trusted_invocation(*, environ: Mapping[str, str], repo: Path) -> str:
    """Name the trusted normal origin of this process, or `ORDINARY` when it has none.

    The sandbox marker is probed only when an incident flag is present: with no
    flag every origin resolves to normal anyway, so the probe would be pure cost.
    """
    if environ.get("GITHUB_ACTIONS") == "true" and environ.get("GITHUB_EVENT_NAME") == "push":
        return Invocation.NORMAL_MASTER
    flagged = any(
        environ.get(name)
        for name in (EXPEDITED_INCIDENT_RESPONSE, EXPEDITED_INCIDENT_RESPONSE_REVERT)
    )
    if flagged and factory_sandbox(repo=repo):
        return Invocation.NORMAL_FACTORY_FOLLOW_UP
    return Invocation.ORDINARY
