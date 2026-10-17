"""Consumer-tier: the gate Job runs the CONSUMER's declared recipe, or goes red.

This repository's `SPECIFICATION/contracts.md` says of the delegated pre-push
gate that the Job MUST run the check recipe the consuming repository declares
for its gate and MUST NOT run a recipe that only livespec-dev-tooling declares,
and that a consumer which does not provide its declared recipe gets a RED
verdict naming it — never a green one and never a fall-back to a recipe it did
not declare. The acceptance shape is the scenario in
`SPECIFICATION/scenarios.md` about a delegated gate Job for a repository
missing its declared recipe.

WHY THIS TIER. The claim spans four artifacts that cannot see each other: the
consumer's `pyproject.toml`, the Python client that reads it, the bash renderer
that writes the manifest, and the pod script the manifest carries. A unit test
on any one of them would pass against a drifted neighbour — which is exactly how
the defect this file closes survived. Measured 2026-10-16: the pod command was a
constant naming livespec-dev-tooling's own `warm-typecheck` and `hook_gate=1
check`, so livespec-orchestrator-beads-fabro's janitor could not use the gate at
all and shipped `venue = host_local` instead.

NOTHING HERE REACHES A CLUSTER, A MIRROR OR A HOST. The consumer is a fixture
tree under `tmp_path`; the client's only door to the world is its
`GateCommandRunner` seam, and the canned runner below answers every git and
`kubectl` step itself. The ONE command it really runs is the renderer — a bash
script that contacts nothing by construction — because "the rendered command is
derived from the consumer's declaration" is a claim about what that script
produces, and a canned manifest would assert it of the fixture instead.
"""

from __future__ import annotations

import json
import os
import subprocess
from itertools import takewhile
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling.gate_remote_delegate import gate_remote_request, run_delegated_gate
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import GATE_FAILED

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"

# The empty tree's hash — a real git object name, and the one the canned
# `rev-parse HEAD^{tree}` below answers with.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ORIGIN = "git@github.com:acme/widget.git"

# The recipe a fixture consumer declares for its gate. Deliberately a name no
# justfile in this repository carries, so a renderer that fell back to a
# livespec-dev-tooling recipe could not produce it by accident.
_CONSUMER_RECIPE = "verify"

# The recipe that is livespec-dev-tooling's OWN and NO other repository's — the
# one survivor of the four-recipe constant the pod command used to be. The other
# three are the SHARED pre-push sequence every fleet consumer runs, and are the
# default below (freeze-driver ruling R92, 2026-10-17); `warm-typecheck` is this
# repository's alone, so it may still never appear in another repository's Job.
_OUR_OWN_RECIPES = ("warm-typecheck",)

# What a consuming repository that declares nothing gets: the SHARED pre-push
# sequence its own local fall-through runs — the pre-push hook's pack install,
# the commit-refuse-hook install, and the hook-gated aggregate the shared
# `scripts/just/check-pre-push.sh` ends in. Each entry is read back out of the
# file that owns it by the helpers below, so the default and the sequence it
# mirrors cannot drift apart silently.
_FALL_THROUGH_SUITE = (
    "install-worktree-pack",
    "install-commit-refuse-hooks",
    "hook_gate=1 check",
)

# The shared pre-push script and the hook that runs it — the two files the
# default above mirrors, read as text so a moved step fails HERE.
_PRE_PUSH_SCRIPT = _REPO_ROOT / "scripts" / "just" / "check-pre-push.sh"
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# The two `kubectl get job --output json` payloads one run sees, in order: a Job
# Kueue has not admitted yet, and then the condition that means the gate ran and
# was RED. Conditions carry `status` as well as `type`, because a Job reports
# every condition it has ever set and a reader that tests only the type would
# call a running gate terminal.
_JOB_ADMITTING = json.dumps({"status": {}})
_JOB_FAILED = json.dumps({"status": {"conditions": [{"type": "Failed", "status": "True"}]}})

