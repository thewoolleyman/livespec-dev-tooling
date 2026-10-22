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
_TEMPLATE = _RENDERER.parent / "gate-job-template.yaml"

# The empty tree's hash — a real git object name, and the one the canned
# `rev-parse HEAD^{tree}` below answers with.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ORIGIN = "git@github.com:acme/widget.git"

# The recipe a fixture consumer declares for its gate. Deliberately a name no
# justfile in this repository carries, so a renderer that fell back to a
# livespec-dev-tooling recipe could not produce it by accident.
_CONSUMER_RECIPE = "verify"

# The invocations that are livespec-dev-tooling's OWN and NO other
# repository's — the two survivors of the four-recipe constant the pod command
# used to be. `warm-typecheck` exists in no other repository's justfile, and
# `hook_gate=1 check` overrides a `just` variable only this justfile DECLARES
# (`export hook_gate := ""`), which `just` refuses to accept from the command
# line anywhere else. Neither may ever appear in another repository's Job.
_OUR_OWN_RECIPES = ("warm-typecheck", "hook_gate=1 check")

# What a consuming repository that declares nothing gets: the SHARED pre-push
# sequence its own local fall-through runs — the pre-push hook's pack install,
# the commit-refuse-hook install, and the ONE recipe that hook then calls.
# Each entry is read back out of the file that owns it by the helpers below, so
# the default and the sequence it mirrors cannot drift apart silently.
_FALL_THROUGH_SUITE = (
    "install-worktree-pack",
    "install-commit-refuse-hooks",
    "check-pre-push",
)

# The hook that runs the pre-push sequence the default above mirrors, read as
# text so a moved step fails HERE. It is the lefthook block and NOT this
# repository's own `scripts/just/check-pre-push.sh`: the RECIPE NAME is what the
# fleet shares, while the script behind it is per repository (freeze-driver
# ruling R100, 2026-10-17).
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# How the pod reaches livespec CORE, which a consumer running `check-doctor-static`
# needs and a `git init` + fetch workspace does not have. The URL is the ANONYMOUS
# https form of a PUBLIC repository — the one property that makes this resolvable
# without handing the pod a credential — and the plugin root is the `.claude-plugin`
# directory of the fetched tree, which is what `LIVESPEC_CORE_PLUGIN_ROOT` means
# everywhere else in the fleet (the consumer's own `just-check-doctor-static.sh`
# resolves `$LIVESPEC_CORE_PLUGIN_ROOT/scripts/bin/doctor_static.py`).
_CORE_URL = "https://github.com/thewoolleyman/livespec.git"
_CORE_PLUGIN_ROOT = "/livespec-core/.claude-plugin"
_CORE_CONTAINER = "fetch-livespec-core"

# What a consumer that pins no livespec release gets — the same fallback its own
# CI step takes when `.livespec.jsonc` carries no `pinned` field.
_CORE_REF_WHEN_UNPINNED = "master"

# The variable livespec core's cross-repo readers resolve a cited sibling's
# clone through, and the template token the renderer fills with the step that
# provisions it. Both are named because the claim spans them: an absent step in
# a non-declaring repository's Job must be a RENDERED absence, which is only
# meaningful while the template it rendered from still carries the step.
_SIBLING_ROOT_VARIABLE = "LIVESPEC_SIBLING_CLONES_ROOT"
_SIBLING_ROOT_EXPORT = f"export {_SIBLING_ROOT_VARIABLE}="
_SIBLING_TOKEN = "@@GATE_SIBLING_CLONES@@"

# The siblings two fixture consumers declare. Deliberately NOT fleet repository
# names: a renderer that reached for a hardcoded list could not produce either
# set, and the two sets differ so one renderer answering both proves the clones
# are DERIVED from the repository under test.
_WIDGET_SIBLINGS = (
    ("widget-core", "https://github.com/acme/widget-core"),
    ("widget-docs", "https://github.com/acme/widget-docs"),
)
_GADGET_SIBLINGS = (("gadget-core", "https://github.com/acme/gadget-core"),)

# The member that really failed on gate-livespec-dev-tooling-54f19942138d, and
# the fixture line the verdict named INSTEAD of it (livespec-dev-tooling-plbimj).
# The text is this repository's own rendered sibling-clone refusal, which its
# gate-renderer exit tests produce and run from inside the gate's own aggregate
# — so it reaches the pod as one member's captured output on a tree that
# registers no siblings whatsoever.
_RED_MEMBER = "check-no-workflow-edits"
_FIXTURE_FATAL_FRAGMENT = "cannot clone cross-repo sibling"
_MEMBER_FIXTURE_FATAL = (
    f"FATAL: {_FIXTURE_FATAL_FRAGMENT} 'widget-core' from "
    "https://github.com/acme/widget-core. Its checks would read the absent clone as an "
    "EMPTY tree and silently drop every allowlisted citation to it, so no recipe was "
    "run; this gate is RED."
)

# The redirect that makes the pod's own last words the cluster's termination
# message. Read as a literal because the ORDERING claim below is about this
# write: `>` truncates, so the LAST one wins, and a member that wrote the file
# mid-run loses to a write the pod makes after its recipes.
_TERMINATION_WRITE = "> /dev/termination-log"

# The two `kubectl get job --output json` payloads one run sees, in order: a Job
# Kueue has not admitted yet, and then the condition that means the gate ran and
# was RED. Conditions carry `status` as well as `type`, because a Job reports
# every condition it has ever set and a reader that tests only the type would
# call a running gate terminal.
_JOB_ADMITTING = json.dumps({"status": {}})
_JOB_FAILED = json.dumps({"status": {"conditions": [{"type": "Failed", "status": "True"}]}})
# The name the API SERVER assigns, and what `kubectl create --output json`
# answers with. The manifest asks for a `metadata.generateName`, so the Job's
# name is an OUTPUT of the submit rather than something the renderer or the
# client can predict (livespec-dev-tooling-44fglo).
_ASSIGNED_JOB = "gate-widget-7f2qd"
_CREATED = json.dumps(
    {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _ASSIGNED_JOB}}
)

