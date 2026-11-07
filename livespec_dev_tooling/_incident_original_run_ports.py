"""The operator entrance's ports, built from the controller's verified installation.

Git and `bd` run in the reference clone, the authority is the manifest's installed
canonical reader, and forge reads use the recovery App's read-only token. Each process
gets a fixed environment and nothing the operator's shell carried.
"""

from __future__ import annotations

import contextlib
import json
import os
import pwd
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_original_run_canonical import CanonicalPorts
from livespec_dev_tooling._incident_run_types import CanonicalRefusalError
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_forge_reads import ForgeReads
from livespec_dev_tooling.incident_original_run_flows import EntryPorts
from livespec_dev_tooling.incident_run_forge import ForgeRunReader

__all__: list[str] = ["installed_ports", "refresh_reference"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-jvfb7x
# Beside controller.json: the role's incident_observer_reader_env_path, which the
# service unit reads as its EnvironmentFile. KEY=value, one per line.
_READER_ENV = "reader.env"
_SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
_TIMEOUT = 120
_UNVERIFIED = "registered incident authority refused or returned an invalid reply"


def _run(
    *,
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin: bytes = b"",
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 -- fixed git, bd and manifest reader argv.
        list(argv),
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        timeout=_TIMEOUT,
        check=check,
    )


def _flags(*, values: Mapping[str, object]) -> list[str]:
    return [part for name, value in values.items() for part in ("--" + name, str(value))]


@dataclass(frozen=True, kw_only=True)
class _Git:
    repo: Path
    env: Mapping[str, str]

    def __call__(self, args: Sequence[str], stdin: bytes) -> bytes:
        return _run(argv=["git", *args], cwd=self.repo, env=self.env, stdin=stdin).stdout


@dataclass(frozen=True, kw_only=True)
class _Ledger:
    """`bd` in the reference clone with the tenant credential, so the item is reachable."""

    repo: Path
    env: Mapping[str, str]

    def __call__(self, args: Sequence[str]) -> str:
        return _run(argv=["bd", *args], cwd=self.repo, env=self.env).stdout.decode()


@dataclass(frozen=True, kw_only=True)
class _Authority:
    """The manifest's installed canonical reader, never caller JSON or a checkout's build."""

    command: tuple[str, ...]
    repo: Path
    env: Mapping[str, str]

    def __call__(
        self, action: str, query: Mapping[str, object], payload: Mapping[str, str]
    ) -> dict[str, Any]:
        argv = [*self.command, action, "--repo", str(self.repo)]
        argv += _flags(values={**query, **payload})
        done = _run(argv=argv, cwd=self.repo, env=self.env, check=False)
        reply = cast("object", json.loads(done.stdout))
        body = cast("dict[str, Any]", reply) if isinstance(reply, dict) else {}
        result = body.get("result")
        if body.get("status") == "refused" and isinstance(result, dict):
            refusal = cast("dict[str, object]", result)
            code = refusal.get("code")
            if isinstance(code, str) and code:
                raise CanonicalRefusalError(code=code, detail=str(refusal.get("detail", "")))
        if (
            done.returncode != 0
            or body.get("schema") != 1
            or body.get("status") != "verified"
            or body.get("normal_factory_proof") is not False
            or not isinstance(result, dict)
        ):
            raise ValueError(_UNVERIFIED)
        return cast("dict[str, Any]", result)


def _account_environment() -> dict[str, str]:
    """The service unit's fixed PATH and this account's own home, and nothing inherited.

    The reader is deliberately not run under -I, so an operator's PYTHONPATH or GIT_DIR
    must not reach it. The unit clears those; this entrance never passes them.
    """
    return {
        "PATH": f"{Path(sys.executable).parent}:{_SYSTEM_PATH}",
        "HOME": pwd.getpwuid(os.geteuid()).pw_dir,
    }


def _tenant_credential(*, config: Path) -> dict[str, str]:
    lines = (config.parent / _READER_ENV).read_text(encoding="utf-8").splitlines()
    pairs = [line.partition("=") for line in lines]
    return {name: value for name, sep, value in pairs if sep}


def installed_ports(*, installation: ControllerInstallation) -> EntryPorts:
    """Git and bd in the reference clone, the manifest's reader, and the App's read token."""
    plain = _account_environment()
    credentialed = {**plain, **_tenant_credential(config=installation.config)}
    repo = installation.repo
    return EntryPorts(
        canonical=CanonicalPorts(
            authority=_Authority(command=installation.reader, repo=repo, env=credentialed),
            ledger=_Ledger(repo=repo, env=credentialed),
        ),
        git=_Git(repo=repo, env=plain),
        read=ForgeRunReader(read=ForgeReads.installed(installation=installation)),
    )


def refresh_reference(*, installation: ControllerInstallation) -> None:
    """Bring a just-pushed revert or corrected head in, as the reference timer's fetch does.

    Best effort: a commit still missing afterward refuses by name at its git read.
    """
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        _ = _run(
            argv=["git", "fetch", "--quiet", "--prune", "--tags", "origin"],
            cwd=installation.repo,
            env=_account_environment(),
            check=False,
        )
