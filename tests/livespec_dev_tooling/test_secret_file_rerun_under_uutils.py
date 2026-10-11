"""Secret-file writes must be re-runnable where `install` refuses an existing destination.

Ubuntu 25.10 and 26.04 ship uutils coreutils in place of GNU coreutils, and
uutils' `install` exits 1 with `install: No such file or directory` whenever the
DESTINATION operand already exists. Four committed scripts delivered their
secret with `printf ... | install -m MODE /dev/stdin DEST`, so each succeeded on
a fresh host and failed on every run after it. Measured live 2026-10-11: uutils
0.2.2 on the VPS (Ubuntu 25.10) and 0.8.0 on poweredge-xubuntu (Ubuntu 26.04),
both exit 0 against an absent destination and exit 1 against an existing one.

The cost was not theoretical. `with-gates-kubeconfig`'s pull-on-401 path calls
`refresh-gates-kubeconfig`, so the VPS gates credential could not self-heal
after a poweredge reboot; and the three seed/provision scripts contradicted the
runner-pool rebuild recipe's "re-runnable against a node already in its declared
state" rule.

WHY THIS SUITE SHADOWS `install` RATHER THAN TRUSTING THE HOST'S. Every machine
this repo's gates run on carries GNU coreutils, whose `install` overwrites an
existing destination happily — so the defect is INVISIBLE here, which is exactly
why the four shell exit-test suites beside the scripts passed throughout. The
lens is a first-on-PATH `install` that refuses an existing destination exactly as
uutils' does. Everything else in the write path — mktemp, tee, chmod, chown, mv,
and the filesystem itself — is REAL, so what is proven is that the scripts no
longer depend on an `install` able to overwrite, which is the property that makes
them re-runnable under either coreutils.

Work-item: livespec-dev-tooling-74q6iw. Plan: livespec
`k3s-on-gmktec-for-vps-usage` (epic livespec-sab5gn), Definition of Done
assertion 5.
"""

from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_REFRESH_GATES = (
    _REPO_ROOT / "ansible" / "roles" / "gates_kubeconfig" / "files" / "refresh-gates-kubeconfig"
)
_SEED_JOIN_TOKEN = _K3S / "secret-reinjection" / "seed-k3s-agent-join-token.sh"
_SEED_NODE_STATUS = _K3S / "secret-reinjection" / "seed-node-status-kubeconfig.sh"
_PROVISION_NODE_STATUS = (
    _K3S / "phase2" / "node-status-credential" / "provision-node-status-credential.sh"
)
# How each script hands its secret to the file, named exactly. Every entry is a
# PIPE into `tee`'s stdin or a HEREDOC into `cat`'s, which is what keeps the
# value off every argv — `printf` is a bash builtin, so nothing on the host can
# read it out of /proc.
_SECRET_DELIVERY = {
    _REFRESH_GATES: '| tee "${tmp_dest}"',
    _SEED_JOIN_TOKEN: '| sudo tee "$TMP_TARGET"',
    _SEED_NODE_STATUS: '| sudo tee "$TMP_TARGET"',
    _PROVISION_NODE_STATUS: 'cat > "$RENDER_TMP" <<KUBECONFIG_EOF',
}

# The COMMITTED second node's profile. Every value the seed scripts read is that
# node's own data; only the destination path is redirected, because the
# committed value names a file on THAT node holding a cluster credential.
_AGENT_PROFILE = _K3S / "phase0-bare-metal" / "profiles" / "gmktec-xubuntu.env"

# Shaped like a k3s join token so the assertions read like the real thing. It is
# not one, and this file is the only place it lives.
_FIXTURE_JOIN_TOKEN = "K10fixturenotasecret::server:0123456789abcdef"

# Shaped like the kubeconfig the cluster-side provisioner renders. Its token is
# the word `fixture`; nothing here reads 1Password or a cluster.
_FIXTURE_NODE_STATUS_KUBECONFIG = "apiVersion: v1\nkind: Config\nusers:\n  - name: node-status-patcher-gmktec-xubuntu\n    user:\n      token: fixture\n"

