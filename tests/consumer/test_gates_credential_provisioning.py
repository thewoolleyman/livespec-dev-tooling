"""Consumer-tier: the gates credential's INSTALLATION and REFRESH, from the shipped bytes.

This is the `## Delegated pre-push gate` section's last two bullets —
"Credential use" and "Credential installation" — asserted where they live: the
`gates_kubeconfig` role that installs the credential, and the two runtime tools
it ships beside it.

WHY THE ROLE IS READ RATHER THAN APPLIED. Its claims are claims about what a
converge DOES — the owner, the group and the mode the credential lands with, and
the group the login user is put in. Applying it needs the VPS, the control-plane
node and a real bearer token, and would still prove it of ONE host rather than of
every converge. So the committed tasks are read, exactly as the sibling
`test_docker_sandbox_slice_scenario` reads its role, text-sliced because no YAML
library is importable here (this package is dependency-free by contract).

WHY THE WRAPPER IS RUN FOR REAL, with fakes on its own PATH. Its claim is a claim
about CONTROL FLOW — recognise the API server's rejection, refresh ONCE through
`sudo -n`, retry the command once — and reading a shell script cannot establish
that. So the shipped script runs, with `id`, `sudo` and the wrapped command
itself faked on a scratch PATH: no cluster is reached, no credential exists, and
every path stays inside `tmp_path`. The same technique the committed
`refresh-gates-kubeconfig-exit-tests.sh` uses, in the suite the aggregate
actually runs.

THE ONE THING FAKED FOR NECESSITY RATHER THAN SAFETY IS `chown`. Only root can
give a file away, and the gate-client group is a provisioned pool fact that
exists on no developer machine and in no CI container — so a real chown would
fail for one of two reasons on every host this suite runs on. Ownership is
therefore asserted on the argv the tool issues; the MODE is asserted on the real
file, because chmod needs no privilege the writer lacks.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "gates_kubeconfig"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_WRAPPER = _ROLE / "files" / "with-gates-kubeconfig"
_REFRESH = _ROLE / "files" / "refresh-gates-kubeconfig"

# The Definition of Done's own values, stated because it states them: the
# credential is root-owned, readable by a declared gate-client group, at 0640.
_CREDENTIAL_MODE = "0640"
_CREDENTIAL_OWNER = "root"
_GROUP_VARIABLE = "gates_kubeconfig_group"
_LOGIN_USER_VARIABLE = "gates_kubeconfig_ssh_user"

# A syntactically-valid stand-in kubeconfig carrying the two markers the refresh
# tool requires before it will overwrite anything. Never a real credential.
_FIXTURE_KUBECONFIG = "kind: Config\napiVersion: v1\nclusters:\n- cluster:\n    server: https://h\n"

# The API server's rejection, as `kubectl` renders it — the one failure a
# credential refresh is the right response to.
_REJECTION = "error: You must be logged in to the server (Unauthorized)"

# The message the API SERVER itself attaches to an unauthenticated response,
# carrying none of the words the rendering above does: no `Unauthorized`, no
# `401`, no "You must be logged in". The two renderings below are built FROM it
# rather than spelled out, because that is the whole point — one refusal, and it
# is the message rather than any one framing of it that a refresh answers.
_SERVER_WORDING = "the server has asked for the client to provide credentials"

# How a refused credential reaches a caller that only READ from the cluster.
_REJECTION_SERVER_WORDING = f"error: {_SERVER_WORDING}"

# How the same refusal reaches `apply` and `create`, and the text MEASURED on
# 2026-10-12 (gate run 20261012T050516Z-1838408). Both verbs validate the
# manifest before sending it, which needs the server's OpenAPI document — so the
# credential is refused during that DOWNLOAD and the failure arrives dressed as a
# schema-validation error, with the server's wording buried mid-line and the
# words every earlier pattern keyed on absent.
_REJECTION_OPENAPI = (
    'error validating "STDIN": error validating data: failed to download openapi: '
    + _SERVER_WORDING
)

# A stand-in for the Job manifest the gate client pipes to `kubectl create
# --filename -`. Its CONTENT is irrelevant and its DELIVERY is the whole point:
# it arrives on stdin, and stdin is a pipe that can be read exactly once.
_FIXTURE_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: gate-fixture\n"


# --- reading the committed role -------------------------------------------


def _tasks() -> list[tuple[str, str]]:
    """Every top-level task of the role, as `(name, body)` in file order."""
    text = _TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{_TASKS} must declare its tasks as column-zero `- name:` entries; this "
        f"reader cannot see a task it cannot find, and an unseen task is a "
        f"credential this test has stopped checking"
    )
    return [
        (text[start:stop].split("\n", 1)[0][len("- name: ") :].strip(), text[start:stop])
        for start, stop in pairwise([*openings, len(text)])
    ]


def _task_declaring(*, key: str, value: str) -> str:
    """The one task whose body declares `key: value` — e.g. the credential's dest."""
    matching = [body for _name, body in _tasks() if f"{key}: {value}" in body]
    assert len(matching) == 1, (
        f"the role must carry exactly one task declaring `{key}: {value}`; found "
        f"{len(matching)}, so this test is reading the wrong one or none at all"
    )
    return matching[0]