# A `just` that provides NOTHING the tree declares — the scenario's Given. Every
# existence probe answers no; anything else succeeds, so a recipe that DID run
# would leave a green gate and a log line, and the assertions can tell the two
# failure shapes apart.
#
# IT ALSO RECORDS THE SIBLING-CLONES ROOT IT INHERITED, and only when that
# variable is SET. That is the one way to observe from outside the pod whether
# the checks would resolve a cited sibling through the provisioned clones or
# through the `/data/projects/<sibling>` path no pod has — the question this
# whole step exists to answer. Recording it conditionally keeps a non-declaring
# repository's log exactly what it has always been.
#
# AND IT ANSWERS `--show` FROM `PROVIDED`, which defaults to EMPTY — the
# provides-nothing Given every arm written before it relies on. A caller that
# names the recipes its fixture tree carries gets a `just` that admits them,
# which is how an arm whose subject is a LATER step reaches that step at all.
#
# UNDER `FAILING_MEMBER` IT IS A RED AGGREGATE rather than a green one, and it
# writes the SHAPE the fleet's own dispatcher writes: each member's CAPTURED
# OUTPUT first, then the summary block that closes the run. Both halves matter
# to the arm that uses it — the captured half is where a member's fixture text
# lives, and the summary half is the only place the run names which members
# failed (`livespec_dev_tooling.parallel_check_dispatcher._emit_summary`).
_JUST_STUB = """#!/usr/bin/env bash
if [ -n "${LIVESPEC_SIBLING_CLONES_ROOT:-}" ]; then
  printf 'sibling-root %s\\n' "${LIVESPEC_SIBLING_CLONES_ROOT}" >> "${STUB_LOG}"
fi
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
if [ "${1:-}" = "--show" ]; then
  case " ${PROVIDED:-} " in
    *" ${2} "*) exit 0 ;;
    *)          exit 1 ;;
  esac
fi
if [ -n "${FAILING_MEMBER:-}" ]; then
  printf '\\n::: just %s [FAILED, wall: 1.0s]\\n' "${FAILING_MEMBER}"
  printf '%s\\n' "${MEMBER_CAPTURED_OUTPUT:-}"
  printf '\\n--- parallel check summary ---\\npassed: 78, failed: 1, skipped: 1\\n'
  printf '\\nFailed targets (1):\\n  - %s\\n' "${FAILING_MEMBER}"
  exit 1
fi
exit 0
"""

# A `git` that NEVER REACHES THE NETWORK, because these fixture siblings are
# `github.com/acme/*` and a real clone of them is both a network call this suite
# forbids itself and a 404. A `clone` succeeds, or — under `CLONE_FAILS` — fails
# the way a sibling that cannot be fetched does, which is the Given of the
# red-gate arm. It CREATES NOTHING: a real `git clone` would make its
# destination and every parent of it, and a stub that did the same would leave
# the pod's clones root on the host running these tests.
_GIT_STUB = """#!/usr/bin/env bash
printf 'git %s\\n' "$*" >> "${STUB_LOG}"
if [ "${1:-}" = "clone" ]; then
  [ -n "${CLONE_FAILS:-}" ] && exit 1
  exit 0
fi
[ "${3:-}" = "rev-parse" ] && echo "0000000000000000000000000000000000000000"
exit 0
"""


def _cross_repo_targets_block(*, siblings: tuple[tuple[str, str], ...]) -> str:
    """The `cross_repo_targets` map, in the shape a real `.livespec.jsonc` writes it.

    Each entry carries the `local_clone` a fleet host has and a gate pod does
    not, because that path is the whole reason the step under test exists: with
    no provisioned root the cross-repo readers resolve it, find nothing, and
    read the absence as an EMPTY heading set rather than as an error.
    """
    entries = ",\n".join(
        "\n".join(
            [
                f'    "{name}": {{',
                f'      "github_url": "{url}",',
                f'      "local_clone": "/data/projects/{name}",',
                '      "default_branch": "master"',
                "    }",
            ]
        )
        for name, url in siblings
    )
    return '  "cross_repo_targets": {\n' + entries + "\n  }"


