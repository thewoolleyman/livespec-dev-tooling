"""Consumer-tier proof for the ``admin_kubeconfig`` role's file effects.

The role copies a cluster-admin certificate from the control-plane node into a
session account's home.  These fixtures run the real role with the same pinned
``ansible-core`` as ``just ansible-drift``, against a local stand-in for the
control-plane node, and hold what it does to the destination file: it installs a
rewritten, owner-only copy, a second apply changes nothing, an unreachable node
leaves an existing file byte-identical, a first install with no reachable node
fails, and a fetched file that is not an admin kubeconfig is refused before the
destination is touched.  Nothing the fixtures run prints the credential.

The live proof, ``kubectl get nodes`` from the vps, needs the cluster and is
host-captured; the two refusal behaviours here are the fixture assertions of
livespec-dev-tooling-uf2pgj.
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES = _REPO_ROOT / "ansible" / "roles"
_ROLE_NAME = "admin_kubeconfig"
_HOST = "fixture-host"
_NODE = "fixture-node"
_DOWN = "fixture-down"
_TIMEOUT_SECONDS = 600
_SECRET = "FIXTURE-CLIENT-KEY-SECRET-0123456789"
_SERVER_URL = f"https://{_NODE}.perch-rudd.ts.net:6443"
_K3S_YAML = f"""apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: Zml4dHVyZS1jYQ==
    server: https://127.0.0.1:6443
  name: default
contexts:
- context:
    cluster: default
    user: default
  name: default
current-context: default
users:
- name: default
  user:
    client-certificate-data: Zml4dHVyZS1jZXJ0
    client-key-data: {_SECRET}
