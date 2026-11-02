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
_CI_POOL_PLAYBOOK = _ANSIBLE / "ci-pool.yml"
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
# the arm under test is an unreadable pin. A URL whose basename is a file in
# STUB_SPEC_DIR answers with that file instead: a committed host_vars file the
# containerd warm reads its process_spec images from. A URL whose basename is
# listed in STUB_UNREADABLE refuses, as a fetch that failed.
set -uo pipefail
[[ "${STUB_PIN_READABLE:-1}" == 1 ]] || exit 7
url="${!#}"
name="${url##*/}"
for refused in ${STUB_UNREADABLE:-}; do
    [[ "$name" == "$refused" ]] && exit 22
done
if [[ -n "${STUB_SPEC_DIR:-}" && -f "$STUB_SPEC_DIR/$name" ]]; then
    cat "$STUB_SPEC_DIR/$name"
    exit 0
fi
printf '%s' "$STUB_PIN_BODY"
"""

_CRICTL_STUB = """#!/usr/bin/env bash
# A `crictl` over the SAME marker-file store and log as the docker stub, so an
# arm can tell which client a warm used by which stub wrote the log line:
# `crictl-pull-*` here, `pull-*` there. `inspecti` is the CRI store read.
set -uo pipefail

key() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }

case "${1:-}" in
    inspecti)
        [[ -f "$STUB_STORE/$(key "${2:-}")" ]] || exit 1
        ;;
    pull)
        printf 'crictl-pull-start %s\\n' "${2:-}" >>"$STUB_LOG"
        sleep "$STUB_PULL_SECONDS"
        : >"$STUB_STORE/$(key "${2:-}")"
        printf 'crictl-pull-end %s\\n' "${2:-}" >>"$STUB_LOG"
        ;;
    *)
        exit 2
        ;;
