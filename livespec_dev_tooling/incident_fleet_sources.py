"""Production sources for the incident fleet audit: claims, core's manifest, serving reads.

Claims are the operator-authored statement of each consumer and surface (disposition,
owner, proof reference, release build). They are never serving evidence: the file
refuses a `serving_build` key, and the audit overwrites it with a host read. Serving
versions come from the installed consumer's own interpreter, and the independent
controller's from its protected installation manifest.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402
from returns.result import Failure, Result, Success  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_fleet_capabilities import CAPABILITIES  # noqa: E402
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence  # noqa: E402
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed  # noqa: E402
from livespec_dev_tooling.fleet._local_context import (  # noqa: E402
    CommandRunner,
    command_answer,
)
from livespec_dev_tooling.fleet._manifest_git import git_file_text  # noqa: E402
from livespec_dev_tooling.incident_controller_installation import (  # noqa: E402
    ControllerInstallation,
)

__all__: list[str] = [
    "CLAIMS_RELATIVE_PATH",
    "core_manifest_reader",
    "host_serving_reader",
    "installed_controller",
    "load_claims",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
CLAIMS_RELATIVE_PATH = Path("config") / "incident-fleet-evidence.json"
_CORE_REPOSITORY = "livespec"
_MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"
_REQUIRED = (
    "repository",
    "surface",
    "disposition",
    "manifest_sha256",
    "source_path",
    "release_build",
    "proof_ref",
    "owner",
    "incident_item",
    "cumulative_scope",
    "normal_factory_proof",
)
_DISTRIBUTION_PROBE = "import importlib.metadata as m; print(m.version('livespec-dev-tooling'))"


def _claim(*, entry: object) -> CapabilityEvidence | None:
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    reason = record.get("reason", "")
    if (
        set(record) - {*_REQUIRED, "reason"}
        or not all(isinstance(record.get(key), str) for key in _REQUIRED)
        or not isinstance(reason, str)
    ):
        return None
    text = cast("dict[str, str]", record)
    return CapabilityEvidence(
        repository=text["repository"],
        surface=text["surface"],
        disposition=text["disposition"],
        manifest_sha256=text["manifest_sha256"],
        source_path=text["source_path"],
        release_build=text["release_build"],
        serving_build="",
        proof_ref=text["proof_ref"],
        owner=text["owner"],
        incident_item=text["incident_item"],
        cumulative_scope=text["cumulative_scope"],
        normal_factory_proof=text["normal_factory_proof"],
        reason=reason,
    )


def load_claims(*, path: Path) -> Result[tuple[CapabilityEvidence, ...], str]:
    """Read the committed claims; an absent file holds no claims, a malformed one is refused."""
    if not path.is_file():
        return Success(())
    try:
        parsed = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as unreadable:
        return Failure(f"{path} is unreadable: {unreadable}")
    document = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    entries = document.get("evidence")
    if document.get("schema") != 1 or not isinstance(entries, list):
        return Failure(f"{path} must be an object with schema 1 and an evidence list")
    claims = tuple(_claim(entry=entry) for entry in cast("list[object]", entries))
    if any(claim is None for claim in claims):
        return Failure(f"{path} holds an entry that is malformed or carries a serving_build")
    return Success(cast("tuple[CapabilityEvidence, ...]", claims))


def core_manifest_reader(*, owner: str, run: CommandRunner) -> Callable[[], str | None]:
    """Each call is a fresh read of livespec core's default branch over the git transport."""

    def read() -> str | None:
        text = git_file_text(run=run, owner=owner, repo=_CORE_REPOSITORY, path=_MANIFEST_PATH)
        return None if isinstance(text, IOFailure) else unsafe_perform_io(text.unwrap())

    return read


def installed_controller(*, config: Path) -> tuple[str, str] | None:
    """The (repository, release) a protected controller installation manifest names."""
    installation = ControllerInstallation.load(config=config)
    return None if installation is None else (installation.repository, installation.release)


def _installed_version(*, checkout: Path, run: CommandRunner) -> str | None:
    answer = command_answer(
        outcome=run(args=[str(checkout / ".venv" / "bin" / "python"), "-c", _DISTRIBUTION_PROBE])
    )
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    return answer.stdout.strip() or None


def _serving(
    *,
    projects_root: Path,
    controller_config_root: Path | None,
    run: CommandRunner,
    load_controller: Callable[[Path], tuple[str, str] | None],
    repository: str,
    capability: str,
) -> str | None:
    name = repository.rsplit("/", 1)[-1]
    if capability not in CAPABILITIES:
        return None
    if capability != "independent-controller":
        return _installed_version(checkout=projects_root / name, run=run)
    if controller_config_root is None:
        return None
    loaded = load_controller(controller_config_root / f"{name}.json")
    return loaded[1] if loaded is not None and loaded[0] == repository else None


def host_serving_reader(
    *,
    projects_root: Path,
    controller_config_root: Path | None,
    run: CommandRunner,
    load_controller: Callable[[Path], tuple[str, str] | None],
) -> Callable[[str, str], str | None]:
    """Read a serving version from the installed consumer or the running controller.

    Unreadable means None, which the audit counts as unverified; nothing is guessed.
    """
    return lambda repository, capability: _serving(
        projects_root=projects_root,
        controller_config_root=controller_config_root,
        run=run,
        load_controller=load_controller,
        repository=repository,
        capability=capability,
    )