"""


def _ansible_core_pin() -> str:
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    match = re.search(r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)", recipe, re.MULTILINE)
    assert match is not None, "justfile must define the ansible-drift recipe"
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", match["body"])
    assert pin is not None, "ansible-drift must pin ansible-core"
    return pin[0]


def _fixture_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ROLES),
    }


def _ssh_stub(*, root: Path) -> Path:
    """A stand-in for ``ssh`` that runs the remote command locally.

    Called as ``stub <node> cat <path>``; a node named ``fixture-down`` is
    unreachable and exits 255 as ``ssh`` does.
    """
    stub = root / "ssh-stub"
    stub.write_text(
        "#!/bin/sh\n"
        'node="$1"\nshift\n'
        f'if [ "$node" = "{_DOWN}" ]; then echo "ssh: cannot reach $node" >&2; exit 255; fi\n'
        'exec "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _run(
    *,
    root: Path,
    source: Path,
    dest_dir: Path,
    node: str,
    check: bool = False,
    fetch: str = "slurp",
) -> subprocess.CompletedProcess[str]:
    inventory = root / "inventory.yml"
    inventory.write_text(
        "---\nall:\n  hosts:\n"
        f"    {_HOST}:\n      ansible_connection: local\n      ansible_become: false\n"
        f"    {_NODE}:\n      ansible_connection: local\n      ansible_become: false\n"
        f"    {_DOWN}:\n      ansible_connection: ssh\n      ansible_host: 127.0.0.1\n"
        "      ansible_port: 1\n"
        "      ansible_ssh_common_args: '-o BatchMode=yes -o ConnectTimeout=3'\n",
        encoding="utf-8",
    )
    play = root / "play.yml"
    play.write_text(
        f"---\n- name: admin kubeconfig fixture\n  hosts: {_HOST}\n  gather_facts: false\n"
        f"  roles:\n    - role: {_ROLE_NAME}\n",
        encoding="utf-8",
    )
    variables = {
        "admin_kubeconfig_user": pwd.getpwuid(os.getuid()).pw_name,
        "admin_kubeconfig_dir": str(dest_dir),
        "admin_kubeconfig_remote_host": node,
        "admin_kubeconfig_remote_path": str(source),
        "admin_kubeconfig_remote_become": False,
        "admin_kubeconfig_group": grp.getgrgid(os.getgid()).gr_name,
        "admin_kubeconfig_fetch": fetch,
        "admin_kubeconfig_ssh_argv": [str(_ssh_stub(root=root))],
    }
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
    if check:
        command.extend(["--check", "--diff"])
    command.extend(["-i", str(inventory), "-e", json.dumps(variables), str(play)])
    return subprocess.run(
        command,
        cwd=root,
        env=_fixture_environment(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def _changed(*, result: subprocess.CompletedProcess[str]) -> int:
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    recap = re.search(rf"^{_HOST}\s*:.*?\bchanged=(?P<count>\d+)", output, re.MULTILINE)
    assert recap is not None, output
    return int(recap["count"])


def _source(*, root: Path, text: str = _K3S_YAML) -> Path:
    path = root / "k3s.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_role_installs_a_rewritten_owner_only_kubeconfig(tmp_path: Path) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"

    result = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE)

    assert _changed(result=result) > 0, result.stdout
    installed = dest_dir / "config"
    text = installed.read_text(encoding="utf-8")
    assert f"server: {_SERVER_URL}" in text, text
    assert "127.0.0.1" not in text, text
    assert stat.S_IMODE(installed.stat().st_mode) == 0o600
    assert stat.S_IMODE(dest_dir.stat().st_mode) == 0o700
    assert _SECRET not in result.stdout + result.stderr, "the role printed the credential"


def test_a_second_apply_changes_nothing(tmp_path: Path) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"
    first = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE)
    assert _changed(result=first) > 0, first.stdout

    second = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE)

    assert _changed(result=second) == 0, second.stdout


def test_an_unreachable_node_leaves_an_existing_file_untouched(tmp_path: Path) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"
    _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE)
    installed = dest_dir / "config"
    before = installed.read_bytes()

    result = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_DOWN)

    assert _changed(result=result) == 0, result.stdout
    assert installed.read_bytes() == before


def test_a_first_install_with_no_reachable_node_fails_and_writes_nothing(tmp_path: Path) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"

    result = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_DOWN)

    assert result.returncode != 0, result.stdout
    assert "nothing to keep" in result.stdout + result.stderr
    assert not (dest_dir / "config").exists()


def test_a_fetched_file_that_is_not_a_kubeconfig_is_refused_before_the_destination_changes(
    tmp_path: Path,
) -> None:
    good = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"
    _run(root=tmp_path, source=good, dest_dir=dest_dir, node=_NODE)
    installed = dest_dir / "config"
    before = installed.read_bytes()
    bad = _source(root=tmp_path, text=f"not a kubeconfig, {_SECRET}\n")

    result = _run(root=tmp_path, source=bad, dest_dir=dest_dir, node=_NODE)

    assert result.returncode != 0, result.stdout
    assert installed.read_bytes() == before
    assert _SECRET not in result.stdout + result.stderr, "the refusal printed the fetched content"


def test_the_ssh_fetch_installs_the_same_rewritten_owner_only_kubeconfig(tmp_path: Path) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"

    result = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE, fetch="ssh")

    assert _changed(result=result) > 0, result.stdout
    installed = dest_dir / "config"
    text = installed.read_text(encoding="utf-8")
    assert f"server: {_SERVER_URL}" in text, text
    assert stat.S_IMODE(installed.stat().st_mode) == 0o600
    assert _SECRET not in result.stdout + result.stderr, "the role printed the credential"


def test_a_failed_ssh_fetch_leaves_an_existing_file_untouched(tmp_path: Path) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"
    _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE, fetch="ssh")
    installed = dest_dir / "config"
    before = installed.read_bytes()

    result = _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_DOWN, fetch="ssh")

    assert _changed(result=result) == 0, result.stdout
    assert installed.read_bytes() == before


def test_a_reachable_node_that_lacks_the_file_leaves_an_existing_file_untouched(
    tmp_path: Path,
) -> None:
    source = _source(root=tmp_path)
    dest_dir = tmp_path / "home" / ".kube"
    _run(root=tmp_path, source=source, dest_dir=dest_dir, node=_NODE)
    installed = dest_dir / "config"
    before = installed.read_bytes()

    result = _run(root=tmp_path, source=tmp_path / "absent.yaml", dest_dir=dest_dir, node=_NODE)

    assert _changed(result=result) == 0, result.stdout
    assert installed.read_bytes() == before
