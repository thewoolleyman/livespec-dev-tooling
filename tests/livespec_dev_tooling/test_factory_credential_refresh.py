"""The installed factory credential REPAIRS ITSELF after a control-plane reboot.

The third half of the factory credential, and the only one that runs with no
operator and no playbook: a rejected credential is re-fetched from the
control-plane node over this host's own tailnet ssh identity and replaced
root-owned, readable by the configured group only.

WHY THE SHIPPED SCRIPTS ARE RUN FOR REAL rather than read. Their claims are
claims about CONTROL FLOW and about FILE OUTCOMES — recognise the API server's
rejection, refresh exactly once through `sudo -n`, retry the command once;
fetch under a named identity and leave a file with a specific owner, group and
mode. Reading shell cannot establish either. So the committed scripts run, with
`id`, `sudo`, `ssh`, `chown` and the wrapped command itself faked on a scratch
PATH: no host is contacted, no cluster is reached, no credential exists, and
every path written stays inside `tmp_path`. This is the technique
`tests/consumer/test_gates_credential_provisioning.py` uses on the sibling
gates tools, and the committed
`ci-runner/k3s/phase2/gates/refresh-gates-kubeconfig-exit-tests.sh` before it.

THE ONE THING FAKED FOR NECESSITY RATHER THAN SAFETY IS `chown`. Only root can
give a file away, and the factory-client group is a provisioned pool fact that
exists on no developer machine and in no CI container — so a real chown would
fail for one of two reasons on every host this suite runs on. Ownership is
therefore asserted on the argv the tool issues; the MODE is asserted on the
real file, because chmod needs no privilege the writer lacks.

THE POOL FACTS ARRIVE THE WAY THE ROLE DELIVERS THEM. Neither script carries a
hostname, an account or a group default, so the tests write the same env-file
`factory_kubeconfig` installs and let the scripts read it. That makes the
delivery mechanism part of what is proven rather than something the tests work
around — and it is why the refusal arm below is possible at all.

Work-item: `livespec-dev-tooling-sqobqv`. Plan: livespec
`factory-worker-nodes-gitops`, epic `livespec-sqvj7p`.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "factory_kubeconfig"
_WRAPPER = _ROLE / "files" / "with-factory-kubeconfig"
_REFRESH = _ROLE / "files" / "refresh-factory-kubeconfig"

# The pool facts the role writes into its env-file, as this suite's stand-ins.
# The control-plane node is a FIXTURE NAME, never the fleet's real one: these
# scripts must work against whatever the inventory resolves, and a test naming
# the live machine would pass for the wrong reason the day it moves.
_REMOTE_HOST = "control-plane.fixture.invalid"
_SSH_USER = "fixture-login"
_GROUP = "factory-client"

# The credential's shape, which is the Definition of Done's own: root-owned,
# readable by the configured group, and by nobody else.
_CREDENTIAL_MODE = 0o640

# A syntactically-valid stand-in kubeconfig carrying the two markers the refresh
# tool requires before it will overwrite anything. Never a real credential.
_FIXTURE_KUBECONFIG = "kind: Config\napiVersion: v1\nclusters:\n- cluster:\n    server: https://h\n"

# The API server's rejection, as `kubectl` renders it for a read.
_REJECTION = "error: You must be logged in to the server (Unauthorized)"

# The message the API SERVER itself attaches to an unauthenticated response,
# carrying none of the words the rendering above does: no `Unauthorized`, no
# `401`, no "You must be logged in". The rendering below is built FROM it rather
# than spelled out, because that is the whole point — one refusal, and it is the
# message rather than any one framing of it that a refresh answers.
_SERVER_WORDING = "the server has asked for the client to provide credentials"

# How the same refusal reaches `create`, which is the verb a sandbox launch
# submits its pod with. It validates the manifest before sending it, which needs
# the server's OpenAPI document — so the credential is refused during that
# DOWNLOAD and the failure arrives dressed as a schema-validation error, with
# the server's wording buried mid-line and the words every naive pattern keys on
# absent. Measured on the sibling gates path 2026-10-12.
_REJECTION_OPENAPI = (
    'error validating "STDIN": error validating data: failed to download openapi: '
    + _SERVER_WORDING
)

# A stand-in for the pod manifest the sandbox backend pipes to `kubectl create
# --filename -`. Its CONTENT is irrelevant and its DELIVERY is the whole point:
# it arrives on stdin, and stdin is a pipe that can be read exactly once.
_FIXTURE_MANIFEST = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: sandbox-fixture\n"


def _fake(*, bin_dir: Path, name: str, body: str) -> None:
    """One executable on the scratch PATH, standing in for a host tool."""
    fake = bin_dir / name
    _ = fake.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    fake.chmod(0o755)


def _scratch_path(*, tmp_path: Path) -> Path:
    """A PATH directory the fakes below take precedence from."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    return bin_dir


