"""The independent controller's serving version, read from the RUNNING observer.

The observer is a systemd unit whose process is the released `venv/bin/python` of the
controller account. What it serves is what that process was started from: the
distribution installed in the venv its command line names, at the revision pip or uv
recorded when it fetched the release, and only if the process started after that
install finished. The unit's protected configuration is never opened (the operator
cannot read it, and a release name written there is a claim), and the auditor's own
package is never consulted (that would make the controller read circular).

Every other outcome is unverified: a stopped, failed or restarting unit, a process that
is not the packaged observer command, a venv without exactly one install, an install
that is not a recorded VCS revision, and a process that predates its install.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import command_answer
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["OBSERVED_REPOSITORY", "read_controller_serving"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
# The ansible role (`incident_observer_repository`) installs exactly one observer, for this
# repository; a test pins this constant to the role's default.
OBSERVED_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_UNIT = "livespec-incident-observer.service"
_COMMAND_TAIL = [
    "-I",
    "-m",
    "livespec_dev_tooling.incident_observer_service",
    "--config",
    "/etc/livespec-incident/controller.json",
]
_COMMIT = re.compile(r"[0-9a-f]{40}")
_FIELD_AFTER_COMMAND = 19


def _unit_pid(*, probe: HostProbe) -> int | None:
    answer = command_answer(
        outcome=probe.run(
            args=["systemctl", "show", _UNIT, "--property=ActiveState,SubState,MainPID"]
        )
    )
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    state = dict(line.split("=", 1) for line in answer.stdout.splitlines() if "=" in line)
    pid = state.get("MainPID", "")
    running = state.get("ActiveState") == "active" and state.get("SubState") == "running"
    return int(pid) if running and pid.isdigit() and int(pid) > 0 else None


def _started_at(*, proc_root: Path, pid: int) -> float | None:
    try:
        stat = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
        ticks = int(stat.rsplit(")", 1)[1].split()[_FIELD_AFTER_COMMAND])
        boot = next(
            int(line.split()[1])
            for line in (proc_root / "stat").read_text(encoding="utf-8").splitlines()
            if line.startswith("btime ")
        )
    except (OSError, ValueError, IndexError, StopIteration):
        return None
    return boot + ticks / os.sysconf("SC_CLK_TCK")


def _command(*, proc_root: Path, pid: int) -> list[str] | None:
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    return raw.decode(errors="replace").rstrip("\0").split("\0")


def _installed(*, dist: Path) -> tuple[str, float] | None:
    try:
        metadata = (dist / "METADATA").read_text(encoding="utf-8")
        direct = cast(
            "object",
            strict_json(text=(dist / "direct_url.json").read_text(encoding="utf-8"), limit=None),
        )
        touched = (dist / "METADATA").stat()
    except (OSError, ValueError, IncidentJsonRefusalError):
        return None
    versions = [line[9:].strip() for line in metadata.splitlines() if line.startswith("Version:")]
    vcs = cast("dict[str, object]", direct).get("vcs_info") if isinstance(direct, dict) else None
    commit = cast("dict[str, object]", vcs).get("commit_id") if isinstance(vcs, dict) else None
    if (
        not versions
        or not versions[0]
        or not isinstance(commit, str)
        or not _COMMIT.fullmatch(commit)
    ):
        return None
    return f"v{versions[0]}@{commit}", max(touched.st_mtime, touched.st_ctime)


def read_controller_serving(*, probe: HostProbe, repository: str) -> str | None:
    """`v<version>@<commit>` of the running observer's installed release, else None."""
    if repository != OBSERVED_REPOSITORY:
        return None
    pid = _unit_pid(probe=probe)
    argv = None if pid is None else _command(proc_root=probe.proc_root, pid=pid)
    if (
        pid is None
        or argv is None
        or argv[1:] != _COMMAND_TAIL
        or Path(argv[0]).parent.name != "bin"
    ):
        return None
    dists = sorted(
        Path(argv[0])
        .parent.parent.joinpath("lib")
        .glob("python*/site-packages/livespec_dev_tooling-*.dist-info")
    )
    installed = _installed(dist=dists[0]) if len(dists) == 1 else None
    started = _started_at(proc_root=probe.proc_root, pid=pid)
    return installed[0] if installed and started and started >= installed[1] else None
