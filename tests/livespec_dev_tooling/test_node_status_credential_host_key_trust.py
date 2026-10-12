"""An agent's node-status credential pull must TRUST the control-plane node it pulls from.

livespec-dev-tooling-yj25uj (PR #2367) made the agent re-fetch its node-status
kubeconfig over ssh from `poweredge-xubuntu`, as the pool's login user, whenever
the API server refuses the credential it holds. Nothing provisioned that
account's host-key trust. Measured 2026-10-12 from gmktec-xubuntu as `cwoolley`:
`ssh -o BatchMode=yes poweredge-xubuntu ...` dies with "Host key verification
failed", while the same command with host-key checking disabled authenticates and
`sudo -n true` succeeds there. So the ssh key and the sudo grant were both in
place and only the `known_hosts` entry was missing — which is a repair path that
fails closed on the next poweredge reboot, and fails closed is exactly when the
repair is needed.

`BatchMode=yes` is the reason the gap is fatal rather than merely noisy: the
refresh tool is invoked by a root systemd unit mid-timer-fire, so there is no
terminal to answer the "are you sure you want to continue connecting?" prompt
with. An unknown host key is therefore not a question, it is a failure.

WHY THE ROLE IS READ RATHER THAN APPLIED. Its claims are claims about what a
CONVERGE does — whose `known_hosts` the entry lands in, under which host name,
and where the trusted bytes were read FROM. Applying it needs the live agent, the
live control-plane node and a real ssh host key, and would still prove it of ONE
pool rather than of every converge. So the committed tasks are read, exactly as
`tests/consumer/test_gates_credential_provisioning.py` reads its own role, and
text-sliced because no YAML library is importable from this suite.

THE ONE CLAIM A READER CAN STILL GET WRONG is "not accepted on first use". A
trust-on-first-use fix — `ssh-keyscan`, or `StrictHostKeyChecking=accept-new` —
would make the measured symptom disappear while authenticating nothing at all on
the one run that matters, and it is the shorter patch, so it is the one a later
change is likely to reach for. Its absence is asserted over the role's
NON-COMMENT lines, so the comment that names the rejected alternative may keep
naming it.

Work-item: livespec-dev-tooling-cehlmt. Plan: livespec `k3s-on-gmktec-for-vps-usage`
(epic livespec-sab5gn). Follow-up to livespec-dev-tooling-yj25uj.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "node_status_credential"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_REFRESH_TOOL = _ROLE / "files" / "refresh-node-status-kubeconfig"

# The role's own variable names, which are the vocabulary the Definition of Done
# is written in: the trust lands for `node_status_credential_ssh_user` under the
# name `node_status_credential_server_host`.
_SSH_USER_VARIABLE = "node_status_credential_ssh_user"
_SERVER_HOST_VARIABLE = "node_status_credential_server_host"
_HOST_KEY_PATH_VARIABLE = "node_status_credential_server_host_key"
_HOST_KEY_TYPE_VARIABLE = "node_status_credential_server_host_key_type"
_KNOWN_HOSTS_VARIABLE = "node_status_credential_known_hosts"
# The fact the delegated read is decoded into, and so the second field of the
# `known_hosts` line the role composes.
_HOST_KEY_FACT = "node_status_credential_host_key"

# OpenSSH's own path for the host's ed25519 public key, and the key type its
# first field carries. Both are stated here because the Definition of Done states
# them: the trusted key is the SERVER's ed25519 host key, read during the apply.
_HOST_KEY_PATH = "/etc/ssh/ssh_host_ed25519_key.pub"
_HOST_KEY_TYPE = "ssh-ed25519"

# `~/.ssh` must be 0700 or ssh ignores what is in it, and the directory has to
# exist before the `known_hosts` entry is written at all — the module stages its
# replacement in the destination's OWN directory, so a missing parent is an apply
# failure rather than a created tree.
_SSH_DIR_MODE = "0700"

# The trust-on-first-use spellings this fix must not become. `ssh-keyscan` asks
# the network who the host is and believes the answer; the two client options
# tell ssh to stop asking. Each makes the measured failure disappear and
# authenticates nothing.
_TRUST_ON_FIRST_USE = ("ssh-keyscan", "StrictHostKeyChecking", "accept-new")

# How a hand-rolled known_hosts write would look, and why it is wrong here: an
# append grows a duplicate entry on every apply, so the converge would never
# report "no change" even with the server's key unchanged.
_APPENDING = ("lineinfile", "blockinfile", ">> ")

# Task openings are matched at the block's OWN indentation (four spaces) rather
# than at column zero: this role's tasks all live inside one agent-gated `block:`,
# whose single column-zero `- name:` entry has every other task as its body. A
# column-zero reader would therefore find exactly one task and prove nothing
# about any of the others.
_TASK_OPENING = re.compile(r"^    - name: .+$", re.MULTILINE)
_TASK_PREFIX = "    - name: "


def _tasks() -> list[tuple[str, str]]:
    """Every task inside the role's agent block, as `(name, body)` in file order."""
    text = _ROLE_TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in _TASK_OPENING.finditer(text)]
    assert openings, (
        f"{_ROLE_TASKS} must declare its tasks as `- name:` entries indented into "
        f"the agent block; this reader cannot see a task it cannot find, and an "
        f"unseen task is a trust decision this test has stopped checking"
    )
    return [
        (text[start:stop].split("\n", 1)[0][len(_TASK_PREFIX) :].strip(), text[start:stop])
        for start, stop in pairwise([*openings, len(text)])
    ]


