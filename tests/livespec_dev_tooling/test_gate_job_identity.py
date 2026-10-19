"""A gate Job's identity: ONE PER RUN, and still selectable by its tree.

WHY THIS EXISTS (livespec-dev-tooling-44fglo, measured 2026-10-18). The gate Job
was named `gate-<repo>-<first 12 hex of the tree hash>` and the template collects
a finished Job an hour after it ends, so for that hour a SECOND gate of the same
tree could not be submitted at all: `kubectl create` answered `AlreadyExists` and
the client reported NO_VERDICT, which is the outcome reserved for a lost cluster.
Gate Job `gate-livespec-473f0ffdee14` ended Failed at 07:02:17Z and an
independent replay of the same tree at 07:07Z was refused at submit, resting
livespec-dev-tooling-s35dcb in acceptance rework for behaviour it had in fact
reproduced. Two ordinary operator moves hit it: a push refused on a red verdict
and retried after a cluster-side fix that changed nothing in the tree, and any
independent replay of a just-gated tree.

THE CLUSTER NAMES THE JOB NOW, which is what makes the second run a run. The
manifest carries `generateName`, so the API server appends a unique suffix at
create time and the client reads the name it was given back off the submit. That
places uniqueness with the one party that can enforce it: two pushes of one tree
racing each other both get a name, where any suffix the client invented itself
could collide.

AND THE TREE SURVIVES THAT, which is the half a fix could silently destroy. Once
a name is `gate-<repo>-<tree12>-<suffix>` it is no longer the identity of a tree,
so the `livespec.gate/tree-hash` label is what still gathers every Job of one
tree — `kubectl get jobs -l livespec.gate/tree-hash=<hash>` is how an operator
finds the gates of the tree in front of them. It is asserted here BESIDE the
naming change rather than anywhere else, because the two are one decision.

NOTHING HERE REACHES A CLUSTER. The renderer really runs — it is a bash script
that reads a fixture directory and writes YAML — while every git and cluster
command is answered by `_NameAwareApiServer` below, which differs from the canned
runners elsewhere in this suite in exactly one way: it knows which Jobs exist, so
a duplicate name is refused the way an API server refuses one and a poll for a
Job nobody created is NotFound rather than a quiet success.
"""

from __future__ import annotations

import json
import subprocess
from itertools import takewhile
from pathlib import Path
from typing import TYPE_CHECKING

from returns.pipeline import is_successful
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_client import run_gate
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request
from livespec_dev_tooling.gate_remote_invocation import GateCommandResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from returns.result import Result

    from livespec_dev_tooling.gate_remote_client import GateRunOutcome
    from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateStepFailed

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"

# The tree of the MEASURED instance, and the repository the fixture stands in
# for. The gated tree names the mirror refs, the Job's label and the Job's name
# prefix, so one value runs through every assertion below.
_TREE = "473f0ffdee148f98221d300ecc6debbf46407f97"
_REPOSITORY = "widget"
_ORIGIN = f"https://github.com/thewoolleyman/{_REPOSITORY}.git"
_NAME_PREFIX = f"gate-{_REPOSITORY}-{_TREE[:12]}"

# The two runs' terminal conditions, in creation order: the first gate of the
# tree is RED and the second is GREEN. "Its own verdict" is therefore a
# DIFFERENCE this test reads rather than a word it repeats — a second run that
# had adopted the first run's Job would report the first run's condition.
_VERDICTS = ("Failed", "Complete")

_IMAGE = "ghcr.io/example/sandbox:python-v1.64.2"
_WORKFLOW = f"jobs:\n  one:\n    runs-on: self-hosted\n    container:\n      image: {_IMAGE}\n"


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


def _ran(*, stdout: str = "") -> GateCommandOutcome:
    """One command that ran and succeeded."""
    return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _refused(*, stderr: str) -> GateCommandOutcome:
    """One command the API server ran and REFUSED — never a command that did not run."""
    return Success(GateCommandResult(returncode=1, stdout="", stderr=stderr))


