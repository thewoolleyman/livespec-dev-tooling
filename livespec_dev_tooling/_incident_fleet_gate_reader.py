"""The gate readers' serving build: the revision of the dev-tooling a consumer's checks run.

A consumer's gates are `livespec_dev_tooling`, as installed in the consumer's own `.venv`.
What serves is the revision pip or uv recorded for that install (`direct_url.json`), never
the distribution's static version label (it does not move when the source does). The
consumer's interpreter is never executed, and nothing is synced or written. A consumer
with no `.venv`, no install or an install that is not a recorded revision is unverified.
The one editable install that counts is a consumer running its OWN source (this library's
checkout). Its serving build is keyed to a release, never to its own HEAD, because a
committed claim can never name the commit that contains it: it is the newest release tag
that is an ancestor of HEAD, served to each row only while every file of that row's
surface at HEAD is byte-identical to the release's (`_incident_fleet_release_keyed`). A
tracked modification serves nothing verifiable; an untracked file is not part of what
serves.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

from livespec_dev_tooling._incident_fleet_clones import consumer_clone
from livespec_dev_tooling._incident_fleet_release_keyed import (
    ServingReading,
    release_keyed_reading,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import command_answer
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["read_gate_readers"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_COMMIT = re.compile(r"[0-9a-f]{40}")
_CAPABILITY = "gate-readers"


def _git(*, probe: HostProbe, clone: Path, args: list[str]) -> str | None:
    answer = command_answer(outcome=probe.run(args=["git", "-C", str(clone), *args]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    return answer.stdout


def _own_release(
    *, probe: HostProbe, clone: Path, repository: str, direct: dict[str, object]
) -> ServingReading | None:
    info = direct.get("dir_info")
    url = direct.get("url")
    if (
        not isinstance(info, dict)
        or cast("dict[str, object]", info).get("editable") is not True
        or not isinstance(url, str)
        or Path(unquote(urlparse(url).path)).resolve() != clone.resolve()
    ):
        return None
    head = _git(probe=probe, clone=clone, args=["rev-parse", "HEAD"])
    head = "" if head is None else head.strip()
    if not _COMMIT.fullmatch(head):
        return ServingReading(build="", detail=f"the HEAD of {clone} cannot be read")
    tracked = _git(probe=probe, clone=clone, args=["status", "--porcelain", "--untracked-files=no"])
    if tracked is None or tracked:
        detail = (
            f"the tracked state of {clone} cannot be read"
            if tracked is None
            else f"tracked modifications at HEAD {head}: {'; '.join(tracked.splitlines())}"
        )
        return ServingReading(build="", detail=detail, head=head)
    return release_keyed_reading(
        run=probe.run,
        clone=clone,
        repo=repository.rsplit("/", 1)[-1],
        head=head,
        capability=_CAPABILITY,
    )


def read_gate_readers(*, probe: HostProbe, repository: str) -> str | ServingReading | None:
    """The 40-hex revision of the consumer's installed `livespec_dev_tooling`, else None.

    A consumer running its own source is read as a release-keyed `ServingReading`.
    """
    clone = consumer_clone(probe=probe, repository=repository)
    dists = (
        []
        if clone is None
        else sorted(clone.glob(".venv/lib/python*/site-packages/livespec_dev_tooling-*.dist-info"))
    )
    if clone is None or len(dists) != 1:
        return None
    try:
        text = (dists[0] / "direct_url.json").read_text("utf-8")
        parsed = cast("object", strict_json(text=text, limit=None))
    except (OSError, ValueError, IncidentJsonRefusalError):
        return None
    direct = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    vcs = direct.get("vcs_info")
    commit = cast("dict[str, object]", vcs).get("commit_id") if isinstance(vcs, dict) else None
    if isinstance(commit, str) and _COMMIT.fullmatch(commit):
        return commit
    return _own_release(probe=probe, clone=clone, repository=repository, direct=direct)
