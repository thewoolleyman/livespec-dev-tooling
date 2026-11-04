"""The action archive seed tier (livespec-dev-tooling-a35sa4), executed rather than read.

SPECIFICATION "Runner-pool build cache tiers" requires a SEEDED tree holding the
archive of every `uses:` action ref pinned on the routed repositories' default
branches, addressed by owner, repository and resolved commit SHA; a runner that reads
it through ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE before it downloads; a populator that
adds a newly pinned ref on its next run; and a job that downloads as it would without
the tier when an archive is missing, the tree is unreadable, or the fleet kill switch
or the cold canary is on. The committed artifacts that carry that are each RUN here
under the shell they ship for:

  - the populator's action archive section (`warm-cache-populate.sh`, step 4b)
    against a local "forge" of git repositories and tarballs;
  - the provisioner's `setup` script against a scratch node path;
  - `arc/action-archive-entry.sh`, the runner container's command, against a fake
    `run.sh` that records the environment it is handed;
  - the hook pod template's postStart script, which records the tier.

The part of the Definition of Done that exists only on the k3s pool (a routed job whose
Set up job log shows no codeload download) stays host-captured.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO / "ci-runner" / "k3s" / "phase2"
_POPULATE = _PHASE2 / "warm-cache" / "warm-cache-populate.sh"
_PROVISIONER = _PHASE2 / "local-path-provisioner" / "local-path-provisioner.yaml"
_ENTRY = _PHASE2 / "arc" / "action-archive-entry.sh"
_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_CRONJOB = _PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml"
_VALUES = sorted(
    path for path in (_PHASE2 / "arc").glob("values-*.yaml") if "EXAMPLE" not in path.name
)
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
_CONSUMER = "consumer"
_SETUP_SCRIPT = re.compile(r"^  setup: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)
_POPULATOR_SECTION = re.compile(
    r"^(?P<body>ACTIONS_GEN_ROOT=.*?)\n\nlog \"run summary:", re.MULTILINE | re.DOTALL
)
_ONE_LINE_HELPER = re.compile(r"^(?:log|gen_bytes|gen_files)\(\) \{.*$", re.MULTILINE)
_MANIFEST_FIELD = re.compile(r"^manifest_field\(\) \{\n.*?\n\}$", re.MULTILINE | re.DOTALL)


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **_GIT_IDENTITY},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


class _Forge:
    """Local stand-in for github.com (git) and codeload.github.com (tarballs)."""

    def __init__(self, *, root: Path) -> None:
        self.git_base = root / "forge"
        self.archive_base = root / "codeload"
        self._work = root / "forge-work"
        self.git_base.mkdir()
        self.archive_base.mkdir()
        self._work.mkdir()

    def repository(self, *, owner: str, name: str) -> Path:
        work = self._work / owner / name
        if not work.exists():
            work.mkdir(parents=True)
            _git("init", "-q", "-b", "main", cwd=work)
        return work

    def commit(self, *, owner: str, name: str, content: str) -> str:
        work = self.repository(owner=owner, name=name)
        (work / "action.yml").write_text(content, encoding="utf-8")
        _git("add", "action.yml", cwd=work)
        _git("commit", "-q", "-m", content, cwd=work)
        return _git("rev-parse", "HEAD", cwd=work)

    def tag(self, *, owner: str, name: str, tag: str, annotated: bool) -> None:
        work = self.repository(owner=owner, name=name)
        args = ["tag", "-f", *(["-a", "-m", tag] if annotated else []), tag]
        _git(*args, cwd=work)

    def publish(self, *, owner: str, name: str) -> None:
        work = self.repository(owner=owner, name=name)
        bare = self.git_base / owner / f"{name}.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        if not bare.exists():
            _git("init", "-q", "--bare", "-b", "main", str(bare), cwd=work)
        _git("push", "-q", "--force", str(bare), "main", "--tags", cwd=work)
        for sha in _git("rev-list", "--all", cwd=work).split():
            self.archive_for(owner=owner, name=name, sha=sha)

    def archive_for(self, *, owner: str, name: str, sha: str) -> Path:
        work = self.repository(owner=owner, name=name)
        target = self.archive_base / owner / name / "tar.gz" / sha
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(
            "archive",
            "--format=tar.gz",
            f"--prefix={owner}-{name}-{sha[:7]}/",
            "-o",
            str(target),
            sha,
            cwd=work,
        )
        return target


def _consumer_workflow(*, root: Path, text: str) -> None:
    workflows = root / "src" / _CONSUMER / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "ci.yml").write_text(text, encoding="utf-8")


def _populator_helpers() -> str:
    script = _POPULATE.read_text(encoding="utf-8")
    one_liners = _ONE_LINE_HELPER.findall(script)
    manifest_field = _MANIFEST_FIELD.search(script)
    assert len(one_liners) == 3 and manifest_field is not None
    return "\n".join([*one_liners, manifest_field.group(0)])


def _populator_section() -> str:
    found = _POPULATOR_SECTION.search(_POPULATE.read_text(encoding="utf-8"))
    assert found is not None, "no action archive seed section in the populator"
    return found.group("body")


def _run_populator(
    *,
    root: Path,
    forge: _Forge,
    budget_bytes: int = 268435456,
    budget_files: int = 512,
    fetched: tuple[str, ...] = (_CONSUMER,),
) -> tuple[str, Path]:
    warm = root / "warm"
    warm.mkdir(exist_ok=True)
    scratch = root / "scratch"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    harness = root / "harness.sh"
    harness.write_text(
        "\n".join(
            [
                "set -uo pipefail",
                f"WARM_ROOT={warm}",
                f"SRC_DIR={root / 'src'}",
                f"SCRATCH={scratch}",
                "KEEP_GENERATIONS=2",
                "WARM_FORCE_REBUILD_SECONDS=86400",
                f"WARM_ACTIONS_BUDGET_BYTES={budget_bytes}",
                f"WARM_ACTIONS_BUDGET_FILES={budget_files}",
                "WARM_ACTIONS_RETAIN_SECONDS=21600",
                f"ACTIONS_GIT_BASE={forge.git_base}",
                f"ACTIONS_ARCHIVE_BASE=file://{forge.archive_base}",
                "WARM_CACHE_UV_ONLY=false",
                "failed=()",
                f"fetched=({' '.join(fetched)})",
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


def _live(*, warm: Path) -> Path:
    link = warm / "actions"
    assert link.is_symlink(), "no generation was published"
    return link.resolve()


def _archives(*, warm: Path) -> dict[str, Path]:
    root = _live(warm=warm) / "archives"
    return {str(path.relative_to(root)): path for path in sorted(root.rglob("*.tar.gz"))}


def _tree_names(*, archive: Path) -> set[str]:
    with tarfile.open(archive) as handle:
        return {
            member.name.split("/", 1)[1] for member in handle.getmembers() if "/" in member.name
        }


_FOUR_PINS = """\
name: ci
on: [push]
jobs:
  build:
    uses: acme/shared/.github/workflows/reusable.yml@v1
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: acme/setup@v1
      - uses: "acme/setup/sub/path@v1"  # same repository, same archive
      - uses: other/tool@{sha}
      # - uses: commented/out@v1
      - uses: ./.github/actions/local
      - uses: docker://alpine:3
