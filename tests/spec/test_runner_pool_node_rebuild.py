"""§"Runner-pool node rebuild recipe" — data in the profile, procedure in the scripts, refusal by name.

The section's obligations are about SHAPE — which artifact carries which
knowledge — and every one of them degrades quietly, because a rebuild recipe is
only exercised on the day a node is rebuilt, which is the worst day to discover
it has rotted.

- **"the procedure MUST NOT embed a value that belongs to one node."** A device
  path or an address hardcoded into a stage does not break the node it was
  copied from; it breaks the SECOND node, months later, by doing the first
  node's thing to it. That is also the shape "a second pool node MUST be a
  second profile [...] and MUST NOT be a second procedure or a hand-edited copy
  of the first" exists to prevent: the copy is what a hardcoded value forces.
  So the assertion is the negative one — no node-identifying value of any
  committed profile appears in any stage's executable text.

- **One parser, every profile.** "A second pool node MUST be a second profile
  consumed by the SAME procedure." Two profiles that declare different key sets
  are two dialects, and the stage reading them will simply find an empty value
  for a key one profile omits — a rebuild that proceeds with a missing device or
  a missing capacity rather than refusing.

- **"the refusal MUST name the volume it refused."** A destructive step behind a
  consent flag is only half the requirement. An unnamed refusal is a refusal an
  operator satisfies by consenting to the wrong target — the remedy hint is the
  safety mechanism, not decoration.

- **"The documented rebuild sequence MUST name the bare-metal stage as its first
  step, so that a rebuild done exactly as written starts from empty storage and
  not from a prepared disk."** The clause is explicitly about the DOCUMENT: a
  sequence whose step 1 is the k3s install reads as complete and produces a node
  built on whatever storage layout happened to already be there.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_BARE_METAL = _K3S / "phase0-bare-metal"
_PROFILES_DIR = _BARE_METAL / "profiles"
_README = _K3S / "README.md"

# The staged procedure: the bare-metal stages, the shared profile parser, the
# k3s install, and the ordered node-local runbook.
_PROCEDURE = (
    _BARE_METAL / "storage-layout.sh",
    _BARE_METAL / "base-os-install.sh",
    _BARE_METAL / "profile.sh",
    _K3S / "provision-k3s.sh",
    _K3S / "phase2" / "install-node.sh",
)

# The profile keys whose values IDENTIFY one node — its name, the media it
# owns, the address its runtime binds, the cluster it joins, the controller
# binary and the operator account. Values of the remaining keys (a filesystem
# type, a distribution name, a size) are shared vocabulary a stage legitimately
# spells out, so they are not node identity and are not searched for.
_IDENTITY_KEYS = (
    "NODE_NAME",
    "TARGET_DEVICE",
    "ESP_DEVICE",
    "NODE_ADDRESS",
    "CLUSTER_JOIN_ADDRESS",
    "NODE_NETWORK_INTERFACE",
    "CONTROLLER_CLI",
    "OPERATOR_ACCOUNT",
)

# The profile's own "derive it, do not state it" sentinel, and the empty value
# a key may legitimately carry: neither is a node-identifying literal.
_UNSET_VALUES = ("", "auto")

_CONSENT_FLAG = "--i-consent-to-destroy"
_BARE_METAL_STAGE = "phase0-bare-metal/"

_PROFILE_ENTRY = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$", re.MULTILINE)
_NUMBERED_STEP = re.compile(r"^(?P<number>\d+)\.\s+\*\*`(?P<artifact>[^`]+)`", re.MULTILINE)


def _profiles() -> dict[str, dict[str, str]]:
    """Each committed per-node profile, parsed as the shared parser parses it."""
    parsed = {
        path.name: {
            entry.group("key"): entry.group("value").strip()
            for entry in _PROFILE_ENTRY.finditer(path.read_text(encoding="utf-8"))
        }
        for path in sorted(_PROFILES_DIR.glob("*.env"))
    }
    assert len(parsed) >= 2, (
        f"a second pool node must be a second PROFILE, so at least two must be committed "
        f"for that claim to be exercised at all; profiles={sorted(parsed)}"
    )
    return parsed


def _executable_lines(*, source: Path) -> list[tuple[int, str]]:
    """Every non-comment, non-blank line of a stage."""
    return [
        (number, line)
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1)
        if line.strip() and not line.strip().startswith("#")
    ]


def test_no_stage_of_the_procedure_embeds_a_value_that_belongs_to_one_node() -> None:
    """Node identity lives in the profile; the stages carry none of it."""
    identity = {
        value: f"{name}:{key}"
        for name, profile in _profiles().items()
        for key, value in profile.items()
        if key in _IDENTITY_KEYS and value not in _UNSET_VALUES
    }
    assert identity, f"the profiles must declare node identity under {_IDENTITY_KEYS}"

    embedded = sorted(
        f"{source.relative_to(_REPO_ROOT)}:{number}: {origin} = {value!r}"
        for source in _PROCEDURE
        for number, line in _executable_lines(source=source)
        for value, origin in identity.items()
        if value in line
    )
    assert not embedded, (
        f"the procedure must read every node-specific value from that node's profile. A "
        f"value embedded in a stage does not break the node it was copied from — it "
        f"breaks the SECOND node, by doing the first node's thing to it, on the one day "
        f"the recipe is exercised; embedded={embedded}"
    )


def test_every_profile_declares_the_same_keys_so_one_parser_reads_them_all() -> None:
    """Two profiles, one dialect — otherwise a stage silently reads an absent key as empty."""
    profiles = _profiles()
    key_sets = {name: frozenset(profile) for name, profile in profiles.items()}
    reference = sorted(key_sets.values(), key=len)[-1]
    divergent = sorted(
        f"{name}: missing={sorted(reference - keys)} extra={sorted(keys - reference)}"
        for name, keys in key_sets.items()
        if keys != reference
    )
    assert not divergent, (
        f"a second node must be a second profile consumed by the SAME procedure, which "
        f"requires one key vocabulary. A profile omitting a key does not fail to parse — "
        f"the stage reads it as empty and rebuilds with a missing device, a missing "
        f"address or a missing capacity; divergent={divergent}"
    )


def test_every_destructive_step_is_gated_on_consent_that_names_its_target() -> None:
    """ "the refusal MUST name the volume it refused" — the remedy hint IS the safety."""
    layout = (_BARE_METAL / "storage-layout.sh").read_text(encoding="utf-8")
    assert _CONSENT_FLAG in layout, (
        f"the destructive stage must be gated behind `{_CONSENT_FLAG}`; the section "
        f"permits destruction only on the operator's explicit consent"
    )
    gate = re.search(r"^require_consent\(\) \{\n(?P<body>(?:.*\n)*?)^\}$", layout, re.MULTILINE)
    assert gate is not None, (
        "the consent decision must live in ONE named gate, so every destructive step is "
        "refused the same way rather than each inventing its own message"
    )
    body = gate.group("body")
    assert "exit 1" in body, "the ungranted-consent path must refuse and stop"
    assert '"$target"' in body and f"{_CONSENT_FLAG}=%s" in body, (
        f"the refusal must NAME the volume it refused and offer consent for exactly that "
        f"target. An unnamed refusal is one an operator satisfies by consenting to the "
        f"wrong volume — which is a destruction the consent gate was supposed to prevent, "
        f"performed with consent; body={body!r}"
    )


def test_the_documented_rebuild_sequence_starts_at_the_bare_metal_stage() -> None:
    """A sequence that starts at the k3s install rebuilds onto whatever disk was there."""
    steps = _NUMBERED_STEP.findall(_README.read_text(encoding="utf-8"))
    assert steps, (
        f"the rebuild sequence must be a NUMBERED, artifact-naming list in "
        f"{_README.relative_to(_REPO_ROOT)} — a rebuild done exactly as written is the "
        f"property the section asks for"
    )
    first_number, first_artifact = steps[0]
    assert first_number == "1" and first_artifact.startswith(_BARE_METAL_STAGE), (
        f"step 1 of the documented sequence must be the bare-metal stage. Any other first "
        f"step reads as complete and produces a node built on whatever storage layout "
        f"happened to already be there — the prepared-disk start the section names "
        f"explicitly; first={first_number}. {first_artifact!r}"
    )