# A syntactically-valid kubeconfig carrying the two markers
# `refresh-gates-kubeconfig` requires before it writes anything. Never a real
# credential: the string is invented here and lives nowhere else.
_FIXTURE_KUBECONFIG = (
    "kind: Config\napiVersion: v1\nclusters:\n- cluster:\n    server: https://127.0.0.1:6443\n"
)

# The cluster-side provisioner's fixtures: a ServiceAccount token (invented here,
# handed to the fake `kubectl` base64-encoded the way a real Secret carries it)
# and a CA blob passed through STILL encoded, which is the encoding the
# kubeconfig format wants.
_FIXTURE_SA_TOKEN = "fixture.not.a.real.serviceaccount.token"
_FIXTURE_CA_B64 = "Zml4dHVyZS1jYS1ub3QtYS1yZWFsLWNlcnRpZmljYXRl"

# The real binaries behind a logger. `install` and `chown` are NOT in this list:
# each needs a behaviour of its own (the uutils lens, and the ownership rewrite
# that stands in for the one privilege the real `sudo` supplies).
_LOGGED_PASSTHROUGHS = ("mktemp", "tee", "chmod", "mv", "rm", "cat")

# uutils' `install`, as measured: a destination that already exists is an error.
# `-d` (directory creation) is delegated untouched — uutils accepts an existing
# directory there, and the four scripts' parent-directory steps are not what
# this regression is about.
_INSTALL_LENS = """\
printf 'install %s\\n' "$*" >> "$ARGV_LOG"
for arg in "$@"; do
  [ "$arg" = -d ] && exec {real} "$@"
done
dest=""
for arg in "$@"; do dest="$arg"; done
if [ -e "$dest" ]; then
  printf 'install: No such file or directory\\n' >&2
  exit 1
fi
exec {real} "$@"
"""

# `chown root:root` rewritten to the invoking user's own names. That rewrite IS
# the privilege the real `sudo` would have supplied, and it is the reason this
# suite passes unprivileged as well as as root (where it is a no-op).
_CHOWN_SHIM = """\
printf 'chown %s\\n' "$*" >> "$ARGV_LOG"
spec="$1"; shift
[ "$spec" = root:root ] && spec="$(id -un):$(id -gn)"
exec {real} "$spec" "$@"
"""

# `sudo`: log the whole argv, drop the `-u USER -H` identity wrapper (the
# refresh tool's fetch runs its ssh through it), rewrite `install`'s `-o`/`-g`
# root ownership to this user's own, and then run the command AS THIS USER.
_SUDO_SHIM = """\
printf 'sudo %s\\n' "$*" >> "$ARGV_LOG"
while [ $# -gt 0 ]; do
  case "$1" in
    -u) shift 2 ;;
    -H) shift ;;
    *) break ;;
  esac
done
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o) args+=(-o "$(id -un)"); shift 2 ;;
    -g) args+=(-g "$(id -gn)"); shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
exec "${args[@]}"
"""

_LOGGED_SHIM = """\
printf '{name} %s\\n' "$*" >> "$ARGV_LOG"
exec {real} "$@"
"""

# `id -u` answers FAKE_EUID so the root-only branch of the refresh tool is
# reachable unprivileged. Every other `id` form falls through to the real one,
# which is what keeps the `chown` and `sudo` shims above able to name this user.
_ID_SHIM = """\
if [ "${{1:-}}" = -u ]; then printf '%s\\n' "${{FAKE_EUID:-0}}"; exit 0; fi
exec {real} "$@"
"""

# `ssh`: log the argv and emit the fixture kubeconfig, standing in for the
# remote `sudo cat`. No host is contacted and no credential is read.
# `kubectl`: log the argv, carry the converge's `--dry-run=client -o yaml | apply`
# pipeline (the first stage echoes the manifest it validated, the second
# consumes it), and serve the ServiceAccount token Secret the provisioner waits
# for. No cluster is contacted and nothing is applied anywhere.
_KUBECTL_SHIM = """\
printf 'kubectl %s\\n' "$*" >> "$ARGV_LOG"
case " $* " in
  *" apply "*)
    if [ "${2:-}" = --dry-run=client ]; then cat; else cat > /dev/null; fi
    exit 0 ;;
  *.data.token*) printf '%s' "$FIXTURE_SA_TOKEN_B64"; exit 0 ;;
  *.data.ca*) printf '%s' "$FIXTURE_CA_B64"; exit 0 ;;
esac
exit 0
"""