def _role_default(*, name: str) -> str:
    """One scalar the role's `defaults/main.yml` declares."""
    found = re.search(
        rf"^{name}: (?P<value>\S+)$", _DEFAULTS.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert found is not None, (
        f"the role must declare `{name}` in defaults/main.yml: the credential's "
        f"group is a pool fact, and a group spelled inline in a task is not one"
    )
    return found["value"]


def test_the_role_installs_the_credential_root_owned_and_gate_client_group_readable() -> None:
    """The credential's owner, group and mode, read out of the task that writes it.

    Root-only is what shipped first, and it made the credential unusable from the
    VPS: pushes run as the login user, not as root, so the gate client could not
    read the file it was supposed to authenticate with. World-readable is the
    other direction and is worse — the file is a bearer token for the gates
    namespace. 0640 with a dedicated group is the only shape that is both
    readable by whoever pushes and writable by nobody but root.
    """
    install = _task_declaring(key="dest", value='"{{ gates_kubeconfig_dest }}"')

    assert f"owner: {_CREDENTIAL_OWNER}" in install
    assert f'group: "{{{{ {_GROUP_VARIABLE} }}}}"' in install
    assert f'mode: "{_CREDENTIAL_MODE}"' in install
    assert "no_log: true" in install


def test_the_role_declares_the_gate_client_group_and_creates_it() -> None:
    """A group the role names and does not create is a converge that fails on apply."""
    group = _role_default(name=_GROUP_VARIABLE)
    creating = [body for _name, body in _tasks() if "ansible.builtin.group:" in body]

    assert group == "gates-client"
    assert len(creating) == 1
    assert f'name: "{{{{ {_GROUP_VARIABLE} }}}}"' in creating[0]
    assert "state: present" in creating[0]


def test_the_role_puts_the_login_user_in_the_gate_client_group() -> None:
    """The group is only a credential path if the account that PUSHES is in it.

    `append: true` is asserted because its absence is the silent catastrophe: a
    bare `groups:` REPLACES the user's group set, which on an Ubuntu cloud image
    removes `sudo` — and `sudo` is what the refresh itself runs through, so the
    converge would break the repair path it just installed.
    """
    membership = [body for _name, body in _tasks() if "ansible.builtin.user:" in body]

    assert len(membership) == 1
    assert f'name: "{{{{ {_LOGIN_USER_VARIABLE} }}}}"' in membership[0]
    assert f'groups: "{{{{ {_GROUP_VARIABLE} }}}}"' in membership[0]
    assert "append: true" in membership[0]


def test_the_refresh_tool_is_told_the_group_the_role_installed() -> None:
    """The runtime tool reproduces the role's ownership, from the role's own fact.

    The group reaches the shipped script through the env-file rather than being
    baked into it, which is the same delivery the ssh identity uses — and it has
    to agree with the default the script falls back to, or an un-provisioned host
    and a converged one would write different ownership.
    """
    env_file = _task_declaring(key="dest", value='"{{ gates_kubeconfig_ssh_env }}"')
    shipped_default = re.search(
        r'^GATES_GROUP="\$\{GATES_GROUP:-(?P<group>[^}"]+)\}"$',
        _REFRESH.read_text(encoding="utf-8"),
        re.MULTILINE,
    )

    assert f"GATES_GROUP={{{{ {_GROUP_VARIABLE} }}}}" in env_file
    assert shipped_default is not None
    assert shipped_default["group"] == _role_default(name=_GROUP_VARIABLE)


# --- running the committed runtime tools ----------------------------------


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


def _run_wrapper(
    *,
    tmp_path: Path,
    euid: str,
    command_exits: tuple[int, ...],
    rejection: str = _REJECTION,
    verb: tuple[str, ...] = ("get", "jobs"),
    capture_lag: str | None = None,
    stdin: str = "",
) -> tuple[int, list[str]]:
    """Run the shipped wrapper against a faked host; return its code and every argv.

    `command_exits` scripts the WRAPPED command one call at a time: `(1, 0)` is a
    credential the API server rejects and then accepts, which is exactly a token
    recreated by a control-plane boot and refreshed. The rejection is written to
    the command's STDERR, because that is where the wrapper recognises it.

    `rejection` and `verb` are parameters rather than constants because kubectl
    renders ONE refused credential in several different texts, and which text a
    caller meets depends on the verb it ran: the arms below pin the real ones.

    `stdin` is piped to the wrapper, and the fake kubectl READS IT when the argv
    names stdin as an input (`-`), exactly as the real one does for
    `--filename -` — recording what each attempt received under `stdin/`. A fake
    that ignored stdin would report a retry as healthy whether or not the retried
    command could still see the manifest, which is the submit the gate depends on.

    `capture_lag` puts a `tee` on the scratch PATH that is SLOW TO START, which
    is a LENS rather than a fake — the same technique the sibling refresh suite
    uses on `install`. It does nothing a real `tee` may not do; it only removes
    the wrapper's luck. The wrapper has to READ what `tee` captured before it can
    recognise a rejection, so a capture the wrapper never waited for is a
    rejection it cannot see — a defect that is invisible on an idle host and
    fires under load, which is where the gate actually runs.
    """
    bin_dir = _scratch_path(tmp_path=tmp_path)
    log = tmp_path / "argv.log"
    attempts = tmp_path / "attempts"
    _ = attempts.write_text("", encoding="utf-8")
    stdin_dir = tmp_path / "stdin"
    stdin_dir.mkdir()
    _fake(bin_dir=bin_dir, name="id", body='[ "${1:-}" = -u ] && printf "%s\\n" "${FAKE_EUID}"\n')
    _fake(
        bin_dir=bin_dir,
        name="sudo",
        body='printf "sudo %s\\n" "$*" >> "${ARGV_LOG}"\nexit 0\n',
    )
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
    if capture_lag is not None:
        _fake(
            bin_dir=bin_dir,
            name="tee",
            body=(
                'sleep "${TEE_LAG}"\n'
                'captured="$(cat)"\n'
                'printf "%s\\n" "${captured}" > "$1"\n'
                'printf "%s\\n" "${captured}"\n'
            ),
        )
    # The refresh itself is NOT the subject here, so it is a fake that logs and
    # succeeds: this test is about whether the wrapper reaches it, and how.
    refresh = tmp_path / "refresh-gates-kubeconfig"
    _ = refresh.write_text(
        '#!/usr/bin/env bash\nprintf "refresh %s\\n" "$*" >> "${ARGV_LOG}"\nexit 0\n',
        encoding="utf-8",
    )
    refresh.chmod(0o755)
    completed = subprocess.run(
        ["bash", str(_WRAPPER), "kubectl", "--namespace", "gates", *verb],
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
                "TEE_LAG": capture_lag or "0",
                "GATES_REFRESH_BIN": str(refresh),
                "GATES_KUBECONFIG": str(tmp_path / "gates.kubeconfig"),
            },
        ),
        # `input` rather than an inherited fd, so stdin is a pipe that reaches EOF
        # on every arm: a wrapper handed the suite runner's own stdin would be
        # read against whatever that happened to be, which is the kind of luck
        # this file's other arms were written to remove.
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, invoked


