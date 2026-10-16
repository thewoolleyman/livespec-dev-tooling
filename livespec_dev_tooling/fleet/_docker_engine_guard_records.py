"""The records the Docker engine install guard's observer and commit half share.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Observe and the challenge" and
"Commit" (this repository). Governing design:
`docs/docker-engine-guard-design.md`, F4, G3, G4 and rider point 5.

`observe` writes these and `confirm` reads them, which is why they live
in neither module: the evidence record that says a window passed, the
challenge that says the controller was asked for a fresh answer, the
nonces a `confirm` has already spent, and the canonical digest of the
role-owned daemon keys. A record read by one module and written by
another is a shared contract rather than a private helper of either.

WHY THE DIGEST IS CANONICAL RATHER THAN THE FILE'S BYTES (design F4).
The commit marker carries the digest of the owned keys PARSED and
re-serialized, so that the slice role's own re-serialization of
`daemon.json` -- which changes no owned key -- changes no digest either.
A digest over the bytes would make an identical configuration read as a
changed one on the next converge.

Stdlib only, for the reason the model module records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_state import write_durable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths

__all__: list[str] = [
    "OWNED_DAEMON_KEYS",
    "Evidence",
    "evidence_path",
    "owned_daemon_keys",
    "owned_keys_digest",
    "write_evidence",
]

# The daemon keys this role OWNS, and the only ones the digest covers.
# Every other key in `daemon.json` belongs to whoever wrote it, so a
# change to one is not a reconfiguration of the guarded install.
OWNED_DAEMON_KEYS: Final[tuple[str, ...]] = (
    "bip",
    "cgroup-parent",
    "ip-forward",
    "ip-forward-no-drop",
    "ip6tables",
    "iptables",
    "ipv6",
    "live-restore",
)


@dataclass(frozen=True, kw_only=True)
class Evidence:
    """What one observation window saw, and whether it passed.

    `passed` and `failure` are written together and never independently:
    the observer derives the first from the second, so no record can
    both claim a pass and name a failure.
    """

    run: str
    boot_id: str
    digest: str
    window_start: float
    window_end: float
    samples: tuple[Mapping[str, object], ...] = ()
    passed: bool = False
    failure: str = ""


def owned_daemon_keys(*, paths: GuardPaths, run: str) -> dict[str, object]:
    """The role-owned daemon keys the controller uploaded for this run.

    Read from the run's own `inputs/` directory, because that is the one
    place a controller may write (design G3). An absent upload reads as
    no owned keys rather than as an error: a run that reaches the commit
    point having been given none has a digest over the empty set, which
    is a fact the marker can carry.
    """
    source = paths.inputs_dir(run=run) / "daemon.json"
    text = source.read_text(encoding="utf-8") if source.is_file() else "{}"
    fields: dict[str, object] = json.loads(text)
    return {key: value for key, value in fields.items() if key in OWNED_DAEMON_KEYS}


def owned_keys_digest(*, paths: GuardPaths, run: str) -> str:
    """The canonical digest of this run's owned daemon keys."""
    canonical = json.dumps(
        owned_daemon_keys(paths=paths, run=run), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evidence_path(*, paths: GuardPaths, run: str) -> Path:
    """Where one run's evidence record lives: in the run's own directory."""
    return paths.run_dir(run=run) / "evidence.json"


def write_evidence(*, paths: GuardPaths, run: str, evidence: Evidence) -> None:
    """Record what the window saw, durably, so a later `confirm` can read it."""
    write_durable(
        path=evidence_path(paths=paths, run=run), data=json.dumps(asdict(evidence), sort_keys=True)
    )
