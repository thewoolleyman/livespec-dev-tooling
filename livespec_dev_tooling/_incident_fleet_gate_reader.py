"""The gate readers' serving build: the revision of the dev-tooling a consumer's checks run.

A consumer's gates are `livespec_dev_tooling`, as installed in the consumer's own `.venv`.
What serves is the revision pip or uv recorded for that install (`direct_url.json`), never
the distribution's static version label (it does not move when the source does). The
consumer's interpreter is never executed, and nothing is synced or written. A consumer
with no `.venv`, no install or an install that is not a recorded revision is unverified.
The one editable install that counts is a consumer running its OWN source (this library's
checkout): that serves its clean HEAD, and a dirty tree serves nothing verifiable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

from livespec_dev_tooling._incident_fleet_clones import consumer_clone
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import command_answer
from livespec_dev_tooling.incident_fleet_host import HostProbe

__all__: list[str] = ["read_gate_readers"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_COMMIT = re.compile(r"[0-9a-f]{40}")


def _git(*, probe: HostProbe, clone: Path, args: list[str]) -> str | None:
    answer = command_answer(outcome=probe.run(args=["git", "-C", str(clone), *args]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    return answer.stdout


def _own_clean_head(*, probe: HostProbe, clone: Path, direct: dict[str, object]) -> str | None:
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
    dirty = _git(probe=probe, clone=clone, args=["status", "--porcelain"])
    head = None if head is None else head.strip()
    return head if head and _COMMIT.fullmatch(head) and dirty == "" else None


def read_gate_readers(*, probe: HostProbe, repository: str) -> str | None:
    """The 40-hex revision of the consumer's installed `livespec_dev_tooling`, else None."""
    clone = consumer_clone(probe=probe, repository=repository)
    dists = (
        []
        if clone is None
        else sorted(clone.glob(".venv/lib/python*/site-packages/livespec_dev_tooling-*.dist-info"))
    )
    if clone is None or len(dists) != 1:
        return None
    try:
        parsed = cast("object", json.loads((dists[0] / "direct_url.json").read_text("utf-8")))
    except (OSError, ValueError):
        return None
    direct = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    vcs = direct.get("vcs_info")
    commit = cast("dict[str, object]", vcs).get("commit_id") if isinstance(vcs, dict) else None
    if isinstance(commit, str) and _COMMIT.fullmatch(commit):
        return commit
    return _own_clean_head(probe=probe, clone=clone, direct=direct)
