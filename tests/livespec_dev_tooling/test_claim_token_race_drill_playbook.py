"""`ansible/claim-token-race-drill.yml` — two hosts race for one claim token, and only one wins.

Orchestrator work item bd-ib-4eeefv, Definition of Done bullet 3 (host-captured),
adopted by plan expedited-incident-response-flag (epic livespec-dev-tooling-bqnzcm).
The governing clause is the "Consent-gated pool-node disruption" section of
`SPECIFICATION/non-functional-requirements.md`.

Every property is asserted by RUNNING the committed playbook through the same
`ansible-core` pin `just ansible-apply` executes, against a local `ci_pool`
inventory, a throwaway git repository holding the fixture plugin
(`fixtures/claim_token_race_drill_plugin`, a file-locked store with the released
package's verbs), a `file://` bd release tarball, and stand-in `ssh` and `ss`
on PATH that are coupled: the stand-in `ssh` holds a marker while the tunnel
"runs" and drops it on TERM, and the stand-in `ss` reports a loopback listener
only while that marker exists. So the play's listener wait can be satisfied
only AFTER its own tunnel opened, and its "no listener afterwards" assertion
only after its own kill. The two writer processes the play launches are the
REAL committed probe racing on the fixture's compare-and-swap, so the token
chain the test reads back out of the store was produced by a real race.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tarfile
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from shutil import copytree

import pytest

__all__: list[str] = []

# INTEGRATION TIER, declared statically for `heading_coverage` direction 4: every
# test drives the real committed playbook through the pinned `ansible-core`.
pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAYBOOK = _REPO_ROOT / "ansible" / "claim-token-race-drill.yml"
_FIXTURE_PLUGIN = Path(__file__).resolve().parent / "fixtures" / "claim_token_race_drill_plugin"

_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

_TARGET = "race-drill-target"
_OTHER = "race-drill-other"
_TAG = "v0.0.0-drill-test"
_PORT = 3307

_PLAYBOOK_TIMEOUT_SECONDS = 600
_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
_REPORT = re.compile(
    rf"Claim-token race drill on (?P<host>\S+)\s+started at (?P<start>{_UTC})\s+ended at (?P<end>{_UTC})"
)
_RECAP_CHANGED = re.compile(r"changed=(?P<changed>\d+)")
_VERDICT_OK = re.compile(r'\\"ok\\": true')

# The stand-in `ssh`: a reverse-forward invocation holds a listener marker until
# it is killed; anything else is an invocation the play was not written to make.
_SSH_STAND_IN = """#!/bin/sh
printf 'ssh %s\\n' "$*" >> "${DRILL_COMMAND_LOG}"
case "$*" in
  *' -R '*)
    marker="${DRILL_STATE_DIR}/tunnel-listening"
    trap 'rm -f "$marker"; exit 0' TERM INT
    touch "$marker"
    while :; do sleep 1; done ;;
esac
printf 'stand-in ssh: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

