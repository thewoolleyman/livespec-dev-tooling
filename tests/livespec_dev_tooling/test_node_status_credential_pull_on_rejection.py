"""An agent's churn-slot patch must tell a REJECTED credential from a missing node.

`ci-runner/k3s/phase2/node-extended-resource/patch-node-churn-capacity.sh` waits
(bounded) for its node to register before patching, and the wait's probe was
`kubectl get --subresource=status node <name> >/dev/null 2>&1`. That discards the
API server's answer, so the one failure that is NOT a late registration — the
server REFUSING the credential — was indistinguishable from a node that had not
appeared yet.

The cost was measured on 2026-10-12, 04:01Z-04:26Z. A poweredge-xubuntu reboot
empties the tmpfs k3s datastore (`phase2/datastore-tmpfs/`), which re-creates
every ServiceAccount and re-mints every token Secret, so the node-status
kubeconfig seeded onto gmktec-xubuntu on 2026-10-10 carried a token the fresh API
server had never seen: "the server has asked for the client to provide
credentials". gmktec was Ready and registered throughout, and
`reapply-node-extended-resource.service` printed "waiting for node
gmktec-xubuntu to register..." until its timeout, every five minutes, while the
node advertised no `ci-runner.io/churn-slot` capacity at all — so Kueue's quota
was denominated in a resource no node offered.

WHY THE SCRIPT IS RUN RATHER THAN READ. Its claim is a claim about CONTROL FLOW —
recognise the rejection, refresh ONCE, retry, and never report a rejected
credential as an unregistered node — and reading a shell script cannot establish
that. So the shipped script runs with `kubectl` and `sleep` faked on a scratch
PATH: no cluster is reached, no credential exists, and every path the script
writes stays inside `tmp_path`. It is the technique
`tests/consumer/test_gates_credential_provisioning.py` uses for the gates
wrapper, whose pull-on-rejection pattern this follows.

Work-item: livespec-dev-tooling-yj25uj. Plan: livespec `k3s-on-gmktec-for-vps-usage`
(epic livespec-sab5gn).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PATCH_SCRIPT = _K3S / "phase2" / "node-extended-resource" / "patch-node-churn-capacity.sh"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "node_status_credential"
_REFRESH_TOOL = _ROLE / "files" / "refresh-node-status-kubeconfig"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_BOOT_CONVERGE = _K3S / "phase2" / "reconstruct" / "converge-ci-stack.sh"
_CONVERGE_UNIT_DEFAULTS = (
    _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml"
)
_RBAC_TEMPLATE_NAME = "node-status-patch-rbac.yaml"
# The same template as a phase2-relative path, which is the form the
# `ci_converge_unit` role's installed-file set uses.
_RBAC_TEMPLATE_SOURCE = f"node-status-credential/{_RBAC_TEMPLATE_NAME}"
_NODE_STATUS_NAMESPACE = "ci-runner-node-status"

# The ONE path the two halves must agree on: the control-plane node renders each
# agent's credential into this DIRECTORY under this FILENAME shape, and that
# agent's refresh tool pulls from exactly there. A disagreement is a pull that
# fetches nothing — silently, because an empty fetch fails closed and leaves the
# stale file in place — so both spellings are asserted against these constants
# rather than against each other's text. Asserted as the two parts they are: each
# side composes the path from a variable (the render directory on one, the node
# name on both), so neither carries the whole thing as one literal.
_REMOTE_CREDENTIAL_DIR = "/etc/ci-runner"
_REMOTE_CREDENTIAL_PREFIX = "node-status-"
_REMOTE_CREDENTIAL_SUFFIX = ".kubeconfig"

# Kubernetes' own label for a control-plane node, used as its ABSENCE: the server
# authenticates as k3s's admin file and must never be handed a narrow credential
# of its own, so the re-mint selects every node that is not the control plane.
_NOT_CONTROL_PLANE = "'!node-role.kubernetes.io/control-plane'"
# The COMMITTED agent profile. Every value the patch script reads is that node's
# own data; only the credential path is redirected, because the committed value
# names a file on THAT node holding a cluster credential.
_AGENT_PROFILE = _K3S / "phase0-bare-metal" / "profiles" / "gmktec-xubuntu.env"
_AGENT_NODE = "gmktec-xubuntu"

# The API server's wording when it refuses a bearer token it has never seen, as
# `kubectl` renders it — quoted from the live 2026-10-12 failure.
_REJECTION = (
    "error: You must be logged in to the server "
    "(the server has asked for the client to provide credentials)"
)
# What a genuinely absent Node object answers instead. The control case: this one
# IS a late registration, and waiting is the right response to it.
_MISSING_NODE = f'Error from server (NotFound): nodes "{_AGENT_NODE}" not found'

# The one message the live defect printed for 25 minutes against a node that was
# registered the whole time. Its ABSENCE is the assertion.
_REGISTRATION_WAIT = "waiting for node"

# The script's own notices, quoted EXACTLY and case-sensitively. A lowercased
# substring check would be satisfied by the wrong thing: pytest names `tmp_path`
# after the test function, so every path this script prints carries the test's own
# name, and `"rejected" in output.lower()` passes inside
# `test_a_rejected_credential_...` no matter what the script said. Caught here
# while the Green of the rejection slice was being read.
_REJECTION_NOTICE = "REJECTED the node-status credential"
_REFRESH_FAILURE_NOTICE = "refresh FAILED"

# `kubectl`: log the argv, then answer the readiness probe from a scripted list
# of outcomes, one entry per probe. The verify read (`-o jsonpath=...`) and the
# patch always succeed — they are not what this suite scripts.
_KUBECTL_SHIM = """\
printf 'kubectl %s\\n' "$*" >> "$ARGV_LOG"
case " $* " in
  *" get --subresource=status node "*)
    case " $* " in *" -o "*) exit 0 ;; esac
    printf 'x' >> "$PROBES"
    probe="$(wc -c < "$PROBES" | tr -d ' ')"
    outcome="$(printf '%s' "$PROBE_OUTCOMES" | cut -d, -f"$probe")"
    outcome="${outcome:-$PROBE_DEFAULT}"
    case "$outcome" in
      ok) exit 0 ;;
      rejected) printf '%s\\n' "$REJECTION" >&2; exit 1 ;;
      *) printf '%s\\n' "$MISSING_NODE" >&2; exit 1 ;;
    esac ;;
