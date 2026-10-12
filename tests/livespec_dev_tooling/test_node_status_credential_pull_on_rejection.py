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
            # Long enough that the bounded wait takes a few turns before giving
            # up, so the registration-wait line a late node earns is actually
            # emitted; short enough that the suite does not wait on it.
            "NODE_WAIT_TIMEOUT": "1",
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
