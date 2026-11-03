"""The sandbox image warm keeps only current tags in each store it fills.

Work-item `livespec-dev-tooling-xknoqf` (orchestrator plan epic `bd-ib-nmuyjc`).
Covers the clause "The sandbox image warm keeps only current tags." in
`SPECIFICATION/non-functional-requirements.md` (the factory host provisioning
section), and the seven v109 scenarios in `SPECIFICATION/scenarios.md` that
state it.

WHAT BROKE, MEASURED. On 2026-11-02 gmktec-xubuntu's Docker store held about
135G of earlier sandbox tags. Every release pulled two new tags (4.52GB and
6.01GB) and nothing removed the old ones until disk_guard's emergency prune. The
containerd warm pulls the same tags per release onto every factory node, where
kubelet GC reclaims images only past its 85% high-water mark.

WHY THE SCRIPT IS RUN AND NOT READ. Each claim is about what the committed shell
does to an image store: which tags it removes, which it keeps, and when it
exits non-zero. So the committed script runs against a stub `docker` and a stub
`crictl` that share one file-backed store. Each reference is a file holding its
image id, and each container is one line naming an image id. The stubs model the
two runtimes' removal semantics, because the spec's rules differ by them:

- Docker `rmi <tag>` untags only that reference, and refuses when it is the
  image's last tag and a container uses the image. A force flag is logged so
  the test can assert it was never passed.
- CRI `rmi <tag>` removes the image with every name it has, and never refuses.

`STUB_RACE_REF` starts a container on a reference's image inside `rmi`, after
the warm's in-use check and before the removal completes. That is the gap the
spec says the warm must close.

WHAT IS NOT PROVEN HERE. The work-item's assertions are host-captured, observed
with `k3s crictl images` and `docker images` on the live factory nodes after a
real release bump. This module proves the mechanism those captures exercise,
against both stores' removal semantics.
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT / "ansible" / "roles" / "sandbox_image_warm" / "files" / "sandbox-image-warm.sh"
)
_TIMEOUT_SECONDS = 120

_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"
_PREFIX = "python-agent"
_OLD_VERSION = "1.145.0"
_NEW_VERSION = "1.146.1"
_SPEC_FILE = "factory-host.yml"

_STORE_STUB = r"""#!/usr/bin/env bash
# One stub for both clients. Invoked as `docker` or `crictl` (by its basename),
# over a file-backed store: $STUB_STORE/<key> holds "<reference> <image-id>".
# $STUB_CONTAINERS lists one image id per container, in any state.
set -uo pipefail
client=$(basename "$0")
key() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }
id_for() {
    local line
    line=$(awk -v r="$1" '$1 == r { print $2 }' "$STUB_IDS" 2>/dev/null)
    # The default id is the reference with / and : replaced, the same scheme the
    # test's _Host._id uses, so both sides name one image the same way.
    if [[ -n $line ]]; then printf '%s' "$line"; else printf 'sha256:%s' "${1//[\/:]/_}"; fi
}
holds() { [[ -f "$STUB_STORE/$(key "$1")" ]]; }
id_of() { awk '{ print $2 }' "$STUB_STORE/$(key "$1")"; }
refs_of_id() { cat "$STUB_STORE"/* 2>/dev/null | awk -v i="$1" '$2 == i { print $1 }'; }
in_use() { grep -qxF -- "$1" "$STUB_CONTAINERS"; }
race() {
    if [[ -n ${STUB_RACE_REF:-} && $1 == "$STUB_RACE_REF" ]]; then
        id_of "$1" >>"$STUB_CONTAINERS"
    fi
}
pull() {
    [[ " ${STUB_PULL_FAIL:-} " == *" $1 "* ]] && exit 1
    printf '%s-pull %s\n' "$client" "$1" >>"$STUB_LOG"
    printf '%s %s\n' "$1" "$(id_for "$1")" >"$STUB_STORE/$(key "$1")"
}
rmi() {
    local ref=$1 id
    printf '%s-rmi %s\n' "$client" "$ref" >>"$STUB_LOG"
    holds "$ref" || exit 1
    [[ " ${STUB_RMI_FAIL:-} " == *" $ref "* ]] && exit 1
    id=$(id_of "$ref")
    race "$ref"
    if [[ $client == docker ]]; then
        # Docker untags ONE reference, and refuses the last tag of an image a
        # container uses.
        if [[ $(refs_of_id "$id" | wc -l) -le 1 ]] && in_use "$id"; then
            echo "conflict: image is being used by a container" >&2
            exit 1
        fi
        rm -f "$STUB_STORE/$(key "$ref")"
    else
        # CRI RemoveImage removes the image with every name it has.
        while IFS= read -r other; do
            rm -f "$STUB_STORE/$(key "$other")"
        done < <(refs_of_id "$id")
    fi
}
case "$client:${1:-}" in
    docker:image) holds "${3:-}" || exit 1 ;;
    crictl:inspecti) holds "${2:-}" || exit 1 ;;
    *:pull) pull "${2:-}" ;;
    docker:images) cat "$STUB_STORE"/* 2>/dev/null | awk '{ print $1, $2 }' ;;
    crictl:images)
        echo "IMAGE TAG IMAGE-ID SIZE"
        cat "$STUB_STORE"/* 2>/dev/null | awk '{ n = split($1, p, ":"); tag = p[n]; repo = substr($1, 1, length($1) - length(tag) - 1); print repo, tag, $2, "1MB" }'
        ;;
    docker:ps) awk '{ print "c" NR }' "$STUB_CONTAINERS" ;;
    docker:container) cat "$STUB_CONTAINERS" ;;
    crictl:ps)
        echo "CONTAINER IMAGE CREATED STATE NAME"
        awk '{ print "c" NR, $1, "now", "Running", "sandbox" }' "$STUB_CONTAINERS"
        ;;
    docker:rmi)
        for arg in "${@:2}"; do [[ $arg == -f || $arg == --force ]] && echo "FORCE" >>"$STUB_LOG"; done
        rmi "${!#}"
        ;;
    crictl:rmi) rmi "${!#}" ;;
    *) exit 2 ;;
esac
"""

_CURL_STUB = r"""#!/usr/bin/env bash
set -uo pipefail
url="${!#}"
name="${url##*/}"
for refused in ${STUB_UNREADABLE:-}; do [[ "$name" == "$refused" ]] && exit 22; done
if [[ -n "${STUB_SPEC_DIR:-}" && -f "$STUB_SPEC_DIR/$name" ]]; then cat "$STUB_SPEC_DIR/$name"; exit 0; fi
printf '{\n  ".": "%s"\n}\n' "$STUB_VERSION"
"""


def _ref(*, version: str, prefix: str = _PREFIX) -> str:
    return f"{_IMAGE}:{prefix}-v{version}"


class _Host:
    """One factory host: its stub store, containers, record and warm env."""

    def __init__(self, *, tmp_path: Path, store: str) -> None:
        self.tmp = tmp_path
        self.store = store
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name in ("docker", "crictl"):
            stub = self.bin / name
            stub.write_text(_STORE_STUB, encoding="utf-8")
            stub.chmod(0o755)
        curl = self.bin / "curl"
        curl.write_text(_CURL_STUB, encoding="utf-8")
        curl.chmod(0o755)
        self.images = tmp_path / "store"
        self.images.mkdir()
        self.containers = tmp_path / "containers"
        self.containers.touch()
        self.ids = tmp_path / "ids"
        self.ids.touch()
        self.log = tmp_path / "store.log"
        self.log.touch()
        self.record_dir = tmp_path / "var-lib-warm"
        self.spec_dir = tmp_path / "spec"
        self.spec_dir.mkdir()

    def same_image(self, *, ref: str, as_ref: str) -> None:
        """Make `ref` resolve to the image id `as_ref` resolves to."""
        with self.ids.open("a", encoding="utf-8") as ids:
            ids.write(f"{ref} {self._id(as_ref)}\n")

    def _id(self, ref: str) -> str:
        for line in self.ids.read_text(encoding="utf-8").splitlines():
            name, image_id = line.split()
            if name == ref:
                return image_id
        return "sha256:" + ref.replace("/", "_").replace(":", "_")

    def preload(self, *, ref: str) -> None:
        """A tag the store holds that the warm did NOT pull."""
        key = "".join(c if c.isalnum() or c in "._-" else "_" for c in ref)
        (self.images / key).write_text(f"{ref} {self._id(ref)}\n", encoding="utf-8")

    def start_container(self, *, ref: str) -> None:
        with self.containers.open("a", encoding="utf-8") as containers:
            containers.write(self._id(ref) + "\n")

    def start_containers(self, *, ref: str, count: int) -> None:
        """Start `count` containers from one image."""
        with self.containers.open("a", encoding="utf-8") as containers:
            containers.write((self._id(ref) + "\n") * count)

    def clear_containers(self) -> None:
        self.containers.write_text("", encoding="utf-8")

    def held(self) -> set[str]:
        return {
            path.read_text(encoding="utf-8").split()[0]
            for path in self.images.iterdir()
            if path.is_file()
        }

    def warm(
        self,
        *,
        version: str,
        extra: dict[str, str] | None = None,
        prefixes: tuple[str, ...] = (_PREFIX,),
        write_process_spec: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """ONE warm run with the pinned set at `version`."""
        assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} must exist"
        env = os.environ | {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "STUB_STORE": str(self.images),
            "STUB_CONTAINERS": str(self.containers),
            "STUB_IDS": str(self.ids),
            "STUB_LOG": str(self.log),
            "STUB_VERSION": version,
            "STUB_SPEC_DIR": str(self.spec_dir),
            "LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE": _IMAGE,
            "LIVESPEC_SANDBOX_IMAGE_WARM_TAG_PREFIXES": " ".join(prefixes),
            "LIVESPEC_SANDBOX_IMAGE_WARM_PIN_URL": "https://pin.invalid/manifest.json",
            "LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_DIR": str(self.tmp / "locks"),
            "LIVESPEC_SANDBOX_IMAGE_WARM_RECORD_DIR": str(self.record_dir),
            "LIVESPEC_SANDBOX_IMAGE_WARM_STORE": self.store,
            "LIVESPEC_SANDBOX_IMAGE_WARM_CRICTL": "crictl",
        }
        if self.store == "containerd" and write_process_spec:
            body = "fabro_server_instances:\n  - sandbox_providers:\n      kubernetes:\n"
            body += "        process_spec:\n"
            for prefix in prefixes:
                body += f"          image: {_ref(version=version, prefix=prefix)}\n"
            (self.spec_dir / _SPEC_FILE).write_text(body, encoding="utf-8")
            env["LIVESPEC_SANDBOX_IMAGE_WARM_PROCESS_SPEC_URLS"] = (
                f"https://raw.invalid/host_vars/{_SPEC_FILE}"
            )
        env |= extra or {}
        return subprocess.run(
            ["bash", str(_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            env=env,
        )

    def log_lines(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()


_STORES = pytest.mark.parametrize("store", ["docker", "containerd"])


def _output(done: subprocess.CompletedProcess[str]) -> str:
    return done.stdout + done.stderr


@_STORES
def test_the_warm_removes_the_tags_it_pulled_for_an_earlier_pin_once_the_new_pin_is_present(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: the sandbox image warm removes the tags it pulled for an earlier pin.

    Four earlier-pin tags, all pulled by the warm. One shares its image with a
    reference of the new pinned set, one with a tag the warm did not pull, and one
    with a tag a container references. The fourth shares nothing, so only the
    fourth can go.
    """
    host = _Host(tmp_path=tmp_path, store=store)
    new_ref = _ref(version=_NEW_VERSION)
    shares_new = _ref(version=_OLD_VERSION)
    shares_foreign = _ref(version=_OLD_VERSION, prefix="python-rust-agent")
    shares_used = _ref(version=_OLD_VERSION, prefix="python-go-agent")
    plain = _ref(version=_OLD_VERSION, prefix="python-node-agent")
    foreign = f"{_IMAGE}:hand-pulled"
    used_alias = f"{_IMAGE}:in-a-container"
    old_prefixes = ("python-agent", "python-rust-agent", "python-go-agent", "python-node-agent")

    host.same_image(ref=new_ref, as_ref=shares_new)
    host.same_image(ref=foreign, as_ref=shares_foreign)
    host.same_image(ref=used_alias, as_ref=shares_used)
    first = host.warm(version=_OLD_VERSION, prefixes=old_prefixes)
    assert first.returncode == 0, _output(first)
    host.preload(ref=foreign)
    host.preload(ref=used_alias)
    host.start_container(ref=used_alias)

    done = host.warm(version=_NEW_VERSION, prefixes=("python-agent",))

    held = host.held()
    assert done.returncode == 0, _output(done)
    assert new_ref in held, "the new pinned set must be present"
    assert plain not in held, f"the earlier-pin tag nothing protects must be removed: {held}"
    assert foreign in held, "a tag the warm did not pull must stay"
    assert used_alias in held, "a tag a container references must stay"
    if store == "docker":
        # Docker untags one name, so the aliases of protected images stay only
        # because the warm skips them, never because a removal was refused.
        assert shares_foreign in held and shares_used in held, _output(done)
    assert "FORCE" not in host.log_lines(), "the warm must never force a docker removal"