# A `just` that provides NOTHING the tree declares — the scenario's Given. Every
# existence probe answers no; anything else succeeds, so a recipe that DID run
# would leave a green gate and a log line, and the assertions can tell the two
# failure shapes apart.
_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
[ "${1:-}" = "--show" ] && exit 1
exit 0
"""


def _a_consumer_repository(*, root: Path, declaration: str) -> Path:
    """A fixture consuming repository, with the one workflow the renderer reads.

    `declaration` is the body of its `[tool.livespec_dev_tooling]` block, so a
    consumer that declares a gate suite and one that declares none differ by
    exactly that line and nothing else.
    """
    root.mkdir(parents=True, exist_ok=True)
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    runs-on: self-hosted\n"
        "    container:\n"
        "      image: ghcr.io/example/sandbox:python-v1.11.1\n",
        encoding="utf-8",
    )
    _ = (root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\ndelegated_gate = true\n{declaration}",
        encoding="utf-8",
    )
    return root


class _CannedWorldRealRenderer:
    """Every git and cluster step canned; the RENDERER really runs.

    The renderer is the subject, so stubbing it would assert the stub. It is a
    bash script that reads a fixture directory and writes YAML to stdout — it
    opens no socket and touches nothing outside its own output.

    `pod_message` is what the cluster reports as the failed pod's termination
    message. A run that never reaches a Job never reads it, so the default is
    the empty string and the assembly-only tests are unaffected by it.
    """

    def __init__(self, *, pod_message: str = "") -> None:
        self.argvs: list[tuple[str, ...]] = []
        self._pod_message = pod_message
        self._polls = 0

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        self.argvs.append(tuple(argv))
        if argv[0] == str(_RENDERER):
            completed = subprocess.run(
                argv, cwd=str(cwd), capture_output=True, text=True, check=False
            )
            return Success(
                GateCommandResult(
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        return Success(GateCommandResult(returncode=0, stdout=self._stdout(argv=argv), stderr=""))

    def _stdout(self, *, argv: list[str]) -> str:
        """What each canned step answers with.

        The polls answer "not admitted yet" once before the verdict, which is
        the realistic shape — no gate is terminal on its first poll — and the
        only way the client's wait is exercised at all.
        """
        if "pods" in argv:
            return self._pod_message
        if "job" in argv:
            self._polls += 1
            return _JOB_ADMITTING if self._polls == 1 else _JOB_FAILED
        if "rev-parse" in argv:
            return f"{_TREE}\n"
        if "get-url" in argv:
            return f"{_ORIGIN}\n"
        # The push, the submit, the log stream and the ref collection: the
        # client reads their exit codes, never their output.
        return ""


def _gate_container_script(*, manifest: str) -> list[str]:
    """The gate container's own shell script, dedented out of the manifest.

    Sliced from `- name: gate` so the initContainer above — which runs its own
    `set -euo pipefail` block — cannot contribute a line to an assertion about
    what the AGGREGATE container runs. `next` raises when either marker is gone,
    which is a defect in the rendered manifest rather than a state to report.
    """
    lines = manifest.splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "- name: gate")
    opener = next(index for index in range(start, len(lines)) if lines[index].strip() == "- |")
    indent = len(lines[opener]) - len(lines[opener].lstrip()) + 2
    pad = " " * indent
    body = takewhile(lambda line: not line.strip() or line.startswith(pad), lines[opener + 1 :])
    return [line[indent:] for line in body]


def _recipes_run(*, manifest: str) -> list[str]:
    """Every `just …` invocation the gate container runs, in order.

    Anchored to a line that STARTS with `just `, so the preflight's own
    `if just --show …` probe — which asks whether a recipe exists rather than
    running it — is not counted as a recipe the gate ran.
    """
    return [
        line.strip()
        for line in _gate_container_script(manifest=manifest)
        if line.strip().startswith("just ")
    ]


def _pre_push_hook_installs() -> tuple[str, ...]:
    """Every `just` recipe the pre-push HOOK runs before the gate script itself.

    lefthook's `pre-push` block is where the pack install lives — it cannot live
    inside the gate script, because the root justfile reaches the pack through
    `import?`, which `just` resolves when it PARSES the file. The gate pod has
    the same problem for the same reason, which is why the default suite runs it
    as its own invocation.
    """
    lines = _LEFTHOOK.read_text(encoding="utf-8").splitlines()
    block = lines[lines.index("pre-push:") :]
    runs = [
        line.strip().removeprefix("run: just ")
        for line in block
        if line.strip().startswith("run: just ")
    ]
    return tuple(takewhile(lambda recipe: recipe != "check-pre-push", runs))


def _shared_pre_push_aggregate() -> str:
    """The last `just` invocation the SHARED pre-push script runs.

    That invocation is what a delegated gate stands in for, and `hook_gate=1` is
    load-bearing in it: the flag omits the world-gate member needing an
    admin-scope credential that no pre-push host and no gate pod holds. A bare
    `just check` ran it and reddened the gate on a target the local pre-push
    never runs.
    """
    lines = _PRE_PUSH_SCRIPT.read_text(encoding="utf-8").splitlines()
    return [
        line.strip().removeprefix("just ") for line in lines if line.strip().startswith("just ")
    ][-1]


def _renderer_default_recipes(*, root: Path) -> list[str]:
    """What the renderer runs when it is handed NO suite at all.

    The client is the one place the default is decided, and the renderer carries
    its own fallback for a hand-run render on a delegating host. Two spellings
    of one sequence drift unless something reads them together — this does.
    """
    completed = subprocess.run(
        [str(_RENDERER), "--repo-root", str(root), "--tree-hash", _TREE],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return _recipes_run(manifest=completed.stdout)


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


def _rendered_for(*, repo_root: Path) -> str:
    """Assemble the real request for `repo_root` and return its manifest."""
    built = gate_remote_request(
        repo_root=repo_root, renderer=_RENDERER, runner=_CannedWorldRealRenderer()
    )
    assert isinstance(built, Success), built
    return built.unwrap().manifest


def test_the_gate_job_runs_the_consumers_own_declared_recipe_and_none_of_ours(
    *, tmp_path: Path
) -> None:
    """Two consumers, one renderer, two different commands — so it is DERIVED.

    The positive arm alone could be satisfied by a template that happened to
    name `verify`; the control arm, which declares nothing and gets the shared
    pre-push sequence instead, is what proves the command comes from the
    repository under test. The negative half is the defect itself: a recipe only
    livespec-dev-tooling declares may not appear in another repository's Job,
    because a consumer that does not carry it is red on every green tree.
    """
    declaring = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
    )
    silent = _a_consumer_repository(root=tmp_path / "silent", declaration="")

    declared_manifest = _rendered_for(repo_root=declaring)
    silent_manifest = _rendered_for(repo_root=silent)

    assert _recipes_run(manifest=declared_manifest) == [f"just {_CONSUMER_RECIPE}"]
    assert _recipes_run(manifest=silent_manifest) == [
        f"just {recipe}" for recipe in _FALL_THROUGH_SUITE
    ]
    for ours in _OUR_OWN_RECIPES:
        assert f"just {ours}" not in declared_manifest
        assert f"just {ours}" not in silent_manifest


def test_a_consumer_that_declares_nothing_gets_the_shared_pre_push_sequence(
    *, tmp_path: Path
) -> None:
    """The default IS the shared pre-push sequence, read out of its own files.

    Freeze-driver ruling R92 (2026-10-17), option A. The default was the single
    `check` recipe, which is a bare `just check` — and a gate Job that runs one
    is NOT the local fall-through it stands in for. Measured the same day on
    livespec-orchestrator-beads-fabro, whose tree was green in CI while its gate
    Job went red from four targets: the two installs the pod never ran left
    `check-primary-checkout-commit-refuse-hook-installed` and
    `check-no-workflow-edits` judging an un-bootstrapped sandbox rather than the
    tree, and the missing `hook_gate=1` ran the admin-scope world gate that no
    pre-push host and no gate pod can satisfy (403).

    WHAT THE CONTRACT ACTUALLY SAYS is that the Job runs "the recipe its local
    fall-through runs", and for a fleet consumer that fall-through is three
    steps, not one: lefthook's `pre-push` hook installs the worktree pack, this
    repository's own gate adds the commit-refuse-hook install, and the shared
    `scripts/just/check-pre-push.sh` ends in `just hook_gate=1 check`. So the
    first two assertions read those steps back out of the files that own them —
    a step that moves there fails HERE, naming the default that must move with
    it, rather than silently reddening a consumer's gate on a green tree.

    The last two arms are what the default is FOR and what it must not become:
    a consumer that declares nothing gets the sequence, and a consumer that
    declares a suite gets ITS suite and none of the default.
    """
    silent = _a_consumer_repository(root=tmp_path / "silent", declaration="")
    declaring = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
    )

    assert _pre_push_hook_installs() == ("install-worktree-pack",)
    assert _shared_pre_push_aggregate() == "hook_gate=1 check"
    assert _FALL_THROUGH_SUITE == (
        "install-worktree-pack",
        "install-commit-refuse-hooks",
        "hook_gate=1 check",
    )

    assert _recipes_run(manifest=_rendered_for(repo_root=silent)) == [
        f"just {recipe}" for recipe in _FALL_THROUGH_SUITE
    ]
    assert _renderer_default_recipes(root=silent) == [
        f"just {recipe}" for recipe in _FALL_THROUGH_SUITE
    ]
    assert _recipes_run(manifest=_rendered_for(repo_root=declaring)) == [f"just {_CONSUMER_RECIPE}"]


def _run_the_pod_script(*, manifest: str, root: Path) -> tuple[int, str, list[str]]:
    """Run the rendered pod script here, against a `just` that provides nothing.

    This is the scenario's When, minus the cluster: the Job's verdict IS this
    script's exit status, and what it invoked is the only way to tell "refused
    before running anything" apart from "ran something and it failed".
    """
    stub_dir = root / "bin"
    stub_dir.mkdir(parents=True)
    stub = stub_dir / "just"
    _ = stub.write_text(_JUST_STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = root / "invocations.log"
    script = root / "gate-script.sh"
    _ = script.write_text("\n".join(_gate_container_script(manifest=manifest)), encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
        }
    )
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stderr, log.read_text(encoding="utf-8").splitlines()


def test_a_gate_for_a_repository_missing_its_declared_recipe_is_red_and_names_it(
    *, tmp_path: Path
) -> None:
    """The scenario, end to end: the pod's refusal and the verdict that carries it.

    The two arms are joined by a VALUE rather than by a shared expectation: the
    message the pod actually produced is the message handed to the canned
    cluster as the failed pod's termination message. So the verdict naming the
    recipe is the pod's own wording reaching an operator, not a second string
    that happens to agree with it today.

    `refuses_push` and the absent token are asserted too, because "red" is only
    half the scenario's Then — a verdict nobody acts on still completes a push.
    """
    consumer = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
    )
    manifest = _rendered_for(repo_root=consumer)

    returncode, stderr, invoked = _run_the_pod_script(manifest=manifest, root=tmp_path / "pod")

    assert returncode != 0
    assert f"'{_CONSUMER_RECIPE}'" in stderr
    assert invoked == [f"just --show {_CONSUMER_RECIPE}"]

    cluster = _CannedWorldRealRenderer(pod_message=stderr.strip())
    verdict = run_delegated_gate(
        repo_root=consumer, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_FAILED
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert _CONSUMER_RECIPE in verdict.detail
    assert not [argv for argv in cluster.argvs if "green_token" in " ".join(argv)]
