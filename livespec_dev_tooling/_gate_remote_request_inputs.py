"""The repository facts needed before a delegated gate Job can be rendered."""

from __future__ import annotations

import sys
from pathlib import Path

from livespec_dev_tooling._gate_remote_assembly import declared_gate_check_suite
from livespec_dev_tooling.gate_private_sibling_token import private_sibling_credential
from livespec_dev_tooling.gate_remote_invocation import GateCommandRunner, GateStepFailed

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = ["gate_request_inputs"]


def gate_request_inputs(
    *, repo_root: Path, runner: GateCommandRunner, helper: Path
) -> Result[tuple[tuple[str, ...], tuple[str, ...], str], GateStepFailed]:
    """Read the declared suite and any private-sibling credential in request order."""
    suite = declared_gate_check_suite(repo_root=repo_root)
    if isinstance(suite, Failure):
        return Failure(suite.failure())
    credential = private_sibling_credential(
        repo_root=repo_root,
        runner=runner,
        helper=helper,
    )
    if isinstance(credential, Failure):
        return Failure(credential.failure())
    private_siblings, private_sibling_token = credential.unwrap()
    return Success((suite.unwrap(), private_siblings, private_sibling_token))