esac
"""

# ONE source for the stub set, so the writer (`_install_stubs`) and the watcher
# (`_stub_identities`) can never disagree about which files the concurrency arm
# must not see rewritten.
_STUB_DIR_NAME = "bin"
_STUBS: tuple[tuple[str, str], ...] = (
    ("docker", _DOCKER_STUB),
    ("curl", _CURL_STUB),
    ("crictl", _CRICTL_STUB),
)


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
    """The stub `docker` and `curl`, idempotently — every SEQUENTIAL arm calls this.

    Idempotent is not concurrency-safe: each call rewrites every stub, so a
    caller that may run while another warm is exec'ing one must reuse an
    installation instead (`_warm_env`'s `install_stubs=False`).
    """
    stub_dir = tmp_path / _STUB_DIR_NAME
    stub_dir.mkdir(exist_ok=True)
    for name, body in _STUBS:
        stub = stub_dir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    (tmp_path / "store").mkdir(exist_ok=True)
    (tmp_path / "docker.log").touch()
    return stub_dir


def _stub_identities(*, stub_dir: Path) -> dict[str, tuple[int, int]]:
    """Each stub's inode and mtime — the observable that says it was not rewritten.

    `write_text` TRUNCATES IN PLACE, so a rewritten stub keeps its inode and only
    its mtime moves; comparing both names the rewrite either way, whether the
    fixture replaced the file or overwrote it.
    """
    stats = {name: (stub_dir / name).stat() for name, _ in _STUBS}
    return {name: (stat.st_ino, stat.st_mtime_ns) for name, stat in stats.items()}


def _warm_env(*, tmp_path: Path, pin_readable: bool, install_stubs: bool = True) -> dict[str, str]:
    """The environment ONE warm invocation runs under.

    `PATH` is PREPENDED rather than replaced: the script resolves `flock`, `tr`,
    `sed` and `date` from the host, and a replaced `PATH` would make this module
    assert against a script that cannot run on a factory host either.

    `install_stubs=False` REUSES stubs a caller already installed, and the
    concurrency arm requires it: installing is `write_text` + `chmod` over every
    stub, which TRUNCATES a file the sibling warm's `bash` may be exec'ing at
    that instant, and Linux answers that exec with ETXTBSY. Measured 2026-10-20
    in CI (PR #2705, run 39513824524): `sandbox-image-warm.sh: line 64:
    .../bin/curl: Text file busy`, then one pull in the log instead of two — the
    FIXTURE racing itself, not the script under test failing its property.
    """
    bin_dir = _install_stubs(tmp_path=tmp_path) if install_stubs else tmp_path / _STUB_DIR_NAME
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


def _warm(
    *, tmp_path: Path, pin_readable: bool = True, install_stubs: bool = True
) -> subprocess.CompletedProcess[str]:
    """ONE warm invocation of the committed script.

    The script's presence is asserted HERE rather than left to `bash` to report,
    because an absent script exits non-zero and pulls nothing — which is
    indistinguishable from the refusal arms' expected answer. Without this guard
    the unreadable-pin arm passes against no script at all.

    `install_stubs` reaches `_warm_env`, which documents why a CONCURRENT caller
    must pass it as False.
    """
    _read(path=_SCRIPT)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=_warm_env(tmp_path=tmp_path, pin_readable=pin_readable, install_stubs=install_stubs),
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

    The stubs are installed ONCE, here, and neither warm reinstalls them: an
    `install_stubs=True` warm rewrites every stub as its first act, which
    truncates a file the other warm's `bash` may be exec'ing and fails that exec
    with ETXTBSY. The identity assertion below is what keeps that true — it is a
    guard on this FIXTURE rather than on the script, and it fails
    deterministically if a later edit lets either warm install stubs again.
    """
    stub_dir = _install_stubs(tmp_path=tmp_path)
    installed = _stub_identities(stub_dir=stub_dir)
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [pool.submit(_warm, tmp_path=tmp_path, install_stubs=False) for _ in range(2)]
        results = [run.result() for run in runs]
    assert _stub_identities(stub_dir=stub_dir) == installed, (
        "neither concurrent warm may rewrite a stub the other may be exec'ing: a "
        "rewritten stub makes this arm fail with `Text file busy` and one pull "
        "instead of two, which reads as the script losing a property it kept"
    )
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


# --- the containerd store (work-item bd-ib-kogktm) --------------------------
#
# A Kubernetes factory pod is pulled by the k3s node's kubelet into K3S
# CONTAINERD's store, which the docker warm never touches. Measured 2026-10-26:
# gmktec-xubuntu's containerd held python-agent-v1.93.5 and not the v1.114.1 the
# pods ran, and every factory pod landed on poweredge-xubuntu. The containerd
# store points the same serialized, re-checked pull at the CRI, and reads its
# references from the registered provider's `process_spec.image` in the
# committed host_vars on master, re-read every tick, so a pin bump is pulled
# with nobody applying anything.

_SPEC_REFERENCE = f"{_IMAGE}:python-agent-v1.136.2"
_SPEC_RUST_REFERENCE = f"{_IMAGE}:python-rust-agent-v1.136.2"
# The shape of a Fabro server host's host_vars, cut to the parts the read must
# get right: two providers, a second instance repeating one image, a
# commented-out rollback image, an `image:` OUTSIDE any process_spec (a docker
# environment's), and an image outside the sandbox repository.
_SPEC_HOST_VARS = f"""fabro_server_instances:
  - unit_name: fabro-server
    environments:
      - id: livespec-ci-rust
        image: {_IMAGE}:python-rust-agent-v1.0.0
    sandbox_providers:
      kubernetes:
        path: /usr/local/bin/sandbox-driver-kubernetes
        process_spec:
          # image: {_IMAGE}:python-agent-v0.0.1
          image: {_SPEC_REFERENCE}
          cpu_cores: 4
      kubernetes-rust:
        process_spec:
          image: "{_SPEC_RUST_REFERENCE}"  # follows the rust layer
          memory_mb: 7629
  - unit_name: fabro-server-candidate
    sandbox_providers:
      kubernetes:
        process_spec:
          image: {_SPEC_REFERENCE}
      elsewhere:
        process_spec:
          image: docker.io/library/busybox:1
"""
_NO_SPEC_HOST_VARS = (
    "fabro_server_instances:\n  - unit_name: fabro-server\n    service_state: stopped\n"
)


def _write_specs(*, tmp_path: Path, specs: dict[str, str]) -> Path:
    """The host_vars files the stub `curl` serves, one per name."""
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir(exist_ok=True)
    for name, body in specs.items():
        (spec_dir / name).write_text(body, encoding="utf-8")
    return spec_dir


def _containerd_warm(
    *,
    tmp_path: Path,
    specs: dict[str, str],
    unreadable: tuple[str, ...] = (),
    concurrent: bool = False,
) -> subprocess.CompletedProcess[str]:
    """ONE containerd warm of the committed script over `specs`' host_vars files.

    `concurrent=True` writes NOTHING — no stub, no spec file — because the caller
    already did, and a rewrite would truncate a file the sibling warm may be
    exec'ing or reading (see `_warm_env` on ETXTBSY).
    """
    _read(path=_SCRIPT)
    spec_dir = tmp_path / "specs" if concurrent else _write_specs(tmp_path=tmp_path, specs=specs)
    env = _warm_env(tmp_path=tmp_path, pin_readable=True, install_stubs=not concurrent) | {
        "STUB_SPEC_DIR": str(spec_dir),
        "STUB_UNREADABLE": " ".join(unreadable),
        "LIVESPEC_SANDBOX_IMAGE_WARM_STORE": "containerd",
        "LIVESPEC_SANDBOX_IMAGE_WARM_CRICTL": "crictl",
        "LIVESPEC_SANDBOX_IMAGE_WARM_PROCESS_SPEC_URLS": " ".join(
            f"https://spec.invalid/host_vars/{name}" for name in specs
        ),
    }
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )


def test_a_containerd_warm_pulls_every_process_spec_image_through_the_cri(
    *, tmp_path: Path
) -> None:
    done = _containerd_warm(
        tmp_path=tmp_path,
        specs={"factory-a.yml": _SPEC_HOST_VARS, "factory-b.yml": _NO_SPEC_HOST_VARS},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert _docker_log(tmp_path=tmp_path) == [
        f"crictl-pull-start {_SPEC_REFERENCE}",
        f"crictl-pull-end {_SPEC_REFERENCE}",
        f"crictl-pull-start {_SPEC_RUST_REFERENCE}",
        f"crictl-pull-end {_SPEC_RUST_REFERENCE}",
    ], (
        "a containerd warm must pull, through crictl and never docker, exactly the "
        "process_spec images inside the sandbox repository, each once — not the "
        "commented-out rollback image, not a docker environment's image, not an image "
        f"of another repository, and not the release-pin tag: {done.stdout + done.stderr}"
    )


def test_a_process_spec_image_the_node_already_holds_is_never_pulled(*, tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    for reference in (_SPEC_REFERENCE, _SPEC_RUST_REFERENCE):
        (store / re.sub(r"[^A-Za-z0-9._-]", "_", reference)).write_text("", encoding="utf-8")
    done = _containerd_warm(tmp_path=tmp_path, specs={"factory-a.yml": _SPEC_HOST_VARS})
    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        _docker_log(tmp_path=tmp_path) == []
    ), "a warm whose images are already in the node's containerd must pull nothing"


def test_two_concurrent_containerd_warms_pull_each_image_exactly_once(*, tmp_path: Path) -> None:
    stub_dir = _install_stubs(tmp_path=tmp_path)
    installed = _stub_identities(stub_dir=stub_dir)
    spec = {"factory-a.yml": _SPEC_HOST_VARS}
    _write_specs(tmp_path=tmp_path, specs=spec)
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [
            pool.submit(_containerd_warm, tmp_path=tmp_path, specs=spec, concurrent=True)
            for _ in range(2)
        ]
        results = [run.result() for run in runs]
    assert _stub_identities(stub_dir=stub_dir) == installed
    for done in results:
        assert done.returncode == 0, done.stdout + done.stderr
    log = _docker_log(tmp_path=tmp_path)
    for reference in (_SPEC_REFERENCE, _SPEC_RUST_REFERENCE):
        assert log.count(f"crictl-pull-start {reference}") == 1, (
            "two containerd warms racing on an image the node lacks must pull it once: " f"{log}"
        )


def test_an_unreadable_process_spec_source_fails_the_warm_and_pulls_nothing(
    *, tmp_path: Path
) -> None:
    """A partial read can omit the very pin that moved, so ANY unreadable file fails."""
    done = _containerd_warm(
        tmp_path=tmp_path,
        specs={"factory-a.yml": _SPEC_HOST_VARS, "factory-b.yml": _NO_SPEC_HOST_VARS},
        unreadable=("factory-b.yml",),
    )
    assert done.returncode != 0, done.stdout + done.stderr
    assert _docker_log(tmp_path=tmp_path) == [], "a failed source read must pull nothing"


def test_sources_declaring_no_process_spec_image_fail_the_warm(*, tmp_path: Path) -> None:
    """Nothing to pull is a broken read, not a healthy tick: never fall back to the pin."""
    done = _containerd_warm(tmp_path=tmp_path, specs={"factory-b.yml": _NO_SPEC_HOST_VARS})
    assert done.returncode != 0, done.stdout + done.stderr
    assert _docker_log(tmp_path=tmp_path) == [], (
        "a containerd warm with no process_spec image must not pull the release-pin tag "
        "instead: no Kubernetes sandbox is built from it"
    )


def test_ci_pool_arms_a_containerd_warm_on_every_factory_node_under_its_own_tag() -> None:
    play = _read(path=_CI_POOL_PLAYBOOK)
    entry = re.search(
        r"^    - role: sandbox_image_warm\n(?P<body>(?:      .*\n)+)", play, re.MULTILINE
    )
    assert entry is not None, (
        "ansible/ci-pool.yml must include sandbox_image_warm, so every k3s factory node's "
        "containerd holds the image its factory pods are built from"
    )
    body = entry["body"]
    assert "      sandbox_image_warm_store: containerd\n" in body, body
    assert (
        "      when: ci_pool_factory_node == 'true'\n" in body
    ), f"the containerd warm must be gated on the profile's FACTORY_NODE:\n{body}"
    assert "      tags: [sandbox_image_warm_containerd]\n" in body, (
        "the containerd warm needs its own tag so the host window can apply it alone, "
        f"distinct from the docker warm's:\n{body}"
    )
    service = _read(path=_SERVICE_TEMPLATE)
    for variable in (
        "LIVESPEC_SANDBOX_IMAGE_WARM_STORE",
        "LIVESPEC_SANDBOX_IMAGE_WARM_CRICTL",
        "LIVESPEC_SANDBOX_IMAGE_WARM_PROCESS_SPEC_URLS",
    ):
        assert variable in service, f"the unit must pass {variable}:\n{service}"
    assert (
        "Wants=network-online.target docker.service" in service.split("{% else %}")[1]
    ), "only the docker store may pull docker.service in"
    containerd_unit = service.split("{% if sandbox_image_warm_store == 'containerd' %}")[1]
    containerd_unit = containerd_unit.split("{% else %}")[0]
    assert "docker" not in containerd_unit, (
        "a containerd warm must not Want or order on docker: Wants= would START dockerd on "
        f"a node where it is installed and stopped:\n{containerd_unit}"
    )
    doc = _read(path=_ROLE_DOC)
    assert (
        "just ansible-apply ansible/ci-pool.yml --tags sandbox_image_warm_containerd" in doc
    ), "the role's HOST_VARS.md must carry the containerd warm's apply command"


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