def _a_consumer_repository(
    *,
    root: Path,
    declaration: str,
    core_pin: str | None = None,
    siblings: tuple[tuple[str, str], ...] = (),
) -> Path:
    """A fixture consuming repository, with the one workflow the renderer reads.

    `declaration` is the body of its `[tool.livespec_dev_tooling]` block, so a
    consumer that declares a gate suite and one that declares none differ by
    exactly that line and nothing else.

    `core_pin` is the livespec release this consumer pins in its own
    `.livespec.jsonc` `compat.pinned` — the same field its CI resolves core at.
    `None` writes no `.livespec.jsonc` at all, which is the consumer that pins
    nothing.

    `siblings` are the `(slug, github_url)` pairs its `.livespec.jsonc`
    registers under `cross_repo_targets` — the same map a cross-repo reader
    looks a cited sibling up in. The empty default writes no such block, which
    is the consumer that declares no siblings at all.
    """
    root.mkdir(parents=True, exist_ok=True)
    if core_pin is not None or siblings:
        pinned = core_pin or _CORE_REF_WHEN_UNPINNED
        blocks = [
            "\n".join(
                [
                    '  "widget": {',
                    f'    "compat": {{ "livespec": ">=0.1.0,<1.0.0", "pinned": "{pinned}" }}',
                    "  }",
                ]
            )
        ]
        if siblings:
            blocks.append(_cross_repo_targets_block(siblings=siblings))
        _ = (root / ".livespec.jsonc").write_text(
            "{\n" + ",\n".join(blocks) + "\n}\n", encoding="utf-8"
        )
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

    `streamed` records the commands the client asked to be STREAMED rather than
    captured, which is a different claim from `argvs`: the verdict stream an
    operator reads is whatever the client hands to the terminal, so a step the
    client captured and discarded reaches nobody even though its argv is here.
    """

    def __init__(self, *, pod_message: str = "") -> None:
        self.argvs: list[tuple[str, ...]] = []
        self.streamed: list[tuple[str, ...]] = []
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
        _ = stdin
        self.argvs.append(tuple(argv))
        if stream:
            self.streamed.append(tuple(argv))
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
        if "create" in argv:
            return _CREATED
        if "job" in argv:
            self._polls += 1
            return _JOB_ADMITTING if self._polls == 1 else _JOB_FAILED
        if "rev-parse" in argv:
            return f"{_TREE}\n"
        if "get-url" in argv:
            return f"{_ORIGIN}\n"
        # The push, the log stream and the ref collection: the client reads
        # their exit codes, never their output.
        return ""


def _container_block(*, manifest: str, name: str) -> list[str]:
    """One container's own YAML block, from its `- name:` line to its last line.

    Bounded by INDENTATION rather than by the next `- name:` spelling, so the
    block of the last container in a list ends where its list does. Every
    assertion below is made of one container's lines alone: a claim about what
    the gate container reads must not be satisfiable by an initContainer, and a
    claim that an initContainer carries no credential must not be read off the
    gate container's env a few lines later.
    """
    lines = manifest.splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == f"- name: {name}")
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = takewhile(
        lambda line: not line.strip() or len(line) - len(line.lstrip()) > indent,
        lines[start + 1 :],
    )
    return [lines[start], *body]


def _container_script(*, manifest: str, name: str) -> list[str]:
    """One container's own shell script, dedented out of its block.

    Sliced from that container's `- name:` line so a sibling — each of which
    runs its own `set -euo pipefail` block — cannot contribute a line to an
    assertion about this one. `next` raises when either marker is gone, which is
    a defect in the rendered manifest rather than a state to report.
    """
    lines = _container_block(manifest=manifest, name=name)
    opener = next(index for index, line in enumerate(lines) if line.strip() == "- |")
    indent = len(lines[opener]) - len(lines[opener].lstrip()) + 2
    pad = " " * indent
    body = takewhile(lambda line: not line.strip() or line.startswith(pad), lines[opener + 1 :])
    return [line[indent:] for line in body]


def _env_value(*, manifest: str, container: str, variable: str) -> str:
    """The literal value one container's env block gives `variable`.

    Read off the container's own block, because an environment variable naming a
    path is only true of the container that also MOUNTS that path.
    """
    lines = _container_block(manifest=manifest, name=container)
    named = next(index for index, line in enumerate(lines) if line.strip() == f"- name: {variable}")
    value = lines[named + 1].strip()
    assert value.startswith("value:"), f"{variable} is not given a literal value: {value}"
    return value.removeprefix("value:").strip().strip('"')


def _literal_env(*, manifest: str, container: str) -> dict[str, str]:
    """Every environment variable one container's block gives a LITERAL value.

    The `valueFrom:` entries are deliberately absent: `GH_TOKEN` comes from an
    optional Secret the cluster resolves, and a harness that invented a value
    for it would be asserting something about this suite's host rather than
    about the pod.

    THIS IS WHY IT EXISTS: a script run outside a pod inherits the HOST's
    environment, and this host — a Fabro sandbox — exports a real
    `LIVESPEC_CORE_PLUGIN_ROOT` of its own pointing at its sibling checkout. A
    pod-script run that took `os.environ` as-is therefore read the SANDBOX's
    core path and reported it as the gate's, which is a test that passes while
    proving nothing. Applying the manifest's own literals is what Kubernetes
    does, so it both models the pod and scrubs the ambient value.
    """
    lines = _container_block(manifest=manifest, name=container)
    declared: dict[str, str] = {}
    for index, line in enumerate(lines[:-1]):
        name = line.strip().removeprefix("- name: ")
        value = lines[index + 1].strip()
        if line.strip().startswith("- name: ") and value.startswith("value:"):
            declared[name] = value.removeprefix("value:").strip().strip('"')
    return declared


def _recipes_run(*, manifest: str) -> list[str]:
    """Every `just …` invocation the gate container runs, in order.

    Anchored to a line that STARTS with `just `, so the preflight's own
    `if just --show …` probe — which asks whether a recipe exists rather than
    running it — is not counted as a recipe the gate ran.
    """
    return [
        line.strip()
        for line in _container_script(manifest=manifest, name="gate")
        if line.strip().startswith("just ")
    ]


def _executable_script(*, manifest: str, name: str) -> list[str]:
    """One container's script with its comment lines dropped.

    The template explains the sibling-clone step at length, and prose about a
    step must never read as the step: every claim below about what a
    non-declaring repository's command does NOT carry is made of these lines.
    """
    return [
        line
        for line in _container_script(manifest=manifest, name=name)
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _exported_sibling_clones_root(*, manifest: str) -> str:
    """The directory the gate container exports as the sibling-clones root.

    Read off the script rather than asserted as a literal, so the tests can pin
    the RELATIONSHIP the step exists for — the clones land where the variable
    the readers consult actually points — rather than a path constant that
    would be satisfied by a variable naming an empty directory.
    """
    exported = [
        line.strip()
        for line in _executable_script(manifest=manifest, name="gate")
        if line.strip().startswith(_SIBLING_ROOT_EXPORT)
    ]
    assert len(exported) == 1, (
        "the gate container does not export exactly one sibling-clones root, so "
        f"the cross-repo readers resolve a cited sibling somewhere else: {exported}"
    )
    return exported[0].removeprefix(_SIBLING_ROOT_EXPORT).strip().strip("'\"")


def _sibling_clone_commands(*, manifest: str) -> list[str]:
    """Every `git clone` the gate container runs, in order.

    Matched anywhere in the line rather than at its start, because the clone is
    the subject of an `if ! … ; then` — the same shape the init containers above
    use to make a failed fetch the Job's own verdict.
    """
    return [
        line.strip()
        for line in _executable_script(manifest=manifest, name="gate")
        if "git clone " in line
    ]


def _index_of_first_recipe(*, manifest: str) -> int:
    """Where the check suite STARTS in the gate container's script.

    Anchored to a line that STARTS with `just `, so the preflight's own
    `if just --show …` existence probe does not count as the suite having
    begun — "before the first check-suite recipe runs" is a claim about the
    recipes, and the probe runs nothing.
    """
    lines = _executable_script(manifest=manifest, name="gate")
    return next(index for index, line in enumerate(lines) if line.strip().startswith("just "))


def _pre_push_hook_recipes() -> tuple[str, ...]:
    """Every `just` recipe lefthook's `pre-push` block names, in order.

    lefthook's `pre-push` block is where the pack install lives — it cannot live
    inside the gate script, because the root justfile reaches the pack through
    `import?`, which `just` resolves when it PARSES the file. The gate pod has
    the same problem for the same reason, which is why the default suite runs it
    as its own invocation.

    THIS BLOCK, AND NOT THE SCRIPT BEHIND IT, is what the fleet shares. Every
    repository's `pre-push` calls `just check-pre-push`; what that recipe then
    runs is per repository (livespec-orchestrator-beads-fabro's ends in
    `just check-skipping check-codex-skill-picker`, this one's in
    `just hook_gate=1 check`). Reading the script instead is the mistake ruling
    R100 corrected — it put a variable only this justfile declares into every
    consumer's gate Job.
    """
    lines = _LEFTHOOK.read_text(encoding="utf-8").splitlines()
    block = lines[lines.index("pre-push:") :]
    return tuple(
        line.strip().removeprefix("run: just ")
        for line in block
        if line.strip().startswith("run: just ")
    )


def _pre_push_hook_installs() -> tuple[str, ...]:
    """The hook's recipes that run BEFORE the gate recipe itself."""
    return tuple(takewhile(lambda recipe: recipe != "check-pre-push", _pre_push_hook_recipes()))


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