# The stand-in `ss`: a listener on the Dolt port exists while the tunnel marker
# does. `DRILL_PORT_BUSY=yes` reports one before any tunnel (the pre-check
# refusal); `DRILL_TUNNEL_BIND=wide` reports the tunnel bound to every address.
_SS_STAND_IN = """#!/bin/sh
printf 'ss %s\\n' "$*" >> "${DRILL_COMMAND_LOG}"
if [ "${DRILL_PORT_BUSY}" = yes ]; then
  printf 'LISTEN 0 128 127.0.0.1:3307 0.0.0.0:*\\n'
  exit 0
fi
if [ -f "${DRILL_STATE_DIR}/tunnel-listening" ]; then
  if [ "${DRILL_TUNNEL_BIND}" = wide ]; then
    printf 'LISTEN 0 128 0.0.0.0:3307 0.0.0.0:*\\n'
  else
    printf 'LISTEN 0 128 127.0.0.1:3307 0.0.0.0:*\\n'
  fi
fi
exit 0
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state_dir: Path
    command_log: Path
    tmp_dir: Path
    store: Path
    plugin_repo: Path
    control_checkout: Path
    tarball: Path
    tarball_sha256: str
    binary_sha256: str
    secret: str

    @property
    def commands(self) -> list[str]:
        if not self.command_log.exists():
            return []
        return self.command_log.read_text(encoding="utf-8").splitlines()

    @property
    def records(self) -> dict[str, dict[str, object]]:
        if not self.store.exists():
            return {}
        loaded = json.loads(self.store.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded  # pyright: ignore[reportUnknownVariableType]

    @property
    def tunnel_listening(self) -> bool:
        return (self.state_dir / "tunnel-listening").exists()

    @property
    def throwaway_dirs(self) -> list[Path]:
        return sorted(self.tmp_dir.glob("claim-token-race-drill.*"))


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry an `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=drill", "-c", "user.email=drill@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True, scope="module")
def _warm_pinned_ansible_env(*, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Build the pinned ansible env with one plain, trivial play before this module's tests.

    `uvx` builds the pinned ansible-core env on a session's first call. Measured
    in the delegated gate Job on 2026-11-06 over four runs: when that first
    call was this module's harness, every controller start in the module then
    timed out at ansible-core 2.21's in-process RPC host ("Local RPC server did
    not start"; 16 of 16 invocations, each 5.7 s), while the sibling drill
    modules passed in the same Job and every invocation shape of the harness
    passed once the env existed. With a plain trivial play run first, all eight
    tests passed. The mechanism is not identified (a follow-up is owed); this
    fixture is the measured remedy, and it asserts its own run so a venue where
    even the plain start fails is reported rather than hidden.
    """
    root = tmp_path_factory.mktemp("ansible-env-warm")
    inventory = root / "inventory.yml"
    inventory.write_text(
        "all:\n  hosts:\n    warm:\n      ansible_connection: local\n", encoding="utf-8"
    )
    play = root / "trivial.yml"
    play.write_text(
        "- hosts: all\n  gather_facts: false\n  tasks:\n    - ansible.builtin.debug:\n        msg: warm\n",
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env["ANSIBLE_NOCOWS"] = "1"
    completed = subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", "-i", str(inventory), str(play)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    """Stand-ins on a private bin dir, a tagged fixture plugin repo, a bd tarball, an empty store."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("ssh", _SSH_STAND_IN), ("ss", _SS_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    control_bd = bin_dir / "bd-control"
    control_bd.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    control_bd.chmod(0o755)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    store = tmp_path / "store.json"

    plugin_repo = tmp_path / "plugin-repo"
    copytree(_FIXTURE_PLUGIN, plugin_repo)
    (plugin_repo / ".beads" / "fake-store-path").write_text(f"{store}\n", encoding="utf-8")
    _git("init", "--quiet", "--initial-branch=main", cwd=plugin_repo)
    _git("add", "--all", cwd=plugin_repo)
    _git("commit", "--quiet", "--message", "fixture plugin", cwd=plugin_repo)
    _git("tag", _TAG, cwd=plugin_repo)

    control_checkout = tmp_path / "control-checkout"
    (control_checkout / ".beads").mkdir(parents=True)
    (control_checkout / ".beads" / "config.yaml").write_text(
        (_FIXTURE_PLUGIN / ".beads" / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (control_checkout / ".beads" / "metadata.json").write_text(
        json.dumps({"backend": "dolt", "dolt_mode": "server", "project_id": "fixture"}),
        encoding="utf-8",
    )

    binary = tmp_path / "bd"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tarball = tmp_path / "beads_test_linux_amd64.tar.gz"
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(binary, arcname="bd")
    return _Scratch(
        root=tmp_path,
        bin_dir=bin_dir,
        state_dir=state_dir,
        command_log=tmp_path / "command.log",
        tmp_dir=tmp_dir,
        store=store,
        plugin_repo=plugin_repo,
        control_checkout=control_checkout,
        tarball=tarball,
        tarball_sha256=sha256(tarball.read_bytes()).hexdigest(),
        binary_sha256=sha256(binary.read_bytes()).hexdigest(),
        secret=f"drill-dummy-secret-{uuid.uuid4().hex}",
    )


def _write_inventory(*, scratch: _Scratch) -> Path:
    inventory = scratch.root / "inventory.yml"
    inventory.write_text(
        "all:\n"
        "  children:\n"
        "    ci_pool:\n"
        "      hosts:\n"
        f"        {_TARGET}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: agent\n"
        f"        {_OTHER}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: server\n",
        encoding="utf-8",
    )
    return inventory


def _run_playbook(
    *,
    scratch: _Scratch,
    confirm: str | None,
    check_mode: bool = False,
    with_secret: bool = True,
    port_busy: bool = False,
    tunnel_bind: str = "loopback",
    hang_intent: str = "",
    probe_timeout: int = 120,
) -> tuple[int, str]:
    """Run the committed playbook; return its exit code and its callback output."""
    # The throwaway root is passed as the play's own variable, never as TMPDIR:
    # ansible-core 2.21 starts its RPC host on an AF_UNIX socket under the
    # temporary directory, and a long pytest basetemp pushes that path past the
    # 107-byte limit ("Local RPC server did not start", measured in the
    # delegated gate Job on 2026-11-06).
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} must exist"
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START"
        and not key.startswith("COV_CORE_")
        and key != "BEADS_DOLT_PASSWORD"
    }
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "DRILL_COMMAND_LOG": str(scratch.command_log),
            "DRILL_STATE_DIR": str(scratch.state_dir),
            "DRILL_PORT_BUSY": "yes" if port_busy else "no",
            "DRILL_TUNNEL_BIND": tunnel_bind,
            "DRILL_FAKE_HANG_INTENT": hang_intent,
            "ANSIBLE_DISPLAY_SKIPPED_HOSTS": "True",
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
            "ANSIBLE_PIPELINING": "True",
        }
    )
    if with_secret:
        env["BEADS_DOLT_PASSWORD"] = scratch.secret
    extra_vars = {
        "claim_token_race_drill_plugin_repository": str(scratch.plugin_repo),
        "claim_token_race_drill_plugin_ref": _TAG,
        "claim_token_race_drill_control_checkout": str(scratch.control_checkout),
        "claim_token_race_drill_control_bd": str(scratch.bin_dir / "bd-control"),
        "claim_token_race_drill_bd_tarball_url": scratch.tarball.as_uri(),
        "claim_token_race_drill_bd_tarball_sha256": scratch.tarball_sha256,
        "claim_token_race_drill_bd_binary_sha256": scratch.binary_sha256,
        "claim_token_race_drill_bd_arch": os.uname().machine,
        "claim_token_race_drill_python": sys.executable,
        "claim_token_race_drill_tmp_root": str(scratch.tmp_dir),
        "claim_token_race_drill_barrier_lead_seconds": 6,
        "claim_token_race_drill_feed_timeout_seconds": 60,
        "claim_token_race_drill_probe_timeout_seconds": probe_timeout,
        "claim_token_race_drill_wait_interval": 1,
        "claim_token_race_drill_wait_retries": 15,
    }
    if confirm is not None:
        extra_vars["claim_token_race_drill_confirm"] = confirm
    argv = [
        "uvx",
        "--from",
        _ansible_core_pin(),
        "ansible-playbook",
        "-i",
        str(_write_inventory(scratch=scratch)),
        "-e",
        json.dumps(extra_vars),
        *(["--check"] if check_mode else []),
        str(_PLAYBOOK),
    ]
    completed = subprocess.run(
        argv,
        cwd=scratch.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _tokens(*, scratch: _Scratch) -> dict[str, dict[str, object]]:
    return {k: v for k, v in scratch.records.items() if "claim-token" in (v.get("labels") or [])}


def _items(*, scratch: _Scratch) -> dict[str, dict[str, object]]:
    return {k: v for k, v in scratch.records.items() if k not in _tokens(scratch=scratch)}


def _reason(*, record: dict[str, object]) -> dict[str, object]:
    """A token's close reason, parsed; every token the protocol closes carries JSON."""
    raw = record.get("close_reason")
    if not isinstance(raw, str):
        return {}
    parsed = json.loads(raw)
    assert isinstance(parsed, dict), raw
    return parsed  # pyright: ignore[reportUnknownVariableType]


def _assert_everything_removed(*, scratch: _Scratch, output: str) -> None:
    assert scratch.secret not in output, "the credential must never reach the play's output"
    assert not scratch.tunnel_listening, "the tunnel must be gone once the play exits"
    assert scratch.throwaway_dirs == [], "both throwaway directories must be gone"
    alive = subprocess.run(
        ["pgrep", "-f", f"{scratch.tmp_dir}/claim-token-race-drill."],
        capture_output=True,
        text=True,
        check=False,
    )
    assert alive.stdout.strip() == "", f"writers still running: {alive.stdout}"


def _assert_tunnel_shape(*, scratch: _Scratch) -> None:
    tunnel = [line for line in scratch.commands if line.startswith("ssh ")]
    assert len(tunnel) == 1, scratch.commands
    assert f"-R 127.0.0.1:{_PORT}:127.0.0.1:{_PORT}" in tunnel[0]
    assert "-o ExitOnForwardFailure=yes" in tunnel[0]
    assert tunnel[0].rstrip().endswith(f"@{_TARGET}"), tunnel[0]


def _assert_token_chain(*, scratch: _Scratch) -> None:
    items = _items(scratch=scratch)
    assert len(items) == 1, items
    ((item_id, item),) = items.items()
    assert item_id.startswith("bd-ib-")
    assert item["status"] == "closed"
    assert "claim-token race drill finished" in str(item["close_reason"])
    metadata = item["metadata"]
    assert isinstance(metadata, dict)
    # The sequential case: the control node wrote first; the target stood down.
    assert metadata["dispatch_claim"]["run_id"] == "drill-sequential-control-node"

    tokens = _tokens(scratch=scratch)
    reasons = {k: _reason(record=v) for k, v in tokens.items()}
    transitions = {k: r for k, r in reasons.items() if r.get("kind") == "claim-token-transition"}
    discards = [k for k, r in reasons.items() if r.get("kind") == "claim-token-discard"]
    open_tokens = [k for k, v in tokens.items() if v["status"] != "closed"]
    # Overlapping winner, sequential first writer, the disposal hold: three
    # transitions; the overlapping loser discarded its successor; the disposal
    # hold's successor is the one open token, and the closed item names it.
    assert len(transitions) == 3, tokens
    assert len(discards) == 1, tokens
    assert open_tokens == [metadata["dispatch_claim_token"]], tokens
    assert sorted(str(r["intent"]) for r in transitions.values()) == [
        "claim-token-race-drill:dispose",
        "claim-token-race-drill:overlapping",
        "claim-token-race-drill:sequential",
    ]
    sequential = next(r for r in transitions.values() if str(r["intent"]).endswith(":sequential"))
    assert sequential["writer"] == "claim-token-race-drill/control-node"
    # The chain is linear: each transition names a distinct successor.
    assert len({str(r["successor"]) for r in transitions.values()}) == 3


@pytest.mark.parametrize("confirm", [None, "not-a-host"])
def test_a_run_without_the_confirmation_naming_the_target_reads_nothing_and_changes_nothing(
    *, scratch: _Scratch, confirm: str | None
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=confirm)

    assert code == 0, output
    assert scratch.commands == [], output
    assert scratch.records == {}
    assert {int(m["changed"]) for m in _RECAP_CHANGED.finditer(output)} == {0}, output


def test_a_control_node_without_the_projected_credential_is_refused_before_any_read(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_TARGET, with_secret=False)

    assert code != 0, output
    assert "with-livespec-env.sh" in output
    assert scratch.commands == [], output
    assert scratch.records == {}


def test_a_target_already_listening_on_the_dolt_port_is_refused_before_any_write(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_TARGET, port_busy=True)

    assert code != 0, output
    assert all(line.startswith("ss ") for line in scratch.commands), scratch.commands
    assert scratch.records == {}
    assert scratch.throwaway_dirs == []


def test_a_check_mode_run_opens_no_tunnel_and_writes_no_record(*, scratch: _Scratch) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_TARGET, check_mode=True)

    assert code == 0, output
    assert "Check mode" in output
    assert all(line.startswith("ss ") for line in scratch.commands), scratch.commands
    assert scratch.records == {}
    assert scratch.throwaway_dirs == []


