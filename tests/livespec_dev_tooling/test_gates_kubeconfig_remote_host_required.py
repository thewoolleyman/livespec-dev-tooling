"""`refresh-gates-kubeconfig` takes its control-plane node from the pool, never from a default.

A machine is bound ONLY through the inventory's host groups and host variables
(livespec-dev-tooling-prdxxe). The runtime refresh tool the `gates_kubeconfig`
role installs defaulted `GATES_REMOTE_HOST` to one machine's inventory name, so
the pool's server lived in two places — the role's inventory-resolved default and
a literal inside a shipped script — and the two could disagree silently. The
role's OTHER pool facts (the ssh identity and the gate-client group) were already
delivered in an env-file rather than baked in; the remote host now joins them.

The tool therefore REFUSES when the variable is unset, naming it, and the role
renders it from the `ci_pool` member whose `cluster_role` is `server`.

WHY THE SCRIPT IS RUN RATHER THAN READ. The claim is about CONTROL FLOW — refuse
BEFORE any fetch is attempted — and reading a shell script cannot establish that.
It runs with `ssh` faked on a scratch PATH, so no host is contacted and the
absence of a fetch is itself an assertion. The role's half is read, exactly as
`tests/consumer/test_gates_credential_provisioning.py` reads it: applying it needs
the VPS, the control-plane node and a real bearer token.

Work-item: livespec-dev-tooling-mavj5i. Plan: livespec-orchestrator-beads-fabro
`petri-factory-on-gmktec`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "gates_kubeconfig"
_REFRESH_TOOL = _ROLE / "files" / "refresh-gates-kubeconfig"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_INVENTORY = _REPO_ROOT / "ansible" / "inventory" / "legacy.yml"

# The variable the env-file carries and the tool must be told.
_REMOTE_HOST_VAR = "GATES_REMOTE_HOST"

# A rendered kubeconfig, carrying the two markers the tool requires before it
# will overwrite anything. Its token is the word `fixture`.
_FIXTURE_KUBECONFIG = (
    "apiVersion: v1\nkind: Config\nclusters:\n  - name: ci-runner\n"
    "    cluster:\n      server: https://an-answering-host.example.ts.net:6443\n"
    "users:\n  - name: gate-submitter\n    user:\n      token: fixture\n"
)

# `ssh`: log the argv and emit the fixture on stdout, standing in for the remote
# `sudo cat`. No host is contacted.
_SSH_SHIM = """\
printf 'ssh %s\\n' "$*" >> "$ARGV_LOG"
printf '%s' "$FIXTURE_KUBECONFIG"
exit 0
"""
# `id -u` answers FAKE_EUID. A NON-root answer keeps the run on the branch that
# fetches as itself and gives no file away: the root branch drops the fetch to
# `sudo -u <login user>`, which is a second tool to fake and a second claim, and
# neither is what this suite asks about. `tests/livespec_dev_tooling/
# test_secret_file_rerun_under_uutils.py` reads the root branch's ownership.
_FAKE_EUID = "1000"
_ID_SHIM = '[ "${1:-}" = -u ] && printf \'%s\\n\' "$FAKE_EUID" && exit 0\nexec /usr/bin/id "$@"\n'


def _shim(*, bin_dir: Path, name: str, body: str) -> None:
    """One executable on the scratch PATH, standing in for a host tool."""
    path = bin_dir / name
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _run_refresh(*, tmp_path: Path, remote_host: str | None) -> tuple[int, str, list[str]]:
    """Run the shipped refresh tool with `GATES_REMOTE_HOST` set or absent."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    dest = tmp_path / "etc" / "ci-runner" / "gates.kubeconfig"
    dest.parent.mkdir(parents=True)
    _shim(bin_dir=bin_dir, name="ssh", body=_SSH_SHIM)
    _shim(bin_dir=bin_dir, name="id", body=_ID_SHIM)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(
        {
            "ARGV_LOG": str(log),
            "FAKE_EUID": _FAKE_EUID,
            "FIXTURE_KUBECONFIG": _FIXTURE_KUBECONFIG,
            "GATES_KUBECONFIG": str(dest),
            # An absent env-file: this suite asks what the tool does when the
            # role has NOT delivered its pool facts.
            "GATES_SSH_ENV": str(tmp_path / "no-such-env-file"),
        }
    )
    env.pop(_REMOTE_HOST_VAR, None)
    if remote_host is not None:
        env[_REMOTE_HOST_VAR] = remote_host
    completed = subprocess.run(
        ["bash", str(_REFRESH_TOOL)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def _inventory_k3s_server() -> str:
    """The `ci_pool` member whose `cluster_role` is `server`, read from the inventory."""
    pool = _INVENTORY.read_text(encoding="utf-8").split("        ci_pool:\n", 1)[1]
    server = re.search(
        r"^ {12}(?P<host>[\w.-]+):\n(?: {14}.*\n)*? {14}cluster_role: server$",
        pool,
        re.MULTILINE,
    )
    assert server is not None, "the inventory's ci_pool must name one server"
    return server["host"]


def test_bash_is_available_to_run_the_shipped_refresh_tool() -> None:
    """The lens this suite reads the script through, named rather than assumed."""
    assert shutil.which("bash") is not None


def test_the_refresh_tool_refuses_before_it_fetches_when_its_remote_host_is_unset(
    *, tmp_path: Path
) -> None:
    """The refusal comes FIRST, names the variable, and nothing is contacted.

    `ssh` is faked and its argv logged, so an empty log is the assertion. A
    default would have been worse than an empty one: the tool would have fetched
    a bearer token from whichever machine the literal named, which on a second
    pool is a host that is not this pool's control plane at all.
    """
    code, output, invoked = _run_refresh(tmp_path=tmp_path, remote_host=None)

    assert code != 0
    assert _REMOTE_HOST_VAR in output
    assert invoked == []


def test_the_refresh_tool_fetches_from_the_host_the_pool_supplies(*, tmp_path: Path) -> None:
    """The control arm: told which node renders the credential, the tool pulls from it.

    The remote verb is a `sudo cat` of the rendered credential and nothing else —
    the narrowest remote verb that can deliver it.
    """
    supplied = "an-answering-host"

    code, _output, invoked = _run_refresh(tmp_path=tmp_path, remote_host=supplied)

    fetches = [line for line in invoked if line.startswith("ssh ")]

    assert code == 0
    assert len(fetches) == 1
    assert supplied in fetches[0]
    assert "sudo cat /etc/ci-runner/gates.kubeconfig" in fetches[0]


def test_the_role_delivers_the_remote_host_in_the_tools_env_file() -> None:
    """The pool fact reaches the shipped tool the way its siblings already do.

    The ssh identity and the gate-client group were delivered in this env-file
    from the start, for the stated reason that both are pool facts rather than
    script behaviour. The control-plane node is the same kind of fact, so it is
    delivered the same way instead of being baked into the script.
    """
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")

    assert f"{_REMOTE_HOST_VAR}={{{{ gates_kubeconfig_remote_host }}}}" in tasks


def test_the_role_resolves_the_remote_host_from_the_ci_pools_server() -> None:
    """No machine is named — the server is the `ci_pool` member whose role says so.

    Asserted against the inventory rather than against a literal, so a pool that
    moves its control plane moves this with it and nothing in the role or the
    script has to be edited.
    """
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")

    assert "selectattr('cluster_role', 'equalto', 'server')" in defaults
    assert _inventory_k3s_server() not in defaults