def test_a_consumer_that_declares_nothing_gets_the_recipe_its_own_pre_push_names(
    *, tmp_path: Path
) -> None:
    """The default IS the shared pre-push sequence, read out of the file that owns it.

    Freeze-driver rulings R92 and R100 (both 2026-10-17). R92 replaced a single
    `check` with three steps, because a gate Job that runs a bare `just check`
    is NOT the local fall-through it stands in for: the two installs the pod
    never ran left `check-primary-checkout-commit-refuse-hook-installed` and
    `check-no-workflow-edits` judging an un-bootstrapped sandbox rather than the
    tree under test.

    R100 THEN CORRECTED ITS LAST STEP, and that correction is what the first two
    arms below pin. R92 wrote `hook_gate=1 check` on the premise that every
    fleet consumer's pre-push ends in THIS repository's
    `scripts/just/check-pre-push.sh`. It does not — each repository ships its
    own script — and `hook_gate` is a `just` variable only this repository's
    justfile declares, which `just` refuses to let the command line override
    anywhere else. Measured 2026-10-17: Job
    gate-livespec-orchestrator-beads-fabro-ee118f8fd5dc died with `error:
    Variable 'hook_gate' overridden on the command line but not present in
    justfile`, before its aggregate ran, on a tree whose master CI was green.

    WHAT IS UNIFORM FLEET-WIDE IS THE RECIPE NAME. `check-pre-push` is what
    every repository's lefthook `pre-push` block calls, and a recipe name is
    what the Job's own preflight can test for — a variable it cannot. So the
    sequence is read back out of `lefthook.yml`, the file that owns it: a step
    that moves there fails HERE, naming the default that must move with it,
    rather than silently reddening a consumer's gate on a green tree.

    AND NO ENTRY MAY CARRY A `name=value` OVERRIDE AT ALL, asserted of the
    default AND of the rendered command. That is the general form of the defect:
    a variable assignment in the shared default is a bet that every consumer's
    justfile declares that variable, and `just` turns a losing bet into a red
    gate before any check has run.

    The last arms are what the default is FOR and what it must not become: a
    consumer that declares nothing gets the sequence through both spellings of
    it — the client's and the renderer's own fallback — and a consumer that
    declares a suite gets ITS suite and none of the default.
    """
    silent = _a_consumer_repository(root=tmp_path / "silent", declaration="")
    declaring = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
    )

    assert _pre_push_hook_installs() == ("install-worktree-pack",)
    assert _pre_push_hook_recipes()[-1] == "check-pre-push"
    assert _FALL_THROUGH_SUITE == (
        "install-worktree-pack",
        "install-commit-refuse-hooks",
        "check-pre-push",
    )
    assert [entry for entry in _FALL_THROUGH_SUITE if "=" in entry] == []

    silent_recipes = _recipes_run(manifest=_rendered_for(repo_root=silent))

    assert silent_recipes == [f"just {recipe}" for recipe in _FALL_THROUGH_SUITE]
    assert [line for line in silent_recipes if "=" in line] == []
    assert _renderer_default_recipes(root=silent) == [
        f"just {recipe}" for recipe in _FALL_THROUGH_SUITE
    ]
    assert _recipes_run(manifest=_rendered_for(repo_root=declaring)) == [f"just {_CONSUMER_RECIPE}"]