def _manifests_seen(*, tmp_path: Path) -> list[str]:
    """What each attempt of the wrapped command actually read from stdin, in order."""
    return [
        path.read_text(encoding="utf-8")
        for path in sorted((tmp_path / "stdin").iterdir(), key=lambda path: int(path.name))
    ]


def test_a_rejected_credential_is_refreshed_once_through_sudo_and_the_command_retried(
    *, tmp_path: Path
) -> None:
    """The pull-on-401 path, from a NON-ROOT caller — which is every delegated push.

    The gate client runs as the pushing user, and the credential it refreshes
    lives under `/etc`. `sudo -n` is how the write happens; NON-interactive
    because a pre-push hook has no terminal to answer a password prompt at, so a
    plain `sudo` would hang the push instead of failing it.

    ONCE, and the retry is asserted as the second `kubectl` rather than as the
    wrapper's exit code alone: a wrapper that refreshed and did not retry would
    still exit zero here if it reported the refresh's own status, which is the
    shape that looks healthy and gates nothing.
    """
    code, invoked = _run_wrapper(tmp_path=tmp_path, euid="1000", command_exits=(1, 0))

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
    assert invoked[1].startswith("sudo -n ")
    assert invoked[1].endswith("refresh-gates-kubeconfig")


def test_the_servers_own_credential_wording_is_refreshed_once_and_retried(
    *, tmp_path: Path
) -> None:
    """The refusal recognised by the MESSAGE, not by one of kubectl's framings of it.

    The arm above pins the framing the wrapper shipped matching — kubectl's
    `(Unauthorized)` rendering — and matching only that was the defect: after the
    control-plane reboot of 2026-10-12 the first delegated push met the API
    server's own wording instead, which carries no `Unauthorized`, no `401` and
    no "You must be logged in", so no refresh ran, the push was refused with no
    verdict, and `/etc/ci-runner/gates.kubeconfig` was still the stale file
    afterwards. One credential rejection has several renderings and a wrapper
    that knows one of them repairs the host only by luck.
    """
    code, invoked = _run_wrapper(
        tmp_path=tmp_path,
        euid="1000",
        command_exits=(1, 0),
        rejection=_REJECTION_SERVER_WORDING,
    )

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
    assert invoked[1].startswith("sudo -n ")


