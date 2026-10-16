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
import secrets
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_state import write_durable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths

__all__: list[str] = [
    "NONCE_BYTES",
    "OWNED_DAEMON_KEYS",
    "Challenge",
    "Evidence",
    "challenge_path",
    "evidence_path",
    "fresh_nonce",
    "owned_daemon_keys",
    "owned_keys_digest",
    "write_challenge",
    "write_evidence",
]

# How much entropy a nonce carries. Each passing window's nonce has to
# differ from every earlier one, and the record of earlier nonces is on
# a host whose /run is cleared by a reboot, so the guarantee rests on
# the entropy rather than on a counter something could reset.
NONCE_BYTES: Final[int] = 16

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


@dataclass(frozen=True, kw_only=True)
class Challenge:
    """One issued challenge: the run, the boot, the nonce and the instant.

    The boot id and the instant are both carried because either alone
    would accept an answer the other rejects: a monotonic instant means
    nothing across a reboot, and a boot id says nothing about age.
    """

    run: str
    boot_id: str
    nonce: str
    issued_monotonic: float


def challenge_path(*, paths: GuardPaths) -> Path:
    """The one challenge, under the RUNTIME root so a reboot clears it.

    Placement is the mechanism, not a filing convention: /run is tmpfs,
    so an answer issued before a reboot can never be accepted after one.
    """
    return paths.runtime_root / "challenge"


def fresh_nonce() -> str:
    """A nonce no earlier window issued."""
    return secrets.token_hex(NONCE_BYTES)


def write_challenge(*, paths: GuardPaths, challenge: Challenge) -> None:
    """Replace any earlier challenge with this one.

    Replaced rather than appended to, per rider point 5: a challenge is
    RE-ISSUED and never reused, so at most one is ever outstanding.
    """
    write_durable(
        path=challenge_path(paths=paths), data=json.dumps(asdict(challenge), sort_keys=True)
    )


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
