"""Consumer-tier: a delegated gate Job leaves the authority members to the pushing host.

The "What the delegated gate runs" bullet of this repository's own
`SPECIFICATION/contracts.md`, delegated pre-push gate section, says of a member
that declares it reads an AUTHORIZATION held outside the tree that it "does not
run in the gate Job". The acceptance shape is the `scenarios.md` scenario about
an authority-reading member of an opted-in push, whose first THEN is exactly
that: "the gate Job MUST NOT run that member".

THE HALF THAT WAS MISSING, AND MEASURED. The pushing-host half shipped first:
`check_authority members` names the declaring members and
`_gate_host_authority.run_host_authority_members` runs them here, with this
host's own credentials. The JOB half existed in exactly ONE place —
`scripts/just/check.sh`, which is livespec-dev-tooling's OWN aggregate runner and
reaches no consuming repository at all. So in every consumer's Job the
forge-admin member ran and failed: measured 2026-10-24 ~11:00Z on livespec's
re-landed opt-in, where gate Job gate-livespec-p87qc refused a green tree because
`check-branch-protection-alignment` got HTTP 403 inside the pod, and again
01:41-01:45Z the same day on gate-livespec-overseer-tpfd2, which ran overseer's
master green on every member except that one.

WHY THE FIX CANNOT BE COPIED INTO EACH CONSUMER, which is the whole reason this
file asserts the two spellings side by side. The consumers do not agree on the
NAME of the variable their own `check` recipe reads its skip list from —
livespec's reads `SKIP_TARGETS`, livespec-overseer's reads `LIVESPEC_CHECK_SKIP`
— so a shared mechanism has to carry the members under WHICHEVER name the
repository under test reads, and one that hardcoded either name would be
correct in one repository and silently inert in the other. Inert is the
dangerous direction: the member runs, fails on a credential the pod is designed
not to hold, and a correct tree reads as RED.

WHY THIS TIER. The claim spans four artifacts that cannot see each other: the
consumer's own `justfile`, the Python client that reads it and the authority
declarations, the bash renderer that writes the manifest, and the pod script
that manifest carries. A unit test on any one of them passes against a drifted
neighbour, which is how the one-repository skip above read as a fleet-wide one.

AND A CONSUMER THE MECHANISM CANNOT TELL GETS NO JOB AT ALL, which is the half
this file asserted the opposite of until 2026-10-25. Rendering a Job for such a
repository was reasoned as safe on the grounds that the member would run and
FAIL, so an unestablished reading could only redden a correct tree. Both halves
of that were measured wrong on 2026-10-24. The silence is the first: three
consumers — livespec-driver-pi, livespec-orchestrator-git-jsonl and
livespec-orchestrator-beads-fabro — read their skip list from no variable this
client recognises, so each one's Job ran the forge-admin member while printing
no `NOT running` line, and nothing anywhere said a mechanism had been skipped.
The second is worse than a red tree: the orchestrator's Job
`gates/gate-livespec-orchestrator-beads-fabro-ssqmj` PASSED on 2026-10-24
18:19:01Z with `check-branch-protection-alignment` executed IN-POD, so the
branch-protection answer came from a credential the gate pod holds rather than
from the pushing host's own — an authorization the host never read, reported as
gated. A Job that cannot be told therefore must not be submitted.

NOTHING HERE REACHES A CLUSTER, A MIRROR OR A HOST. The consumer is a fixture
tree under `tmp_path` and the client's only door to the world is its
`GateCommandRunner` seam, which the canned runner below answers itself. The ONE
command it really runs is the renderer — a bash script that contacts nothing by
construction — because "the Job is told what not to run" is a claim about what
that script produces, and a canned manifest would assert it of the fixture.
"""

from __future__ import annotations

import subprocess
from itertools import takewhile
from pathlib import Path

import pytest
from returns.pipeline import is_successful
from returns.result import Result, Success
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.check_authority import repository_authority_members
from livespec_dev_tooling.gate_remote_client import GateRunRequest
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request, resolve_renderer
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandOutcome,
    GateCommandResult,
    GateStepFailed,
)

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = resolve_renderer(repo_root=_REPO_ROOT)

# The empty tree's hash — a real git object name, and the one the canned
# `rev-parse HEAD^{tree}` below answers with — plus the origin the client
# derives the mirror name and the gated repository's identity from.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ORIGIN = "git@github.com:acme/widget.git"