@pytest.mark.parametrize("verb", ["apply", "create"])
def test_a_refusal_dressed_as_a_schema_error_is_refreshed_once_and_retried(
    *, tmp_path: Path, verb: str
) -> None:
    """The REAL failure of 2026-10-12, which reached the wrapper looking like bad YAML.

    `create` is the verb the gate client submits its Job with and `apply` is the
    verb every operator reaches for, and both validate before they send: the
    credential is refused while kubectl downloads the OpenAPI document, so the
    message the wrapper has to recognise arrives wrapped in a validation error
    about `"STDIN"`. Nothing in it says `Unauthorized`, so the shipped wrapper
    read a credential refusal as a malformed manifest, refreshed nothing, and the
    push was refused with no verdict.

    Both verbs are run rather than just the one measured, because the wrapper is
    verb-blind by construction and a test that pinned only `create` would let a
    future narrowing keyed on the submit path through.
    """
    code, invoked = _run_wrapper(
        tmp_path=tmp_path,
        euid="1000",
        command_exits=(1, 0),
        rejection=_REJECTION_OPENAPI,
        verb=(verb, "--filename", "-"),
    )

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
    assert invoked[0].endswith(f"--namespace gates {verb} --filename -")


def test_the_retry_of_a_stdin_fed_submit_resubmits_the_same_manifest(*, tmp_path: Path) -> None:
    """The retry carries the MANIFEST, not just the argv — the submit is piped.

    This is the failure the verb arms above cannot see. The gate client submits
    its Job as `kubectl create --filename -` with the manifest on stdin, ONCE,
    and stdin is a pipe that can be read exactly once: the rejected first attempt
    drains it, so a retry that merely re-runs the same argv reads EOF and dies
    with `error: no objects passed to create`. The credential would be refreshed
    and the submit would STILL not have happened — a push refused with no verdict
    after the repair, which is the shape the Definition of Done rules out when it
    requires the FIRST delegated push after a reboot to complete on a verdict.

    So both attempts are asserted to have received the same bytes, and the fake
    kubectl reads stdin when the argv names it, exactly as the real one does. An
    argv-only assertion passes against a wrapper that resubmits nothing.
    """
    code, invoked = _run_wrapper(
        tmp_path=tmp_path,
        euid="1000",
        command_exits=(1, 0),
        rejection=_REJECTION_OPENAPI,
        verb=("create", "--filename", "-"),
        stdin=_FIXTURE_MANIFEST,
    )

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]
    assert _manifests_seen(tmp_path=tmp_path) == [_FIXTURE_MANIFEST, _FIXTURE_MANIFEST]


def test_a_root_caller_refreshes_without_sudo(*, tmp_path: Path) -> None:
    """The boot re-injection's own path — already root, so no privilege to raise.

    The control arm for the test above: it is the CALLER's identity that selects
    the spelling, not a flag, so a wrapper that always reached for `sudo` would
    make root depend on a sudoers rule it does not need.
    """
    code, invoked = _run_wrapper(tmp_path=tmp_path, euid="0", command_exits=(1, 0))

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "refresh", "kubectl"]


def test_a_rejection_the_capture_was_slow_to_record_is_still_refreshed(*, tmp_path: Path) -> None:
    """The wrapper WAITS for the capture it matches on, instead of racing it.

    Recognising the message is only half of it: the wrapper reads the rejection
    out of a file something else is writing, and an unwaited-for capture is
    EMPTY, which matches no pattern at all. So the defect this suite's other arms
    describe as "the pattern missed" has a twin that no pattern can fix — and it
    presents identically, as a push refused with no verdict and a credential
    nobody refreshed.

    Pinned with a `tee` that is slow to START (see `_run_wrapper`) rather than by
    reading the wrapper's redirection syntax, because the claim is about ORDER,
    not about spelling. Found by this very suite on 2026-10-12: the arms above
    passed alone and one of them failed in the full concurrent aggregate, which
    is the signature of a test that was passing on scheduling luck.
    """
    code, invoked = _run_wrapper(
        tmp_path=tmp_path, euid="1000", command_exits=(1, 0), capture_lag="0.3"
    )

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]