esac
exit 0
"""

# `sleep`: logged, and shortened to a fifth of a second so the bounded
# registration wait costs almost no wall clock while still advancing `date`'s
# one-second clock. The wait's DURATION is not what is under test; what it
# decides to wait FOR is.
_SLEEP_SHIM = 'printf \'sleep %s\\n\' "$*" >> "$ARGV_LOG"\nexec /bin/sleep 0.2\n'

# The refresh tool, faked: it logs and exits with a scripted status. This suite
# asks whether the patch script REACHES it, once, and what it does with the
# answer — not what the tool itself does.
_REFRESH_FAKE = 'printf \'refresh %s\\n\' "$*" >> "$ARGV_LOG"\nexit "$REFRESH_EXIT"\n'


def _shim(*, bin_dir: Path, name: str, body: str) -> None:
    """One executable on the scratch PATH, standing in for a host tool."""
    path = bin_dir / name
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _run_patch(
    *,
    tmp_path: Path,
    probes: tuple[str, ...],
    probe_default: str = "missing",
    refresh_installed: bool = True,
    refresh_exit: int = 0,
) -> tuple[int, str, list[str]]:
    """Run the shipped patch script against a faked cluster; return code, output, argv.

    `probes` scripts the readiness probe one call at a time:
    `("rejected", "ok")` is a credential the API server refuses and then accepts,
    which is exactly a token re-minted by a control-plane boot and refreshed.
    `probe_default` answers every probe past the end of the list, so a run can be
    told to reject forever without the list deciding how many probes it takes.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    kubeconfig = tmp_path / "node-status-kubeconfig"
    _ = kubeconfig.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    _shim(bin_dir=bin_dir, name="kubectl", body=_KUBECTL_SHIM)
    _shim(bin_dir=bin_dir, name="sleep", body=_SLEEP_SHIM)
    refresh = tmp_path / "refresh-node-status-kubeconfig"
    if refresh_installed:
        _shim(bin_dir=tmp_path, name=refresh.name, body=_REFRESH_FAKE)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(
        {
            "ARGV_LOG": str(log),
            "PROBES": str(tmp_path / "probes"),
            "PROBE_OUTCOMES": ",".join(probes),
            "PROBE_DEFAULT": probe_default,
            "REJECTION": _REJECTION,
            "MISSING_NODE": _MISSING_NODE,
            "REFRESH_EXIT": str(refresh_exit),
            "NODE_STATUS_REFRESH_BIN": str(refresh),
            "KUBECONFIG": str(kubeconfig),
            # Long enough that the bounded wait takes several turns before giving
            # up, so the registration-wait line a late node earns is emitted on
            # every host rather than on a fast one: at 1s, `date`'s one-second
            # clock could tick between the deadline and the first check and the
            # script would give up before printing anything, which is a flake that
            # looks exactly like the defect under test. Short enough that the one
            # test taking this path does not wait on it; a rejected credential
            # leaves on its first probe and never reaches the deadline.
            "NODE_WAIT_TIMEOUT": "3",
        }
    )
    completed = subprocess.run(
        ["bash", str(_PATCH_SCRIPT), str(_AGENT_PROFILE)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def test_bash_is_available_to_run_the_shipped_patch_script() -> None:
    """The lens this suite reads the script through, named rather than assumed."""
    assert shutil.which("bash") is not None


def test_a_rejected_credential_is_reported_as_a_rejection_not_as_a_missing_node(
    *, tmp_path: Path
) -> None:
    """The 2026-10-12 defect, stated as the assertion that would have caught it.

    With no refresh tool installed the run still FAILS — a rejected credential is
    not something this script can patch through — but it must fail SAYING SO. The
    `waiting for node ... to register` line is asserted ABSENT because its
    presence is the whole defect: it sent an operator reading the journal after a
    reboot to look at node registration, which was healthy, instead of at the
    credential, which was not.
    """
    code, output, invoked = _run_patch(
        tmp_path=tmp_path, probes=("rejected",), probe_default="rejected", refresh_installed=False
    )

    assert code != 0
    assert _REJECTION_NOTICE in output
    assert _REGISTRATION_WAIT not in output
    assert [line.split(" ")[0] for line in invoked] == ["kubectl"]


def test_a_missing_node_is_still_waited_for(*, tmp_path: Path) -> None:
    """The control arm: late registration is real, and waiting is its right answer.

    At boot the reapply unit is ordered `After=k3s-agent.service`, but that unit
    reaching active does not mean the Node object is addressable yet. A change
    that reported THAT as a rejected credential would have traded one wrong
    diagnosis for another.
    """
    code, output, invoked = _run_patch(
        tmp_path=tmp_path, probes=("missing",), probe_default="missing", refresh_installed=False
    )

    assert code != 0
    assert _REGISTRATION_WAIT in output
    assert "refresh" not in [line.split(" ")[0] for line in invoked]


def test_a_rejected_credential_is_refreshed_once_and_the_patch_then_succeeds(
    *, tmp_path: Path
) -> None:
    """The pull-on-rejection path: no operator step stands between reboot and capacity.

    A poweredge reboot re-mints the credential cluster-side, so the agent's first
    probe after it is EXPECTED to be refused. Rather than have an operator notice
    and re-seed, the patch script re-fetches the credential once and retries — the
    shape `with-gates-kubeconfig` established for the VPS gates credential.

    The retry is asserted as the SECOND probe rather than by the exit code alone:
    a script that refreshed and did not retry would still exit zero if it reported
    the refresh's own status, which is the shape that looks healthy and advertises
    nothing.
    """
    code, _output, invoked = _run_patch(tmp_path=tmp_path, probes=("rejected", "ok"))

    verbs = [line.split(" ")[0] for line in invoked]

    assert code == 0
    assert verbs.count("refresh") == 1
    assert verbs.index("refresh") == 1
    assert any(
        line.startswith("kubectl patch node ") and "--subresource=status" in line
        for line in invoked
    )


def test_a_second_rejection_is_reported_as_itself(*, tmp_path: Path) -> None:
    """ONCE, deliberately — a refresh loop would hammer the control-plane node.

    One refresh tells the EXPECTED case (a token re-minted by a reboot) apart from
    the real one (the credential is revoked, or the RBAC changed). The second
    rejection stands, and the unit fails with it rather than retrying forever.
    """
    code, output, invoked = _run_patch(
        tmp_path=tmp_path, probes=("rejected",), probe_default="rejected"
    )

    assert code != 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "refresh", "kubectl"]
    assert _REGISTRATION_WAIT not in output


def test_a_refresh_that_cannot_fetch_leaves_the_rejection_standing(*, tmp_path: Path) -> None:
    """FAILS CLOSED. An unreachable control-plane node is never read as capacity set.

    The patch script's whole output is a node that advertises its capacity or a
    loud failure; a refresh that could not fetch must produce the second, naming
    the refresh rather than the node's registration.
    """
    code, output, invoked = _run_patch(
        tmp_path=tmp_path, probes=("rejected",), probe_default="rejected", refresh_exit=1
    )

    assert code != 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "refresh"]
    assert _REFRESH_FAILURE_NOTICE in output
    assert _REGISTRATION_WAIT not in output