# The member of the measured defect, and a SHIPPED one: its authority
# declaration is the `CHECK_AUTHORITY = "forge-admin"` constant in
# `livespec_dev_tooling/checks/branch_protection_alignment.py`, so a fixture
# naming it declares what every real consumer declares rather than inventing a
# declaration this repository would then be the only reader of.
_AUTHORITY_MEMBER = "check-branch-protection-alignment"
# A member beside it that declares NOTHING, so the Job's coverage is observable:
# the direction a careless implementation drains is moving members onto the
# pushing host until the cluster gates nothing.
_PLAIN_MEMBER = "check-widget-lint"

# The two spellings the fleet actually carries, which is why the mechanism may
# not hardcode either: livespec's `check` recipe reads the first and
# livespec-overseer's reads the second.
_FLEET_SKIP_VARIABLES = ("SKIP_TARGETS", "LIVESPEC_CHECK_SKIP")

_GATE_CONTAINER = "gate"


class _CannedWorldRealRenderer:
    """The two local git reads canned; the RENDERER really runs.

    The renderer is half the subject, so stubbing it would assert the stub. It
    is a bash script that reads a fixture directory and writes YAML to stdout —
    it opens no socket and touches nothing outside its own output.

    NOTHING ELSE IS ANSWERED, because nothing else is asked. Assembling a
    request issues exactly three commands — the tree read, the origin read and
    the render — and a canned arm for a cluster step no arm here reaches would
    be a stub for a claim nobody makes.
    """

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
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
        """The tree under test, or the origin the gated identity is derived from."""
        if "rev-parse" in argv:
            return f"{_TREE}\n"
        return f"{_ORIGIN}\n"


