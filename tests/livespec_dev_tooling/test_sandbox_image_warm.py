"""A docker Fabro factory host warms the sandbox image tag before a run needs it.

Work-item `livespec-dev-tooling-dq3km7`; plan `delegated-gate-fleet-rollout`, epic
`livespec-dev-tooling-mvalxq`. Covers the `## Fabro factory host provisioning`
section of `SPECIFICATION/non-functional-requirements.md`, whose "One play,
applied after a drift read" clause requires every Fabro factory control this
repository installs on a host to be a role the `ansible/fabro-hosts.yml` play
includes for that host.

WHAT BROKE, MEASURED. On 2026-10-20 at 08:09:51-52Z two runs started within one
second on hp-xubuntu and both needed
`ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.118.5`, a tag the
host did not hold (it held v1.118.4 and older). Each run's pull tore down the
other's containerd leases and both died in sandbox init with "Failed to pull
Docker image ... causes=[Docker stream error]" in 0.8 s and 3.3 s. The tag was in
the registry the whole time: neither auth nor network. Nothing serialized the
FIRST pull of a new tag, so every image bump re-armed the race, and it fired
hardest when the fleet was busiest.

WHY THE WARM IS THE REMEDY AND NOT A RETRY. The race exists only while the host
does not hold the tag, so the fix is to stop that window from coinciding with a
dispatch: a host-side warm that pulls each new tag into the local image store
ahead of the runs, under a per-reference lock so the warm can neither race a
concurrent warm nor re-arm the very race it exists to close. Two properties are
load-bearing and both are asserted below — the lock SERIALIZES, and the holder
RE-CHECKS inside it, so the second caller finds the tag already held and pulls
nothing. A lock without the re-check serializes two pulls instead of preventing
one.

WHY THE TIMER AND NOT A PLAYBOOK STEP. A warm that runs only when an operator
applies a playbook by hand lags the pin exactly as the gate renderer lagged the
gate client (work-item `livespec-dev-tooling-vurvjl`). So the role arms a systemd
timer, and `--list-tasks` over the committed play is what proves a plain converge
arms it — a real run of the committed file that reaches no host, the same
mechanism the sibling `test_fabro_factory_registry_role` uses for a claim about
selection rather than about resolution.

WHY THE TAG IS DERIVED FROM THIS REPOSITORY'S MASTER. The tag a repository
dispatches on is `<layer>-v<version>`, where the version is this repository's
released version: the sandbox image layers are built and published from here, and
the release fan-out is what rewrites every consumer's `docker =` pin to the new
tag (`livespec_dev_tooling/cross_repo/fabro_image_pin_rewrite.py`, whose
`bump_pin` preserves the layer prefix and moves only the version). Reading the
version from `.release-please-manifest.json` on this repository's master
therefore names the tag the fleet is about to dispatch on, and names it no later
than the pin bump that makes a repository dispatch on it.

WHY THE SCRIPT IS RUN AND NOT READ. Every claim here is a claim about what the
committed shell actually does under concurrency — whether the lock is taken
before the pull, whether the holder re-checks, whether an unreadable pin fails
loudly. None of that is decided by what the file says. So the committed script
runs, with `docker` and `curl` stubbed FIRST on `PATH` (prepended, never
replacing it: the script's own `flock`, `tr` and `sed` are the host's). No image
is pulled and no registry is reached.

WHAT IS NOT PROVEN HERE. Both of the work-item's acceptance assertions are
host-captured on a live docker factory host: they need that host's containerd
image store, a tag it does not yet hold, and concurrent Fabro sandbox inits on
it, and no sandbox capability supplies a factory host's image store. What this
module proves is the mechanism those captures exercise — the serialized
pull-once, the derived tag, the armed timer — and the silent-success failure mode
that would make a host capture read green against a warm that warmed nothing.
"""

from __future__ import annotations

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAYBOOK = _ANSIBLE / "fabro-hosts.yml"
_LEGACY_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_ROLE_NAME = "sandbox_image_warm"
_ROLE = _ANSIBLE / "roles" / _ROLE_NAME
_SCRIPT = _ROLE / "files" / "sandbox-image-warm.sh"
_TASKS = _ROLE / "tasks" / "main.yml"
_TIMER_TEMPLATE = _ROLE / "templates" / "livespec-sandbox-image-warm.timer.j2"
_SERVICE_TEMPLATE = _ROLE / "templates" / "livespec-sandbox-image-warm.service.j2"
_ROLE_DOC = _ROLE / "HOST_VARS.md"

# The task whose presence in a plain converge IS "with no operator command run by
# hand": once the timer is enabled and started, the host re-reads the pin on its
# own cadence and nobody has to apply anything for a new tag to arrive.
_ARM_TASK = "Enable and start the sandbox image warm timer"