def test_a_command_the_server_accepts_is_never_refreshed(*, tmp_path: Path) -> None:
    """A credential refresh is the right response to ONE failure, not to any failure."""
    code, invoked = _run_wrapper(tmp_path=tmp_path, euid="1000", command_exits=(0,))

    assert code == 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl"]


def test_a_second_rejection_is_reported_as_itself(*, tmp_path: Path) -> None:
    """One refresh distinguishes a stale token from a revoked one; it never loops.

    A retry loop would turn a genuinely revoked credential into an unbounded ssh
    hammer against the control-plane node, so the second rejection stands — and
    the caller reads a non-zero exit as a gate that reached no verdict, which
    refuses the push.
    """
    code, invoked = _run_wrapper(tmp_path=tmp_path, euid="1000", command_exits=(1, 1))

    assert code != 0
    assert [line.split(" ")[0] for line in invoked] == ["kubectl", "sudo", "kubectl"]


def _run_refresh(
    *, tmp_path: Path, euid: str, already_there: str | None = None
) -> tuple[int, list[str], Path]:
    """Run the shipped refresh tool against a faked host; return code, argv, dest.

    `ssh` and `sudo` emit the fixture kubeconfig on stdout, standing in for the
    remote `sudo cat`: no host is contacted and no real credential exists. The
    WRITE is real and lands inside `tmp_path`, which is what lets the mode be
    asserted on the file rather than on an argv.

    `already_there` pre-creates the destination, which is the state the refresh
    is actually called in: the pull-on-401 path reaches it precisely when the
    file is present and stale.
    """
    bin_dir = _scratch_path(tmp_path=tmp_path)
    log = tmp_path / "argv.log"
    dest = tmp_path / "gates.kubeconfig"
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
                "GATES_SSH_ENV": str(tmp_path / "absent.env"),
                "GATES_KUBECONFIG": str(dest),
                # The pool's control-plane node, supplied the way the role
                # supplies it (it renders GATES_REMOTE_HOST into the env-file
                # above). The tool carries no default for it and refuses without
                # it, because a machine is bound only through the inventory
                # (livespec-dev-tooling-mavj5i); the refusal itself is read in
                # `tests/livespec_dev_tooling/
                # test_gates_kubeconfig_remote_host_required.py`. The name is
                # invented here and lives nowhere else.
                "GATES_REMOTE_HOST": "a-control-plane-node",
            },
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, invoked, dest


def test_a_root_run_refresh_over_an_existing_credential_keeps_its_owner_and_mode(
    *, tmp_path: Path
) -> None:
    """The REPLACEMENT carries the same ownership and mode the role installed.

    Asserted over an EXISTING destination because that is the case the refresh
    exists for: the pull-on-401 path calls it precisely when the file is already
    there and stale. A refresh that left the replacement root-only would silently
    un-delegate the host it had just repaired — a valid credential nobody who
    pushes can read, and a next push that fails 401 with nothing on the host
    stating why.
    """
    code, invoked, dest = _run_refresh(
        tmp_path=tmp_path,
        euid="0",
        already_there="stale: the credential a refresh must replace\n",
    )

    assert code == 0
    assert dest.read_text(encoding="utf-8") == _FIXTURE_KUBECONFIG
    assert stat.S_IMODE(dest.stat().st_mode) == 0o640
    assert [line for line in invoked if line.startswith("chown root:gates-client ")]
    # The temp file the write renamed over the destination is gone: a 0644
    # stand-in left beside a credential is the exposure the rename shape exists
    # to prevent.
    assert not list(dest.parent.glob(f"{dest.name}.refresh.*"))


def test_a_root_run_refresh_onto_a_fresh_host_lands_the_same_shape(*, tmp_path: Path) -> None:
    """The first install and every repair after it leave the same file.

    Two shapes rather than one because the pair is where the last defect lived:
    `install` succeeded on an absent destination and failed on an existing one,
    so the first refresh worked and every refresh after it did not.
    """
    code, invoked, dest = _run_refresh(tmp_path=tmp_path, euid="0")

    assert code == 0
    assert stat.S_IMODE(dest.stat().st_mode) == 0o640
    assert [line for line in invoked if line.startswith("chown root:gates-client ")]