"""


def _seed_forge(*, root: Path) -> tuple[_Forge, dict[str, str]]:
    forge = _Forge(root=root)
    shas = {
        "setup": forge.commit(owner="acme", name="setup", content="setup-one"),
        "tool": forge.commit(owner="other", name="tool", content="tool-one"),
        "shared": forge.commit(owner="acme", name="shared", content="shared-one"),
    }
    forge.tag(owner="acme", name="setup", tag="v1", annotated=True)
    forge.publish(owner="acme", name="setup")
    forge.publish(owner="other", name="tool")
    forge.publish(owner="acme", name="shared")
    _consumer_workflow(root=root, text=_FOUR_PINS.replace("{sha}", shas["tool"]))
    return forge, shas


def test_every_pinned_action_ref_is_filed_by_owner_repository_and_resolved_commit(
    tmp_path: Path,
) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    failed, warm = _run_populator(root=tmp_path, forge=forge)
    assert failed == ""
    assert (
        sorted(_archives(warm=warm))
        == sorted([f"acme_setup/{shas['setup']}.tar.gz", f"other_tool/{shas['tool']}.tar.gz"])
    ), "an annotated tag files under its COMMIT; local, docker, commented and reusable-workflow uses are not actions"
    manifest = json.loads((_live(warm=warm) / ".actions-seed-manifest.json").read_text("utf-8"))
    assert manifest["generation_files"] == 2 and manifest["budget_files"] == 512


def test_an_archive_is_the_forges_tree_at_the_sha_so_a_moved_tag_cannot_alias_an_old_key(
    tmp_path: Path,
) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    _, warm = _run_populator(root=tmp_path, forge=forge)
    old = _archives(warm=warm)[f"acme_setup/{shas['setup']}.tar.gz"]
    assert "action.yml" in _tree_names(archive=old)
    moved = forge.commit(owner="acme", name="setup", content="setup-two")
    forge.tag(owner="acme", name="setup", tag="v1", annotated=True)
    forge.publish(owner="acme", name="setup")
    failed, warm = _run_populator(root=tmp_path, forge=forge)
    assert failed == ""
    archives = _archives(warm=warm)
    assert f"acme_setup/{moved}.tar.gz" in archives
    assert (
        f"acme_setup/{shas['setup']}.tar.gz" not in archives
    ), "the old key is not served for the moved tag"
    with tarfile.open(archives[f"acme_setup/{moved}.tar.gz"]) as handle:
        member = next(m for m in handle.getmembers() if m.name.endswith("/action.yml"))
        extracted = handle.extractfile(member)
        assert extracted is not None and extracted.read().decode("utf-8") == "setup-two"


def test_a_newly_pinned_ref_is_added_by_the_next_run_and_unchanged_archives_are_reused(
    tmp_path: Path,
) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    _, warm = _run_populator(root=tmp_path, forge=forge)
    before = _archives(warm=warm)
    reused_inode = before[f"acme_setup/{shas['setup']}.tar.gz"].stat().st_ino
    extra = forge.commit(owner="late", name="addition", content="added-later")
    forge.publish(owner="late", name="addition")
    _consumer_workflow(
        root=tmp_path,
        text=_FOUR_PINS.replace("{sha}", shas["tool"]) + f"      - uses: late/addition@{extra}\n",
    )
    failed, warm = _run_populator(root=tmp_path, forge=forge)
    after = _archives(warm=warm)
    assert failed == "" and f"late_addition/{extra}.tar.gz" in after
    assert set(before) < set(after)
    assert after[f"acme_setup/{shas['setup']}.tar.gz"].stat().st_ino == reused_inode


def test_an_unchanged_set_of_pins_builds_nothing(tmp_path: Path) -> None:
    forge, _ = _seed_forge(root=tmp_path)
    _, warm = _run_populator(root=tmp_path, forge=forge)
    first = _live(warm=warm)
    _, warm = _run_populator(root=tmp_path, forge=forge)
    assert _live(warm=warm) == first
    assert len(list((warm / "actions-generations").iterdir())) == 1
    last = json.loads((warm / "actions-seed-last-run.json").read_text("utf-8"))
    assert last["outcome"] == "unchanged"


def test_a_tree_over_budget_is_refused_and_the_previous_generation_stays_live(
    tmp_path: Path,
) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    _, warm = _run_populator(root=tmp_path, forge=forge)
    first = _live(warm=warm)
    extra = forge.commit(owner="late", name="addition", content="added-later")
    forge.publish(owner="late", name="addition")
    _consumer_workflow(
        root=tmp_path,
        text=_FOUR_PINS.replace("{sha}", shas["tool"]) + f"      - uses: late/addition@{extra}\n",
    )
    failed, warm = _run_populator(root=tmp_path, forge=forge, budget_files=2)
    assert "actions:over-budget" in failed
    assert _live(warm=warm) == first
    assert json.loads((warm / "actions-seed-last-run.json").read_text("utf-8"))["refused"] == 1


def test_a_ref_the_forge_cannot_resolve_is_named_and_the_rest_still_publish(
    tmp_path: Path,
) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    _consumer_workflow(
        root=tmp_path,
        text=_FOUR_PINS.replace("{sha}", shas["tool"]) + "      - uses: acme/setup@v99\n",
    )
    failed, warm = _run_populator(root=tmp_path, forge=forge)
    assert failed == "actions:acme/setup@v99:resolve"
    assert f"acme_setup/{shas['setup']}.tar.gz" in _archives(warm=warm)


def test_a_download_that_is_not_the_archive_of_its_sha_is_never_published(tmp_path: Path) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    wrong = forge.archive_for(owner="acme", name="shared", sha=shas["shared"])
    served = forge.archive_base / "acme" / "setup" / "tar.gz" / shas["setup"]
    served.write_bytes(wrong.read_bytes())
    failed, warm = _run_populator(root=tmp_path, forge=forge)
    assert failed == "actions:acme/setup@v1:fetch"
    assert list(_archives(warm=warm)) == [f"other_tool/{shas['tool']}.tar.gz"]


def test_only_the_workflows_of_fetched_default_branch_clones_are_read(tmp_path: Path) -> None:
    forge, shas = _seed_forge(root=tmp_path)
    stray = tmp_path / "src" / "not-fetched" / ".github" / "workflows"
    stray.mkdir(parents=True)
    (stray / "ci.yml").write_text(f"steps:\n  - uses: acme/shared@{shas['shared']}\n", "utf-8")
    failed, warm = _run_populator(root=tmp_path, forge=forge)
    assert failed == "" and not any(name.startswith("acme_shared") for name in _archives(warm=warm))


# ---- the provisioner's seed -------------------------------------------------


def _setup_script() -> str:
    found = _SETUP_SCRIPT.search(_PROVISIONER.read_text(encoding="utf-8"))
    assert found is not None
    return "\n".join(line[4:] for line in found.group("body").splitlines()) + "\n"


def _node_with_actions_generation(*, root: Path) -> Path:
    node = root / "storage"
    generation = node / ".warm" / "actions-generations" / "20261104T000000Z"
    (generation / "archives" / "acme_setup").mkdir(parents=True)
    (generation / "archives" / "acme_setup" / f"{'a' * 40}.tar.gz").write_text(
        "archive", encoding="utf-8"
    )
    (node / ".warm" / "actions").symlink_to("actions-generations/20261104T000000Z")
    return node


def _provision(*, root: Path, node: Path, claim: str, reflink_fails: bool = False) -> Path:
    shim_dir = root / "shim"
    shim_dir.mkdir(exist_ok=True)
    shim = shim_dir / "cp"
    refuse = (
        'for a in "$@"; do [ "$a" = --reflink=always ] && exit 1; done\n' if reflink_fails else ""
    )
    shim.write_text(
        "#!/bin/sh\n"
        + refuse
        + 'for a in "$@"; do shift; [ "$a" = --reflink=always ] || set -- "$@" "$a"; done\n'
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


@pytest.mark.parametrize("claim", ["livespec-runtime-k3s-abc-runner-def-work", "runner-x-work"])
def test_every_volume_is_born_with_the_pools_archive_tree_and_its_generation(
    tmp_path: Path, claim: str
) -> None:
    node = _node_with_actions_generation(root=tmp_path)
    volume = _provision(root=tmp_path, node=node, claim=claim)
    seeded = volume / "_warm" / "actions"
    assert (seeded / "archives" / "acme_setup" / f"{'a' * 40}.tar.gz").read_text(
        "utf-8"
    ) == "archive"
    assert (seeded / ".generation").read_text("utf-8").strip() == "20261104T000000Z"
    assert (seeded / "archives").stat().st_ino != (
        node / ".warm" / "actions-generations" / "20261104T000000Z" / "archives"
    ).stat().st_ino, "a private copy, never the shared tree"


def test_a_node_with_no_published_tree_seeds_nothing(tmp_path: Path) -> None:
    (tmp_path / "storage" / ".warm").mkdir(parents=True)
    volume = _provision(root=tmp_path, node=tmp_path / "storage", claim="runner-x-work")
    assert not (volume / "_warm" / "actions").exists()


def test_a_failed_reflink_copy_leaves_no_archive_seed(tmp_path: Path) -> None:
    node = _node_with_actions_generation(root=tmp_path)
    volume = _provision(root=tmp_path, node=node, claim="runner-x-work", reflink_fails=True)
    assert not (volume / "_warm" / "actions").exists()


# ---- the runner container's entry point -------------------------------------


def _template(*, switch: str = "", canary: str = "20") -> str:
    return (
        "spec:\n  containers:\n    - name: $job\n      env:\n"
        f'        - name: CI_CACHE_KILL_SWITCH\n          value: "{switch}"\n'
        f'        - name: CI_CACHE_CANARY_N\n          value: "{canary}"\n'
    )


def _canary_status(*, runner_pod: str, canary: int = 20) -> bool:
    name = f"{runner_pod[:54]}-workflow"
    crc = subprocess.run(
        ["cksum"], input=name, capture_output=True, text=True, check=True
    ).stdout.split()[0]
    return int(crc) % canary == 0


def _pod_name(*, canary: bool) -> str:
    names = (f"livespec-runtime-k3s-abcde-runner-{index:05d}" for index in range(2000))
    return next(name for name in names if _canary_status(runner_pod=name) == canary)


def _enter(
    *,
    root: Path,
    template: str | None,
    pod: str,
    tree: bool = True,
    tree_is_file: bool = False,
    inherited: str | None = None,
    exit_code: int = 0,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    seed = root / "work" / "_warm" / "actions" / "archives"
    if tree and tree_is_file:
        seed.parent.mkdir(parents=True)
        seed.write_text("not a directory", encoding="utf-8")
    elif tree:
        seed.mkdir(parents=True)
    fake_run = root / "run.sh"
    fake_run.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "${ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE-UNSET}" > "$0.env"\n'
        'printf "%s\\n" "$@" > "$0.args"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = {
        "PATH": os.environ["PATH"],
        "ACTIONS_RUNNER_POD_NAME": pod,
        "ACTION_ARCHIVE_SEED_DIR": str(seed),
        "RUNNER_RUN_SH": str(fake_run),
    }
    if template is not None:
        template_path = root / "hook-pod-template.yaml"
        template_path.write_text(template, encoding="utf-8")
        env["ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE"] = str(template_path)
    if inherited is not None:
        env["ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE"] = inherited
    done = subprocess.run(
        ["bash", str(_ENTRY), "--startuptype", "service"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    seen = {
        "cache": (root / "run.sh.env").read_text("utf-8").strip(),
        "args": (root / "run.sh.args").read_text("utf-8"),
        "seed": str(seed),
    }
    return done, seen


def test_the_runner_is_told_the_seeded_tree_when_the_tiers_are_on(tmp_path: Path) -> None:
    done, seen = _enter(root=tmp_path, template=_template(), pod=_pod_name(canary=False))
    assert done.returncode == 0, done.stderr
    assert seen["cache"] == seen["seed"]
    assert (
        seen["args"] == "--startuptype\nservice\n"
    ), "run.sh gets the container's arguments unchanged"


def test_the_fleet_kill_switch_leaves_the_variable_unset_and_clears_an_inherited_one(
    tmp_path: Path,
) -> None:
    done, seen = _enter(
        root=tmp_path,
        template=_template(switch="operator"),
        pod=_pod_name(canary=False),
        inherited="/somewhere/else",
    )
    assert done.returncode == 0 and seen["cache"] == "UNSET"


def test_the_cold_canary_runs_without_the_tier_and_a_non_canary_pod_does_not(
    tmp_path: Path,
) -> None:
    _, canary_seen = _enter(
        root=tmp_path / "canary", template=_template(), pod=_pod_name(canary=True)
    )
    _, warm_seen = _enter(root=tmp_path / "warm", template=_template(), pod=_pod_name(canary=False))
    assert canary_seen["cache"] == "UNSET" and warm_seen["cache"] == warm_seen["seed"]


@pytest.mark.parametrize("canary", ["", "0", "off", "5"])
def test_the_canary_rule_is_the_one_the_post_start_script_applies(
    tmp_path: Path, canary: str
) -> None:
    pods = [f"livespec-runtime-k3s-abcde-runner-{index:05d}" for index in range(60)]
    for index, pod in enumerate(pods):
        _, seen = _enter(root=tmp_path / str(index), template=_template(canary=canary), pod=pod)
        sampled = (
            canary.isdigit()
            and int(canary) > 0
            and _canary_status(runner_pod=pod, canary=int(canary))
        )
        assert (seen["cache"] == "UNSET") == bool(sampled), (canary, pod)


def test_a_missing_or_unreadable_tree_or_template_leaves_the_variable_unset(tmp_path: Path) -> None:
    pod = _pod_name(canary=False)
    _, no_tree = _enter(root=tmp_path / "a", template=_template(), pod=pod, tree=False)
    _, no_template = _enter(root=tmp_path / "b", template=None, pod=pod)
    assert no_tree["cache"] == "UNSET" and no_template["cache"] == "UNSET"
    _, not_a_directory = _enter(
        root=tmp_path / "c", template=_template(), pod=pod, tree_is_file=True
    )
    assert not_a_directory["cache"] == "UNSET"


def test_the_entry_point_hands_run_sh_exit_status_back(tmp_path: Path) -> None:
    done, _ = _enter(root=tmp_path, template=_template(), pod=_pod_name(canary=False), exit_code=9)
    assert done.returncode == 9


def test_the_entry_point_reads_the_switch_and_canary_from_the_committed_template_shape() -> None:
    template = _TEMPLATE.read_text(encoding="utf-8")
    source = _ENTRY.read_text(encoding="utf-8")
    function = re.search(r"^template_value\(\) \{\n.*?\n\}$", source, re.MULTILINE | re.DOTALL)
    assert function is not None
    read = subprocess.run(
        [
            "bash",
            "-c",
            f'{function.group(0)}\nf="$1"; echo "[$(template_value "$f" CI_CACHE_KILL_SWITCH)]'
            f'[$(template_value "$f" CI_CACHE_CANARY_N)]"',
            "_",
            str(_TEMPLATE),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    canary = re.search(r'CI_CACHE_CANARY_N\n\s+value: "(\d+)"', template)
    assert canary is not None and read == f"[][{canary.group(1)}]"


# ---- the postStart record and the wiring ------------------------------------


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
    if seeded:
        seed = work / "_warm" / "actions"
        (seed / "archives").mkdir(parents=True)
        (seed / ".generation").write_text("20261104T000000Z\n", encoding="utf-8")
    for absolute, local in (
        ("/__w", work),
        ("/.cargo", root / "cargo"),
        ("/opt/ci-runner/bin", root / "bin"),
    ):
        script = script.replace(absolute, str(local))
    hook = root / "post-start.sh"
    hook.write_text(script, encoding="utf-8")
    done = subprocess.run(
        ["sh", str(hook)],
        env={
            "PATH": os.environ["PATH"],
            "HOSTNAME": "runner-abc-default",
            "CI_CACHE_KILL_SWITCH": switch,
        },
        capture_output=True,
        text=True,
        check=False,
    )
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
    mine = [row for row in parsed if row["tier"] == "actions"]
    assert len(mine) == 1, "exactly one actions-tier row per job"
    return mine[0]


def test_a_seeded_job_records_an_actions_hit_with_its_generation(tmp_path: Path) -> None:
    row = _post_start(root=tmp_path, seeded=True)
    assert (row["hit"], row["generation"], row["error"]) == ("true", "20261104T000000Z", "")


def test_a_job_with_no_seed_records_an_actions_miss_with_a_reason(tmp_path: Path) -> None:
    row = _post_start(root=tmp_path, seeded=False)
    assert (row["hit"], row["error"]) == ("false", "actions-seed-absent")


def test_the_kill_switch_records_the_actions_tier_cold_and_removes_the_seed(tmp_path: Path) -> None:
    row = _post_start(root=tmp_path, seeded=True, switch="operator")
    assert (row["hit"], row["error"]) == ("false", "off:operator")
    assert not (tmp_path / "w" / "_warm" / "actions").exists()


def test_every_values_file_starts_the_runner_through_the_entry_point() -> None:
    for values in [*_VALUES, _PHASE2 / "arc" / "values-EXAMPLE-repo.yaml"]:
        text = values.read_text(encoding="utf-8")
        assert (
            'command: ["/bin/bash", "/home/runner/hook-template/action-archive-entry.sh"]' in text
        ), values.name
        assert "mountPath: /home/runner/hook-template" in text, values.name
        assert 'command: ["/home/runner/run.sh"]' not in text, values.name


def test_the_entry_point_travels_in_the_template_configmap() -> None:
    converge = (_PHASE2 / "arc" / "converge-hook-pod-template.sh").read_text(encoding="utf-8")
    assert '"action-archive-entry.sh=${SCRIPT_DIR}/action-archive-entry.sh"' in converge
    role = (_REPO / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml").read_text(
        encoding="utf-8"
    )
    assert "src: arc/action-archive-entry.sh" in role


def test_the_actions_budget_lives_beside_the_other_budgets_and_reaches_the_populator() -> None:
    cronjob = _CRONJOB.read_text(encoding="utf-8")
    assert re.search(r'^  actions-bytes: "\d+"$', cronjob, re.MULTILINE)
    assert re.search(r'^  actions-files: "\d+"$', cronjob, re.MULTILINE)
    for variable, key in (
        ("WARM_ACTIONS_BUDGET_BYTES", "actions-bytes"),
        ("WARM_ACTIONS_BUDGET_FILES", "actions-files"),
    ):
        assert re.search(
            rf"name: {variable}\n\s+valueFrom:\n\s+configMapKeyRef:\n\s+name: warm-cache-budget\n\s+key: {key}\n",
            cronjob,
        ), variable


def test_the_host_gauges_report_the_actions_generation() -> None:
    gauges = (_REPO / "ci-runner" / "observability" / "ci-cache-gauges.sh").read_text("utf-8")
    assert "put actions_generation_age_s" in gauges and "put actions_generation_bytes" in gauges
    assert '"actions_generation_age_s"' in gauges and '{"tier": "actions"}' in gauges
