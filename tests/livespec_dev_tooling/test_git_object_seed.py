"""The git object seed tier (livespec-dev-tooling-dciyg5), executed rather than read.

SPECIFICATION "Runner-pool build cache tiers" requires a SEEDED tree of each routed
repository's default-branch and tag objects, a job container that names its OWN
repository's copy in GIT_ALTERNATE_OBJECT_DIRECTORIES from the runner container hook
(only when the directory exists, never under the kill switch), a checkout that
fetches only what the seed lacks, and a per-tier cache span. Three committed
artifacts carry that, and each is RUN here under the shell or node it ships for:

  - the populator's git section (`warm-cache-populate.sh`, step 5) against a local
    "forge" holding a default branch, a tag, a side branch and a pull-request ref;
  - the provisioner's `setup` script against a scratch node path;
  - `arc/git-seed-hook.js`, the runner's container hook entry point, against a fake
    "real hook" that records the stdin line it is handed.

The properties asserted are the Definition of Done's: the seed holds only objects
reachable from the default branch and tags; a checkout with the seed transfers only
objects the seed lacks and lands on the same refs; a volume carries its own
repository's seed and no other; the variable is named only when the directory
exists and the tiers are on; and the postStart hook records a hit or a miss with
the generation. The part of the Definition of Done that exists only on the k3s pool
(a routed job on a node that holds the seed) stays host-captured.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO / "ci-runner" / "k3s" / "phase2"
_POPULATE = _PHASE2 / "warm-cache" / "warm-cache-populate.sh"
_PROVISIONER = _PHASE2 / "local-path-provisioner" / "local-path-provisioner.yaml"
_WRAPPER = _PHASE2 / "arc" / "git-seed-hook.js"
_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_VALUES = sorted(
    path for path in (_PHASE2 / "arc").glob("values-*.yaml") if "EXAMPLE" not in path.name
)
_NODE = shutil.which("node")
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
_REPO_NAME = "livespec-runtime"
_CLAIM_SUFFIX = "abcde-runner-fghij-work"
_SETUP_SCRIPT = re.compile(r"^  setup: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)
_POPULATOR_SECTION = re.compile(
    r"^(?P<body>GIT_SRC_ROOT=.*?)\nlog \"run summary", re.MULTILINE | re.DOTALL
)
_ONE_LINE_HELPER = re.compile(r"^(?:log|gen_bytes|gen_files)\(\) \{.*$", re.MULTILINE)
_MANIFEST_FIELD = re.compile(r"^manifest_field\(\) \{\n.*?\n\}$", re.MULTILINE | re.DOTALL)
_VERIFY_FUNCTION = re.compile(r"^git_verify_store\(\) \{\n.*?\n\}$", re.MULTILINE | re.DOTALL)


def _git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **_GIT_IDENTITY, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


def _commit(*, work: Path, name: str) -> str:
    (work / name).write_text(name, encoding="utf-8")
    _git("add", name, cwd=work)
    _git("commit", "-q", "-m", name, cwd=work)
    return _git("rev-parse", "HEAD", cwd=work)


def _forge(*, root: Path) -> dict[str, str]:
    """A bare forge repository with main + a tag + a side branch + a pull-request ref."""
    work = root / "work"
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    shas = {"first": _commit(work=work, name="first")}
    _git("tag", "-a", "-m", "v1", "v1", cwd=work)
    shas["second"] = _commit(work=work, name="second")
    _git("checkout", "-q", "-b", "side", "main", cwd=work)
    shas["side"] = _commit(work=work, name="side-only")
    _git("checkout", "-q", "-b", "pr", "main", cwd=work)
    shas["pull"] = _commit(work=work, name="pull-request-only")
    forge = root / "forge" / f"{_REPO_NAME}.git"
    forge.parent.mkdir()
    _git("init", "-q", "--bare", "-b", "main", str(forge), cwd=root)
    _git("push", "-q", str(forge), "main", "side", "--tags", cwd=work)
    _git("push", "-q", str(forge), "pr:refs/pull/1/head", cwd=work)
    shas["forge"] = str(forge)
    return shas


def _populator_helpers() -> str:
    script = _POPULATE.read_text(encoding="utf-8")
    one_liners = _ONE_LINE_HELPER.findall(script)
    manifest_field = _MANIFEST_FIELD.search(script)
    assert len(one_liners) == 3 and manifest_field is not None
    return "\n".join([*one_liners, manifest_field.group(0)])


def _populator_section() -> str:
    found = _POPULATOR_SECTION.search(_POPULATE.read_text(encoding="utf-8"))
    assert found is not None, "no git object seed section in the populator"
    return found.group("body")


def _run_populator(
    *, root: Path, forge: str, budget_bytes: int = 134217728, budget_files: int = 64
) -> tuple[str, Path]:
    warm = root / "warm"
    warm.mkdir(exist_ok=True)
    scratch = root / "scratch"
    scratch.mkdir(exist_ok=True)
    harness = root / "harness.sh"
    harness.write_text(
        "\n".join(
            [
                "set -uo pipefail",
                f"WARM_ROOT={warm}",
                f"SCRATCH={scratch}",
                "KEEP_GENERATIONS=2",
                "WARM_FORCE_REBUILD_SECONDS=86400",
                f"WARM_GIT_BUDGET_BYTES={budget_bytes}",
                f"WARM_GIT_BUDGET_FILES={budget_files}",
                "WARM_GIT_RETAIN_SECONDS=21600",
                "WARM_CACHE_UV_ONLY=false",
                "failed=()",
                f"fetched=({_REPO_NAME})",
                "declare -A repo_url",
                f"repo_url[{_REPO_NAME}]={forge}",
                "generation=test-run",
                _populator_helpers(),
                _populator_section(),
                'printf "FAILED=%s\\n" "${failed[*]:-}"',
            ]
        ),
        encoding="utf-8",
    )
    done = subprocess.run(
        ["bash", str(harness)],
        env={**os.environ, **_GIT_IDENTITY},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    failed = re.search(r"^FAILED=(.*)$", done.stdout, re.MULTILINE)
    assert failed is not None
    return failed.group(1), warm


def _seed_dir(*, warm: Path) -> Path:
    link = warm / "git" / _REPO_NAME
    assert link.is_symlink(), "no generation was published"
    return link.resolve() / "objects"


def _has_object(*, seed: Path, sha: str, scratch: Path) -> bool:
    probe = scratch / "probe.git"
    if not probe.exists():
        _git("init", "-q", "--bare", str(probe), cwd=scratch)
    done = subprocess.run(
        ["git", "--git-dir", str(probe), "cat-file", "-e", sha],
        env={**os.environ, "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(seed)},
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def test_a_generation_holds_default_branch_and_tag_objects_and_no_pull_request_object(
    tmp_path: Path,
) -> None:
    shas = _forge(root=tmp_path)
    failed, warm = _run_populator(root=tmp_path, forge=shas["forge"])
    assert failed == ""
    seed = _seed_dir(warm=warm)
    for kept in ("first", "second"):
        assert _has_object(seed=seed, sha=shas[kept], scratch=tmp_path), kept
    assert _git("rev-parse", "v1^{tag}", cwd=tmp_path / "work")
    for excluded in ("pull", "side"):
        assert not _has_object(
            seed=seed, sha=shas[excluded], scratch=tmp_path
        ), f"{excluded} is not reachable from the default branch or a tag but is in the seed"
    manifest = json.loads((seed.parent / ".git-seed-manifest.json").read_text(encoding="utf-8"))
    assert manifest["default_branch"] == "main"
    assert manifest["default_tip"] == shas["second"]
    last_run = json.loads((warm / "git-seed-last-run.json").read_text(encoding="utf-8"))
    assert last_run["repos"][_REPO_NAME]["outcome"] == "built"


def test_a_checkout_with_the_seed_transfers_only_what_the_seed_lacks_and_lands_on_the_same_refs(
    tmp_path: Path,
) -> None:
    shas = _forge(root=tmp_path)
    _, warm = _run_populator(root=tmp_path, forge=shas["forge"])
    seed = _seed_dir(warm=warm)
    work = tmp_path / "work"
    _git("checkout", "-q", "main", cwd=work)
    newest = _commit(work=work, name="after-the-seed")
    _git("push", "-q", shas["forge"], "main", cwd=work)

    def fetch(*, name: str, alternates: Path | None) -> Path:
        job = tmp_path / f"job-{name}"
        job.mkdir()
        _git("init", "-q", cwd=job)
        env = {"GIT_ALTERNATE_OBJECT_DIRECTORIES": str(alternates)} if alternates else {}
        _git(
            "fetch", "-q", "--no-tags", shas["forge"],
            "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*",
            cwd=job, env=env,
        )  # fmt: skip
        return job

    def written(*, job: Path) -> int:
        return sum(1 for path in (job / ".git" / "objects").rglob("*") if path.is_file())

    cold = fetch(name="cold", alternates=None)
    warm_job = fetch(name="warm", alternates=seed)
    refs = lambda job: _git("for-each-ref", "--format=%(objectname) %(refname)", cwd=job)  # noqa: E731
    assert refs(warm_job) == refs(cold)
    assert _git("rev-parse", "refs/remotes/origin/main", cwd=warm_job) == newest
    assert written(job=warm_job) < written(job=cold)
    # every git process must see the seed: the job's objects reference it.
    _git("fsck", "--no-dangling", cwd=warm_job, env={"GIT_ALTERNATE_OBJECT_DIRECTORIES": str(seed)})


def test_a_generation_over_budget_is_refused_and_the_previous_one_stays_live(
    tmp_path: Path,
) -> None:
    shas = _forge(root=tmp_path)
    failed, warm = _run_populator(root=tmp_path, forge=shas["forge"], budget_files=1)
    assert failed == f"{_REPO_NAME}:git-over-budget"
    assert not (warm / "git" / _REPO_NAME).exists(), "an over-budget generation was published"
    assert list((warm / "git-generations" / _REPO_NAME).glob("*.refused"))
    failed, warm = _run_populator(root=tmp_path, forge=shas["forge"])
    assert failed == ""
    live = (warm / "git" / _REPO_NAME).resolve()
    work = tmp_path / "work"
    _git("checkout", "-q", "main", cwd=work)
    _commit(work=work, name="next")
    _git("push", "-q", shas["forge"], "main", cwd=work)
    failed, warm = _run_populator(root=tmp_path, forge=shas["forge"], budget_bytes=1)
    assert failed == f"{_REPO_NAME}:git-over-budget"
    assert (warm / "git" / _REPO_NAME).resolve() == live


def test_an_unchanged_default_branch_and_tag_set_builds_nothing(tmp_path: Path) -> None:
    shas = _forge(root=tmp_path)
    _, warm = _run_populator(root=tmp_path, forge=shas["forge"])
    first = (warm / "git" / _REPO_NAME).resolve()
    failed, warm = _run_populator(root=tmp_path, forge=shas["forge"])
    assert failed == ""
    assert (warm / "git" / _REPO_NAME).resolve() == first
    last_run = json.loads((warm / "git-seed-last-run.json").read_text(encoding="utf-8"))
    assert last_run["repos"][_REPO_NAME]["outcome"] == "unchanged"


def test_the_store_verifier_refuses_an_object_reachable_from_no_default_or_tag_ref(
    tmp_path: Path,
) -> None:
    function = _VERIFY_FUNCTION.search(_POPULATE.read_text(encoding="utf-8"))
    assert function is not None
    shas = _forge(root=tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    def verdict(*, store: Path) -> int:
        script = tmp_path / "verify.sh"
        script.write_text(
            "\n".join(
                [
                    f"SCRATCH={scratch}",
                    "log() { :; }",
                    function.group(0),
                    f'git_verify_store "{store}" main',
                ]
            ),
            encoding="utf-8",
        )
        return subprocess.run(["bash", str(script)], check=False, capture_output=True).returncode

    clean = tmp_path / "clean.git"
    _git("clone", "-q", "--bare", shas["forge"], str(clean), cwd=tmp_path)
    for ref in _git("for-each-ref", "--format=%(refname)", "refs/heads", cwd=clean).split():
        if ref != "refs/heads/main":
            _git("update-ref", "-d", ref, cwd=clean)
    _git("repack", "-a", "-d", "-q", cwd=clean)
    _git("prune", "--expire=now", cwd=clean)
    assert verdict(store=clean) == 0

    with_stray_ref = tmp_path / "stray.git"
    shutil.copytree(clean, with_stray_ref)
    _git("update-ref", "refs/pull/1/head", shas["second"], cwd=with_stray_ref)
    assert verdict(store=with_stray_ref) == 1, "a pull-request ref was accepted"

    with_orphan = tmp_path / "orphan.git"
    shutil.copytree(clean, with_orphan)
    blob = subprocess.run(
        ["git", "--git-dir", str(with_orphan), "hash-object", "-w", "--stdin"],
        input="pull-request-only",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert blob
    assert verdict(store=with_orphan) == 1, "an object reachable from no ref was accepted"


# ---- the provisioner's seed -------------------------------------------------


def _setup_script() -> str:
    found = _SETUP_SCRIPT.search(_PROVISIONER.read_text(encoding="utf-8"))
    assert found is not None
    return "\n".join(line[4:] for line in found.group("body").splitlines()) + "\n"


def _node_with_git_generations(*, root: Path, repos: tuple[str, ...]) -> Path:
    node = root / "storage"
    for repo in repos:
        generation = node / ".warm" / "git-generations" / repo / "20261104T000000Z"
        (generation / "objects" / "pack").mkdir(parents=True)
        (generation / "objects" / "pack" / "pack-1.pack").write_text(repo, encoding="utf-8")
        (node / ".warm" / "git").mkdir(exist_ok=True)
        (node / ".warm" / "git" / repo).symlink_to(f"../git-generations/{repo}/20261104T000000Z")
    return node


def _provision(*, root: Path, node: Path, claim: str) -> Path:
    shim_dir = root / "shim"
    shim_dir.mkdir(exist_ok=True)
    shim = shim_dir / "cp"
    shim.write_text(
        '#!/bin/sh\nfor a in "$@"; do shift; [ "$a" = --reflink=always ] || set -- "$@" "$a"; done\n'
        'exec /bin/cp "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    script = root / "setup"
    script.write_text(_setup_script(), encoding="utf-8")
    vol_dir = node / f"pvc-0000_arc-runners_{claim}"
    done = subprocess.run(
        ["/bin/sh", str(script)],
        env={
            **os.environ,
            "PATH": f"{shim_dir}:{os.environ['PATH']}",
            "VOL_DIR": str(vol_dir),
            "VOL_MODE": "Filesystem",
            "VOL_SIZE_BYTES": "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return vol_dir


def test_a_volume_is_seeded_with_its_own_repositorys_objects_and_no_other(
    tmp_path: Path,
) -> None:
    node = _node_with_git_generations(root=tmp_path, repos=("livespec-runtime", "livespec"))
    volume = _provision(root=tmp_path, node=node, claim=f"livespec-runtime-k3s-{_CLAIM_SUFFIX}")
    seeded = volume / "_warm" / "git"
    assert [path.name for path in seeded.iterdir()] == ["livespec-runtime"]
    assert (seeded / "livespec-runtime" / "objects" / "pack" / "pack-1.pack").read_text(
        encoding="utf-8"
    ) == "livespec-runtime"
    assert (seeded / "livespec-runtime" / ".generation").read_text(
        encoding="utf-8"
    ).strip() == "20261104T000000Z"


@pytest.mark.parametrize(
    "claim",
    ["runner-x-work", f"unknown-k3s-{_CLAIM_SUFFIX}"],
)
def test_a_claim_no_scale_set_owns_gets_no_git_seed(tmp_path: Path, claim: str) -> None:
    node = _node_with_git_generations(root=tmp_path, repos=("livespec-runtime",))
    volume = _provision(root=tmp_path, node=node, claim=claim)
    assert not (volume / "_warm" / "git").exists()


def test_a_repository_with_no_published_generation_gets_no_git_seed(tmp_path: Path) -> None:
    node = _node_with_git_generations(root=tmp_path, repos=("livespec",))
    volume = _provision(root=tmp_path, node=node, claim=f"livespec-runtime-k3s-{_CLAIM_SUFFIX}")
    assert not (volume / "_warm" / "git").exists()


@pytest.mark.parametrize("values", _VALUES, ids=lambda path: path.name)
def test_the_claim_table_maps_every_scale_set_to_the_repository_it_serves(
    tmp_path: Path, values: Path
) -> None:
    text = values.read_text(encoding="utf-8")
    scale_set = re.search(r'^runnerScaleSetName:\s*"([^"]+)"', text, re.MULTILINE)
    url = re.search(r'^githubConfigUrl:\s*"https://github.com/[^/]+/([^"]+)"', text, re.MULTILINE)
    assert scale_set is not None and url is not None
    served = url.group(1)
    all_repos = tuple(
        re.search(
            r'^githubConfigUrl:\s*"https://github.com/[^/]+/([^"]+)"',
            v.read_text(encoding="utf-8"),
            re.MULTILINE,
        ).group(1)  # type: ignore[union-attr]
        for v in _VALUES
    )
    node = _node_with_git_generations(root=tmp_path, repos=tuple(sorted(set(all_repos))))
    volume = _provision(root=tmp_path, node=node, claim=f"{scale_set.group(1)}-{_CLAIM_SUFFIX}")
    seeded = sorted(path.name for path in (volume / "_warm" / "git").iterdir())
    assert seeded == [served], f"{scale_set.group(1)} serves {served} but its volume got {seeded}"


# ---- the container hook entry point ----------------------------------------

_needs_node = pytest.mark.skipif(_NODE is None, reason="node is not installed")


def _template(*, switch: str = "", canary: str = "20") -> str:
    text = _TEMPLATE.read_text(encoding="utf-8")
    text = re.sub(
        r'(name: CI_CACHE_KILL_SWITCH\n\s+value: )""', lambda m: f'{m.group(1)}"{switch}"', text
    )
    return re.sub(
        r'(name: CI_CACHE_CANARY_N\n\s+value: )"\d+"', lambda m: f'{m.group(1)}"{canary}"', text
    )


def _hook_run(
    *,
    root: Path,
    command: str = "prepare_job",
    seeded: bool = True,
    template: str | None = None,
    pod: str = "livespec-runtime-k3s-abcde-runner-fghij",
    workspace_repo: str = _REPO_NAME,
    exit_code: int = 0,
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run git-seed-hook.js against a fake real hook; return the run and the line it received."""
    work = root / "_work"
    (work / workspace_repo).mkdir(parents=True)
    if seeded:
        (work / "_warm" / "git" / workspace_repo / "objects" / "pack").mkdir(parents=True)
    (root / "template.yaml").write_text(template or _template(), encoding="utf-8")
    real = root / "real-hook.js"
    real.write_text(
        "const fs = require('fs')\n"
        f"fs.writeFileSync({json.dumps(str(root / 'received'))}, fs.readFileSync(0))\n"
        "process.stdout.write('real-hook-output')\n"
        f"process.exit({exit_code})\n",
        encoding="utf-8",
    )
    payload = {
        "command": command,
        "responseFile": "/tmp/response",
        "args": {"container": {"image": "x", "environmentVariables": {"CI": "true"}}},
        "state": {},
    }
    assert _NODE is not None
    done = subprocess.run(
        [_NODE, str(_WRAPPER)],
        input=json.dumps(payload) + "\n",
        env={
            "PATH": os.environ["PATH"],
            "RUNNER_WORKSPACE": str(work / workspace_repo),
            "ACTIONS_RUNNER_POD_NAME": pod,
            "ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE": str(root / "template.yaml"),
            "FLEET_REAL_CONTAINER_HOOK": str(real),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return done, (root / "received").read_text(encoding="utf-8")


def _container_env(*, received: str) -> dict[str, str]:
    return json.loads(received)["args"]["container"]["environmentVariables"]


def _non_canary_pod() -> str:
    pod = "livespec-runtime-k3s-abcde-runner-00001"
    checksum = int(
        subprocess.run(
            ["cksum"], input=f"{pod}-workflow", text=True, capture_output=True, check=True
        ).stdout.split()[0]
    )
    assert checksum % 20 != 0, "the fixture pod is the canary at the template's N"
    return pod


@_needs_node
def test_the_hook_names_the_jobs_own_seed_when_it_exists(tmp_path: Path) -> None:
    done, received = _hook_run(root=tmp_path, pod=_non_canary_pod())
    assert done.returncode == 0 and done.stdout == "real-hook-output"
    environment = _container_env(received=received)
    assert environment["GIT_ALTERNATE_OBJECT_DIRECTORIES"] == (
        f"/__w/_warm/git/{_REPO_NAME}/objects"
    )
    assert environment["CI"] == "true", "an unrelated variable of the job container changed"


@_needs_node
def test_the_hook_names_nothing_when_the_seed_is_missing_or_unreadable(tmp_path: Path) -> None:
    pod = _non_canary_pod()
    done, received = _hook_run(root=tmp_path / "missing", seeded=False, pod=pod)
    assert done.returncode == 0
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in _container_env(received=received)
    broken = tmp_path / "broken"
    (broken / "_work" / "_warm" / "git" / _REPO_NAME).mkdir(parents=True)
    (broken / "_work" / "_warm" / "git" / _REPO_NAME / "objects").write_text("x", encoding="utf-8")
    done, received = _hook_run(root=broken, seeded=False, pod=pod)
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in _container_env(received=received)


@_needs_node
def test_the_hook_never_names_another_repositorys_seed(tmp_path: Path) -> None:
    pod = _non_canary_pod()
    root = tmp_path
    (root / "_work" / "_warm" / "git" / "livespec" / "objects").mkdir(parents=True)
    done, received = _hook_run(root=root, seeded=False, pod=pod)
    assert done.returncode == 0
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in _container_env(received=received)


@_needs_node
def test_the_fleet_kill_switch_removes_the_variable_and_the_canary_is_not_the_switch(
    tmp_path: Path,
) -> None:
    pod = _non_canary_pod()
    _, received = _hook_run(root=tmp_path / "off", template=_template(switch="operator"), pod=pod)
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in _container_env(received=received)
    _, received = _hook_run(root=tmp_path / "on", template=_template(switch=""), pod=pod)
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" in _container_env(received=received)
    _, received = _hook_run(root=tmp_path / "canary", template=_template(canary="1"), pod=pod)
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in _container_env(
        received=received
    ), "every pod is the canary at N=1, and the canary job runs cold"
    _, received = _hook_run(root=tmp_path / "no-canary", template=_template(canary="0"), pod=pod)
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" in _container_env(received=received)


@_needs_node
def test_the_hooks_canary_choice_is_the_one_the_post_start_script_makes(tmp_path: Path) -> None:
    pods = [f"livespec-runtime-k3s-abcde-runner-{index:05d}" for index in range(40)] + ["p" * 80]
    assert _NODE is not None
    for index, pod in enumerate(pods):
        job_pod = f"{pod[:54]}-workflow"
        shell = int(
            subprocess.run(
                ["cksum"], input=job_pod, text=True, capture_output=True, check=True
            ).stdout.split()[0]
        )
        _, received = _hook_run(
            root=tmp_path / f"pod-{index}", pod=pod, template=_template(canary="3")
        )
        named = "GIT_ALTERNATE_OBJECT_DIRECTORIES" in _container_env(received=received)
        assert named == (shell % 3 != 0), pod


@_needs_node
def test_every_other_command_reaches_the_real_hook_unchanged_and_its_exit_status_is_kept(
    tmp_path: Path,
) -> None:
    done, received = _hook_run(root=tmp_path / "step", command="run_script_step", exit_code=7)
    assert done.returncode == 7 and done.stdout == "real-hook-output"
    assert json.loads(received)["command"] == "run_script_step"
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in _container_env(received=received)


@_needs_node
def test_the_hook_reads_the_switch_and_canary_from_the_committed_template_shape() -> None:
    template = _TEMPLATE.read_text(encoding="utf-8")
    assert _NODE is not None
    read = subprocess.run(
        [
            _NODE,
            "-e",
            "const h = require(process.argv[1]); const t = require('fs').readFileSync(process.argv[2], 'utf8');"
            "console.log(JSON.stringify([h.templateValue(t, 'CI_CACHE_KILL_SWITCH'), h.templateValue(t, 'CI_CACHE_CANARY_N')]))",
            str(_WRAPPER),
            str(_TEMPLATE),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(read) == [
        "",
        re.search(r'CI_CACHE_CANARY_N\n\s+value: "(\d+)"', template).group(1),
    ]  # type: ignore[union-attr]


# ---- the postStart record and the wiring ----------------------------------


def _post_start(*, root: Path, seeded: bool, switch: str = "") -> dict[str, str]:
    template = _TEMPLATE.read_text(encoding="utf-8")
    block = re.search(
        r"        postStart:\n          exec:\n            command:\n              - sh\n"
        r"              - -c\n              - \|\n(?P<body>(?:                [^\n]*\n|\n)*)",
        template,
    )
    assert block is not None
    script = "\n".join(
        line[16:] if line.startswith(" " * 16) else line
        for line in block.group("body").splitlines()
    )
    work = root / "w"
    (work / "_warm").mkdir(parents=True)
    env = {
        "PATH": os.environ["PATH"],
        "HOSTNAME": "runner-abc-default",
        "CI_CACHE_KILL_SWITCH": switch,
    }
    if seeded:
        seed = work / "_warm" / "git" / _REPO_NAME
        (seed / "objects").mkdir(parents=True)
        (seed / ".generation").write_text("20261104T000000Z\n", encoding="utf-8")
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(seed / "objects")
    for absolute, local in (
        ("/__w", work),
        ("/.cargo", root / "cargo"),
        ("/opt/ci-runner/bin", root / "bin"),
    ):
        script = script.replace(absolute, str(local))
    hook = root / "post-start.sh"
    hook.write_text(script, encoding="utf-8")
    done = subprocess.run(["sh", str(hook)], env=env, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    columns = (
        "at_ns",
        "tier",
        "hit",
        "generation",
        "copy_ms",
        "copy_bytes",
        "copy_method",
        "error",
    )
    rows = (work / "_temp" / "_ci_cache" / "warm-copy.tsv").read_text(encoding="utf-8").splitlines()
    parsed = [dict(zip(columns, (row.split("\t") + [""] * 8)[:8], strict=True)) for row in rows]
    git_rows = [row for row in parsed if row["tier"] == "git"]
    assert len(git_rows) == 1, "exactly one git-tier row per job"
    return git_rows[0]


def test_a_seeded_job_records_a_git_hit_with_its_generation(tmp_path: Path) -> None:
    row = _post_start(root=tmp_path, seeded=True)
    assert (row["hit"], row["generation"], row["error"]) == ("true", "20261104T000000Z", "")


def test_a_job_with_no_seed_records_a_git_miss_with_a_reason(tmp_path: Path) -> None:
    row = _post_start(root=tmp_path, seeded=False)
    assert (row["hit"], row["error"]) == ("false", "git-seed-absent")


def test_the_kill_switch_records_the_git_tier_cold_and_removes_the_seed(tmp_path: Path) -> None:
    row = _post_start(root=tmp_path, seeded=True, switch="operator")
    assert (row["hit"], row["error"]) == ("false", "off:operator")
    assert not (tmp_path / "w" / "_warm" / "git").exists()


def test_every_values_file_runs_the_pools_hook_entry_point_over_the_patched_hook() -> None:
    for values in [*_VALUES, _PHASE2 / "arc" / "values-EXAMPLE-repo.yaml"]:
        text = values.read_text(encoding="utf-8")
        assert re.search(
            r"- name: ACTIONS_RUNNER_CONTAINER_HOOKS\n(?:\s+#[^\n]*\n)*\s+value: "
            r"/home/runner/hook-template/git-seed-hook\.js\n",
            text,
        ), values.name
        assert "mountPath: /home/runner/fleet-hook/index.js" in text, values.name
        assert "mountPath: /home/runner/hook-template" in text, values.name


def test_the_hook_entry_point_travels_in_the_template_configmap() -> None:
    converge = (_PHASE2 / "arc" / "converge-hook-pod-template.sh").read_text(encoding="utf-8")
    assert '--from-file="git-seed-hook.js=${HOOK_SRC}"' in converge
    role = (_REPO / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml").read_text(
        encoding="utf-8"
    )
    assert "src: arc/git-seed-hook.js" in role


def test_the_git_budget_lives_beside_the_uv_budget_and_reaches_the_populator() -> None:
    cronjob = (_PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml").read_text(encoding="utf-8")
    assert re.search(r'^  git-bytes: "\d+"$', cronjob, re.MULTILINE)
    assert re.search(r'^  git-files: "\d+"$', cronjob, re.MULTILINE)
    for variable, key in (
        ("WARM_GIT_BUDGET_BYTES", "git-bytes"),
        ("WARM_GIT_BUDGET_FILES", "git-files"),
    ):
        assert re.search(
            rf"name: {variable}\n\s+valueFrom:\n\s+configMapKeyRef:\n\s+name: warm-cache-budget\n\s+key: {key}\n",
            cronjob,
        ), variable