_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"
_PREFIX = "python-agent"
_VERSION = "1.118.5"
_REFERENCE = f"{_IMAGE}:{_PREFIX}-v{_VERSION}"
# The shape of this repository's release manifest, which is what the warm reads.
_PIN_BODY = '{\n  ".": "' + _VERSION + '"\n}\n'

_TIMEOUT_SECONDS = 600
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# Long enough that a second unserialized pull would overlap it beyond any
# scheduling noise, short enough to keep the module quick.
_PULL_SECONDS = "1"

_DOCKER_STUB = """#!/usr/bin/env bash
# A `docker` that records what the warm asked for and holds a local image store
# as one marker file per reference. `image inspect` is the store read; `pull`
# brackets itself in the log so an OVERLAP is visible and not merely a count.
set -uo pipefail

key() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }

case "${1:-}" in
    image)
        [[ "${2:-}" == inspect ]] || exit 2
        [[ -f "$STUB_STORE/$(key "${3:-}")" ]] || exit 1
        ;;
    pull)
        printf 'pull-start %s\\n' "${2:-}" >>"$STUB_LOG"
        sleep "$STUB_PULL_SECONDS"
        : >"$STUB_STORE/$(key "${2:-}")"
        printf 'pull-end %s\\n' "${2:-}" >>"$STUB_LOG"
        ;;
    *)
        exit 2
        ;;
esac
"""

_CURL_STUB = """#!/usr/bin/env bash
# A `curl` that answers with this repository's release manifest, or refuses when
# the arm under test is an unreadable pin.
set -uo pipefail
[[ "${STUB_PIN_READABLE:-1}" == 1 ]] || exit 7
printf '%s' "$STUB_PIN_BODY"
"""


def _read(*, path: Path) -> str:
    """One committed file, asserting its presence before reading it.

    An absent file is the finding, so it is an assertion rather than a
    `FileNotFoundError` raised from inside a reader: a test that dies before its
    first assertion proves only that a path is missing, not what the missing
    thing was supposed to do.
    """
    assert path.is_file(), (
        f"{path.relative_to(_REPO_ROOT)} must exist: it is the host-side warm that "
        "keeps a new sandbox image tag out of the first-pull race"
    )
    return path.read_text(encoding="utf-8")