def test_the_gate_job_resolves_livespec_core_at_the_consumers_pinned_release(
    *, tmp_path: Path
) -> None:
    """The pod gets livespec CORE, at the consumer's pin, with no credential.

    A consumer whose check aggregate runs `check-doctor-static` needs core
    inside the pod: core ships the checker, and the recipe resolves it through
    `LIVESPEC_CORE_PLUGIN_ROOT` or the installed plugin cache. The gate pod has
    neither — `/workspace` is a `git init` + fetch and no plugin is installed —
    so that target failed with core's own "livespec core not found" on a tree
    that was green in CI (freeze-driver ruling R92, 2026-10-17, part ii).

    THE PIN IS THE CONSUMER'S, which is why three fixtures are rendered rather
    than one: a constant could satisfy any single arm and not the set. Each
    consumer's `.livespec.jsonc` `compat.pinned` is the same field its CI
    resolves core at, so the gate and CI judge the tree against the same core
    build; a consumer that pins nothing gets the same `master` fallback its CI
    step takes.

    AND NO CREDENTIAL REACHES THE POD FOR IT. livespec core is public, so the
    anonymous https remote is the whole mechanism: the init container declares
    no env block at all, which is a stronger statement than the absence of one
    token name — there is nothing there to leak and nothing to rotate. The two
    credential-reading aggregate members still read their GH_TOKEN from the gate
    container's own optional Secret reference, which this leaves untouched.
    """
    pinned = _a_consumer_repository(root=tmp_path / "pinned", declaration="", core_pin="v0.42.1")
    other = _a_consumer_repository(root=tmp_path / "other", declaration="", core_pin="v9.99.0")
    unpinned = _a_consumer_repository(root=tmp_path / "unpinned", declaration="")

    manifest = _rendered_for(repo_root=pinned)
    assert f"- name: {_CORE_CONTAINER}" in manifest, (
        "the rendered gate Job has no init container fetching livespec core, so a "
        "consumer running check-doctor-static cannot resolve it in the pod"
    )

    fetch = "\n".join(_container_script(manifest=manifest, name=_CORE_CONTAINER))
    assert _CORE_URL in fetch
    assert "v0.42.1" in fetch
    assert "v9.99.0" in "\n".join(
        _container_script(manifest=_rendered_for(repo_root=other), name=_CORE_CONTAINER)
    )
    assert _CORE_REF_WHEN_UNPINNED in "\n".join(
        _container_script(manifest=_rendered_for(repo_root=unpinned), name=_CORE_CONTAINER)
    )

    assert (
        _env_value(manifest=manifest, container="gate", variable="LIVESPEC_CORE_PLUGIN_ROOT")
        == _CORE_PLUGIN_ROOT
    )
    gate = "\n".join(_container_block(manifest=manifest, name="gate"))
    assert "mountPath: /livespec-core" in gate, (
        "the gate container names a core plugin root it does not mount, so the "
        "path is empty where its checks read it"
    )

    core_block = "\n".join(_container_block(manifest=manifest, name=_CORE_CONTAINER))
    assert "env:" not in core_block
    assert "secretKeyRef" not in core_block
    assert "@github.com" not in core_block


def _run_the_pod_script(
    *,
    manifest: str,
    root: Path,
    clone_fails: bool = False,
    provides: tuple[str, ...] = (),
    failing_member: str = "",
    member_captured_output: str = "",
) -> tuple[int, str, str, list[str]]:
    """Run the rendered pod script here, against a `just` that provides nothing.

    This is the scenario's When, minus the cluster: the Job's verdict IS this
    script's exit status, and what it invoked is the only way to tell "refused
    before running anything" apart from "ran something and it failed".

    `clone_fails` makes the stub `git` refuse every `clone`, which is the Given
    of a sibling the pod cannot fetch. The stub never reaches the network either
    way — see `_GIT_STUB`.

    `provides` are the recipes the fixture tree carries. The default is NONE,
    which is the provides-nothing Given; naming them is what lets an arm whose
    subject sits after the preflight reach it.

    `failing_member` makes the recipe RUN and go red on that one member, and
    `member_captured_output` is what that member printed — the Given of a tree
    whose recipe reached its own members rather than one whose provisioning
    stopped short of them.

    Returns the exit status, STDOUT, stderr and the invocation log, in that
    order. Both streams are returned because the pod writes to each for a
    different reason: its refusal goes to stderr, where the cluster also lifts
    it into the termination message, while what it REPORTS about its own
    environment goes to stdout. The client streams both as one verdict stream,
    and keeping them apart here is what lets a claim about one not be satisfied
    by the other.
    """
    stub_dir = root / "bin"
    stub_dir.mkdir(parents=True)
    for name, body in (("just", _JUST_STUB), ("git", _GIT_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    log = root / "invocations.log"
    script = root / "gate-script.sh"
    _ = script.write_text(
        "\n".join(_container_script(manifest=manifest, name="gate")), encoding="utf-8"
    )
    env = dict(os.environ)
    # The pod's OWN declared environment, which Kubernetes would apply and this
    # host would otherwise shadow — see `_literal_env`.
    env.update(_literal_env(manifest=manifest, container="gate"))
    # THE SAME SHADOWING HAZARD, for a variable no env block declares. A Fabro
    # sandbox exports a real `LIVESPEC_SIBLING_CLONES_ROOT` naming its own
    # sibling checkouts, and the pod gets this variable from its SCRIPT rather
    # than from Kubernetes — so an inherited value would make a Job that
    # provisions nothing look exactly like one that provisioned correctly.
    _ = env.pop(_SIBLING_ROOT_VARIABLE, None)
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
            "PROVIDED": " ".join(provides),
        }
    )
    if clone_fails:
        env["CLONE_FAILS"] = "1"
    if failing_member:
        env["FAILING_MEMBER"] = failing_member
        env["MEMBER_CAPTURED_OUTPUT"] = member_captured_output
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        completed.returncode,
        completed.stdout,
        completed.stderr,
        log.read_text(encoding="utf-8").splitlines(),
    )


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

    returncode, _stdout, stderr, invoked = _run_the_pod_script(
        manifest=manifest, root=tmp_path / "pod"
    )

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