def _a_consumer_repository(*, root: Path, skip_variable: str | None) -> Path:
    """A fixture opted-in consumer whose `check` recipe names ONE authority member.

    `skip_variable` is the environment variable that recipe reads its skip list
    from, written in the shape both real consumers write it. `None` writes a
    recipe that reads NO such variable, which is the repository where the
    mechanism can establish nothing — and must therefore change nothing.

    The check set is declared in the recipe's own `targets=(...)` array rather
    than in a `check-targets.txt`, because that is the surface every consuming
    repository in this fleet actually uses: none of them carries the inventory
    file this repository does.
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
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )
    reads = (
        "" if skip_variable is None else f'    read -ra skip_targets <<< "${{{skip_variable}:-}}"\n'
    )
    _ = (root / "justfile").write_text(
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        f"{reads}"
        "    targets=(\n"
        f"        {_AUTHORITY_MEMBER}\n"
        f"        {_PLAIN_MEMBER}\n"
        "    )\n"
        '    for target in "${targets[@]}"; do just "${target}"; done\n',
        encoding="utf-8",
    )
    return root


def _assembled(*, repo_root: Path) -> Result[GateRunRequest, GateStepFailed]:
    """What this client assembles for `repo_root` — a request, or its refusal.

    The RESULT rather than the manifest, because the two claims this file makes
    live on opposite tracks: a repository whose skip surface resolves renders a
    Job to read, and one whose surface cannot be established renders none at
    all, and a helper that unwrapped would turn the second claim into an error
    before any assertion saw it.
    """
    return gate_remote_request(
        repo_root=repo_root, renderer=_RENDERER, runner=_CannedWorldRealRenderer()
    )


def _rendered_manifest(*, repo_root: Path) -> str:
    """The manifest this client renders for `repo_root`, through the real renderer."""
    request = _assembled(repo_root=repo_root)
    assert is_successful(request), f"the request must assemble; got {request}"
    return request.unwrap().manifest


def _gate_container_script(*, manifest: str) -> list[str]:
    """The gate container's own shell script, dedented out of its block.

    Sliced from that container's `- name:` line so an initContainer — each of
    which runs its own `set -euo pipefail` block — cannot contribute a line to
    an assertion about this one.
    """
    lines = manifest.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.strip() == f"- name: {_GATE_CONTAINER}"
    )
    indent = len(lines[start]) - len(lines[start].lstrip())
    block = [
        lines[start],
        *takewhile(
            lambda line: not line.strip() or len(line) - len(line.lstrip()) > indent,
            lines[start + 1 :],
        ),
    ]
    opener = next(index for index, line in enumerate(block) if line.strip() == "- |")
    script_indent = len(block[opener]) - len(block[opener].lstrip()) + 2
    pad = " " * script_indent
    body = takewhile(lambda line: not line.strip() or line.startswith(pad), block[opener + 1 :])
    return [line[script_indent:] for line in body]


def _exported_skip(*, script: list[str], variable: str) -> list[str]:
    """The members one `export <variable>="..."` line of the pod script names.

    An ABSENT export answers the empty list, which is what a repository the
    mechanism can establish nothing for must render: there is a real difference
    between "no member was omitted" and "a member was omitted", and a reader
    that could not tell them apart would read today's RED pod as a fixed one.
    """
    prefix = f"export {variable}="
    exports = [line for line in script if line.startswith(prefix)]
    if not exports:
        return []
    assert len(exports) == 1, f"{variable} must be exported once; got {exports}"
    return exports[0][len(prefix) :].strip().strip('"').split()


def _declared_authority_members(*, repo_root: Path) -> tuple[str, ...]:
    """What `check_authority members` names for `repo_root`, resolution asserted."""
    resolved = repository_authority_members(repo_root=repo_root)
    assert is_successful(resolved), f"the authority resolution must succeed; got {resolved}"
    return unsafe_perform_io(resolved.unwrap())


@pytest.mark.parametrize("skip_variable", _FLEET_SKIP_VARIABLES)
def test_the_gate_job_omits_the_authority_members_under_the_consumers_own_skip_variable(
    *, tmp_path: Path, skip_variable: str
) -> None:
    """The scenario's first THEN, asserted where EVERY consumer reads it.

    One fixture consumer per spelling the fleet carries, each declaring the same
    one authority member in its own `targets=(...)` array. The rendered Job must
    carry that member — and only that member — under the variable that
    repository's own `check` recipe reads its skip list from, so the aggregate
    the pod runs never invokes it and never fails on the credential the pod is
    designed not to hold.
    """
    repo = _a_consumer_repository(root=tmp_path / "widget", skip_variable=skip_variable)
    declared = _declared_authority_members(repo_root=repo)
    assert declared == (_AUTHORITY_MEMBER,), f"the fixture must declare one member; got {declared}"

    script = _gate_container_script(manifest=_rendered_manifest(repo_root=repo))

    assert _exported_skip(script=script, variable=skip_variable) == list(declared)


def test_the_gate_job_still_runs_every_member_no_authority_declaration_names(
    *, tmp_path: Path
) -> None:
    """The second half: the Job verifies the same set, MINUS the authority members only.

    The direction a careless implementation drains is moving members onto the
    pushing host until the cluster gates nothing, so a repository that declares
    one authority member must have exactly that one omitted — the member beside
    it that declares nothing stays in the Job, which is where the whole
    aggregate runs.
    """
    declaring = _a_consumer_repository(
        root=tmp_path / "widget", skip_variable=_FLEET_SKIP_VARIABLES[0]
    )
    declaring_script = _gate_container_script(manifest=_rendered_manifest(repo_root=declaring))
    omitted = _exported_skip(script=declaring_script, variable=_FLEET_SKIP_VARIABLES[0])

    assert _PLAIN_MEMBER not in omitted
    assert omitted == [_AUTHORITY_MEMBER]


def test_a_consumer_whose_skip_surface_cannot_be_established_gets_no_gate_job_at_all(
    *, tmp_path: Path
) -> None:
    """A Job that cannot be told to leave the member out is never assembled.

    THE CLAIM IS ABOUT THE JOB, and it is made by observing that there is no
    Job: the client assembles no request, so nothing is rendered, nothing is
    submitted, and no pod runs the member this repository's own authority
    declaration names. The fixture is the shape all three measured consumers
    carry — a `check` recipe that reads its skip list from no variable this
    client recognises — and the control beside it is the same fixture WITH such
    a variable, which still assembles, so the refusal is a fact about the skip
    surface rather than about fixture repositories in general.

    WHY NOT RENDER IT ANYWAY, which is what this client did until 2026-10-25.
    The old reasoning was that an un-told Job merely runs the member and fails,
    reddening a correct tree at worst. The orchestrator's Job
    `gates/gate-livespec-orchestrator-beads-fabro-ssqmj` disproved it by
    PASSING: the pod ran `check-branch-protection-alignment` at 18:19:01Z on
    2026-10-24 and answered from a forge credential the pod itself holds, so the
    delegated verdict reported an authorization the pushing host never read as
    granted — which the contract's own "it never treats an unevaluated
    authorization as granted" forbids outright.
    """
    unestablishable = _a_consumer_repository(root=tmp_path / "gadget", skip_variable=None)
    declared = _declared_authority_members(repo_root=unestablishable)
    assert declared == (_AUTHORITY_MEMBER,), f"the fixture must declare one member; got {declared}"
    establishable = _a_consumer_repository(
        root=tmp_path / "widget", skip_variable=_FLEET_SKIP_VARIABLES[0]
    )

    refused = _assembled(repo_root=unestablishable)

    assert not is_successful(refused), f"no Job may be assembled; got {refused}"
    assert is_successful(_assembled(repo_root=establishable))