def _a_gated_repository(*, root: Path) -> Path:
    """The smallest tree the renderer will render for: one container image.

    The image is read from the gated repository's OWN workflow rather than baked
    into the template, so a fixture without a `ci.yml` is refused — which is the
    renderer working as specified, not a shortcoming of this fixture.
    """
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_text(_WORKFLOW, encoding="utf-8")
    return root


class _NameAwareApiServer:
    """`kubectl` against an API server that ENFORCES name uniqueness.

    The one property the canned runners elsewhere in this suite do not model, and
    the whole subject here: a `create` of an object whose name is already taken is
    refused with `AlreadyExists`, and a `get job` for a name nobody created is
    `NotFound`. Both answers are REFUSALS — exit 1 with the API server's own
    wording — rather than commands that did not run, because the defect under
    test is a command that ran and was declined.

    `jobs` is the namespace's Job list in creation order, which is also the whole
    measurement: two entries means a tree was gated twice.

    `silent_submit` makes `create` succeed while printing nothing — not a shape a
    real `kubectl create --output name` produces, which is the point: the client
    cannot verify that it does not, so an unreadable answer needs a disposition.

    The RENDERER really runs. It is the artifact that decides how a Job is named,
    so stubbing it would assert the stub; it reads a fixture directory and writes
    YAML to stdout, opening no socket and touching nothing outside its output.
    """

    def __init__(self, *, silent_submit: bool = False) -> None:
        self.jobs: list[str] = []
        self.argvs: list[tuple[str, ...]] = []
        self._polled: set[str] = set()
        self._silent_submit = silent_submit

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = stream
        self.argvs.append(tuple(argv))
        if argv[0] == str(_RENDERER):
            return self._render(argv=argv, cwd=cwd)
        if "create" in argv:
            return self._create(manifest=stdin or "")
        if "job" in argv:
            return self._get_job(name=argv[argv.index("job") + 1])
        if "rev-parse" in argv:
            return _ran(stdout=f"{_TREE}\n")
        if "get-url" in argv:
            return _ran(stdout=f"{_ORIGIN}\n")
        # The mirror push, the log stream, the pod read and the ref collection:
        # the run reads their exit codes, never their output.
        return _ran()

    def _render(self, *, argv: Sequence[str], cwd: Path) -> GateCommandOutcome:
        completed = subprocess.run(
            list(argv), cwd=str(cwd), capture_output=True, text=True, check=False
        )
        return Success(
            GateCommandResult(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        )

    def _create(self, *, manifest: str) -> GateCommandOutcome:
        """Admit one Job, by the name the manifest asks for or by one assigned here.

        A `generateName` manifest is what an API server appends a suffix to, so
        the suffix is assigned HERE, from the Job count — deterministic rather
        than random, because what has to be readable is that the two names
        DIFFER, not what they differ by.
        """
        if self._silent_submit:
            return _ran()
        generated = _metadata_field(manifest=manifest, key="generateName")
        if generated is not None:
            return self._admit(name=f"{generated}{len(self.jobs):05d}")
        fixed = _metadata_field(manifest=manifest, key="name")
        assert fixed is not None, f"the manifest names no Job at all:\n{manifest}"
        if fixed in self.jobs:
            return _refused(
                stderr=(
                    'Error from server (AlreadyExists): error when creating "STDIN": '
                    f'jobs.batch "{fixed}" already exists\n'
                )
            )
        return self._admit(name=fixed)

    def _admit(self, *, name: str) -> GateCommandOutcome:
        """Record the created Job and answer as `kubectl create --output name` does."""
        self.jobs.append(name)
        return _ran(stdout=f"job.batch/{name}\n")

    def _get_job(self, *, name: str) -> GateCommandOutcome:
        """One Job's status — or NotFound, for a name this namespace never held.

        A Job reports NO condition on its first poll, because Kueue has to
        unsuspend it first, and the per-Job sequence is what makes that true of
        the second run as well as the first. It is also the only thing that
        exercises the run's wait at all.
        """
        if name not in self.jobs:
            return _refused(stderr=f'Error from server (NotFound): jobs.batch "{name}" not found\n')
        if name not in self._polled:
            self._polled.add(name)
            return _ran(stdout=json.dumps({"status": {}}))
        state = _VERDICTS[self.jobs.index(name)]
        return _ran(
            stdout=json.dumps({"status": {"conditions": [{"type": state, "status": "True"}]}})
        )


def _job_metadata_lines(*, manifest: str) -> list[str]:
    """The JOB's own `metadata:` block — never the pod template's.

    Bounded by COLUMN ZERO, because the template carries a second
    `metadata:`/`labels:` pair inside its pod spec: a claim about how the Job is
    named must not be satisfiable by a label on its pods.
    """
    lines = manifest.splitlines()
    start = lines.index("metadata:")
    return list(takewhile(lambda line: line.startswith((" ", "\t")), lines[start + 1 :]))


def _metadata_field(*, manifest: str, key: str) -> str | None:
    """One `key:` value out of the Job's metadata block, or `None` when absent.

    Comment lines are dropped first: the template explains at length WHY the
    cluster assigns the name, and prose about a field must never read as the
    field.
    """
    for line in _job_metadata_lines(manifest=manifest):
        stripped = line.strip()
        if not stripped.startswith("#") and stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _one_gate_run(
    *, repo_root: Path, cluster: _NameAwareApiServer
) -> Result[GateRunOutcome, GateStepFailed]:
    """One whole delegated gate of `repo_root`'s HEAD tree, assembly included.

    The request is ASSEMBLED rather than hand-written, so the Job name this run
    waits on is the one the real renderer and the real client agree on. A
    hand-written request would let a test pass with a renderer that names the
    Job any way at all.
    """
    built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=cluster)
    assert isinstance(built, Success), built
    return run_gate(request=built.unwrap(), runner=cluster, sleeper=_no_sleep)