def _task_using(*, module: str) -> str:
    """The one task in the block that invokes `module`."""
    matching = [body for _name, body in _tasks() if f"{module}:" in body]
    assert len(matching) == 1, (
        f"the role must carry exactly one task invoking `{module}`; found "
        f"{len(matching)}, so this test is reading the wrong one or none at all"
    )
    return matching[0]


def _role_default(*, name: str) -> str:
    """One scalar the role's `defaults/main.yml` declares, unquoted."""
    found = re.search(
        rf"^{name}: (?P<value>.+)$", _ROLE_DEFAULTS.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert found is not None, (
        f"the role must declare `{name}` in defaults/main.yml: the server's host "
        f"key and the account that trusts it are pool facts, and a pool fact "
        f"spelled inline in a task is not one"
    )
    return found["value"].strip().strip('"')


def _effective(*, source: Path) -> str:
    """`source` with whole-line comments dropped.

    A comment that NAMES the rejected alternative is the record of why it was
    rejected, and it must not read as a use of it. Only whole-line comments are
    dropped, so an inline `# ...` trailing a real task line still participates —
    which is the conservative direction for a guard like this.
    """
    return "\n".join(
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_the_role_trusts_the_control_plane_nodes_host_key_for_the_refresh_tools_ssh_user() -> None:
    """The Definition of Done's first assertion, stated where the converge makes it true.

    The entry lands in the SSH USER's own `known_hosts` — not root's: the refresh
    tool runs as root and drops the fetch to that account via `sudo -u`, so root's
    trust store is the one file that cannot help it. And it lands under the name
    `node_status_credential_server_host`, because that is the literal the shipped
    tool passes to `ssh`, and `known_hosts` is matched on the name given rather
    than on anything it resolves to.

    `key:` is asserted to OPEN with the same host name as `name:`, because the
    module requires the two to agree: a `known_hosts` line's first field IS the
    host it authenticates, so a mismatch installs an entry ssh will never consult.
    """
    trust = _task_using(module="ansible.builtin.known_hosts")

    assert f'name: "{{{{ {_SERVER_HOST_VARIABLE} }}}}"' in trust
    assert f'key: "{{{{ {_SERVER_HOST_VARIABLE} }}}} {{{{ {_HOST_KEY_FACT} }}}}"' in trust
    assert f'path: "{{{{ {_KNOWN_HOSTS_VARIABLE} }}}}"' in trust
    assert "state: present" in trust
    assert "become: true" in trust
    assert f'become_user: "{{{{ {_SSH_USER_VARIABLE} }}}}"' in trust
    assert _SSH_USER_VARIABLE in _role_default(name=_KNOWN_HOSTS_VARIABLE)


def test_the_trusted_key_is_read_from_the_server_itself_and_not_accepted_on_first_use() -> None:
    """The Definition of Done's second assertion, and the one a shortcut would break.

    The bytes come from the server's OWN host-key file, read on the server via
    `delegate_to` during the apply — the control node already authenticates to
    both machines, so the read inherits that authentication instead of minting a
    new act of faith. The alternative an agent could perform unaided is
    trust-on-first-use, which believes whatever answers to the name on the first
    connection and therefore authenticates nothing on the one run that matters.
    """
    read = _task_using(module="ansible.builtin.slurp")

    assert f'src: "{{{{ {_HOST_KEY_PATH_VARIABLE} }}}}"' in read
    assert f'delegate_to: "{{{{ {_SERVER_HOST_VARIABLE} }}}}"' in read
    assert _role_default(name=_HOST_KEY_PATH_VARIABLE) == _HOST_KEY_PATH
    for spelling in _TRUST_ON_FIRST_USE:
        assert spelling not in _effective(source=_ROLE_TASKS)
        assert spelling not in _effective(source=_REFRESH_TOOL)


def test_a_reapply_with_an_unchanged_server_key_changes_nothing() -> None:
    """Idempotence, asserted as the two properties that actually deliver it.

    The entry is installed by the declarative `known_hosts` module, which
    reconciles by content and reports no change when the key is already trusted;
    an appended line would accumulate a duplicate on every apply and report a
    change forever. And the delegated read is marked `changed_when: false`,
    because a read that reports itself as a change makes the whole role
    permanently dirty — the drift report's value is that a clean run means
    something.
    """
    read = _task_using(module="ansible.builtin.slurp")
    effective = _effective(source=_ROLE_TASKS)

    assert "changed_when: false" in read
    assert "ansible.builtin.known_hosts:" in effective
    for spelling in _APPENDING:
        assert spelling not in effective


def test_the_ssh_users_ssh_directory_exists_before_the_known_hosts_entry_is_written() -> None:
    """`--check` cannot see past a missing parent, and the module stages its temp file in it.

    The `known_hosts` module writes its replacement into the DESTINATION's own
    directory and renames it over the destination, so an absent `~/.ssh` is an
    apply failure rather than a created tree — the same reason this role already
    creates the credential-tooling directory explicitly. 0700 because ssh ignores
    the contents of a group- or world-writable `~/.ssh`, so a looser mode would
    install trust ssh declines to read.
    """
    tasks = _tasks()
    names = [name for name, _body in tasks]
    creating = [
        name
        for name, body in tasks
        if "ansible.builtin.file:" in body and _SSH_USER_VARIABLE in body
    ]
    trusting = [name for name, body in tasks if "ansible.builtin.known_hosts:" in body]

    assert len(creating) == 1
    assert len(trusting) == 1
    assert f'mode: "{_SSH_DIR_MODE}"' in dict(tasks)[creating[0]]
    assert names.index(creating[0]) < names.index(trusting[0])


def test_the_role_refuses_a_delegated_read_that_is_not_an_ed25519_host_public_key() -> None:
    """An empty or wrong-typed read must fail the apply, never reach `known_hosts`.

    A `known_hosts` line whose key field is empty or malformed is an entry ssh
    cannot match, so the agent would still fail host-key verification — with a
    converge that reported success. This is the refusal idiom the role already
    uses for an empty cluster CA, pointed at the other thing it must not deliver
    silently.
    """
    refusals = [
        body
        for _name, body in _tasks()
        if "ansible.builtin.assert:" in body and _HOST_KEY_TYPE_VARIABLE in body
    ]

    assert len(refusals) == 1
    assert _role_default(name=_HOST_KEY_TYPE_VARIABLE) == _HOST_KEY_TYPE
