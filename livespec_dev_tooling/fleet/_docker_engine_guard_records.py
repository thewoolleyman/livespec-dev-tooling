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

The reconfigured digest beside the commit marker belongs here for the
same reason, one operation later: `reconfigure` writes it and the
post-commit validation reads it.

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
    "CHALLENGE_MAX_AGE_SECONDS",
    "NONCE_BYTES",
    "OWNED_DAEMON_KEYS",
    "Challenge",
    "Evidence",
    "challenge_path",
    "consumed_nonces",
    "durability_warning_path",
    "evidence_passed",
    "evidence_path",
    "fresh_nonce",
    "marker_digest",
    "owned_daemon_keys",
    "owned_keys_digest",
    "publish_marker",
    "read_challenge",
    "reconfigured_digest",
    "reconfigured_digest_path",
    "record_consumed_nonce",
    "record_durability_warning",
    "record_reconfigured_digest",
    "submitted_nonce",
    "write_challenge",
    "write_evidence",
]

# How long an answer may take to come back. The controller runs its own
# probes (a fresh Tailscale SSH session, the LLM health read, a LAN
# fallback login) only after reading the challenge, so a longer answer
# than this vouches for a host as it was rather than as it is.
CHALLENGE_MAX_AGE_SECONDS: Final[int] = 120

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


def read_challenge(*, paths: GuardPaths) -> Challenge | None:
    """The outstanding challenge, or `None` when none is outstanding.

    `None` where a reboot has cleared the runtime root, which is the
    answer that matters: no challenge is not a stale challenge, and both
    refuse a `confirm`.
    """
    path = challenge_path(paths=paths)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Challenge(
        run=str(payload["run"]),
        boot_id=str(payload["boot_id"]),
        nonce=str(payload["nonce"]),
        issued_monotonic=float(payload["issued_monotonic"]),
    )


def submitted_nonce(*, paths: GuardPaths, run: str) -> str:
    """The nonce the controller answered with, or an empty string for none.

    The answer arrives in the run's own `inputs/` directory like every
    other input, because the controller never writes into place (design
    G3). An empty string rather than a `None` so that the one comparison
    that matters -- against the outstanding challenge's nonce -- has a
    single shape: no answer simply does not match.
    """
    path = paths.inputs_dir(run=run) / "challenge-answer"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def evidence_passed(*, paths: GuardPaths, run: str) -> bool:
    """True only when this run's evidence record is present and records a pass.

    Fail-closed on both unknowns: an absent record and a record whose
    `passed` is anything but exactly `True` are each read as "the window
    did not pass", because neither is evidence that it did.
    """
    path = evidence_path(paths=paths, run=run)
    payload: dict[str, object] = (
        json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    )
    return payload.get("passed") is True


def _consumed_path(*, paths: GuardPaths, run: str) -> Path:
    """Where this run's spent nonces are recorded, durably and cumulatively."""
    return paths.run_dir(run=run) / "consumed-nonces"


def consumed_nonces(*, paths: GuardPaths, run: str) -> tuple[str, ...]:
    """Every nonce a `confirm` of this run has already spent."""
    path = _consumed_path(paths=paths, run=run)
    return tuple(path.read_text(encoding="utf-8").split()) if path.is_file() else ()


def record_consumed_nonce(*, paths: GuardPaths, run: str, nonce: str) -> None:
    """Spend `nonce`, durably, BEFORE the commit point.

    Before rather than after, and that order is the whole of the
    already-spent rule: a `confirm` that died between spending the nonce
    and the commit rename must not be replayable with the same answer.
    Recording it afterwards would leave exactly that hole, and the run
    would then be committed by an answer prepared for an earlier attempt.
    """
    spent = (*consumed_nonces(paths=paths, run=run), nonce)
    write_durable(path=_consumed_path(paths=paths, run=run), data="\n".join(spent))