_SSH_SHIM = """\
printf 'ssh %s\\n' "$*" >> "$ARGV_LOG"
printf '%s' "$FIXTURE_KUBECONFIG"
"""


def _real(*, name: str) -> str:
    """The host's own `name`, resolved OUTSIDE the shim directory."""
    found = shutil.which(name, path="/usr/bin:/bin")
    assert found is not None, f"the host must provide {name} for this suite to shim it"
    return found


def _shim(*, bin_dir: Path, name: str, body: str) -> None:
    """Write an executable bash shim `name` into `bin_dir`."""
    path = bin_dir / name
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _write_path_bin(*, tmp_path: Path) -> Path:
    """A first-on-PATH bin dir: the uutils `install` lens plus logging passthroughs.

    Only `install` and `chown` change behaviour. mktemp / tee / chmod / mv / rm /
    cat are the REAL binaries behind a logger, so the write a script performs
    here is a real filesystem write into `tmp_path` and nothing else.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _shim(bin_dir=bin_dir, name="install", body=_INSTALL_LENS.format(real=_real(name="install")))
    _shim(bin_dir=bin_dir, name="chown", body=_CHOWN_SHIM.format(real=_real(name="chown")))
    _shim(bin_dir=bin_dir, name="sudo", body=_SUDO_SHIM)
    _shim(bin_dir=bin_dir, name="id", body=_ID_SHIM.format(real=_real(name="id")))
    for name in _LOGGED_PASSTHROUGHS:
        _shim(
            bin_dir=bin_dir, name=name, body=_LOGGED_SHIM.format(name=name, real=_real(name=name))
        )
    return bin_dir


def _run(
    *, script: Path, args: list[str], bin_dir: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run `script` with `bin_dir` first on PATH and nothing of this host's env."""
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": "/nonexistent", **env},
    )


def test_refresh_gates_kubeconfig_rewrites_an_existing_destination_when_run_as_root(
    *, tmp_path: Path
) -> None:
    """Definition of Done 1: an existing destination is REPLACED, 0600, exit 0.

    The pull-on-401 path in `with-gates-kubeconfig` calls this tool, so a refresh
    that fails whenever the file it is repairing already exists is a credential
    that can never self-heal — which is precisely what the VPS saw after every
    poweredge reboot.

    Ownership is asserted as the EUID the tool ran under rather than the literal
    `root` the live assertion names: the write is a rename of a file this
    unprivileged suite created, so "owned by whoever ran it" is the off-host
    generalisation of "owned by root when root runs it". The live replay on the
    VPS is the Definition of Done's own host-captured half.
    """
    bin_dir = _write_path_bin(tmp_path=tmp_path)
    _shim(bin_dir=bin_dir, name="ssh", body=_SSH_SHIM)
    dest = tmp_path / "etc" / "ci-runner" / "gates.kubeconfig"
    dest.parent.mkdir(parents=True)
    _ = dest.write_text("kind: Config\n# the stale token a refresh replaces\n", encoding="utf-8")
    dest.chmod(0o600)

    result = _run(
        script=_REFRESH_GATES,
        args=[],
        bin_dir=bin_dir,
        env={
            "ARGV_LOG": str(tmp_path / "argv.log"),
            "FAKE_EUID": "0",
            "FIXTURE_KUBECONFIG": _FIXTURE_KUBECONFIG,
            "GATES_KUBECONFIG": str(dest),
            "GATES_SSH_ENV": str(tmp_path / "no-such-env-file"),
            "GATES_REMOTE_HOST": "poweredge-xubuntu",
        },
    )

    assert result.returncode == 0, (
        "a refresh over an EXISTING destination must exit 0; under an `install` "
        "that refuses an existing destination it did not: "
        f"rc={result.returncode}\n{result.stderr}"
    )
    assert (
        dest.read_text(encoding="utf-8") == _FIXTURE_KUBECONFIG
    ), "the fetched kubeconfig must REPLACE the stale one"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600, "the refreshed file must be owner-only"
    assert dest.stat().st_uid == os.getuid(), "the refreshed file must belong to the writing euid"


