"""The dev host reclaims disk on a timer instead of waiting for a human to notice.

WHY IT EXISTS (work-item `livespec-dev-tooling-fj6dm5`). Measured 2026-10-21 on the
maintainer's dev host: `/` at 94% — 637G of 678G, 39.4G free — with no standing
retention of any kind. `~/.cache/uv` held 52G and a hand `uv cache prune` reclaimed
~6G before ABORTING on a path under `archive-v0` it was not permitted to remove, so
an unattended prune did not complete at all. The docker store held 21G, 7.8G of it
dangling sandbox images. `tmp/gate-runs` held 1.1G over 4935 run directories across
four governed checkouts, with no retention period defined anywhere.

WHAT THE RATIFIED RULES REQUIRE, and what each test below holds the role to. This
repository's `SPECIFICATION/non-functional-requirements.md` states the dev host's
disk retention (v084), and its `SPECIFICATION/scenarios.md` carries the acceptance
scenario for an in-flight gate run beside an aged terminal one. The retention is
PROVISIONED — a committed script and a daily systemd timer installed by a role
`ansible/dev-host.yml` includes — it removes dangling docker images while leaving
tagged and in-use ones, it prunes the uv cache and CONTINUES past a path it cannot
remove, and it removes a gate run only when that run is TERMINAL and older than the
retention period.

WHY THE SCRIPT IS RUN AND NOT READ. Every claim here is a claim about what the
committed shell DOES: whether the docker prune is the dangling-only spelling,
whether an aborting uv prune still leaves the later steps to run, whether the
liveness probe keeps an in-flight gate run. None of that is settled by what the file
says. So the committed script runs, with `docker` and `uv` stubbed FIRST on `PATH`
(prepended, never replacing it: the script's own `git`, `df`, `date` and `rm` are the
host's). No image is pruned, no cache is touched, and every path the run reaches is
derived from `tmp_path`.

WHY THE LIVE GATE RUN IS A REAL CHILD PROCESS. "Its recorded process is still alive"
is the whole content of the keep rule, and the predicate under test is
`gate-run.sh`'s own `derive_state` — a `kill -0` against the pid the run published.
A fabricated pid would make the arm pass against a script that never probed, so the
fixture starts an actual child and records ITS pid.

WHAT IS NOT PROVEN HERE. The work-item's remaining assertion is host-captured: that
`systemctl list-timers` on the dev host lists the retention timer with a next run
within 24 hours, after `just ansible-apply ansible/dev-host.yml` converges it. That
is a host mutation no sandbox can make or observe. What this module proves is the
mechanism that capture exercises — the committed play reaching the arming task, and
the script the armed unit runs.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_GATE_RUN_BODY

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAYBOOK = _ANSIBLE / "dev-host.yml"
_LEGACY_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_ROLE_NAME = "dev_host_retention"
_ROLE = _ANSIBLE / "roles" / _ROLE_NAME
_SCRIPT = _ROLE / "files" / "dev-host-retention.sh"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_SERVICE_TEMPLATE = _ROLE / "templates" / "livespec-dev-host-retention.service.j2"
_TIMER_TEMPLATE = _ROLE / "templates" / "livespec-dev-host-retention.timer.j2"
_ROLE_DOC = _ROLE / "HOST_VARS.md"

# The role variable the section requires: "its retention period MUST be a role
# variable documented in the role's HOST_VARS.md".
_PERIOD_VARIABLE = "dev_host_retention_gate_run_days"
_UV_BIN_VARIABLE = "dev_host_retention_uv_bin"
# The task whose presence in a plain converge IS "the play includes the role that
# installs the retention script and its daily systemd timer".
_ARM_TASK = "Enable and start the dev host retention timer"
# Any OTHER role of the same play, used to prove the arming task is reachable under
# this role's tag alone rather than on every converge of the dev host.
_OTHER_DEV_HOST_TAG = "otel_collector"

_RETENTION_DAYS = 7
_TIMEOUT_SECONDS = 600
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
# Long enough to outlive one retention run by any margin, short enough that a leaked
# child on a developer's machine is gone before the next test module finishes.
_LIVE_CHILD_SECONDS = "120"

# git sets these in a hook's environment; under a lefthook pre-commit they leak in
# from the surrounding repository and would point the fixture's `git` at it.
_GIT_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

_DOCKER_STUB = """#!/usr/bin/env bash
# A `docker` whose image store is one marker file per image, named
# `<id>.<kind>` with kind one of `dangling`, `tagged` or `in-use`.
#
# `image prune -f` removes the DANGLING markers. Passing `-a` also removes the
# TAGGED ones, exactly as real docker does — that is the whole difference
# between the two spellings, and it is why the tagged marker surviving is a
# claim about the script's argv and not about this stub.
# An `in-use` marker is never removed by either spelling.
set -uo pipefail
printf '%s\\n' "$*" >>"$STUB_DOCKER_LOG"
[[ ${1:-} == image && ${2:-} == prune ]] || exit 2
prune_all=0
for arg in "$@"; do
    [[ $arg == -a || $arg == --all ]] && prune_all=1