def _install_stubs(*, tmp_path: Path) -> Path:
    """The stub `docker` and `curl`, idempotently — every arm calls this."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    for name, body in (("docker", _DOCKER_STUB), ("curl", _CURL_STUB)):
        stub = stub_dir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    (tmp_path / "store").mkdir(exist_ok=True)
    (tmp_path / "docker.log").touch()
    return stub_dir


def _warm_env(*, tmp_path: Path, pin_readable: bool) -> dict[str, str]:
    """The environment ONE warm invocation runs under.

    `PATH` is PREPENDED rather than replaced: the script resolves `flock`, `tr`,
    `sed` and `date` from the host, and a replaced `PATH` would make this module
    assert against a script that cannot run on a factory host either.
    """
    bin_dir = _install_stubs(tmp_path=tmp_path)
    store = tmp_path / "store"
    return os.environ | {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(tmp_path / "docker.log"),
        "STUB_STORE": str(store),
        "STUB_PULL_SECONDS": _PULL_SECONDS,
        "STUB_PIN_BODY": _PIN_BODY,
        "STUB_PIN_READABLE": "1" if pin_readable else "0",
        "LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE": _IMAGE,
        "LIVESPEC_SANDBOX_IMAGE_WARM_TAG_PREFIXES": _PREFIX,
        "LIVESPEC_SANDBOX_IMAGE_WARM_PIN_URL": "https://pin.invalid/manifest.json",
        "LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_DIR": str(tmp_path / "locks"),
    }


def _warm(*, tmp_path: Path, pin_readable: bool = True) -> subprocess.CompletedProcess[str]:
    """ONE warm invocation of the committed script.

    The script's presence is asserted HERE rather than left to `bash` to report,
    because an absent script exits non-zero and pulls nothing — which is
    indistinguishable from the refusal arms' expected answer. Without this guard
    the unreadable-pin arm passes against no script at all.
    """
    _read(path=_SCRIPT)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=_warm_env(tmp_path=tmp_path, pin_readable=pin_readable),
    )


def _docker_log(*, tmp_path: Path) -> list[str]:
    """Every `docker pull` bracket the warm produced, in the order it produced them."""
    log = tmp_path / "docker.log"
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line]


def test_the_warm_pulls_the_tag_this_repositorys_master_pin_names(*, tmp_path: Path) -> None:
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} must exist"
    done = _warm(tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _docker_log(tmp_path=tmp_path) == [
        f"pull-start {_REFERENCE}",
        f"pull-end {_REFERENCE}",
    ], (
        "the warm must derive the tag the fleet is about to dispatch on from the "
        f"version on this repository's master, which is {_VERSION}: "
        f"{done.stdout + done.stderr}"
    )


def test_two_concurrent_warms_of_an_absent_tag_pull_it_exactly_once(*, tmp_path: Path) -> None:
    """The property the incident lacked: ONE pull, even started together.

    Two bracketed pulls in the log would be the incident reproduced — that is the
    shape that tore down each other's leases. One `pull-start` followed by its own
    `pull-end` is both halves of the remedy at once: the lock serialized the two
    callers, and the second re-checked the store inside it and pulled nothing.
    """
    _install_stubs(tmp_path=tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [pool.submit(_warm, tmp_path=tmp_path) for _ in range(2)]
        results = [run.result() for run in runs]
    for done in results:
        assert done.returncode == 0, done.stdout + done.stderr
    assert _docker_log(tmp_path=tmp_path) == [
        f"pull-start {_REFERENCE}",
        f"pull-end {_REFERENCE}",
    ], (
        "two warms racing on a tag the host does not hold must pull it exactly once, "
        "with no second pull overlapping the first: "
        f"{[done.stdout + done.stderr for done in results]}"
    )


def test_a_tag_the_host_already_holds_is_never_pulled(*, tmp_path: Path) -> None:
    env = _warm_env(tmp_path=tmp_path, pin_readable=True)
    held = Path(env["STUB_STORE"]) / re.sub(r"[^A-Za-z0-9._-]", "_", _REFERENCE)
    held.write_text("", encoding="utf-8")
    done = _warm(tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        _docker_log(tmp_path=tmp_path) == []
    ), "a warm whose tag is already in the local image store must pull nothing"


def test_a_pin_the_host_cannot_read_fails_the_warm_rather_than_reporting_success(
    *, tmp_path: Path
) -> None:
    """The silent-success arm, and the reason it is not merely tidy.

    A warm that cannot read the pin has warmed nothing, and the next run on this
    host meets exactly the first-pull race this role exists to close. Exiting 0
    would record that non-event as a healthy timer run in the journal, so the
    only honest answer is a non-zero exit with no pull attempted.
    """
    done = _warm(tmp_path=tmp_path, pin_readable=False)
    assert done.returncode != 0, (
        "a warm that cannot read the pin has warmed nothing and must say so: "
        f"{done.stdout + done.stderr}"
    )
    assert (
        _docker_log(tmp_path=tmp_path) == []
    ), "a warm with no version must not pull a reference it could not derive"


# --- the committed play and role ------------------------------------------


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


def test_the_sandbox_host_play_arms_the_warm_timer_with_no_operator_command() -> None:
    assert _ARM_TASK in _list_tasks(tags=None), (
        "ansible/fabro-hosts.yml must arm the sandbox image warm timer on its sandbox "
        "hosts, or the warm lags the pin exactly as a hand-applied step would"
    )
    tasks = _read(path=_TASKS)
    arm = tasks.split(_ARM_TASK, maxsplit=1)[1]
    assert "enabled: true" in arm and "state: started" in arm, (
        "the timer must be enabled AND started by the converge: an installed-but-idle "
        f"timer warms nothing until the next reboot:\n{arm}"
    )
    assert _ARM_TASK not in _list_tasks(tags=["disk_guard"]), (
        "the warm must carry its own tag, so an operator converging one other control "
        "does not arm it and `--tags sandbox_image_warm` can converge it alone"
    )
    timer = _read(path=_TIMER_TEMPLATE)
    assert "OnUnitActiveSec=" in timer, (
        "the timer must repeat: a one-shot warm covers the tag live at converge time "
        f"and no tag after it:\n{timer}"
    )
    assert "OnBootSec=" in timer, f"the timer must also fire after a reboot:\n{timer}"
    assert "WantedBy=timers.target" in timer, f"the timer must be installable:\n{timer}"


def test_the_warm_service_passes_the_role_variables_the_script_reads() -> None:
    service = _read(path=_SERVICE_TEMPLATE)
    for variable in (
        "LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE",
        "LIVESPEC_SANDBOX_IMAGE_WARM_TAG_PREFIXES",
        "LIVESPEC_SANDBOX_IMAGE_WARM_PIN_URL",
        "LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_DIR",
    ):
        assert variable in service, (
            f"the unit must pass {variable} from the role's variables, or the host runs "
            f"on the script's built-in default and the inventory cannot change it:\n{service}"
        )
    doc = _read(path=_ROLE_DOC)
    assert "sandbox_image_warm_image" in doc, (
        "the owning role's HOST_VARS.md must document every per-host variable the role "
        "reads, per the Fabro factory host provisioning section's documentation clause"
    )