def durability_warning_path(*, paths: GuardPaths, run: str) -> Path:
    """Where a run's durability warning is recorded, for an operator to find."""
    return paths.run_dir(run=run) / "durability-warning"


def record_durability_warning(*, paths: GuardPaths, run: str, failure: str) -> str:
    """Record a durability warning for `run`, and hand back what it says.

    An empty `failure` records nothing and says nothing: the ordinary
    commit, where every fsync returned, leaves no warning behind, and a
    warning file that was always written would make the one case that
    matters invisible among the ones that do not.
    """
    if not failure:
        return ""
    warning = f"the commit marker is in place but a durability step after it failed: {failure}"
    write_durable(path=durability_warning_path(paths=paths, run=run), data=warning)
    return warning


def publish_marker(*, paths: GuardPaths, run: str, digest: str) -> str:
    """Write the commit marker, and report what if anything went wrong.

    The marker carries two things and needs both. The run id is what
    lets every later dispatch tell this host's own commitment from
    another run's. The digest is what lets a later converge tell a
    post-commit reconfiguration from a no-op without reading the daemon
    configuration's bytes.

    The return value is the failure a durable step met, or an empty
    string. It deliberately does NOT say whether the run committed: the
    rename is the commit point, and a failure can fall on either side of
    it, so the caller reads the MARKER back to learn which. Reporting
    "failed" for both would roll back a host whose marker is already
    visible -- and the guarded units' start condition reads that marker.
    """
    payload = json.dumps({"digest": digest, "run": run}, sort_keys=True)
    try:
        write_durable(path=paths.marker, data=payload)
    except OSError as failure:
        return f"{type(failure).__name__}: {failure}"
    return ""


def reconfigured_digest_path(*, paths: GuardPaths) -> Path:
    """Where a post-commit reconfiguration records the digest it has just written.

    BESIDE the commit marker and never inside it, which is the whole
    mechanism rather than a filing choice. The specification forbids
    `reconfigure` from removing or rewriting the marker -- the marker is
    the statement that this host COMMITTED, and a reconfiguration must
    not be able to restate it -- so a second record is the only place
    the reconfigured digest can go. Durable rather than runtime: the
    reconfiguration survives the reboot that clears /run, and so must
    the statement of what it wrote.
    """
    return paths.state_root / "reconfigured"


def record_reconfigured_digest(*, paths: GuardPaths, run: str, digest: str) -> None:
    """Record the owned-keys digest a reconfiguration has written, durably.

    Written AFTER the keys reach the host, and that order is the only
    safe one. Interrupted between the two, the host carries the new keys
    and no record of them, so the next converge reports a fault and an
    operator's `reconfigure` repeats idempotently. Recorded first, an
    interruption would leave a record vouching for keys the host never
    received -- and the next converge would accept it, silently.
    """
    write_durable(
        path=reconfigured_digest_path(paths=paths),
        data=json.dumps({"digest": digest, "run": run}, sort_keys=True),
    )


def reconfigured_digest(*, paths: GuardPaths) -> str:
    """The owned-keys digest the latest reconfiguration recorded, or an empty string.

    An empty string where no reconfiguration has happened, which cannot
    equal any real digest -- every digest is a SHA256 hex string, even
    the one over an empty set of owned keys -- so a caller comparing the
    two is fail-closed with no second branch for "nothing was ever
    reconfigured".
    """
    path = reconfigured_digest_path(paths=paths)
    payload: dict[str, object] = (
        json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    )
    return str(payload.get("digest", ""))


def marker_digest(*, paths: GuardPaths) -> str:
    """The owned-keys digest the commit marker carries, or an empty string.

    An empty string for an absent or digest-less marker, which cannot
    equal any real digest -- so a caller comparing the two is fail-closed
    without a second branch for "no marker to compare against".
    """
    payload: dict[str, object] = (
        json.loads(paths.marker.read_text(encoding="utf-8")) if paths.marker.is_file() else {}
    )
    return str(payload.get("digest", ""))


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