done
removed=0
for marker in "$STUB_STORE"/*.dangling; do
    [[ -e $marker ]] || continue
    rm -f "$marker"
    removed=$((removed + 1))
done
if [[ $prune_all == 1 ]]; then
    for marker in "$STUB_STORE"/*.tagged; do
        [[ -e $marker ]] || continue
        rm -f "$marker"
        removed=$((removed + 1))
    done
fi
printf 'deleted: %s images\\n' "$removed"
"""

_UV_STUB = """#!/usr/bin/env bash
# A `uv` that records its argv and, when armed, reproduces the 2026-10-21
# abort: a prune that names one path it was not permitted to remove and exits
# non-zero having removed everything else.
set -uo pipefail
printf '%s\\n' "$*" >>"$STUB_UV_LOG"
if [[ ${STUB_UV_PRUNE_FAILS:-0} == 1 ]]; then
    printf 'error: Failed to clear cache\\n' >&2
    printf '  Caused by: failed to remove directory `%s`\\n' "$STUB_UV_BLOCKED_PATH" >&2
    printf '  Caused by: Permission denied (os error 13)\\n' >&2
    exit 2
fi
printf 'Removed 4096 files\\n'
"""

_STUBS: tuple[tuple[str, str], ...] = (("docker", _DOCKER_STUB), ("uv", _UV_STUB))


def _read(*, path: Path) -> str:
    """One committed file, asserting its presence before reading it.

    An absent file is the finding, so it is an assertion rather than a
    `FileNotFoundError` raised from inside a reader: a test that dies before its
    first assertion proves only that a path is missing, not what the missing thing
    was supposed to do.
    """
    assert path.is_file(), (
        f"{path.relative_to(_REPO_ROOT)} must exist: it is part of the standing disk "
        "retention the dev host has no other source of"
    )
    return path.read_text(encoding="utf-8")


def _install_stubs(*, tmp_path: Path) -> Path:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    for name, body in _STUBS:
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    (tmp_path / "store").mkdir(exist_ok=True)
    (tmp_path / "docker.log").touch()
    (tmp_path / "uv.log").touch()
    return stub_dir


def _base_env(*, tmp_path: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in _GIT_ENV_VARS}
    stub_dir = _install_stubs(tmp_path=tmp_path)
    return env | {
        "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
        "STUB_STORE": str(tmp_path / "store"),
        "STUB_DOCKER_LOG": str(tmp_path / "docker.log"),
        "STUB_UV_LOG": str(tmp_path / "uv.log"),
        "LIVESPEC_DEV_HOST_RETENTION_DAYS": str(_RETENTION_DAYS),
        "LIVESPEC_DEV_HOST_RETENTION_CHECKOUT_ROOTS": str(tmp_path / "projects"),
    }


def _retain(*, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """ONE run of the committed retention script.

    The script's presence is asserted HERE rather than left to `bash`, because an
    absent script exits non-zero having reclaimed nothing — indistinguishable from
    a run that correctly left everything in place.
    """
    _ = _read(path=_SCRIPT)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )


def _image(*, tmp_path: Path, name: str) -> Path:
    marker = tmp_path / "store" / name
    _ = marker.write_text("", encoding="utf-8")
    return marker


def _checkout(*, tmp_path: Path, env: dict[str, str]) -> Path:
    """A governed checkout: a git repository carrying the canonical gate runner."""
    checkout = tmp_path / "projects" / "repo"
    checkout.mkdir(parents=True)
    _ = subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=master"],
        cwd=str(checkout),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    runner = checkout / "dev-tooling" / "gate-run.sh"
    runner.parent.mkdir(parents=True, exist_ok=True)
    _ = runner.write_text(CANONICAL_GATE_RUN_BODY, encoding="utf-8")
    runner.chmod(0o755)
    return checkout


def _gate_run(
    *, checkout: Path, run_id: str, age_days: int, exit_code: str | None = None, pid: int | None
) -> Path:
    """One gate-run record, exactly as the detached child leaves it on disk."""
    run_dir = checkout / "tmp" / "gate-runs" / run_id
    run_dir.mkdir(parents=True)
    started = datetime.now(timezone.utc) - timedelta(days=age_days)
    _ = (run_dir / "started_at").write_text(
        started.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8"
    )
    _ = (run_dir / "command").write_text("just\ncheck\n", encoding="utf-8")
    _ = (run_dir / "output.log").write_text("::: just check-lint [ok, wall: 1.4s]\n", "utf-8")
    if exit_code is not None:
        _ = (run_dir / "exit_code").write_text(f"{exit_code}\n", encoding="utf-8")
    if pid is not None:
        _ = (run_dir / "pid").write_text(f"{pid}\n", encoding="utf-8")
    return run_dir


@pytest.fixture
def live_child() -> Iterator[subprocess.Popen[bytes]]:
    """A real process whose pid an in-flight gate run can record.

    Torn down unconditionally: the keep rule is proven by `kill -0` succeeding
    DURING the run, and nothing about this module wants the child to outlive it.
    """
    child = subprocess.Popen(["sleep", _LIVE_CHILD_SECONDS])
    try:
        yield child
    finally:
        child.terminate()
        _ = child.wait(timeout=30)


def test_a_run_removes_dangling_images_and_leaves_tagged_and_in_use_ones(*, tmp_path: Path) -> None:
    """The docker leg, and the reason the argv is the claim.

    `docker image prune -f` removes dangling images; `docker image prune -a -f`
    also removes every tagged image no container uses. The dev host's 21G docker
    store holds the sandbox tags its own runs dispatch on, so the `-a` spelling
    would reclaim the warm image store this fleet pays a role to keep warm. The
    tagged marker surviving is what says the script asked for the narrow one.
    """
    env = _base_env(tmp_path=tmp_path)
    dangling = _image(tmp_path=tmp_path, name="sha256-abc.dangling")
    tagged = _image(tmp_path=tmp_path, name="sandbox-v1.tagged")
    in_use = _image(tmp_path=tmp_path, name="running-sandbox.in-use")

    done = _retain(env=env)

    assert done.returncode == 0, done.stdout + done.stderr
    assert not dangling.exists(), (
        "a retention run must remove dangling docker images — 7.8G of the dev host's "
        f"21G store was dangling on 2026-10-21:\n{done.stdout + done.stderr}"
    )
    assert tagged.exists(), (
        "a tagged image must survive the retention: the `-a` spelling would evict the "
        f"sandbox tags this host dispatches on:\n{(tmp_path / 'docker.log').read_text()}"
    )
    assert in_use.exists(), "an image a container uses must survive the retention"


def test_a_run_prunes_the_uv_cache(*, tmp_path: Path) -> None:
    env = _base_env(tmp_path=tmp_path)
    done = _retain(env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "cache prune" in (tmp_path / "uv.log").read_text(encoding="utf-8"), (
        "a retention run must prune the uv cache: it was the dev host's largest "
        f"reclaimable consumer at 52G on 2026-10-21:\n{done.stdout + done.stderr}"
    )


def test_a_run_with_no_uv_on_path_uses_the_configured_uv_executable(*, tmp_path: Path) -> None:
    """The root systemd PATH must not prevent the retention user's cache prune."""
    env = _base_env(tmp_path=tmp_path)
    configured_uv = tmp_path / "configured-uv"
    _ = configured_uv.write_text(_UV_STUB, encoding="utf-8")
    configured_uv.chmod(0o755)
    cache_dir = tmp_path / "uv-cache"
    cache_dir.mkdir()
    env |= {
        "PATH": "/usr/bin:/bin",
        "LIVESPEC_DEV_HOST_RETENTION_UV_BIN": str(configured_uv),
        "LIVESPEC_DEV_HOST_UV_CACHE_DIR": str(cache_dir),
    }

    no_uv = subprocess.run(
        ["bash", "-c", "command -v uv"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert no_uv.returncode != 0, "this regression needs a PATH without uv"

    done = _retain(env=env)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "cache prune" in (tmp_path / "uv.log").read_text(encoding="utf-8")
    assert "uv cache prune: Removed 4096 files" in done.stdout


def test_a_uv_path_the_prune_cannot_remove_is_logged_and_the_run_still_finishes(
    *, tmp_path: Path
) -> None:
    """The abort that made the 2026-10-21 prune useless, and the two halves of the fix.

    A hand prune reclaimed ~6G and then exited non-zero on one path under
    `archive-v0`. Under a timer that is worse than it sounds: the steps after the
    prune never run at all, so an unattended retention would reclaim nothing from
    docker and nothing from `tmp/gate-runs` either. So the run must LOG the path
    and CONTINUE — and the gate-run removal below is what proves "continue".
    """
    env = _base_env(tmp_path=tmp_path)
    blocked = tmp_path / "uv-cache" / "archive-v0" / "0b3a9f2c"
    env |= {"STUB_UV_PRUNE_FAILS": "1", "STUB_UV_BLOCKED_PATH": str(blocked)}
    checkout = _checkout(tmp_path=tmp_path, env=env)
    aged = _gate_run(checkout=checkout, run_id="aged", age_days=30, exit_code="0", pid=None)

    done = _retain(env=env)

    assert done.returncode == 0, done.stdout + done.stderr
    assert str(blocked) in done.stdout, (
        "the run must name the path the prune could not remove, or the operator "
        f"cannot tell a partial prune from a complete one:\n{done.stdout + done.stderr}"
    )
    assert not aged.exists(), (
        "the steps after the uv prune must still run: an aborting prune is what made "
        f"the 2026-10-21 reclamation stop at ~6G:\n{done.stdout + done.stderr}"
    )
    assert "free space after" in done.stdout, done.stdout


def test_a_run_removes_an_aged_terminal_gate_run_and_leaves_an_in_flight_one(
    *, tmp_path: Path, live_child: subprocess.Popen[bytes]
) -> None:
    """The acceptance scenario in `SPECIFICATION/scenarios.md` for a retention run
    that leaves an in-flight gate run and removes an aged terminal one, driven end
    to end over one run of the committed script.

    The three records are the whole predicate: TERMINAL-and-aged goes, LIVE stays
    whatever its age, and TERMINAL-but-recent stays. Without the third the arm would
    pass against a script that removed every terminal run and never read
    `started_at` at all.
    """
    env = _base_env(tmp_path=tmp_path)
    checkout = _checkout(tmp_path=tmp_path, env=env)
    aged = _gate_run(
        checkout=checkout, run_id="aged-terminal", age_days=30, exit_code="1", pid=None
    )
    live = _gate_run(checkout=checkout, run_id="aged-live", age_days=30, pid=live_child.pid)
    recent = _gate_run(checkout=checkout, run_id="recent", age_days=1, exit_code="0", pid=None)

    done = _retain(env=env)

    assert done.returncode == 0, done.stdout + done.stderr
    assert not aged.exists(), (
        "a gate run that is terminal and older than the retention period must be "
        f"removed:\n{done.stdout + done.stderr}"
    )
    assert live.exists(), (
        "a gate run whose recorded process is alive must remain in place whatever its "
        f"age — removing it destroys the only evidence an in-flight gate leaves:"
        f"\n{done.stdout + done.stderr}"
    )
    assert recent.exists(), (
        "a terminal gate run inside the retention period must remain: the period is "
        f"what makes this retention and not a sweep:\n{done.stdout + done.stderr}"
    )


def test_a_run_logs_what_it_removed_and_the_free_space_before_and_after(
    *, tmp_path: Path, live_child: subprocess.Popen[bytes]
) -> None:
    """The scenario's third Then-line: the log names the removal and both figures."""
    env = _base_env(tmp_path=tmp_path)
    checkout = _checkout(tmp_path=tmp_path, env=env)
    aged = _gate_run(
        checkout=checkout, run_id="aged-terminal", age_days=30, exit_code="1", pid=None
    )
    _ = _gate_run(checkout=checkout, run_id="aged-live", age_days=30, pid=live_child.pid)

    done = _retain(env=env)

    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        str(aged) in done.stdout
    ), f"the run must name the directory it removed:\n{done.stdout + done.stderr}"
    free = re.findall(r"free space (before|after): (\d+) KiB available on (\S+)", done.stdout)
    assert [entry[0] for entry in free] == ["before", "before", "after", "after"], (
        "the run must report the filesystem's free space before and after, in that "
        f"order — a reclamation nobody can measure is a reclamation nobody trusts:"
        f"\n{done.stdout + done.stderr}"
    )
    assert {entry[2] for entry in free} == {
        "/",
        "/tmp",
    }, f"the retention must report both the root filesystem and tmpfs:\n{done.stdout}"


def test_the_retention_period_is_a_role_variable_documented_in_host_vars() -> None:
    """The section's "its retention period MUST be a role variable" clause."""
    defaults = _read(path=_DEFAULTS)
    assert re.search(rf"^{_PERIOD_VARIABLE}: \d+$", defaults, re.MULTILINE), (
        f"{_ROLE_NAME} must declare {_PERIOD_VARIABLE} as a whole number of days, so "
        f"the period is an inventory value and not a literal in the script:\n{defaults}"
    )
    service = _read(path=_SERVICE_TEMPLATE)
    assert f"{{{{ {_PERIOD_VARIABLE} }}}}" in service, (
        "the unit must pass the role's retention period to the script, or the host "
        f"runs on the script's built-in default and the inventory cannot change it:"
        f"\n{service}"
    )
    doc = _read(path=_ROLE_DOC)
    assert _PERIOD_VARIABLE in doc, (
        f"the owning role's HOST_VARS.md must document {_PERIOD_VARIABLE}: the section "
        "names that file as where the retention period is documented"
    )


def test_the_retention_service_hands_its_configured_uv_executable_to_the_script() -> None:
    """Systemd's root PATH cannot be the source of the executable the script runs."""
    defaults = _read(path=_DEFAULTS)
    assert re.search(rf"^{_UV_BIN_VARIABLE}: /\S+$", defaults, re.MULTILINE), (
        f"{_ROLE_NAME} must configure the uv executable as a path rather than depend on "
        f"systemd's PATH:\n{defaults}"
    )
    service = _read(path=_SERVICE_TEMPLATE)
    assert (
        f'Environment="LIVESPEC_DEV_HOST_RETENTION_UV_BIN={{{{ {_UV_BIN_VARIABLE} }}}}"' in service
    ), (
        "the rendered retention service must hand the configured uv executable to the "
        f"script:\n{service}"
    )


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-apply` recipe resolves."""
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry the `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _list_tasks(*, tags: list[str] | None) -> str:
    argv = ["-i", str(_LEGACY_INVENTORY), "--list-tasks", str(_PLAYBOOK)]
    if tags is not None:
        argv += ["--tags", ",".join(tags)]
    done = subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", *argv],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=os.environ | {"ANSIBLE_ROLES_PATH": str(_ANSIBLE / "roles"), "ANSIBLE_NOCOWS": "1"},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def test_the_dev_host_play_installs_the_retention_script_and_its_daily_timer() -> None:
    """The play reaches the arming task, and the timer it arms fires at least daily."""
    assert _ARM_TASK in _list_tasks(tags=None), (
        "ansible/dev-host.yml must include the role that installs the retention: a "
        "hand-installed user unit is not provisioned state and no drift report sees it"
    )
    arm = _read(path=_TASKS).split(_ARM_TASK, maxsplit=1)[1]
    assert (
        "enabled: true" in arm and "state: started" in arm
    ), f"an installed-but-idle timer reclaims nothing until the next reboot:\n{arm}"
    assert _ARM_TASK not in _list_tasks(tags=[_OTHER_DEV_HOST_TAG]), (
        "the role must carry its own tag, so converging one other dev-host control "
        "does not arm it and `--tags dev_host_retention` can converge it alone"
    )
    timer = _read(path=_TIMER_TEMPLATE)
    assert "OnCalendar=" in timer, f"the timer must fire on a calendar cadence:\n{timer}"
    assert "Persistent=true" in timer, (
        "a host that was down across a firing must reclaim on its next boot rather "
        f"than waiting out a whole day first:\n{timer}"
    )
    assert "WantedBy=timers.target" in timer, f"the timer must be installable:\n{timer}"