def _redirected_profile(*, tmp_path: Path, key: str, value: Path) -> Path:
    """The committed agent profile with one destination key pointed at `value`.

    Every other value is the committed one, so what the script is proven against
    is the node's own data rather than a fixture derived from it.
    """
    rewritten = [
        f"{key}={value}" if line.startswith(f"{key}=") else line
        for line in _AGENT_PROFILE.read_text(encoding="utf-8").splitlines()
    ]
    path = tmp_path / f"{key.lower().replace('_', '-')}-redirected.env"
    _ = path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return path


def test_seed_k3s_agent_join_token_rewrites_an_existing_target(*, tmp_path: Path) -> None:
    """Definition of Done 2: a re-run rewrites the target, owner/group/mode, exit 0.

    The target is pre-created with DIFFERENT bytes, because the script's own
    idempotence skip (byte-identical content is reported, not rewritten) would
    otherwise never reach the write at all — and the write is what the uutils
    lens judges. A re-seed after a rotation is exactly this shape, and it is what
    the runner-pool rebuild recipe's "re-runnable against a node already in its
    declared state" rule requires.
    """
    bin_dir = _write_path_bin(tmp_path=tmp_path)
    target = tmp_path / "etc" / "rancher" / "k3s" / "agent-join-token"
    target.parent.mkdir(parents=True)
    _ = target.write_text("the join token a rotation replaces", encoding="utf-8")
    target.chmod(0o644)
    profile = _redirected_profile(tmp_path=tmp_path, key="CLUSTER_TOKEN_FILE", value=target)

    result = _run(
        script=_SEED_JOIN_TOKEN,
        args=[str(profile)],
        bin_dir=bin_dir,
        env={
            "ARGV_LOG": str(tmp_path / "argv.log"),
            "K3S_AGENT_JOIN_TOKEN_CI_RUNNER": _FIXTURE_JOIN_TOKEN,
        },
    )

    assert result.returncode == 0, (
        "re-seeding an EXISTING target must exit 0; under an `install` that "
        f"refuses an existing destination it did not: rc={result.returncode}\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert (
        target.read_text(encoding="utf-8") == _FIXTURE_JOIN_TOKEN
    ), "the rotated token must replace the stale one, byte for byte"
    assert (
        stat.S_IMODE(target.stat().st_mode) == 0o600
    ), "the re-seeded token must be owner-only, even when the file it replaced was not"
    assert target.stat().st_uid == os.getuid(), (
        "the re-seeded token must carry the requested ownership (root:root on a "
        "node; this suite's own user behind the sudo/chown shims)"
    )


def test_seed_node_status_kubeconfig_rewrites_an_existing_target(*, tmp_path: Path) -> None:
    """Definition of Done 3: a re-run rewrites the target, owner/group/mode, exit 0.

    The delivery half of the churn-slot credential, and deliberately the join
    token's own shape — so it carried the join token's defect too, and a
    re-delivery after a rotation failed on the file it was replacing.
    """
    bin_dir = _write_path_bin(tmp_path=tmp_path)
    target = tmp_path / "etc" / "rancher" / "k3s" / "node-status-kubeconfig"
    target.parent.mkdir(parents=True)
    _ = target.write_text("the kubeconfig a rotation replaces\n", encoding="utf-8")
    target.chmod(0o644)
    profile = _redirected_profile(tmp_path=tmp_path, key="CHURN_KUBECONFIG_FILE", value=target)

    result = _run(
        script=_SEED_NODE_STATUS,
        args=[str(profile)],
        bin_dir=bin_dir,
        env={
            "ARGV_LOG": str(tmp_path / "argv.log"),
            "K3S_NODE_STATUS_KUBECONFIG_CI_RUNNER": _FIXTURE_NODE_STATUS_KUBECONFIG,
        },
    )

    assert result.returncode == 0, (
        "re-delivering an EXISTING node-status kubeconfig must exit 0; under an "
        "`install` that refuses an existing destination it did not: "
        f"rc={result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    assert (
        target.read_text(encoding="utf-8") == _FIXTURE_NODE_STATUS_KUBECONFIG
    ), "the re-delivered credential must replace the stale one, byte for byte"
    assert (
        stat.S_IMODE(target.stat().st_mode) == 0o600
    ), "a bearer token is owner-only even when the file it replaced was not"
    assert (
        target.stat().st_uid == os.getuid()
    ), "the re-delivered credential must carry the requested ownership"


