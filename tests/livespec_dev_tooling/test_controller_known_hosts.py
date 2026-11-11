"""The control node trusts every ci_pool host's tailnet ssh host key from committed bytes.

Until 2026-11-11 every pool host's entry in the control node's known_hosts was a
hand edit, so the first ci-pool converge of gamingpc-xubuntu (the first host
enrolled after the last hand entry) failed with "Host key verification failed".
Role `controller_known_hosts`, run by ansible/dev-host.yml, now writes each entry
from a key pinned in the host's host_vars.

The tests read the committed files as text, as the node_status_credential role's
tests do, because applying the role needs the live control node. Two properties
are worth pinning:

- Each pinned key is the key its recorded fingerprint names. The fingerprint is
  what a reader verifies against the host's info repository, so a pasted key
  that does not hash to it is caught here rather than at the next failed ssh.
- The role reads no key from the network. Trust on first use (`ssh-keyscan`, or
  `StrictHostKeyChecking=accept-new`) is the shorter patch and authenticates
  nothing on the run that matters, so its absence is asserted over the role's
  non-comment lines.

Plan homelab-k8s-worker-nodes, epic livespec-dev-tooling-ko26ez.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "controller_known_hosts"
_DEV_HOST_PLAY = _REPO_ROOT / "ansible" / "dev-host.yml"

_PINNED_HOSTS = ("gamingpc-xubuntu", "gmktec-xubuntu", "hp-xubuntu", "poweredge-xubuntu")
# gamingpc-xubuntu-info docs/bootstrap.md records this fingerprint for the key
# Tailscale SSH presents at gamingpc-xubuntu.
_GAMINGPC_RECORDED_FINGERPRINT = "SHA256:B80TQ80TSdj4j8fef3gQhQtWnafGppS4N817Gh4z33o"

_KEY_LINE = re.compile(
    r'^controller_known_hosts_ed25519: "ssh-ed25519 (?P<key>[A-Za-z0-9+/]+={0,2})"$', re.MULTILINE
)
_FINGERPRINT = re.compile(r"Fingerprint\s*(?:\n#\s*)?(?P<fp>SHA256:[A-Za-z0-9+/]{43})")


def _fingerprint(key_b64: str) -> str:
    digest = hashlib.sha256(base64.b64decode(key_b64)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _pinned(host: str) -> tuple[str, str]:
    text = (_HOST_VARS / f"{host}.yml").read_text()
    keys = _KEY_LINE.findall(text)
    assert (
        len(keys) == 1
    ), f"{host}'s host_vars must pin exactly one controller_known_hosts_ed25519; found {keys!r}"
    recorded = _FINGERPRINT.findall(text)
    assert (
        len(recorded) == 1
    ), f"{host}'s host_vars must record the pinned key's fingerprint once; found {recorded!r}"
    return keys[0], recorded[0]


def _non_comment_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")]


def test_every_pinned_key_hashes_to_the_fingerprint_recorded_beside_it() -> None:
    for host in _PINNED_HOSTS:
        key, recorded = _pinned(host)
        assert (
            _fingerprint(key) == recorded
        ), f"{host}: the pinned key hashes to {_fingerprint(key)}, not the recorded {recorded}"


def test_gamingpc_pins_the_key_its_host_record_names() -> None:
    key, _ = _pinned("gamingpc-xubuntu")
    assert _fingerprint(key) == _GAMINGPC_RECORDED_FINGERPRINT


def test_the_role_reads_no_host_key_from_the_network() -> None:
    for path in sorted((_ROLE / "tasks").glob("*.yml")):
        body = "\n".join(_non_comment_lines(path))
        assert "ssh-keyscan" not in body, f"{path} must not read a host key with ssh-keyscan"
        assert "accept-new" not in body, f"{path} must not trust a host key on first use"
        assert (
            "ansible.builtin.known_hosts" in body
        ), f"{path} must write the entries with ansible.builtin.known_hosts"


def test_the_dev_host_play_runs_the_role() -> None:
    assert "    - role: controller_known_hosts" in _DEV_HOST_PLAY.read_text().splitlines()