def _env_file(*, tmp_path: Path, facts: dict[str, str] | None = None) -> Path:
    """The pool-fact env-file the `factory_kubeconfig` role installs.

    Written in the role's own shape — `KEY=value` lines, no quoting, no secret —
    so the scripts are exercised against the delivery they actually get. Pass
    `facts` to omit or change one, which is how the refusal arm stages an
    un-provisioned host.
    """
    written = (
        {
            "FACTORY_REMOTE_HOST": _REMOTE_HOST,
            "FACTORY_REMOTE_KUBECONFIG": "/etc/ci-runner/factory.kubeconfig",
            "FACTORY_SSH_USER": _SSH_USER,
            "FACTORY_GROUP": _GROUP,
        }
        if facts is None
        else facts
    )
    path = tmp_path / "factory-refresh.env"
    _ = path.write_text(
        "".join(f"{key}={value}\n" for key, value in written.items()), encoding="utf-8"
    )
    return path


def _env_with(*, bin_dir: Path, extra: dict[str, str]) -> dict[str, str]:
    """This process's environment with the scratch PATH first and `extra` applied.

    `COVERAGE_PROCESS_START` and `COV_CORE_*` are scrubbed so a shell child
    cannot self-instrument and race the concurrent coverage runs the parallel
    dispatcher starts — the same scrub the other subprocess-driving tests do.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(extra)
    return env


def _run_refresh(
    *,
    tmp_path: Path,
    euid: str,
    already_there: str | None = None,
    facts: dict[str, str] | None = None,
) -> tuple[int, list[str], Path]:
    """Run the shipped refresh tool against a faked host; return code, argv, dest.

    `ssh` and `sudo` emit the fixture kubeconfig on stdout, standing in for the
    remote `sudo cat`: no host is contacted and no real credential exists. The
    WRITE is real and lands inside `tmp_path`, which is what lets the mode be
    asserted on the file rather than on an argv.

    `already_there` pre-creates the destination, which is the state the refresh
    is actually called in: the pull-on-rejection path reaches it precisely when
    the file is present and stale.
    """
    bin_dir = _scratch_path(tmp_path=tmp_path)
    log = tmp_path / "argv.log"
    dest = tmp_path / "factory.kubeconfig"
    if already_there is not None:
        _ = dest.write_text(already_there, encoding="utf-8")
        dest.chmod(0o600)
    _fake(bin_dir=bin_dir, name="id", body='[ "${1:-}" = -u ] && printf "%s\\n" "${FAKE_EUID}"\n')
    for name in ("ssh", "sudo"):
        _fake(
            bin_dir=bin_dir,
            name=name,
            body=(
                f'printf "{name} %s\\n" "$*" >> "${{ARGV_LOG}}"\n'
                'printf "%s" "${FIXTURE_OUT}"\nexit 0\n'
            ),
        )
    _fake(
        bin_dir=bin_dir, name="chown", body='printf "chown %s\\n" "$*" >> "${ARGV_LOG}"\nexit 0\n'
    )
    completed = subprocess.run(
        ["bash", str(_REFRESH)],
        cwd=str(tmp_path),
        env=_env_with(
            bin_dir=bin_dir,
            extra={
                "ARGV_LOG": str(log),
                "FAKE_EUID": euid,
                "FIXTURE_OUT": _FIXTURE_KUBECONFIG,
                "FACTORY_REFRESH_ENV": str(_env_file(tmp_path=tmp_path, facts=facts)),
                "FACTORY_KUBECONFIG": str(dest),
            },
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, invoked, dest


def test_a_rejected_credential_is_refetched_over_this_hosts_tailnet_ssh_identity(
    *, tmp_path: Path
) -> None:
    """The fetch runs as the CONFIGURED account, not as root — root holds no identity.

    This is the Definition of Done's own sentence, split into its two verifiable
    halves; this is the first. The ssh key that reaches the control-plane node
    over the tailnet belongs to a login user, so an `ssh <node>` issued as root
    fails to authenticate (measured live on the sibling gates path, 2026-09-10).
    But the write lands under `/etc` and needs root. So ONLY the fetch drops to
    the configured account via `sudo -u … -H`, which is what gives ssh that
    account's HOME and therefore its `~/.ssh`.

    Asserted on the ARGV rather than on a successful login, because the claim is
    WHICH IDENTITY is used — and the account is a pool fact read from the
    role's env-file, so a script that ignored the file and reached for a default
    would fetch as the wrong user on exactly the host this credential exists
    for.
    """
    code, invoked, _dest = _run_refresh(
        tmp_path=tmp_path, euid="0", already_there="stale: the credential a refresh must replace\n"
    )
    fetches = [line for line in invoked if line.startswith("sudo ")]

    assert code == 0
    assert fetches, "the refresh must fetch; nothing reached ssh at all"
    assert f"-u {_SSH_USER} " in fetches[0], (
        "the fetch must run as the account the role's env-file names: root on a "
        "factory host has no tailnet ssh identity, and the fleet's usual `ubuntu` is "
        "rejected by the tailnet ACL on the host that runs today's Fabro servers"
    )
    assert "-H " in fetches[0], (
        "`sudo -u` without `-H` leaves HOME as root's, so ssh looks for the key in "
        "/root/.ssh and finds nothing — a fetch that fails for a reason the log does "
        "not name"
    )
    assert f" {_REMOTE_HOST} " in fetches[0], (
        "the fetch must reach the control-plane node the env-file names, which the "
        "role resolves from the inventory rather than baking into the script"
    )


def test_a_refresh_over_an_existing_credential_lands_root_owned_and_group_readable_only(
    *, tmp_path: Path
) -> None:
    """The second half: root-owned, readable by the configured group, by nobody else.

    Asserted over an EXISTING destination because that is the case the refresh
    exists for — the pull-on-rejection path calls it precisely when the file is
    there and stale. A refresh that left the replacement root-only would silently
    un-provision the host it had just repaired: a valid credential nobody who
    launches can read, and a next launch that fails with nothing on the host
    stating why. World-readable is the other direction and is worse, on a machine
    that also runs untrusted sandbox workloads.

    The MODE is read off the real file; the OWNER off the argv, because only root
    can give a file away and the group is a provisioned fact no test host has.
    """
    code, invoked, dest = _run_refresh(
        tmp_path=tmp_path, euid="0", already_there="stale: the credential a refresh must replace\n"
    )

    assert code == 0
    assert dest.read_text(encoding="utf-8") == _FIXTURE_KUBECONFIG
    assert stat.S_IMODE(dest.stat().st_mode) == _CREDENTIAL_MODE
    assert not stat.S_IMODE(dest.stat().st_mode) & stat.S_IROTH, (
        "the credential is a bearer token for the whole factory namespace on a host "
        "that runs untrusted sandbox workloads; it is never world-readable"
    )
    assert [line for line in invoked if line.startswith(f"chown root:{_GROUP} ")], (
        "the replacement must be given to root and the configured reader group, from "
        "the role's own fact — a group spelled inside the script would diverge from "
        "the group the converge actually created"
    )
    # The temp file the write renamed over the destination is gone: a 0600
    # stand-in left beside a credential is litter, and one left group-readable
    # would be the exposure the rename shape exists to prevent.
    assert not list(dest.parent.glob(f"{dest.name}.refresh.*"))


def test_a_refresh_onto_a_fresh_host_lands_the_same_shape(*, tmp_path: Path) -> None:
    """The first install and every repair after it leave the same file.

    Two shapes rather than one because the pair is where the sibling's last
    defect lived: uutils' `install` succeeded on an absent destination and failed
    on an existing one, so the first refresh worked and every refresh after it
    did not — a credential that cannot self-heal, which is the one thing this
    tool exists to do (livespec-dev-tooling-74q6iw).
    """
    code, invoked, dest = _run_refresh(tmp_path=tmp_path, euid="0")

    assert code == 0
    assert stat.S_IMODE(dest.stat().st_mode) == _CREDENTIAL_MODE
    assert [line for line in invoked if line.startswith(f"chown root:{_GROUP} ")]


def test_an_unprovisioned_host_refuses_rather_than_guessing_a_control_plane_node(
    *, tmp_path: Path
) -> None:
    """With no pool facts the refresh fails CLOSED, and says what to run.

    The script carries NO hostname default, deliberately: a default would be a
    second, silent place a machine binding lives — the posture
    livespec-dev-tooling-prdxxe ratified — and it would be a WRONG one the moment
    the pool's server moves, arriving as an unexplained ssh timeout on a host
    nobody is watching. So an un-provisioned host must refuse loudly and leave
    the existing credential alone, rather than reach for a machine that may no
    longer be the cluster's server.
    """
    stale = "stale: the credential a failed refresh must not touch\n"
    code, invoked, dest = _run_refresh(tmp_path=tmp_path, euid="0", already_there=stale, facts={})

    assert code != 0
    assert not invoked, "nothing may be fetched without knowing which node to fetch from"
    assert dest.read_text(encoding="utf-8") == stale, (
        "a refresh that cannot proceed must leave the existing credential untouched; "
        "overwriting a good file with nothing is worse than failing"
    )


def _run_wrapper(
    *,
    tmp_path: Path,
    euid: str,
    command_exits: tuple[int, ...],
    rejection: str = _REJECTION,
    verb: tuple[str, ...] = ("get", "pods"),
    stdin: str = "",
) -> tuple[int, list[str], list[str]]:
    """Run the shipped wrapper against a faked host; return code, argv, manifests.

    `command_exits` scripts the WRAPPED command one call at a time: `(1, 0)` is a
    credential the API server rejects and then accepts, which is exactly a token
    recreated by a control-plane boot and then refreshed. The rejection is
    written to the command's STDERR, because that is where the wrapper
    recognises it.

    `stdin` is piped to the wrapper, and the fake kubectl READS IT when the argv
    names stdin as an input (`-`), exactly as the real one does for
    `--filename -`. A fake that ignored stdin would report a retry as healthy
    whether or not the retried command could still see the manifest, which is
    the submit a sandbox launch depends on.

    The refresh itself is NOT the subject here, so it is a fake that logs and
    succeeds: these arms are about whether the wrapper reaches it, and how.
    """
    bin_dir = _scratch_path(tmp_path=tmp_path)
    log = tmp_path / "argv.log"
    attempts = tmp_path / "attempts"
    _ = attempts.write_text("", encoding="utf-8")
    stdin_dir = tmp_path / "stdin"
    stdin_dir.mkdir()
    _fake(bin_dir=bin_dir, name="id", body='[ "${1:-}" = -u ] && printf "%s\\n" "${FAKE_EUID}"\n')
    _fake(bin_dir=bin_dir, name="sudo", body='printf "sudo %s\\n" "$*" >> "${ARGV_LOG}"\nexit 0\n')
    _fake(
        bin_dir=bin_dir,
        name="kubectl",
        body=(
            'printf "kubectl %s\\n" "$*" >> "${ARGV_LOG}"\n'
            'printf "x" >> "${ATTEMPTS}"\n'
            'attempt="$(wc -c < "${ATTEMPTS}" | tr -d " ")"\n'
            'case " $* " in *" - "*) cat > "${STDIN_DIR}/${attempt}" ;; esac\n'
            'code="$(printf "%s" "${COMMAND_EXITS}" | cut -d, -f"${attempt}")"\n'
            '[ "${code}" = 0 ] || printf "%s\\n" "${REJECTION}" >&2\n'
            'exit "${code}"\n'
        ),
    )
    refresh = tmp_path / "refresh-factory-kubeconfig"
    _ = refresh.write_text(
        '#!/usr/bin/env bash\nprintf "refresh %s\\n" "$*" >> "${ARGV_LOG}"\nexit 0\n',
        encoding="utf-8",
    )
    refresh.chmod(0o755)
    completed = subprocess.run(
        ["bash", str(_WRAPPER), "kubectl", "--namespace", "factory", *verb],
        cwd=str(tmp_path),
        env=_env_with(
            bin_dir=bin_dir,
            extra={
                "ARGV_LOG": str(log),
                "ATTEMPTS": str(attempts),
                "STDIN_DIR": str(stdin_dir),
                "COMMAND_EXITS": ",".join(str(code) for code in command_exits),
                "REJECTION": rejection,
                "FAKE_EUID": euid,
                "FACTORY_REFRESH_BIN": str(refresh),
                "FACTORY_KUBECONFIG": str(tmp_path / "factory.kubeconfig"),
            },
        ),
        # `input` rather than an inherited fd, so stdin is a pipe that reaches
        # EOF on every arm: a wrapper handed the suite runner's own stdin would
        # be read against whatever that happened to be.
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    manifests = [
        path.read_text(encoding="utf-8")
        for path in sorted(stdin_dir.iterdir(), key=lambda path: int(path.name))
    ]
    return completed.returncode, invoked, manifests


def test_the_first_use_after_a_control_plane_reboot_refreshes_once_and_retries(
    *, tmp_path: Path
) -> None:
    """The pull-on-rejection path, from a NON-ROOT caller — which is every launch.

    The Fabro server runs as the host's service account, not as root, and the
    credential it refreshes lives under `/etc`. `sudo -n` is how the write
    happens; NON-interactive because a sandbox launch has no terminal to answer
    a password prompt at, so a plain `sudo` would hang the launch instead of
    failing it.

    ONCE, and the retry is asserted as the second `kubectl` rather than as the
    wrapper's exit code alone: a wrapper that refreshed and did not retry would
    still exit zero here if it reported the refresh's own status, which is the
    shape that looks healthy and repairs nothing.
    """
    code, invoked, _manifests = _run_wrapper(tmp_path=tmp_path, euid="1000", command_exits=(1, 0))

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
    assert invoked[1].startswith("sudo -n ")
    assert invoked[1].endswith("refresh-factory-kubeconfig")


def test_a_refusal_dressed_as_a_schema_error_still_refreshes_and_resubmits_the_manifest(
    *, tmp_path: Path
) -> None:
    """The refusal recognised by the MESSAGE, and the retry carrying the POD manifest.

    Two defects in one arm, because a sandbox launch meets both at once. `create`
    validates before it sends, so a refused credential arrives as a failed
    OpenAPI download inside a validation error about `"STDIN"` — carrying no
    `Unauthorized`, no `401` and no "You must be logged in", which is how the
    sibling gates wrapper read a credential refusal as a malformed manifest on
    2026-10-12 and refreshed nothing.

    And the manifest arrives on stdin, ONCE: the rejected first attempt drains
    that pipe, so a retry that merely re-runs the same argv reads EOF and dies
    with `error: no objects passed to create`. The credential would be refreshed
    and the pod would STILL not have been created — which is why both attempts
    are asserted to have received the same bytes. An argv-only assertion passes
    against a wrapper that resubmits nothing.
    """
    code, invoked, manifests = _run_wrapper(
        tmp_path=tmp_path,
        euid="1000",
        command_exits=(1, 0),
        rejection=_REJECTION_OPENAPI,
        verb=("create", "--filename", "-"),
        stdin=_FIXTURE_MANIFEST,
    )

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
    assert manifests == [_FIXTURE_MANIFEST, _FIXTURE_MANIFEST]


def test_a_root_caller_refreshes_without_sudo(*, tmp_path: Path) -> None:
    """The control arm for the `sudo -n` one: the CALLER's identity selects it.

    A wrapper that always reached for `sudo` would make a root caller depend on a
    sudoers rule it does not need, and a wrapper that never did would make the
    service account's launch hang on a prompt. It is the identity, not a flag.
    """
    code, invoked, _manifests = _run_wrapper(tmp_path=tmp_path, euid="0", command_exits=(1, 0))

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "refresh", "kubectl"]


def test_a_command_the_server_accepts_is_never_refreshed(*, tmp_path: Path) -> None:
    """A credential refresh is the right response to ONE failure, not to any failure."""
    code, invoked, _manifests = _run_wrapper(tmp_path=tmp_path, euid="1000", command_exits=(0,))

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl"]


def test_a_second_rejection_is_reported_as_itself(*, tmp_path: Path) -> None:
    """One refresh distinguishes a stale token from a revoked one; it never loops.

    A retry loop would turn a genuinely revoked credential into an unbounded ssh
    hammer against the control-plane node, so the second rejection stands and the
    caller reads a non-zero exit as a launch that did not happen — which is the
    honest answer, rather than a pod the backend believes it created.
    """
    code, invoked, _manifests = _run_wrapper(tmp_path=tmp_path, euid="1000", command_exits=(1, 1))

    assert code != 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