# --- the refresh tool itself ----------------------------------------------

# `ssh` and `sudo` emit the fixture kubeconfig on stdout, standing in for the
# remote `sudo cat`: no host is contacted and no real credential is read.
_FETCH_SHIM = """\
printf '{name} %s\\n' "$*" >> "$ARGV_LOG"
printf '%s' "$FIXTURE_OUT"
exit 0
"""

# `id -u` answers FAKE_EUID so the root-only branch is reachable unprivileged;
# `chown` is logged rather than performed, because only root can give a file away
# and the OWNERSHIP claim is asserted on the argv the tool issues. The MODE is
# asserted on the real file, because chmod needs no privilege the writer lacks.
_ID_SHIM = '[ "${1:-}" = -u ] && printf \'%s\\n\' "$FAKE_EUID" && exit 0\nexec /usr/bin/id "$@"\n'
_CHOWN_SHIM = 'printf \'chown %s\\n\' "$*" >> "$ARGV_LOG"\nexit 0\n'

# A rendered node-status kubeconfig, carrying the two markers the refresh tool
# requires before it will overwrite anything. Its token is the word `fixture`;
# the string is invented here and lives nowhere else.
_FIXTURE_KUBECONFIG = (
    "apiVersion: v1\n"
    "kind: Config\n"
    "clusters:\n"
    "  - name: ci-runner\n"
    "    cluster:\n"
    "      server: https://poweredge-xubuntu.perch-rudd.ts.net:6443\n"
    f"users:\n  - name: node-status-patcher-{_AGENT_NODE}\n    user:\n      token: fixture\n"
)

