"""The one client for the orchestrator's incident authority process.

Every dev-tooling caller of `incident_authority.py` (the hook, the historical
provenance reader, the observer's current and history readers and the operator
entrance) reaches it here, so one liveness ceiling and one set of reply checks apply
to all of them. A caller keeps only what must differ: WHICH command it runs, which is
its trust boundary (the registered plugin through the credential wrapper, or the
manifest-provisioned reader), and what it does with a verified result.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Failure, Result, Success  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)

__all__: list[str] = [
    "AUTHORITY_CALL_CEILING_SECONDS",
    "AuthorityRefusal",
    "call_authority",
    "check_authority_reply",
    "registered_authority_command",
    "report_authority_refusal",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-iezdmk
# A hang guard for one canonical authority call, never a verdict. Measured on the
# dev host 2026-11-08 (livespec-dev-tooling-yaprm4): read-local-gates took 21-39 s
# and grows with the chain's generation, so a 30 s bound refused live expedited
# commits, and 10 s then 45 s refused a current, verified read-current chain
# (livespec-dev-tooling-ws2idp). Ten minutes stops a hung wrapper or ledger without
# deciding a slow one, and it is the same bound for every caller.
AUTHORITY_CALL_CEILING_SECONDS = 600
_CANONICAL_REFUSED_EXIT = 78
_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
_SCRIPT = Path("scripts") / "bin" / "incident_authority.py"
_CURRENT_ACTION = "read-current"
_STDERR_LIMIT = 2000


@dataclass(frozen=True, kw_only=True)
class AuthorityRefusal:
    """A call refused by name; `canonical` marks the authority's own named refusal."""

    code: str
    detail: str
    canonical: bool = False


_Checked = Result[dict[str, Any], AuthorityRefusal]


def registered_authority_command(*, plugin_root: Path) -> list[str]:
    """The registered plugin's authority script, run through the credential wrapper."""
    return [_WRAPPER, "--", "python3", str(plugin_root / _SCRIPT)]


def _refuse(*, code: str, detail: str) -> _Checked:
    return Failure(AuthorityRefusal(code=code, detail=detail))


_PARSE_REFUSALS = {
    "duplicate-key": ("incident-authority-duplicate-keys", "reply repeats a JSON key"),
    "non-finite": ("incident-authority-malformed-reply", "reply carries a non-finite number"),
    "nesting": ("incident-authority-malformed-reply", "reply nests JSON too deeply"),
}


def _parse(*, text: str) -> _Checked:
    try:
        value = cast("object", strict_json(text=text, limit=None))
    except IncidentJsonRefusalError as refusal:
        code, detail = _PARSE_REFUSALS.get(
            refusal.kind, ("incident-authority-malformed-reply", "reply is not JSON")
        )
        return _refuse(code=code, detail=detail)
    if not isinstance(value, dict):
        return _refuse(
            code="incident-authority-malformed-reply", detail="reply is not a JSON object"
        )
    return Success(cast("dict[str, Any]", value))


def _canonical_refusal(*, reply: dict[str, Any]) -> _Checked:
    result = reply.get("result")
    body = cast("dict[str, Any]", result) if isinstance(result, dict) else {}
    code = body.get("code")
    detail = body.get("detail")
    if (
        reply.get("status") == "refused"
        and reply.get("authorizes_current_effects") is False
        and isinstance(code, str)
        and code
        and isinstance(detail, str)
    ):
        return Failure(AuthorityRefusal(code=code, detail=detail, canonical=True))
    return _refuse(
        code="incident-authority-malformed-refusal",
        detail="exit 78 did not carry a named canonical refusal",
    )


def _verified(*, action: str, reply: dict[str, Any]) -> _Checked:
    if reply.get("status") != "verified":
        return _refuse(code="incident-authority-not-verified", detail="reply is not verified")
    if reply.get("authorizes_current_effects") is not (action == _CURRENT_ACTION):
        return _refuse(
            code="incident-authority-wrong-kind",
            detail=f"{action} reply carries the wrong current-effects authority",
        )
    result = reply.get("result")
    if not isinstance(result, dict):
        return _refuse(code="incident-authority-malformed-result", detail="result is not an object")
    return Success(cast("dict[str, Any]", result))


def _check_reply(*, action: str, returncode: int, stdout: str) -> _Checked:
    if returncode not in {0, _CANONICAL_REFUSED_EXIT}:
        return _refuse(
            code="incident-authority-exit", detail=f"{action} exited with status {returncode}"
        )
    parsed = _parse(text=stdout)
    if not is_successful(parsed):
        return parsed
    reply = parsed.unwrap()
    schema = reply.get("schema")
    if type(schema) is not int or schema != 1:
        return _refuse(code="incident-authority-schema", detail="reply is not schema 1")
    if reply.get("normal_factory_proof") is not False:
        return _refuse(
            code="incident-authority-proof-flag",
            detail="reply does not state normal_factory_proof is false",
        )
    if returncode == _CANONICAL_REFUSED_EXIT:
        return _canonical_refusal(reply=reply)
    return _verified(action=action, reply=reply)


def check_authority_reply(*, action: str, returncode: int, stdout: str, stderr: str) -> _Checked:
    """The one set of reply checks, each refusal carrying the failing call's stderr."""
    checked = _check_reply(action=action, returncode=returncode, stdout=stdout)
    if is_successful(checked):
        return checked
    refusal = checked.failure()
    words = stderr.strip()[:_STDERR_LIMIT]
    if refusal.canonical or not words:
        return checked
    return Failure(replace(refusal, detail=f"{refusal.detail}: {words}"))


def report_authority_refusal(*, refusal: AuthorityRefusal) -> None:
    """Name a refusal on stderr for the readers whose own answer is only a bare verdict."""
    _ = sys.stderr.write(f"incident-authority-refused: {refusal.code}: {refusal.detail}\n")


def call_authority(
    *,
    command: Sequence[str],
    action: str,
    flags: Mapping[str, object],
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> _Checked:
    """Run `command action --flag value ...` once under the ceiling and check its reply."""
    argv = [*command, action]
    for name, value in flags.items():
        argv.extend(["--" + name, str(value)])
    try:
        done = subprocess.run(  # noqa: S603 — fixed registered or manifest argv; no shell.
            argv,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=AUTHORITY_CALL_CEILING_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        ceiling = f"{AUTHORITY_CALL_CEILING_SECONDS} s liveness ceiling"
        return _refuse(
            code="incident-authority-timeout",
            detail=f"registered canonical incident process {action} exceeded its {ceiling}",
        )
    except (OSError, subprocess.SubprocessError) as unavailable:
        return _refuse(
            code="incident-authority-unavailable",
            detail=f"{action} could not run: {type(unavailable).__name__}: {unavailable}",
        )
    return check_authority_reply(
        action=action, returncode=done.returncode, stdout=done.stdout, stderr=done.stderr
    )
