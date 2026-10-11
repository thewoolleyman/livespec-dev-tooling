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

import os
import shutil
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REFRESH_GATES = (
    _REPO_ROOT / "ansible" / "roles" / "gates_kubeconfig" / "files" / "refresh-gates-kubeconfig"
)

# A syntactically-valid kubeconfig carrying the two markers
# `refresh-gates-kubeconfig` requires before it writes anything. Never a real
# credential: the string is invented here and lives nowhere else.
_FIXTURE_KUBECONFIG = (
    "kind: Config\napiVersion: v1\nclusters:\n- cluster:\n    server: https://127.0.0.1:6443\n"
)

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