def test_a_confirmed_run_races_both_cases_and_exactly_one_writer_wins_each_token(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_TARGET)

    assert code == 0, output
    _assert_everything_removed(scratch=scratch, output=output)
    report = _REPORT.search(output)
    assert report is not None, output
    assert report["host"] == _TARGET
    assert report["start"] <= report["end"]
    assert len(_VERDICT_OK.findall(output)) >= 2, output

    _assert_tunnel_shape(scratch=scratch)
    _assert_token_chain(scratch=scratch)


def test_a_tunnel_bound_beyond_loopback_is_refused_and_still_torn_down(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_TARGET, tunnel_bind="wide")

    assert code != 0, output
    assert "not loopback-only" in output
    _assert_everything_removed(scratch=scratch, output=output)
    assert scratch.records == {}, "the probe item is created only after the tunnel is verified"


def test_a_writer_that_never_finishes_is_killed_and_the_probe_item_still_disposed(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(
        scratch=scratch,
        confirm=_TARGET,
        hang_intent="claim-token-race-drill:overlapping",
        probe_timeout=8,
    )

    assert code != 0, output
    _assert_everything_removed(scratch=scratch, output=output)
    items = _items(scratch=scratch)
    assert len(items) == 1, items
    (item,) = items.values()
    assert item["status"] == "closed", "the always block disposes of the probe item"
    assert _REPORT.search(output) is not None, "times are printed even when a case fails"