@_STORES
def test_the_warm_keeps_an_earlier_pin_tag_a_container_references_and_removes_it_once_free(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: the sandbox image warm keeps an earlier-pin tag that a container still references."""
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0
    host.start_container(ref=old_ref)

    kept = host.warm(version=_NEW_VERSION)

    assert kept.returncode == 0, _output(kept)
    assert old_ref in host.held(), "a tag a container references must stay"
    host.clear_containers()

    later = host.warm(version=_NEW_VERSION)

    assert later.returncode == 0, _output(later)
    assert old_ref not in host.held(), "once no container references it, a later run removes it"


@_STORES
def test_the_warm_keeps_a_referenced_tag_when_the_in_use_listing_is_large(
    *, tmp_path: Path, store: str
) -> None:
    """A protected id remains protected when the store reports many containers.

    `grep -qxF` may find the first matching id before its `printf` producer has
    written the complete listing.  Under `pipefail`, that producer's SIGPIPE
    must not turn the successful protected-tag lookup into a false negative.
    """
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0
    host.start_containers(ref=old_ref, count=4_096)

    kept = host.warm(version=_NEW_VERSION)

    assert kept.returncode == 0, _output(kept)
    assert old_ref in host.held(), "a tag referenced by any container must stay"
    assert not [line for line in host.log_lines() if line.endswith(f"-rmi {old_ref}")]


@_STORES
def test_2000_concurrent_warms_keep_an_earlier_pin_tag_a_container_references(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: concurrent warms never remove a tag an existing container uses."""
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0
    host.start_container(ref=old_ref)
    # Preload the new pin without a removal pass, so the 2,000 measured runs
    # exercise the protected-tag decision rather than concurrent pulls.
    assert (
        host.warm(
            version=_NEW_VERSION,
            extra={"LIVESPEC_SANDBOX_IMAGE_WARM_REMOVE_SUPERSEDED": "false"},
        ).returncode
        == 0
    )

    with ThreadPoolExecutor(max_workers=32) as executor:
        completed = list(
            executor.map(
                lambda _: host.warm(version=_NEW_VERSION, write_process_spec=False),
                range(2_000),
            )
        )

    assert all(done.returncode == 0 for done in completed), "\n".join(
        _output(done) for done in completed if done.returncode != 0
    )
    assert old_ref in host.held(), "every run must retain the referenced earlier-pin tag"
    assert not [line for line in host.log_lines() if line.endswith(f"-rmi {old_ref}")]
    assert not any("began referencing" in _output(done) for done in completed)


@_STORES
@pytest.mark.parametrize("failure", ["pull", "source"])
def test_a_warm_run_that_has_not_resolved_and_pulled_the_whole_pinned_set_removes_nothing(
    *, tmp_path: Path, store: str, failure: str
) -> None:
    """Scenario: a sandbox image warm run that has not resolved and pulled the whole pinned set removes nothing."""
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0
    if failure == "pull":
        extra = {"STUB_PULL_FAIL": _ref(version=_NEW_VERSION)}
    elif store == "containerd":
        extra = {"STUB_UNREADABLE": _SPEC_FILE}
    else:
        extra = {"STUB_UNREADABLE": "manifest.json"}

    done = host.warm(version=_NEW_VERSION, extra=extra)

    assert old_ref in host.held(), f"no tag may be removed: {_output(done)}"
    assert done.returncode != 0, _output(done)
    assert not [line for line in host.log_lines() if "-rmi " in line]
    if failure == "source":
        source = _SPEC_FILE if store == "containerd" else "manifest.json"
        assert source in _output(done), "the run must name the source it could not read"


@_STORES
def test_a_container_that_starts_during_a_removal_keeps_its_tag_and_fails_the_run(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: a container that starts during a sandbox image warm removal keeps its tag."""
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0

    done = host.warm(version=_NEW_VERSION, extra={"STUB_RACE_REF": old_ref})

    assert (
        old_ref in host.held()
    ), f"the raced tag must be present when the run ends: {_output(done)}"
    assert done.returncode != 0, _output(done)
    assert old_ref in _output(done), "the run must name the tag"
    assert "FORCE" not in host.log_lines(), "the warm must never force a docker removal"


@_STORES
def test_a_removal_the_store_rejects_leaves_the_tag_and_fails_the_run(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: a sandbox image warm removal the store rejects leaves the tag and fails the run."""
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0

    done = host.warm(version=_NEW_VERSION, extra={"STUB_RMI_FAIL": old_ref})

    assert old_ref in host.held(), _output(done)
    assert done.returncode != 0, _output(done)
    assert old_ref in _output(done), "the run must name the tag"


@_STORES
def test_a_disabled_removal_pass_leaves_every_tag_the_warm_pulled(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: a disabled removal pass leaves every tag the sandbox image warm pulled."""
    host = _Host(tmp_path=tmp_path, store=store)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0

    done = host.warm(
        version=_NEW_VERSION, extra={"LIVESPEC_SANDBOX_IMAGE_WARM_REMOVE_SUPERSEDED": "false"}
    )

    assert done.returncode == 0, _output(done)
    assert {old_ref, _ref(version=_NEW_VERSION)} <= host.held()


@_STORES
def test_the_warms_record_of_the_tags_it_pulled_survives_a_reboot(
    *, tmp_path: Path, store: str
) -> None:
    """Scenario: the sandbox image warm's record of the tags it pulled survives a reboot.

    A reboot clears tmpfs, which here is the lock directory; the record directory
    is the unit's StateDirectory under /var/lib, and it is the only state carried
    across. A tag present before the warm first kept its record stays.
    """
    host = _Host(tmp_path=tmp_path, store=store)
    before_record = f"{_IMAGE}:python-agent-v1.100.0"
    host.preload(ref=before_record)
    old_ref = _ref(version=_OLD_VERSION)
    assert host.warm(version=_OLD_VERSION).returncode == 0
    for lock in (tmp_path / "locks").iterdir():
        lock.unlink()
    (tmp_path / "locks").rmdir()

    done = host.warm(version=_NEW_VERSION)

    held = host.held()
    assert done.returncode == 0, _output(done)
    assert old_ref not in held, "the tag the warm pulled for the earlier pin must be removed"
    assert before_record in held, "a tag present before the record existed must stay"
    assert (host.record_dir / "pulled").read_text(encoding="utf-8").split() == [
        _ref(version=_NEW_VERSION)
    ]


def test_a_tag_another_party_pulls_after_the_record_exists_is_not_removed(
    *, tmp_path: Path
) -> None:
    """A tag pulled by anyone else is not the warm's, even once the record exists."""
    host = _Host(tmp_path=tmp_path, store="docker")
    assert host.warm(version=_OLD_VERSION).returncode == 0
    other = f"{_IMAGE}:python-agent-v1.140.0"
    host.preload(ref=other)

    done = host.warm(version=_NEW_VERSION)

    assert done.returncode == 0, _output(done)
    assert other in host.held()