_REMOTE_HOST = "poweredge-xubuntu"


def _run_refresh(
    *, tmp_path: Path, fetched: str = _FIXTURE_KUBECONFIG, already_there: str | None = None
) -> tuple[int, list[str], Path]:
    """Run the shipped refresh tool against a faked host; return code, argv, dest.

    `already_there` pre-creates the destination, which is the state the refresh is
    actually called in: the pull-on-rejection path reaches it precisely when the
    file is present and stale.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    dest = tmp_path / "node-status-kubeconfig"
    if already_there is not None:
        _ = dest.write_text(already_there, encoding="utf-8")
        dest.chmod(0o600)
    for name in ("ssh", "sudo"):
        _shim(bin_dir=bin_dir, name=name, body=_FETCH_SHIM.format(name=name))
    _shim(bin_dir=bin_dir, name="id", body=_ID_SHIM)
    _shim(bin_dir=bin_dir, name="chown", body=_CHOWN_SHIM)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(
        {
            "ARGV_LOG": str(log),
            "FAKE_EUID": "0",
            "FIXTURE_OUT": fetched,
            "NODE_STATUS_REFRESH_ENV": str(tmp_path / "absent.env"),
            "NODE_STATUS_NODE_NAME": _AGENT_NODE,
            "NODE_STATUS_REMOTE_HOST": _REMOTE_HOST,
            "NODE_STATUS_KUBECONFIG": str(dest),
        }
    )
    completed = subprocess.run(
        ["bash", str(_REFRESH_TOOL)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, invoked, dest


def test_the_refresh_tool_pulls_the_credential_from_the_control_plane_node(
    *, tmp_path: Path
) -> None:
    """A PULL, for the reason the gates tool pulls: it needs nothing new on the server.

    The remote command is a `sudo cat` of the node's own rendered credential and
    nothing else — the narrowest remote verb that can deliver it, and the one that
    cannot change cluster state even by mistake.
    """
    code, invoked, _dest = _run_refresh(tmp_path=tmp_path)

    fetches = [line for line in invoked if "ssh" in line]

    assert code == 0
    assert len(fetches) == 1
    assert _REMOTE_HOST in fetches[0]
    assert f"sudo cat /etc/ci-runner/node-status-{_AGENT_NODE}.kubeconfig" in fetches[0]


def test_the_refresh_tool_replaces_an_existing_credential_at_0600_root_owned(
    *, tmp_path: Path
) -> None:
    """The replacement carries the mode and ownership the seed and the role write.

    Asserted over an EXISTING destination because that is the case the refresh
    exists for. It is also where the uutils-coreutils trap lives
    (livespec-dev-tooling-74q6iw): `install` refuses a destination that already
    exists on Ubuntu 25.10+, so the write is a temp file and a rename, which is
    atomic and behaves the same under either coreutils.
    """
    code, invoked, dest = _run_refresh(
        tmp_path=tmp_path, already_there="stale: the credential a refresh must replace\n"
    )

    assert code == 0
    assert dest.read_text(encoding="utf-8") == _FIXTURE_KUBECONFIG
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600
    assert any(line.startswith("chown root:root ") for line in invoked)


def test_the_refresh_tool_refuses_to_overwrite_a_credential_with_a_non_kubeconfig(
    *, tmp_path: Path
) -> None:
    """A truthful-looking but malformed answer is worse than a failure.

    It would replace a good credential with a useless one, and the next rejection
    would then be unrecoverable rather than self-healing.
    """
    stale = "stale: still the best credential this node has\n"
    code, _invoked, dest = _run_refresh(
        tmp_path=tmp_path, fetched="poweredge-xubuntu: command not found\n", already_there=stale
    )

    assert code != 0
    assert dest.read_text(encoding="utf-8") == stale


# --- the chain that makes the repair unattended ---------------------------
#
# Read rather than applied, exactly as `tests/consumer/test_gates_credential_provisioning.py`
# reads its role. These are claims about what a CONVERGE does — which host
# re-mints the credential, where it lands, and which tool is installed to pull
# it — and applying them needs the VPS, the control-plane node, an agent and a
# real bearer token, and would still prove it of ONE pool rather than of every
# converge.


def _role_tasks() -> str:
    return _ROLE_TASKS.read_text(encoding="utf-8")


def _converge() -> str:
    return _BOOT_CONVERGE.read_text(encoding="utf-8")


def test_the_role_installs_the_refresh_tool_on_the_agent() -> None:
    """A repair path the agent does not carry is a repair path an operator performs.

    The tool is installed by the same role that delivers the credential, agent-only
    and executable, for the reason the `gates_kubeconfig` role installs
    `refresh-gates-kubeconfig` beside the credential it refreshes: the role owns
    the tool's INSTALLATION, not its behaviour.
    """
    tasks = _role_tasks()
    # Matched on `src:` rather than on the tool's name anywhere in the block: the
    # env-file task's own comment names the tool too (it says what reads it), so a
    # name-anywhere match finds two tasks and proves neither.
    installing = [
        block for block in tasks.split("\n    - name: ") if f"src: {_REFRESH_TOOL.name}" in block
    ]

    assert tasks.count("node_status_credential_cluster_role == 'agent'") == 1
    assert len(installing) == 1
    assert 'mode: "0755"' in installing[0]


def test_the_role_tells_the_refresh_tool_which_node_and_which_server_it_pulls_from() -> None:
    """Pool facts reach the shipped tool in an env-file, never baked into it.

    The node's name, the host that renders its credential, the path that render
    lands at and the path this node reads are all per-node or per-pool data — the
    same delivery the gates refresh tool's ssh identity takes. Baked into the
    script, a second pool node would need a second script.
    """
    tasks = _role_tasks()

    for variable in (
        "NODE_STATUS_NODE_NAME",
        "NODE_STATUS_REMOTE_HOST",
        "NODE_STATUS_REMOTE_KUBECONFIG",
        "NODE_STATUS_KUBECONFIG",
        "NODE_STATUS_SSH_USER",
    ):
        assert f"{variable}=" in tasks


def test_the_refresh_tool_and_the_role_name_the_same_control_plane_node() -> None:
    """An un-provisioned host must fail against the right name, not an empty string.

    The shipped script's fallback and the role's default are two spellings of one
    pool fact, and a disagreement would make a converged node and an
    un-provisioned one pull from different hosts.
    """
    shipped = re.search(
        r'^REMOTE_HOST="\$\{NODE_STATUS_REMOTE_HOST:-(?P<host>[^}"]+)\}"$',
        _REFRESH_TOOL.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    declared = re.search(
        r"^node_status_credential_server_host: (?P<host>\S+)$",
        _ROLE_DEFAULTS.read_text(encoding="utf-8"),
        re.MULTILINE,
    )

    assert shipped is not None
    assert declared is not None
    assert shipped["host"] == declared["host"]


def test_the_boot_converge_remints_every_agent_nodes_node_status_rbac() -> None:
    """The re-mint is the half no agent can perform, so the server does it at boot.

    A reboot empties the tmpfs datastore, so the per-node ServiceAccount and its
    token Secret are GONE — not stale. No credential the agent holds can recreate
    them, and that is deliberate (the grant cannot reach anything but one node's
    status). Until the boot converge re-applied this RBAC, an agent's refresh had
    nothing current to fetch and the repair needed an operator's `ansible-apply`.
    """
    converge = _converge()

    assert _RBAC_TEMPLATE_NAME in converge
    assert "NODE_NAME_PLACEHOLDER" in converge
    assert _NODE_STATUS_NAMESPACE in converge


def test_the_boot_converge_remints_for_agents_only_and_never_for_itself() -> None:
    """A server must not be handed a narrow credential beside its unrestricted one.

    It authenticates as k3s's own admin kubeconfig, so a per-node token for it
    would be a second long-lived credential on the machine that already holds the
    first — the refusal `seed-node-status-kubeconfig.sh` and the
    `node_status_credential` role both state, restated where the unattended path
    would otherwise quietly widen it.
    """
    assert _NOT_CONTROL_PLANE in _converge()


def test_the_boot_converge_renders_each_credential_where_its_agent_pulls_from() -> None:
    """The coupling that makes the pull work, asserted on both halves at once.

    The render's destination and the refresh tool's source are one path. If they
    drift the fetch returns nothing, the tool fails closed on a stale file, and the
    symptom is the ORIGINAL defect again — a node that never advertises capacity —
    with nothing naming the mismatch.
    """
    converge = _converge()
    shipped = _REFRESH_TOOL.read_text(encoding="utf-8")

    for half in (converge, shipped):
        assert _REMOTE_CREDENTIAL_DIR in half
        assert _REMOTE_CREDENTIAL_PREFIX in half
        assert _REMOTE_CREDENTIAL_SUFFIX in half


def test_the_ci_converge_unit_role_installs_the_node_status_rbac_template() -> None:
    """A manifest the boot converge applies but the role does not install is lost.

    The boot converge runs from `/usr/local/lib/ci-runner-k3s/` on the host, with
    no checkout present, so a template it reads relative to itself must be in the
    installed tree. This is the same invariant
    `test_ci_runner_k3s_boot_converge_reachability.py` holds for apply-bearing
    converge SCRIPTS; a template is reached by neither of its two walks.
    """
    defaults = _CONVERGE_UNIT_DEFAULTS.read_text(encoding="utf-8")

    assert f"- src: {_RBAC_TEMPLATE_SOURCE}" in defaults
    assert "  - node-status-credential\n" in defaults
