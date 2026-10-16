"""The factory credential is DELIVERED to every Fabro-server host by the fabro play.

`poweredge-xubuntu`'s k3s datastore is a tmpfs
(`ci-runner/k3s/phase2/datastore-tmpfs/`), so the `factory` namespace's
`sandbox-launcher` ServiceAccount and its token Secret are recreated at every
boot and the kubeconfig rendered from them is a NEW file each time. The hosts
that run a Fabro server consume that credential, so they need the same two
halves the gates credential already has: a converge-time FETCH of the rendered
file, and a runtime pull-on-rejection that re-fetches it after a control-plane
reboot without an operator.

This file asserts the FETCH half — the `factory_kubeconfig` role and the play
that runs it. The render half is `test_ci_runner_k3s_factory_credential.py`;
the runtime half is `test_factory_credential_refresh.py`.

WHY THE ROLE IS READ RATHER THAN APPLIED, and why the task list rather than the
`--list-tasks` output: applying the role needs the factory host, the
control-plane node and a real bearer token, and would still prove it of ONE
host. `ansible-playbook --list-tasks` renders exactly the role's own task names
under its play, so reading the committed play and the committed tasks asserts
the same thing of every host the group holds — the sibling
`test_ci_runner_k3s_factory_namespace.py` reads its manifests the same way.

A MACHINE IS NAMED NOWHERE. The play targets an inventory GROUP and the role
resolves the control-plane host out of `ci_pool` by `cluster_role`, which is
the posture `livespec-dev-tooling-prdxxe` ratified and
`just check-ansible-hostname-free` enforces. These tests assert that posture
rather than a hostname, so they keep passing when the factory moves hosts.

Work-item: `livespec-dev-tooling-sqobqv`. Plan: livespec
`factory-worker-nodes-gitops`, epic `livespec-sqvj7p`.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_FABRO_PLAY = _ANSIBLE / "fabro-hosts.yml"
_GATES_PLAY = _ANSIBLE / "gates-kubeconfig.yml"
_ROLE = _ANSIBLE / "roles" / "factory_kubeconfig"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars" / "hp-xubuntu.yml"
_GATES_TASKS = _ANSIBLE / "roles" / "gates_kubeconfig" / "tasks" / "main.yml"

# The group the play must target. Every host that runs a Fabro server is
# reached through a GROUP, never by name: `livespec-dev-tooling-2puzjr` moves
# the live Fabro server onto another machine, and a play that named today's
# host would deliver the credential to the wrong one afterwards.
_FABRO_SERVER_GROUP = "sandbox_hosts"

# The two runtime tools the role ships beside the credential. The wrapper is
# what a caller runs; the refresh tool is what the wrapper invokes on a
# rejection. Both are installed by the role and neither is named by a host.
_RUNTIME_TOOLS = ("refresh-factory-kubeconfig", "with-factory-kubeconfig")

# The credential's path on a Fabro-server host, and the rendered file on the
# control-plane node it is fetched from. The same name on both sides, because
# the converge renders it beside the gates one under the same directory.
_CREDENTIAL_DEST = "/etc/ci-runner/factory.kubeconfig"

# How the control-plane node is resolved: the `ci_pool` member whose
# `cluster_role` is `server`. Asserted as the EXPRESSION rather than as a
# hostname, which is the whole point of the posture.
_SERVER_SELECTORS = (
    "groups['ci_pool']",
    "selectattr('cluster_role', 'equalto', 'server')",
)

# The gates play's task list, FROZEN. The Definition of Done requires the vps
# play's gates tasks to be unchanged by this slice, and `gates_kubeconfig` is
# named BY ROLE NAME in this repository's `SPECIFICATION/contracts.md`, in the
# ratified clause stating how the delegated pre-push gate's credential is
# installed — so a generalisation that renamed the role or its tasks would be a
# ratified-spec change, not an implementation choice. This tuple is what
# `ansible-playbook --list-tasks ansible/gates-kubeconfig.yml` prints today, in
# order.
_GATES_TASK_NAMES = (
    "Install kubectl pinned to the cluster's k3s minor",
    "Install the gates-credential scripts",
    "Read the rendered gates kubeconfig from the control-plane node",
    "Refuse a fetched file that is not a kubeconfig",
    "Create the credential directory",
    "Create the group that may read the gates credential",
    "Put this host's login user in the gate-client group",
    "Install the refresh tool's ssh-identity and group env-file",
    "Install the gates kubeconfig",
)


def _read(*, path: Path) -> str:
    """One committed file, asserting its presence first.

    An absent file is the finding, so it is stated as an ASSERTION rather than
    left to surface as a `FileNotFoundError` from inside a reader — a test that
    dies before its first assertion proves only that a path is missing, not what
    the missing thing was supposed to do.
    """
    assert path.is_file(), (
        f"{path.relative_to(_REPO_ROOT)} must exist: the factory credential is "
        f"delivered by a role, and a Fabro-server host that holds no factory "
        f"kubeconfig cannot launch a sandbox pod"
    )
    return path.read_text(encoding="utf-8")


def _tasks(*, path: Path) -> tuple[tuple[str, str], ...]:
    """Every top-level task of one role, as `(name, body)` in file order."""
    text = _read(path=path)
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{path} must declare its tasks as column-zero `- name:` entries; this reader "
        f"cannot see a task it cannot find, and an unseen task is a credential this "
        f"test has stopped checking"
    )
    return tuple(
        (text[start:stop].split("\n", 1)[0][len("- name: ") :].strip(), text[start:stop])
        for start, stop in pairwise([*openings, len(text)])
    )


def _play(*, name: str) -> str:
    """One play of `ansible/fabro-hosts.yml`, from its `- name:` to the next."""
    text = _read(path=_FABRO_PLAY)
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    bodies = [text[start:stop] for start, stop in pairwise([*openings, len(text)])]
    matching = [body for body in bodies if f"hosts: {name}" in body]
    assert len(matching) == 1, (
        f"ansible/fabro-hosts.yml must carry exactly one play whose `hosts:` is "
        f"`{name}`; found {len(matching)}, so this test is reading the wrong play"
    )
    return matching[0]


def test_the_fabro_server_play_runs_the_factory_kubeconfig_role() -> None:
    """The role is reached through the GROUP play, so a new factory host inherits it.

    Asserted on the play that already converges the Fabro servers rather than on
    a playbook of its own: the credential is one of that host's Fabro facilities,
    and this repository's `SPECIFICATION/non-functional-requirements.md` requires
    every Fabro factory-host facility it provisions to be installed by a role
    `ansible/fabro-hosts.yml` includes for that host, with every host-specific
    value read from that host's host_vars.
    """
    _ = _read(path=_TASKS)
    play = _play(name=_FABRO_SERVER_GROUP)

    assert "- role: factory_kubeconfig" in play, (
        f"the {_FABRO_SERVER_GROUP} play must include the factory_kubeconfig role, so "
        f"`just ansible-apply ansible/fabro-hosts.yml` delivers the credential as part "
        f"of converging the host's Fabro facilities"
    )
    assert "tags: [factory_kubeconfig]" in play, (
        "the role must carry its own tag, so an operator can converge the credential "
        "alone after a control-plane rebuild without re-running every other role"
    )


def test_the_role_installs_kubectl_pinned_to_the_clusters_k3s_minor() -> None:
    """A credential with no client is not access; the client is pinned, not latest.

    kubectl is supported within one minor of the API server, and `latest` drifts
    away from a cluster that does not. The gates role pins for the same reason
    and the two versions are co-maintained with the cluster's own k3s minor.
    """
    pinning = [body for name, body in _tasks(path=_TASKS) if "kubectl" in name]

    assert len(pinning) == 1
    assert "{{ factory_kubeconfig_kubectl_version }}" in pinning[0], (
        "the kubectl download must name the role's pinned version variable; a URL "
        "carrying `latest` installs whatever upstream published today"
    )
    assert "checksum:" in pinning[0], (
        "the download must verify the PUBLISHED checksum fetched from its own URL — a "
        "digest computed from the downloaded file proves only internal consistency"
    )
    assert re.search(
        r"^factory_kubeconfig_kubectl_version: v\d+\.\d+\.\d+$",
        _read(path=_DEFAULTS),
        re.MULTILINE,
    ), "the pinned minor must be a declared role default, not spelled inline in the task"


def test_the_role_installs_the_factory_refresh_tool_and_its_wrapper() -> None:
    """Both runtime tools ship, and both are executable where a caller finds them.

    The wrapper alone would leave a rejected credential rejected; the refresh tool
    alone would need an operator to notice. The pair is what makes a
    control-plane reboot invisible to the next sandbox launch.
    """
    installing = [body for name, body in _tasks(path=_TASKS) if "scripts" in name]

    assert len(installing) == 1
    for tool in _RUNTIME_TOOLS:
        assert f"- {tool}" in installing[0], (
            f"the role must install {tool}; the runtime pull-on-rejection path is the "
            f"half that survives a control-plane reboot with no command run on any host"
        )
        assert (_ROLE / "files" / tool).is_file(), (
            f"{tool} must be committed under the role's files/, or the install task "
            f"copies a file that does not exist"
        )
    assert 'mode: "0755"' in installing[0]


def test_the_role_fetches_the_rendered_credential_from_the_inventory_resolved_server() -> None:
    """The fetch reads the control-plane node's rendered file, and names no machine.

    A pull rather than a push: the factory host already reaches the control-plane
    node over the tailnet, so nothing new has to be granted, and the fetch fails
    CLOSED — an unreachable server leaves the existing credential alone.
    """
    fetching = [body for _name, body in _tasks(path=_TASKS) if "ansible.builtin.slurp:" in body]
    defaults = _read(path=_DEFAULTS)

    assert len(fetching) == 1
    assert "{{ factory_kubeconfig_remote_path }}" in fetching[0]
    assert 'delegate_to: "{{ factory_kubeconfig_remote_host }}"' in fetching[0], (
        "the read must be delegated to the control-plane node, which is where the "
        "converge renders the file"
    )
    assert "no_log: true" in fetching[0], "the fetched content is a bearer token"
    for selector in _SERVER_SELECTORS:
        assert selector in defaults, (
            f"factory_kubeconfig_remote_host must resolve the server from the inventory "
            f"via {selector}; a hostname in a role default is the second, silent place a "
            f"machine binding lives (livespec-dev-tooling-prdxxe)"
        )
    assert f"factory_kubeconfig_remote_path: {_CREDENTIAL_DEST}" in defaults
    assert f"factory_kubeconfig_dest: {_CREDENTIAL_DEST}" in defaults


def test_the_role_reads_this_hosts_ssh_identity_from_its_host_vars() -> None:
    """The fetching account is a HOST fact, and hp's is not the fleet's usual one.

    The refresh runs as root at runtime and root holds no tailnet ssh identity, so
    the fetch drops to a login user whose `~/.ssh` reaches the control-plane node.
    On the host that runs today's Fabro servers that account is `cwoolley`, not
    `ubuntu` — the tailnet ACL rejects `ubuntu` there — so a role default would be
    wrong for exactly the host this credential exists for.
    """
    defaults = _read(path=_DEFAULTS)
    host_vars = _read(path=_HOST_VARS)

    assert "factory_kubeconfig_ssh_user:" in defaults
    assert re.search(r"^factory_kubeconfig_ssh_user: \S+$", host_vars, re.MULTILINE), (
        "ansible/inventory/host_vars/hp-xubuntu.yml must declare "
        "factory_kubeconfig_ssh_user: the fetching account varies by machine, and "
        "host_vars is the only place a machine's values are bound"
    )
    assert "# --- factory_kubeconfig ---" in host_vars, (
        "the host_vars entry must sit under its owning role's generated section header, "
        "so the next regeneration from HOST_VARS.md keeps it"
    )
    assert (_ROLE / "HOST_VARS.md").is_file(), (
        "host_vars is GENERATED from each role's HOST_VARS.md, so a role with per-host "
        "values and no HOST_VARS.md loses them at the next regeneration"
    )


def test_the_gates_plays_task_list_is_unchanged() -> None:
    """The delegated pre-push gate's own credential is untouched by this slice.

    `gates_kubeconfig` is named by name in this repository's
    `SPECIFICATION/contracts.md`, in the ratified clause governing the delegated
    pre-push gate's credential, and it is the live credential every fleet
    repository's delegated push authenticates with. So the factory ships as a
    SIBLING role rather than by generalising that one into a parameterised role:
    the generalisation the work-item prefers would rename the role the ratified
    spec names, which is a propose-change rather than an implementation choice.
    This test is the lock that keeps the preference from being taken by accident.
    """
    gates_play = _read(path=_GATES_PLAY)

    assert tuple(name for name, _body in _tasks(path=_GATES_TASKS)) == _GATES_TASK_NAMES
    assert "hosts: dev_hosts" in gates_play
    assert "- gates_kubeconfig" in gates_play
    assert "factory" not in gates_play, (
        "the gates play must not acquire the factory credential: a dev host is not a "
        "Fabro factory host, and the two credentials grant different namespaces"
    )