def test_re_gating_a_tree_whose_previous_job_still_exists_is_a_new_job_with_its_own_verdict(
    *, tmp_path: Path
) -> None:
    """The measured defect, as the two runs an operator actually makes.

    One tree, gated twice against a namespace that still holds the first gate's
    Job — which is the state the template's one-hour `ttlSecondsAfterFinished`
    guarantees for an hour after any gate ends. Both runs must reach a verdict,
    and each must reach ITS OWN: the stand-in answers the first Job `Failed` and
    the second `Complete`, so a run that had adopted the other's Job reports the
    other's condition and fails here.

    `is_successful` is asserted on BOTH halves because the defect was a refusal
    at submit, not a wrong answer: `AlreadyExists` reaches the client as a step
    that could not be completed, which the verdict layer above reports as
    NO_VERDICT and the push is refused.
    """
    repo_root = _a_gated_repository(root=tmp_path / _REPOSITORY)
    cluster = _NameAwareApiServer()

    first = _one_gate_run(repo_root=repo_root, cluster=cluster)
    second = _one_gate_run(repo_root=repo_root, cluster=cluster)

    assert is_successful(first), first
    assert is_successful(second), second
    assert len(cluster.jobs) == 2, cluster.jobs
    assert all(name.startswith(_NAME_PREFIX) for name in cluster.jobs), cluster.jobs
    assert cluster.jobs[0] != cluster.jobs[1]
    assert [first.unwrap().job_name, second.unwrap().job_name] == cluster.jobs
    assert [first.unwrap().terminal_state, second.unwrap().terminal_state] == list(_VERDICTS)


