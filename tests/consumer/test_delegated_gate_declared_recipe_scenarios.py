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

import subprocess
from itertools import takewhile
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling.gate_remote_delegate import gate_remote_request
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult

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

# The recipes that are livespec-dev-tooling's OWN — the constant the pod command
# used to be. None of them may appear in another repository's gate Job.
_OUR_OWN_RECIPES = (
    "install-worktree-pack",
    "install-commit-refuse-hooks",
    "warm-typecheck",
    "hook_gate=1 check",
)

# What a consuming repository that declares nothing gets: the recipe its local
# pre-push fall-through runs.
_FALL_THROUGH_RECIPE = "check"


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
    """

    def __init__(self) -> None:
        self.argvs: list[tuple[str, ...]] = []

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
        # The assembly's only other two reaches, in the order it makes them:
        # the tree under test, then the repository the mirror is named after.
        answered = _TREE if "rev-parse" in argv else _ORIGIN
        return Success(GateCommandResult(returncode=0, stdout=f"{answered}\n", stderr=""))


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
    name `verify`; the control arm, which declares nothing and gets the
    fall-through `check`, is what proves the command comes from the repository
    under test. The negative half is the defect itself: not one of
    livespec-dev-tooling's own recipes may appear in another repository's Job,
    because a consumer that does not carry them is red on every green tree.
    """
    declaring = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
    )
    silent = _a_consumer_repository(root=tmp_path / "silent", declaration="")

    declared_manifest = _rendered_for(repo_root=declaring)
    silent_manifest = _rendered_for(repo_root=silent)

    assert _recipes_run(manifest=declared_manifest) == [f"just {_CONSUMER_RECIPE}"]
    assert _recipes_run(manifest=silent_manifest) == [f"just {_FALL_THROUGH_RECIPE}"]
    for ours in _OUR_OWN_RECIPES:
        assert f"just {ours}" not in declared_manifest
        assert f"just {ours}" not in silent_manifest
