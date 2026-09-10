"""Railway-typed I/O seams for the operator Git identity audit."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402
from returns.result import Failure, Result, Success  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling.fleet import _git_identity_host_canary as host_canary  # noqa: E402
from livespec_dev_tooling.fleet import _git_identity_host_git as host_git  # noqa: E402
from livespec_dev_tooling.fleet import _git_identity_host_probe as host_probe  # noqa: E402
from livespec_dev_tooling.fleet._git_identity_audit_model import (  # noqa: E402
    CommandOutcome,
    IdentityAuditCommandResult,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)

__all__: list[str] = []

_PROBE_RESOURCE = Path(host_probe.__file__)
_PROBE_HELPER = Path(host_git.__file__)
_PROBE_CANARY = Path(host_canary.__file__)


@dataclass(frozen=True, kw_only=True)
class AuditIOFailure:
    operation: str
    path: Path
    detail: str


def default_runner(  # pragma: no cover - exercised directly in follow-up Red cycle
    *, args: tuple[str, ...], stdin: str | None = None
) -> IOResult[IdentityAuditCommandResult, InvocationNotPerformed]:
    if shutil.which(args[0]) is None:
        return IOFailure(
            InvocationNotPerformed(argv=args, kind=BINARY_ABSENT, detail=f"{args[0]} not on PATH")
        )
    try:
        completed = subprocess.run(
            args, input=stdin, text=True, capture_output=True, check=False, timeout=300
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return IOFailure(InvocationNotPerformed(argv=args, kind=SPAWN_FAILED, detail=str(error)))
    return IOSuccess(
        IdentityAuditCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    )


def command_result(
    *, outcome: CommandOutcome
) -> Result[IdentityAuditCommandResult, InvocationNotPerformed]:
    if isinstance(outcome, IdentityAuditCommandResult):
        return Success(outcome)
    if isinstance(outcome, IOFailure):  # pragma: no cover - follow-up Red cycle
        return Failure(unsafe_perform_io(outcome.failure()))
    return Success(unsafe_perform_io(outcome.unwrap()))  # pragma: no cover - follow-up Red cycle


def read_object(*, path: Path) -> IOResult[dict[str, object], AuditIOFailure]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:  # pragma: no cover - follow-up Red cycle
        return IOFailure(AuditIOFailure(operation="read-json", path=path, detail=str(error)))
    if not isinstance(value, dict):  # pragma: no cover - follow-up Red cycle
        return IOFailure(
            AuditIOFailure(operation="read-json-object", path=path, detail="not an object")
        )
    return IOSuccess(cast("dict[str, object]", value))


def source_pair(*, inventory_path: Path) -> IOResult[tuple[str, str], AuditIOFailure]:
    try:
        inventory = inventory_path.read_text(encoding="utf-8")
        helper = _PROBE_HELPER.read_text(encoding="utf-8")
        canary = _PROBE_CANARY.read_text(encoding="utf-8")
        probe = _PROBE_RESOURCE.read_text(encoding="utf-8")
    except OSError as error:  # pragma: no cover - follow-up Red cycle
        return IOFailure(
            AuditIOFailure(operation="read-audit-source", path=inventory_path, detail=str(error))
        )
    module_name = "livespec_dev_tooling.fleet._git_identity_host_git"
    canary_name = "livespec_dev_tooling.fleet._git_identity_host_canary"
    bootstrap = (
        "import sys,types\n"
        f"_helper=types.ModuleType({module_name!r})\n"
        f"exec(compile({helper!r},'_git_identity_host_git.py','exec'),_helper.__dict__)\n"
        f"sys.modules[{module_name!r}]=_helper\n"
        f"_canary=types.ModuleType({canary_name!r})\n"
        f"exec(compile({canary!r},'_git_identity_host_canary.py','exec'),_canary.__dict__)\n"
        f"sys.modules[{canary_name!r}]=_canary\n"
        f"exec(compile({probe!r},'_git_identity_host_probe.py','exec'))\n"
    )
    return IOSuccess((inventory, bootstrap))
