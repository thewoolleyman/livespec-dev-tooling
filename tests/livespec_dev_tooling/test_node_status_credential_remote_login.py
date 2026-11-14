"""A pool agent whose operator account is not the server's login account still pulls its credential.

The node-status refresh tool drops its fetch to `node_status_credential_ssh_user`
on the AGENT and ssh's to the control-plane node. Until 2026-11-11 that one
variable was also, implicitly, the account it logged in as on the SERVER, because
the rendered `NODE_STATUS_REMOTE_HOST` carried a bare host name. Every pool node
then logged in as `cwoolley`, so the conflation was invisible.

gamingpc-xubuntu (plan homelab-k8s-worker-nodes, epic livespec-dev-tooling-ko26ez)
is the first agent whose operator account is `ubuntu`. Measured 2026-11-11 ~07:10Z
from that host as `ubuntu`: `ssh poweredge-xubuntu` is refused with
"tailscale: failed to look up local user", while `ssh cwoolley@poweredge-xubuntu`
authenticates and passes `sudo -n`. Its first converge then failed earlier still,
becoming a `cwoolley` that does not exist there.

The role now takes an optional `node_status_credential_remote_user`. The tests
read the committed role as text, as its sibling
`test_node_status_credential_host_key_trust.py` does and for the same reason: a
converge needs the live agent, the live server and a real host key.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "node_status_credential"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_GAMINGPC_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "gamingpc-xubuntu.yml"

_REMOTE_USER_VARIABLE = "node_status_credential_remote_user"
_SERVER_HOST_VARIABLE = "node_status_credential_server_host"
_REMOTE_LOGIN_VARIABLE = "node_status_credential_remote_login"


def _non_comment_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")]


def _remote_host_line() -> str:
    lines = [line for line in _non_comment_lines(_ROLE_TASKS) if "NODE_STATUS_REMOTE_HOST=" in line]
    assert (
        len(lines) == 1
    ), f"expected exactly one rendered NODE_STATUS_REMOTE_HOST line, found {lines!r}"
    return lines[0]


def test_the_remote_login_user_defaults_to_empty_so_existing_agents_render_unchanged() -> None:
    defaults = _non_comment_lines(_ROLE_DEFAULTS)
    assert f'{_REMOTE_USER_VARIABLE}: ""' in defaults, (
        f"{_ROLE_DEFAULTS} must default {_REMOTE_USER_VARIABLE} to the empty string, so a node that "
        "sets nothing renders a bare host name exactly as before"
    )


def test_the_rendered_remote_host_prefixes_the_login_user_only_when_one_is_set() -> None:
    assert (
        _remote_host_line().strip()
        == "NODE_STATUS_REMOTE_HOST={{ " + _REMOTE_LOGIN_VARIABLE + " }}"
    )
    composed = [line.strip() for line in _non_comment_lines(_ROLE_DEFAULTS)]
    expected = (
        f"{{{{ ({_REMOTE_USER_VARIABLE} ~ '@') if {_REMOTE_USER_VARIABLE} else '' }}}}"
        f"{{{{ {_SERVER_HOST_VARIABLE} }}}}"
    )
    assert expected in composed, (
        f"{_REMOTE_LOGIN_VARIABLE} must render `<user>@` only when {_REMOTE_USER_VARIABLE} is set, "
        f"then the server host; expected the line {expected!r} in {_ROLE_DEFAULTS}"
    )


def test_the_known_hosts_entry_stays_under_the_bare_server_host_name() -> None:
    trust_lines = [
        line
        for line in _non_comment_lines(_ROLE_TASKS)
        if line.strip().startswith(("name:", "key:")) and _SERVER_HOST_VARIABLE + " }}" in line
    ]
    assert trust_lines, "the role must still write a known_hosts entry named by the server host"
    for line in trust_lines:
        assert _REMOTE_USER_VARIABLE not in line and _REMOTE_LOGIN_VARIABLE not in line, (
            "ssh matches known_hosts on the host name, never on `<user>@<host>`, so the login user must "
            f"not reach the trust entry; got {line!r}"
        )


def test_gamingpc_fetches_as_its_operator_account_and_logs_in_as_the_servers_account() -> None:
    host_vars = _non_comment_lines(_GAMINGPC_HOST_VARS)
    assert "node_status_credential_ssh_user: ubuntu" in host_vars
    assert f"{_REMOTE_USER_VARIABLE}: cwoolley" in host_vars