def test_the_verdict_stream_reports_whether_livespec_core_was_resolved(*, tmp_path: Path) -> None:
    """The core resolution is an OBSERVABLE of the run, not only a fact of the manifest.

    The test above this one proves the pod is HANDED core at the consumer's pin.
    That is a property of the rendered YAML, and nobody reading a verdict reads
    YAML: the gate client streams the Job's logs and that stream is the whole of
    what an operator sees. So "the gate resolved core at /livespec-core" was
    unanswerable from a gate's own output — including from the output of the
    very failure it explains, a consumer's `check-doctor-static` reporting
    core's own "livespec core not found" (freeze-driver ruling R100,
    2026-10-17).

    THREE ARMS, BECAUSE THE CLAIM SPANS TWO ARTIFACTS THAT CANNOT SEE EACH
    OTHER. The pod script has to SAY it: the rendered gate container reports the
    `LIVESPEC_CORE_PLUGIN_ROOT` it received and the ref that root was fetched
    at. It has to say it BEFORE the sequence runs, so a Job that refuses a
    missing recipe still reports it — which is asserted by position against the
    first `just` the script reaches, and then by RUNNING the script against a
    `just` that provides nothing: the value reaches stdout even on the refusal
    path. And the client has to CARRY it: the log step is the one command the
    run asks to be STREAMED rather than captured, so what the pod printed is
    what the operator reads.

    The streamed step is read off `streamed` rather than `argvs` on purpose. A
    client that captured the logs and dropped them would record the identical
    argv here and show an operator nothing.
    """
    consumer = _a_consumer_repository(
        root=tmp_path / "pinned",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
        core_pin="v0.42.1",
    )
    manifest = _rendered_for(repo_root=consumer)
    script = _container_script(manifest=manifest, name="gate")

    reporting = [
        line
        for line in script
        if "LIVESPEC_CORE_PLUGIN_ROOT" in line and not line.lstrip().startswith("#")
    ]

    assert len(reporting) == 1, (
        "the gate container's script does not report the core plugin root it "
        "was handed, so a reader of the verdict stream cannot tell whether "
        f"core was resolved: {reporting}"
    )

    reports = script.index(reporting[0])
    first_just = next(index for index, line in enumerate(script) if "just " in line)

    assert reports < first_just, (
        "the gate container reports its core resolution only after the check "
        "sequence has started, so a Job that refuses a missing recipe reports "
        "nothing about core"
    )
    assert _literal_env(manifest=manifest, container="gate")["LIVESPEC_CORE_PLUGIN_ROOT"] == (
        _CORE_PLUGIN_ROOT
    )

    returncode, stdout, _stderr, invoked = _run_the_pod_script(
        manifest=manifest, root=tmp_path / "pod"
    )

    assert returncode != 0
    assert invoked == [f"just --show {_CONSUMER_RECIPE}"]
    assert _CORE_PLUGIN_ROOT in stdout, (
        "the gate pod ran without reporting the core plugin root it was handed: " f"{stdout!r}"
    )
    assert "v0.42.1" in stdout

    cluster = _CannedWorldRealRenderer()
    _ = run_delegated_gate(
        repo_root=consumer, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert len(cluster.streamed) == 1
    streamed = cluster.streamed[0]
    assert "logs" in streamed
    assert "--follow" in streamed
    assert f"job/{_ASSIGNED_JOB}" in streamed


def _gate_script_from_a_template_without_the_sibling_step(
    *, root: Path, scratch: Path
) -> list[str]:
    """`root`'s gate script, rendered from the template with the step's LINE deleted.

    The control that makes "exactly as before" measurable rather than asserted.
    A template whose `@@GATE_SIBLING_CLONES@@` line is gone is the template this
    repository shipped before the step existed, so a non-declaring repository's
    command matching this one — line for executable line — is the whole of the
    claim that nothing changed for it.
    """
    mutant = scratch / "template-without-the-step.yaml"
    scratch.mkdir(parents=True, exist_ok=True)
    _ = mutant.write_text(
        "\n".join(
            line
            for line in _TEMPLATE.read_text(encoding="utf-8").splitlines()
            if _SIBLING_TOKEN not in line
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(_RENDERER), "--repo-root", str(root), "--tree-hash", _TREE],
        cwd=str(root),
        env={**os.environ, "GATE_JOB_TEMPLATE": str(mutant)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return _executable_script(manifest=completed.stdout, name="gate")


def test_the_gate_job_provisions_the_sibling_clones_the_consumers_checks_read(
    *, tmp_path: Path
) -> None:
    """The pod gets the cited siblings, anonymously, before any recipe runs.

    livespec core validates every `external_references` entry against the cited
    sibling's REAL headings, read at whatever `resolve_effective_local_clone`
    returns: `$LIVESPEC_SIBLING_CLONES_ROOT/<sibling>` when that variable is
    set, and otherwise the manifest's own `local_clone` —
    `/data/projects/<sibling>`, which exists on a fleet host and NOWHERE in a
    gate pod. A MISSING PATH IS NOT AN ERROR THERE: the reader takes it as an
    empty heading set and drops every allowlist entry for that sibling, so a
    correctly allowlisted citation is reported "not allowlisted". Measured
    2026-10-18 on Job gate-livespec-e0a55a1a58f6, which failed
    `doctor-no-cross-spec-reference` at livespec
    `SPECIFICATION/constraints.md:298` on a tree whose master CI was green and
    which passes that check locally.

    THE CONSUMER'S OWN CI ALREADY DOES THIS, and a gate is held to judging the
    tree the way CI does: livespec's workflow step "Clone sibling repos for
    cross-repo wiring check" shallow-clones its siblings from github.com into
    `$RUNNER_TEMP/sibling-clones` and exports the variable for
    `check-doctor-static`.

    TWO FIXTURES, BECAUSE THE SET MUST BE DERIVED. A hardcoded list could
    satisfy either arm alone and not both; these declare different siblings and
    one renderer answers each with its own. The clones are asserted against the
    EXPORTED root rather than a path literal, because the property the readers
    depend on is that the directory the variable names is the directory the
    clones landed in — and the last arm observes exactly that from outside the
    pod, by running the script and reading the root `just` inherited.

    AND NO CREDENTIAL REACHES THE POD FOR THEM, which is what makes this the
    same kind of fetch as the livespec core one above: these are public
    repositories on github.com over anonymous https, so there is nothing in the
    clone commands to leak or rotate.
    """
    declaring = _a_consumer_repository(
        root=tmp_path / "declaring", declaration="", siblings=_WIDGET_SIBLINGS
    )
    other = _a_consumer_repository(
        root=tmp_path / "other", declaration="", siblings=_GADGET_SIBLINGS
    )

    manifest = _rendered_for(repo_root=declaring)
    clones_root = _exported_sibling_clones_root(manifest=manifest)
    clones = _sibling_clone_commands(manifest=manifest)

    assert clones_root.startswith(
        "/"
    ), f"the sibling-clones root is not an absolute path in the pod: {clones_root!r}"
    assert not clones_root.startswith("/workspace"), (
        "the gate clones its siblings INTO the tree under test, so the aggregate "
        f"judges a worktree the gate itself dirtied: {clones_root!r}"
    )
    assert len(clones) == len(
        _WIDGET_SIBLINGS
    ), f"the Job does not clone one sibling per declared target: {clones}"
    for (name, url), command in zip(_WIDGET_SIBLINGS, clones, strict=True):
        assert f"'{url}'" in command, f"{name} is not cloned from its declared url: {command}"
        assert (
            f"'{clones_root}/{name}'" in command
        ), f"{name} is not cloned where the readers resolve it: {command}"
        assert "--depth" in command, f"the {name} clone is not shallow: {command}"
        assert "@" not in command, f"a credential rides the {name} clone: {command}"

    assert [
        command.split("'")[1]
        for command in _sibling_clone_commands(manifest=_rendered_for(repo_root=other))
    ] == [url for _name, url in _GADGET_SIBLINGS], (
        "a second declaration renders the same clones, so the set is a constant "
        "rather than the repository's own"
    )

    first_recipe = _index_of_first_recipe(manifest=manifest)
    script = _executable_script(manifest=manifest, name="gate")
    assert max(script.index(command) for command in clones) < first_recipe
    assert (
        next(
            index
            for index, line in enumerate(script)
            if line.strip().startswith(_SIBLING_ROOT_EXPORT)
        )
        < first_recipe
    )

    returncode, _stdout, _stderr, invoked = _run_the_pod_script(
        manifest=manifest, root=tmp_path / "pod", provides=_FALL_THROUGH_SUITE
    )

    assert returncode == 0, f"the gate refused a tree whose siblings cloned cleanly: {invoked}"
    assert f"sibling-root {clones_root}" in invoked, (
        "the gate's own check suite does not inherit the provisioned root, so a "
        f"cited sibling still resolves at /data/projects: {invoked}"
    )
    assert max(
        index for index, line in enumerate(invoked) if line.startswith("git clone ")
    ) < invoked.index(
        f"just {_FALL_THROUGH_SUITE[0]}"
    ), f"a check-suite recipe ran before its siblings were provisioned: {invoked}"


def test_a_consumer_declaring_no_cross_repo_siblings_gets_the_command_it_has_today(
    *, tmp_path: Path
) -> None:
    """A repository that declares nothing renders no step, and nothing else moves.

    The absence has to be a RENDERED one. A test that only looked for missing
    `git clone` lines would pass just as well against a template that had never
    carried the step at all, so the first arm asserts the template DOES carry
    it — the step is there, and this repository's render of it is empty.

    THE CONTROL IS THE WHOLE POINT OF THE SECOND HALF. "Exactly as before" is
    measured against the same template with the step's line deleted, which IS
    the template that shipped before this step existed: executable line for
    executable line, the two commands are the same script. And the pod run
    closes it behaviourally — the suite runs with the variable UNSET, so a
    cited sibling resolves exactly where it resolved yesterday rather than
    through a root holding no clones, which would be strictly worse than not
    provisioning at all.
    """
    silent = _a_consumer_repository(root=tmp_path / "silent", declaration="")
    pinning_only = _a_consumer_repository(
        root=tmp_path / "pinning-only", declaration="", core_pin="v0.42.1"
    )

    assert _SIBLING_TOKEN in _TEMPLATE.read_text(encoding="utf-8"), (
        "the template carries no sibling-clone step at all, so no repository's "
        "Job can provision the clones its cross-repo readers need"
    )

    for repo_root in (silent, pinning_only):
        manifest = _rendered_for(repo_root=repo_root)
        script = _executable_script(manifest=manifest, name="gate")

        assert [line for line in script if _SIBLING_ROOT_VARIABLE in line] == []
        assert _sibling_clone_commands(manifest=manifest) == []
        assert _recipes_run(manifest=manifest) == [
            f"just {recipe}" for recipe in _FALL_THROUGH_SUITE
        ]
        assert script == _gate_script_from_a_template_without_the_sibling_step(
            root=repo_root, scratch=repo_root / "control"
        )

    manifest = _rendered_for(repo_root=silent)
    _returncode, _stdout, _stderr, invoked = _run_the_pod_script(
        manifest=manifest, root=tmp_path / "pod"
    )

    assert [line for line in invoked if line.startswith("sibling-root")] == []
    assert [line for line in invoked if line.startswith("git ")] == []


def test_a_gate_whose_sibling_clone_fails_is_red_and_names_that_sibling(*, tmp_path: Path) -> None:
    """A sibling the pod cannot fetch is a RED gate, named, before any recipe runs.

    This is the failure mode the step must not have. An unfetched sibling does
    not make a cross-repo reader fail — it makes it read an empty tree and drop
    the allowlist entries it would have validated, which is a GREEN gate on a
    tree nothing judged. So the clone's own failure has to be the verdict, and
    it has to arrive before the suite starts rather than as one red member among
    a run that may or may not have reached it.

    THE TWO ARMS ARE JOINED BY A VALUE, as in the missing-recipe scenario above:
    the message the pod actually produced is the message the canned cluster
    reports as the failed pod's termination message, so the verdict naming the
    sibling is the pod's own wording reaching an operator. `refuses_push` and
    the absent green token are asserted too — a verdict nobody acts on still
    completes a push.

    AND THE LAST ARM IS THE CONTROL. The same manifest, with a clone that
    succeeds, runs the declared recipe: the refusal is the clone failing, not
    the step refusing everything.
    """
    consumer = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
        siblings=_WIDGET_SIBLINGS,
    )
    manifest = _rendered_for(repo_root=consumer)
    failed, _url = _WIDGET_SIBLINGS[0]

    returncode, _stdout, stderr, invoked = _run_the_pod_script(
        manifest=manifest,
        root=tmp_path / "failing",
        clone_fails=True,
        provides=(_CONSUMER_RECIPE,),
    )

    assert returncode != 0
    assert (
        f"'{failed}'" in stderr
    ), f"the gate is red but does not name the sibling it could not clone: {stderr!r}"
    assert [
        line for line in invoked if line.startswith(f"just {_CONSUMER_RECIPE}")
    ] == [], f"a check-suite recipe ran despite an unprovisioned sibling: {invoked}"

    cluster = _CannedWorldRealRenderer(pod_message=stderr.strip())
    verdict = run_delegated_gate(
        repo_root=consumer, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_FAILED
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert failed in verdict.detail
    assert not [argv for argv in cluster.argvs if "green_token" in " ".join(argv)]

    code, _out, _err, ran = _run_the_pod_script(
        manifest=manifest, root=tmp_path / "clean", provides=(_CONSUMER_RECIPE,)
    )

    assert code == 0, f"the gate refused a tree whose siblings cloned cleanly: {ran}"
    assert f"just {_CONSUMER_RECIPE}" in ran


def test_a_private_sibling_uses_a_per_run_secret_without_putting_its_token_in_the_manifest(
    *, tmp_path: Path
) -> None:
    """A private sibling reads its token from the per-run Secret mount.

    The renderer is deliberately given a distinctive token-like value only as
    the Secret's *name*.  A real installation token never reaches its argv:
    this assertion is about the rendered artifact an API server and Job log can
    expose, so it must contain the mount reference and clone behaviour but not
    credential material.
    """
    private_name, private_url = _WIDGET_SIBLINGS[0]
    public_name, public_url = _WIDGET_SIBLINGS[1]
    consumer = _a_consumer_repository(
        root=tmp_path / "declaring", declaration="", siblings=_WIDGET_SIBLINGS
    )
    secret_name = "gate-sibling-token-7f2qd"
    completed = subprocess.run(
        [
            str(_RENDERER),
            "--repo-root",
            str(consumer),
            "--tree-hash",
            _TREE,
            "--private-sibling",
            private_name,
            "--private-sibling-secret",
            secret_name,
        ],
        cwd=str(consumer),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = completed.stdout
    private_clone = next(
        line for line in _sibling_clone_commands(manifest=manifest) if f"'{private_url}'" in line
    )
    public_clone = next(
        line for line in _sibling_clone_commands(manifest=manifest) if f"'{public_url}'" in line
    )
    assert "http.extraHeader" in private_clone
    assert "/run/secrets/gate-private-siblings/token" in private_clone
    assert "http.extraHeader" not in public_clone
    assert f"name: {secret_name}" in manifest
    assert "secretName: " + secret_name in manifest
    assert "token-like-value" not in manifest


def test_a_red_members_verdict_names_the_member_not_a_fatal_from_its_own_output(
    *, tmp_path: Path
) -> None:
    """A red MEMBER is named as the cause; a `FATAL:` it printed is not.

    THE DEFECT THIS CLOSES, MEASURED 2026-10-19 (livespec-dev-tooling-plbimj).
    The red verdict of `gate-livespec-dev-tooling-54f19942138d` read "FATAL:
    cannot clone cross-repo sibling 'widget-core' from
    https://github.com/acme/widget-core … so no recipe was run". Both halves
    were false: the recipe ran (78 passed, 1 failed, 1 skipped) and its one
    failure was `check-no-workflow-edits`. `acme/widget-core` is FIXTURE TEXT
    belonging to this repository's own gate-renderer exit tests, which run
    inside the gate's own aggregate and write the rendered refusal to the pod's
    real `/dev/termination-log`. So the one line an operator reads sent them
    after a clone failure that never happened, on a repository registering no
    siblings at all.

    THE FIX IS OWNERSHIP, AND THAT IS WHAT THE LAST ARM ASSERTS. The pod writes
    the verdict detail AFTER its recipes have run and TRUNCATES the termination
    log doing so, so a member that wrote that file mid-run cannot be the message
    the cluster reports. Nothing here can observe the real
    `/dev/termination-log` — the write is best-effort and this host has no such
    file — so the arms join on the string the pod puts on BOTH streams, exactly
    as the missing-recipe and failed-clone scenarios above do, plus the rendered
    script's own ordering.

    The provisioning verdicts are NOT changed by any of this: the two scenarios
    above are the regression guard for them, and they still read the pod's own
    words for a failed clone and a missing recipe.
    """
    consumer = _a_consumer_repository(
        root=tmp_path / "declaring",
        declaration=f'gate_check_suite = ["{_CONSUMER_RECIPE}"]\n',
    )
    manifest = _rendered_for(repo_root=consumer)

    returncode, stdout, stderr, invoked = _run_the_pod_script(
        manifest=manifest,
        root=tmp_path / "pod",
        provides=(_CONSUMER_RECIPE,),
        failing_member=_RED_MEMBER,
        member_captured_output=_MEMBER_FIXTURE_FATAL,
    )

    # The Given, asserted rather than assumed: the recipe RAN, and the fixture
    # `FATAL:` really is inside that member's own captured output.
    assert invoked == [f"just --show {_CONSUMER_RECIPE}", f"just {_CONSUMER_RECIPE}"]
    assert _MEMBER_FIXTURE_FATAL in stdout
    # The verdict STATE and the exit status are untouched by this item.
    assert returncode == 1

    assert _RED_MEMBER in stderr, (
        "the gate is red on a member but its message does not name that member, so the "
        f"one line an operator reads cannot be acted on: {stderr!r}"
    )
    assert _FIXTURE_FATAL_FRAGMENT not in stderr, (
        "a `FATAL:` line from inside a member's captured output became the pod's own "
        f"last words: {stderr!r}"
    )

    cluster = _CannedWorldRealRenderer(pod_message=stderr.strip())
    verdict = run_delegated_gate(
        repo_root=consumer, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_FAILED
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert _RED_MEMBER in verdict.detail
    assert _FIXTURE_FATAL_FRAGMENT not in verdict.detail
    assert not [argv for argv in cluster.argvs if "green_token" in " ".join(argv)]

    # THE MECHANISM, in the rendered script: a member's mid-run write to the
    # termination log is overwritten because the pod's own write comes after the
    # recipes and truncates. Without this the two arms above would hold only for
    # a pod whose members happened to leave the file alone.
    script = _executable_script(manifest=manifest, name="gate")
    writes = [index for index, line in enumerate(script) if _TERMINATION_WRITE in line]
    assert writes, f"the gate container never writes its own termination message: {script}"
    assert max(writes) > _index_of_first_recipe(manifest=manifest), (
        "every termination-log write the gate container makes precedes its recipes, so a "
        "member that writes that file mid-run is the message the cluster reports"
    )