def test_the_stand_in_still_refuses_a_duplicate_fixed_name_the_way_the_api_server_did() -> None:
    """The CONTROL — an instrument that cannot see the defect proves nothing.

    Every pass above is read off `_NameAwareApiServer`, so a stand-in that
    quietly admitted a duplicate name would report the fixed shape for a
    manifest that still carries one, and the measurement would be a tautology.
    This drives it with the manifest the renderer produced BEFORE the fix — a
    `metadata.name` fixed by the gated tree — and with a poll for a name nobody
    created, and asserts the two refusals the API server makes: `AlreadyExists`
    at the second create, `NotFound` at the poll. Those are the answers that
    make the passes above measurements.
    """
    cluster = _NameAwareApiServer()
    fixed = f"apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: {_NAME_PREFIX}\n"
    submit = ["kubectl", "create", "--filename", "-", "--output", "name"]

    admitted = cluster(argv=submit, cwd=_REPO_ROOT, stdin=fixed)
    duplicate = cluster(argv=submit, cwd=_REPO_ROOT, stdin=fixed)
    unknown = cluster(argv=["kubectl", "get", "job", f"{_NAME_PREFIX}-x7k2q"], cwd=_REPO_ROOT)

    assert cluster.jobs == [_NAME_PREFIX]
    assert admitted.unwrap().stdout.strip() == f"job.batch/{_NAME_PREFIX}"
    assert duplicate.unwrap().returncode == 1
    assert "AlreadyExists" in duplicate.unwrap().stderr
    assert unknown.unwrap().returncode == 1
    assert "NotFound" in unknown.unwrap().stderr


def test_each_run_waits_on_the_job_the_cluster_created_rather_than_a_name_it_chose(
    *, tmp_path: Path
) -> None:
    """The name is READ BACK, which is what the poll and the log stream then use.

    A client that submitted a `generateName` manifest and went on waiting on a
    name of its own would poll a Job that does not exist — and the API server
    answers NotFound, which is a refusal, so the gate it just submitted would be
    reported as no verdict. Asserted on the argv of the poll and of the log
    stream, because those are the two commands that have to carry the assigned
    name for the verdict and its log to be the ones an operator reads.
    """
    repo_root = _a_gated_repository(root=tmp_path / _REPOSITORY)
    cluster = _NameAwareApiServer()

    outcome = _one_gate_run(repo_root=repo_root, cluster=cluster)

    assert is_successful(outcome), outcome
    created = cluster.jobs[0]
    assert created != _NAME_PREFIX
    assert [argv for argv in cluster.argvs if "job" in argv and created in argv]
    assert [argv for argv in cluster.argvs if f"job/{created}" in argv]


def test_a_submit_that_names_no_job_is_a_plumbing_failure_rather_than_a_nameless_wait(
    *, tmp_path: Path
) -> None:
    """A create the client cannot read a name out of decided NOTHING.

    The name is the only handle on the Job that was just created, so a submit
    that printed none leaves the run with nothing to poll, nothing to stream and
    nothing to collect. That is a step that did not do its job — the step is
    named and the push is refused — rather than a wait on the empty string,
    which the API server would answer for some other object or not at all.
    """
    repo_root = _a_gated_repository(root=tmp_path / _REPOSITORY)
    cluster = _NameAwareApiServer(silent_submit=True)

    outcome = _one_gate_run(repo_root=repo_root, cluster=cluster)

    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "submit-gate-job"
    assert outcome.failure().returncode is None
    assert "named no Job" in outcome.failure().detail


def test_the_rendered_job_lets_the_cluster_name_it_and_still_labels_the_gated_tree(
    *, tmp_path: Path
) -> None:
    """The two halves of the naming change, asserted as the one decision they are.

    NOTHING FIXES THE NAME: the manifest carries `generateName` and no `name`, so
    a second gate of one tree is a new object rather than a duplicate the API
    server refuses. The prefix still carries the tree, so a Job is still legible
    as the gate of a particular tree at a glance.

    AND THE TREE IS STILL A LABEL, which is the part the first half could have
    taken with it. Once the name ends in a suffix the cluster chose, the name no
    longer identifies a tree; `livespec.gate/tree-hash` is what gathers every Job
    of one tree, which is how an operator selects the gates of the tree in front
    of them and how any sweep over a tree's Jobs is written.
    """
    repo_root = _a_gated_repository(root=tmp_path / _REPOSITORY)
    cluster = _NameAwareApiServer()
    built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=cluster)

    assert isinstance(built, Success), built
    manifest = built.unwrap().manifest

    assert _metadata_field(manifest=manifest, key="name") is None, manifest
    assert _metadata_field(manifest=manifest, key="generateName") == f"{_NAME_PREFIX}-"
    assert _metadata_field(manifest=manifest, key="livespec.gate/tree-hash") == _TREE