def test_provision_node_status_credential_rewrites_an_existing_rendered_kubeconfig(
    *, tmp_path: Path
) -> None:
    """Definition of Done 4: a re-run rewrites the rendered kubeconfig at its mode.

    The token Secret is populated by the converge's own step 1, so a re-run
    renders the SAME token rather than rotating it — which means the re-run is
    the NORMAL path here, not an exception, and `--render-to` pointing at a file
    an earlier run already produced is the ordinary state of the server.
    """
    bin_dir = _write_path_bin(tmp_path=tmp_path)
    _shim(bin_dir=bin_dir, name="kubectl", body=_KUBECTL_SHIM)
    render_to = tmp_path / "node-status-kubeconfig"
    _ = render_to.write_text("the kubeconfig an earlier run rendered\n", encoding="utf-8")
    render_to.chmod(0o644)

    result = _run(
        script=_PROVISION_NODE_STATUS,
        args=["--render-to", str(render_to), str(_AGENT_PROFILE)],
        bin_dir=bin_dir,
        env={
            "ARGV_LOG": str(tmp_path / "argv.log"),
            "KUBECONFIG": str(tmp_path / "admin.kubeconfig"),
            "FIXTURE_SA_TOKEN_B64": base64.b64encode(_FIXTURE_SA_TOKEN.encode()).decode(),
            "FIXTURE_CA_B64": _FIXTURE_CA_B64,
        },
    )

    assert result.returncode == 0, (
        "re-rendering over an EXISTING kubeconfig must exit 0; under an "
        "`install` that refuses an existing destination it did not: "
        f"rc={result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    rendered = render_to.read_text(encoding="utf-8")
    assert (
        f"token: {_FIXTURE_SA_TOKEN}" in rendered
    ), "the re-rendered kubeconfig must carry the decoded ServiceAccount token"
    assert (
        f"certificate-authority-data: {_FIXTURE_CA_B64}" in rendered
    ), "the CA must be passed through STILL base64-encoded, the encoding the format wants"
    assert stat.S_IMODE(render_to.stat().st_mode) == 0o600, (
        "the rendered kubeconfig must come back at its declared mode, not at the "
        "mode the file it replaced happened to carry"
    )


def test_every_secret_write_is_delivered_over_stdin_or_a_heredoc() -> None:
    """Definition of Done 5: the secret reaches the destination file, never an argv.

    This is the invariant the repair had to PRESERVE rather than establish: the
    `install -m MODE /dev/stdin DEST` idiom it replaced kept the secret off argv
    too, which is why it was the fleet idiom in the first place. What is asserted
    here is that the replacement kept that property — each script still hands its
    secret to a command over standard input or a heredoc — and that the idiom
    itself is gone from all four, so a future edit cannot quietly reintroduce the
    destination-already-exists refusal.

    The behavioural half lives beside each script, in its own exit-test suite:
    those run the real write and assert the fixture credential appears nowhere in
    what `sudo` was asked to run.
    """
    for script, delivery in _SECRET_DELIVERY.items():
        text = script.read_text(encoding="utf-8")
        # Comments are out of scope: the design record has to be able to name
        # what it replaced, and a comment delivers no secret anywhere.
        declared = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        assert delivery in text, (
            f"{script.name} must deliver its secret over stdin or a heredoc as "
            f"{delivery!r}; a secret on a command line is readable out of /proc "
            "by anything on the host"
        )
        assert "/dev/stdin" not in declared, (
            f"{script.name} still names /dev/stdin — the `install -m MODE "
            "/dev/stdin DEST` idiom exits 1 under uutils coreutils whenever DEST "
            "already exists, which is the whole of livespec-dev-tooling-74q6iw"
        )
