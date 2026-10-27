"""The private cross-repo sibling's token: minted on the host, carried by one Job.

`SPECIFICATION/contracts.md` says, of the delegated pre-push gate and its
cross-repository siblings, that a private sibling is cloned with a GitHub App
installation token the PUSHING HOST mints at submission, that it must not appear in the
rendered manifest's text, that it must not be stored as a long-lived Secret or
under any new standing credential name, and that a host which cannot mint it
"refuses the push as a missing verdict". Work-item livespec-dev-tooling-7kvh2d.

WHAT THIS FILE OWNS, AND WHAT IT DOES NOT. The RENDERED half of the claim — the
mount, the clone that reads it, and the public sibling that still clones
anonymously — is asserted at the consumer tier by
`tests/consumer/test_delegated_gate_declared_recipe_scenarios.py`, against the
real renderer. This file owns the HOST half: which repositories are even asked
about, what the client does with the answer, where the token travels, and the
refusal when the mint does not happen. A live mint and an executed gate Job are
host-captured by the work-item and provable nowhere but the real cluster.

NOTHING HERE REACHES A HOST, A CLUSTER OR GITHUB. The client's only door to the
world is its `GateCommandRunner` seam, and the stub below is the whole world: no
minter runs, no token exists outside this module, and the renderer is canned
because what the renderer DOES with the argv is the consumer tier's claim and a
real render here would assert it twice.
"""

from __future__ import annotations

import json
from pathlib import Path

from returns.result import Failure, Success

from livespec_dev_tooling.gate_outcome_telemetry import GATE_OUTCOME_NO_VERDICT
from livespec_dev_tooling.gate_private_sibling_token import DELIVER_STEP, MINT_STEP
from livespec_dev_tooling.gate_remote_delegate import (
    GATE_PRIVATE_SIBLING_TOKEN_HELPER,
    gate_remote_request,
    run_delegated_gate,
)
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT, GATE_PASSED

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MINTER_IN_REPO = Path("ci-runner/k3s/phase2/gates/mint-private-sibling-token.sh")

_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
_ORIGIN_URL = "git@github.com:acme/widget.git"

# The Job the API server reports back from `create --output json`. The UID is the
# half this file cares about: it is what the token Secret's ownerReference is
# built from, and it is the reason the Secret is created AFTER the Job.
_JOB = "gate-widget-7f2qd"
_JOB_UID = "6f1d7b0a-1c2e-4a55-9d60-b6a1f0c3e4d5"
_CREATED = json.dumps(
    {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB, "uid": _JOB_UID}}
)
_CREATED_WITHOUT_UID = json.dumps(
    {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}}
)
_JOB_ADMITTING = json.dumps({"status": {}})
_JOB_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})

# A token-SHAPED value, invented here. It is the string every "must not appear"
# assertion below searches for, so it is deliberately distinctive: a substring
# that could occur in a manifest by accident would make those assertions pass
# for the wrong reason.
_TOKEN = "ghs_7kvh2d_private_sibling_token"
_PRIVATE = "dolt-server"
_PUBLIC = "widget-docs"

_SIBLINGS = f"""{{
  "cross_repo_targets": {{
    "{_PRIVATE}": {{ "github_url": "https://github.com/thewoolleyman/{_PRIVATE}" }},
    "{_PUBLIC}": {{ "github_url": "https://github.com/acme/{_PUBLIC}" }}
  }}
}}
"""
_NO_SIBLINGS = """{
  "widget": { "compat": { "livespec": ">=0.1.0,<1.0.0", "pinned": "v0.1.0" } }
}
"""


def _a_repository(*, root: Path, config: str | None) -> Path:
    """A fixture repository, optionally carrying a `.livespec.jsonc`.

    `None` writes no declaration file at all, which is the state of a repository
    that pins nothing and cites nothing — and so can never need a token.
    """
    root.mkdir(parents=True, exist_ok=True)
    if config is not None:
        _ = (root / ".livespec.jsonc").write_text(config, encoding="utf-8")
    return root


class _World:
    """Every command one delegated push issues, canned — the minter included.

    `minted` is what the minter answers on stdout; `refuse_mint` makes the
    minter exit non-zero instead, which is the host that cannot mint.
    `refuse_secret` does the same to the token Secret's create. `created` is the
    submit's answer, so a Job reported without a UID is expressible.

    Both the argv and the STDIN of every call are recorded, because this file's
    central claim is about WHERE the token travelled: an assertion that reads
    only argvs cannot tell a token passed on stdin from a token not passed at
    all, and an assertion that reads only stdin cannot catch one in an argv.
    """

    def __init__(
        self,
        *,
        minted: str = "",
        refuse_mint: bool = False,
        refuse_secret: bool = False,
        created: str = _CREATED,
    ) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self.stdins: list[str] = []
        self._minted = minted
        self._refuse_mint = refuse_mint
        self._refuse_secret = refuse_secret
        self._created = created
        self._polls = 0

    def mint_argv(self) -> tuple[str, ...] | None:
        """The one minter invocation, or `None` when the minter was never run."""
        return next(
            (argv for argv in self.argvs if argv[0] == str(GATE_PRIVATE_SIBLING_TOKEN_HELPER)),
            None,
        )

    def render_argv(self) -> tuple[str, ...]:
        """The one render invocation. Absent is a defect, not a state."""
        return next(argv for argv in self.argvs if argv[0] == str(_RENDERER))

    def secret_stdin(self) -> str:
        """The Secret document the client piped in, or the empty string."""
        return next(
            (
                stdin
                for stdin in self.stdins
                if '"kind": "Secret"' in stdin or '"kind":"Secret"' in stdin
            ),
            "",
        )

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (cwd, stream)
        self.argvs.append(tuple(argv))
        self.stdins.append(stdin or "")
        if argv[0] == str(GATE_PRIVATE_SIBLING_TOKEN_HELPER):
            if self._refuse_mint:
                return Success(
                    GateCommandResult(
                        returncode=1, stdout="", stderr="FATAL: GITHUB_APP_ID is not projected"
                    )
                )
            return Success(GateCommandResult(returncode=0, stdout=self._minted, stderr=""))
        if argv[0] == str(_RENDERER):
            return Success(GateCommandResult(returncode=0, stdout=_MANIFEST, stderr=""))
        return self._cluster_or_git(argv=argv)

    def _cluster_or_git(self, *, argv: list[str]) -> GateCommandOutcome:
        """The git and `kubectl` steps, answered the way the real ones answer.

        The Job submit and the Secret create are both `kubectl create`, so they
        are told apart by `--output json`, which only the submit passes — it is
        the submit alone that reads an answer back.
        """
        if "create" in argv:
            if "--output" in argv:
                return Success(GateCommandResult(returncode=0, stdout=self._created, stderr=""))
            if self._refuse_secret:
                return Success(
                    GateCommandResult(returncode=1, stdout="", stderr="secrets is forbidden")
                )
            return Success(GateCommandResult(returncode=0, stdout="", stderr=""))
        if "get" in argv:
            self._polls += 1
            answer = _JOB_ADMITTING if self._polls == 1 else _JOB_COMPLETE
            return Success(GateCommandResult(returncode=0, stdout=answer, stderr=""))
        return Success(GateCommandResult(returncode=0, stdout=self._identity(argv=argv), stderr=""))

    def _identity(self, *, argv: list[str]) -> str:
        """The tree read and the origin read; everything else answers nothing.

        A `--git-common-dir` probe is deliberately NOT answered: every fixture
        here is a primary checkout whose directory name already matches its
        origin, so `gate_repo_name` never asks — and an arm nothing reaches is
        an arm that proves nothing.
        """
        if "rev-parse" in argv:
            return f"{_TREE}\n"
        if "get-url" in argv:
            return f"{_ORIGIN_URL}\n"
        return ""


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


def _recorder() -> tuple[list[dict[str, object]], object]:
    """An `emit` seam that records the one outcome event a run reports."""
    events: list[dict[str, object]] = []

    def emit(**attributes: object) -> None:
        events.append(attributes)

    return events, emit


# ---------------------------------------------------------------------------
# WHO IS ASKED — a repository citing no sibling needs no credential
# ---------------------------------------------------------------------------


def test_a_repository_with_no_declaration_file_never_runs_the_minter(*, tmp_path: Path) -> None:
    """No `.livespec.jsonc` at all is the state of most repositories."""
    world = _World()

    built = gate_remote_request(
        repo_root=_a_repository(root=tmp_path / "bare", config=None),
        renderer=_RENDERER,
        runner=world,
    )

    assert isinstance(built, Success)
    assert world.mint_argv() is None
    assert built.unwrap().private_sibling_token == ""
    assert built.unwrap().private_sibling_secret == ""


def test_a_repository_citing_no_cross_repo_targets_never_runs_the_minter(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` that only pins core cannot need a sibling token.

    THE SKIP IS LOAD-BEARING, not a saving. The minter reads the fleet GitHub
    App's credentials through the environment wrapper, so a client that ran it
    on every push would make a host holding no App credential unable to delegate
    a push that needs no token at all — and by the contract's own words that
    host would then have to refuse the push.
    """
    world = _World()

    built = gate_remote_request(
        repo_root=_a_repository(root=tmp_path / "pinning", config=_NO_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
    )

    assert isinstance(built, Success)
    assert world.mint_argv() is None


def test_the_minter_runs_through_the_wrapper_from_the_repository_being_pushed(
    *, tmp_path: Path
) -> None:
    """The in-tree minter is preferred, and the wrapper is what invokes it.

    THE WRAPPER IS THE PROGRAM, not the minter. `with-livespec-env.sh` projects
    the App credentials from 1Password and SCRUBS the caller's environment, so a
    minter invoked directly would see neither — and the gate pod never sees them
    at all, which is the property the whole design rests on.

    The IN-REPO copy wins where it exists so a change to the minter is gated by
    the very push that makes it; every other repository reaches the copy the
    wheel ships. That is the same pairing `resolve_renderer` makes, and the
    reason is the one stop-the-line R283 recorded — a client and the script it
    drives that move on different schedules.
    """
    repo_root = _a_repository(root=tmp_path / "widget", config=_SIBLINGS)
    minter = repo_root / _MINTER_IN_REPO
    minter.parent.mkdir(parents=True)
    _ = minter.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    world = _World(minted=json.dumps({"private_siblings": [_PRIVATE], "token": _TOKEN}))

    built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=world)

    assert isinstance(built, Success)
    argv = world.mint_argv()
    assert argv is not None
    assert argv[0] == str(GATE_PRIVATE_SIBLING_TOKEN_HELPER)
    assert argv[1] == "--"
    assert argv[2] == str(minter)
    assert argv[argv.index("--repo-root") + 1] == str(repo_root)


def test_the_packaged_minter_is_used_outside_this_repository(*, tmp_path: Path) -> None:
    """A consumer repository carries no `ci-runner/` tree, and still mints.

    The packaged path is asserted to be the one the wheel's `force-include`
    table ships — read off `pyproject.toml` rather than restated — because a
    client naming a file the package does not carry fails at the step with an
    argv nobody can act on.
    """
    repo_root = _a_repository(root=tmp_path / "consumer", config=_SIBLINGS)
    world = _World(minted=json.dumps({"private_siblings": [_PRIVATE], "token": _TOKEN}))

    built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=world)

    assert isinstance(built, Success)
    argv = world.mint_argv()
    assert argv is not None
    assert argv[2].endswith("livespec_dev_tooling/gates/mint-private-sibling-token.sh")
    declaration = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{_MINTER_IN_REPO}" = "livespec_dev_tooling/gates/' in declaration


# ---------------------------------------------------------------------------
# WHERE THE TOKEN GOES — the Secret, and nowhere else
# ---------------------------------------------------------------------------


def test_only_the_private_sibling_and_a_secret_name_reach_the_render(*, tmp_path: Path) -> None:
    """The render argv names the private sibling; the public one is absent.

    The ARGV is the artifact under assertion rather than the manifest, because
    everything in it is copied into the manifest the API server stores — so a
    token here is a token no later care could take back.
    """
    world = _World(minted=json.dumps({"private_siblings": [_PRIVATE], "token": _TOKEN}))

    built = gate_remote_request(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
    )

    assert isinstance(built, Success)
    render = world.render_argv()
    assert render[render.index("--private-sibling") + 1] == _PRIVATE
    assert _PUBLIC not in render
    assert _TOKEN not in render
    secret = render[render.index("--private-sibling-secret") + 1]
    assert secret.startswith("gate-sibling-token-")
    assert built.unwrap().private_sibling_secret == secret
    assert built.unwrap().private_sibling_token == _TOKEN


def test_the_token_secret_is_owned_by_the_job_and_piped_in_on_stdin(*, tmp_path: Path) -> None:
    """The token reaches ONE Job's Secret, and nothing long-lived holds it.

    THREE CLAIMS IN ONE RUN, because they are one property. The Secret carries an
    ownerReference to the Job the API server just created — which is what makes
    garbage collection, rather than a `delete` verb this credential does not
    hold, remove it — so nothing it contains outlives that Job. The token
    travels on STDIN, never in an argv, because an argv is readable in `ps` on
    the pushing host for as long as the call lasts. And the manifest, the
    artifact a `kubectl get job -o yaml` will hand anyone, does not contain it.
    """
    world = _World(minted=json.dumps({"private_siblings": [_PRIVATE], "token": _TOKEN}))
    events, emit = _recorder()

    verdict = run_delegated_gate(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_PASSED, verdict.detail
    secret = json.loads(world.secret_stdin())
    assert secret["stringData"] == {"token": _TOKEN}
    assert secret["metadata"]["ownerReferences"] == [
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "name": _JOB,
            "uid": _JOB_UID,
            "controller": True,
        }
    ]
    assert all(_TOKEN not in part for argv in world.argvs for part in argv)
    assert _TOKEN not in _MANIFEST
    assert len(events) == 1


def test_no_token_secret_is_created_for_a_push_that_minted_nothing(*, tmp_path: Path) -> None:
    """A repository citing only public siblings creates no Secret at all.

    The control for the test above: the Secret step is entered because a token
    exists, not because a repository happens to cite a sibling.
    """
    world = _World(minted=json.dumps({"private_siblings": []}))
    events, emit = _recorder()

    verdict = run_delegated_gate(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_PASSED, verdict.detail
    assert world.secret_stdin() == ""
    render = world.render_argv()
    assert "--private-sibling" not in render
    assert "--private-sibling-secret" not in render
    assert len(events) == 1


# ---------------------------------------------------------------------------
# WHEN THE MINT DOES NOT HAPPEN — a missing verdict, never a green push
# ---------------------------------------------------------------------------


def test_a_host_that_cannot_mint_the_token_refuses_the_push_as_a_missing_verdict(
    *, tmp_path: Path
) -> None:
    """The contract's own words, as a behaviour: no token, no verdict.

    THE DIRECTION IS THE WHOLE POINT. The alternative a careless client would
    take is to carry on and let the pod clone anonymously — which fails, leaving
    the recipe's cross-repo readers an EMPTY tree where a cited sibling should
    be, and an absent citation target reads as GREEN. So the failure must stop
    the push before any Job is submitted, and it must stop it as NO VERDICT
    rather than as a red tree: the tree was never judged.
    """
    world = _World(refuse_mint=True)
    events, emit = _recorder()

    verdict = run_delegated_gate(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.token_written is False
    assert MINT_STEP in verdict.detail
    assert not any("create" in argv for argv in world.argvs)
    assert events == [
        {
            "outcome": GATE_OUTCOME_NO_VERDICT,
            "repository": None,
            "tree_hash": None,
            "job_name": None,
        }
    ]


def test_an_unreadable_mint_answer_refuses_the_push_without_quoting_itself(
    *, tmp_path: Path
) -> None:
    """A malformed answer can still carry a real token, so the refusal is mute.

    The detail reaches the pushing operator's terminal, and the contract forbids
    the token appearing in any log — so the refusal names the step and the argv
    it ran, and quotes none of what came back.
    """
    world = _World(minted=f"<html>502 Bad Gateway {_TOKEN}</html>")

    built = gate_remote_request(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
    )

    assert isinstance(built, Failure)
    failure = built.failure()
    assert failure.step == MINT_STEP
    assert _TOKEN not in failure.detail
    assert _TOKEN not in repr(failure)


def test_a_mint_answer_naming_siblings_without_a_token_is_refused(*, tmp_path: Path) -> None:
    """Names without a token would render a mount no Secret ever fills.

    Readable JSON, correct types, and still unusable — which is why the shapes
    this client accepts are stated as a pairing rather than as a type check.
    """
    world = _World(minted=json.dumps({"private_siblings": [_PRIVATE], "token": ""}))

    built = gate_remote_request(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
    )

    assert isinstance(built, Failure)
    assert built.failure().step == MINT_STEP


def test_a_job_reported_without_a_uid_refuses_rather_than_orphan_the_secret(
    *, tmp_path: Path
) -> None:
    """No UID is no ownerReference, and no ownerReference is a lasting Secret.

    An unowned Secret holding an installation token is exactly what the contract
    forbids, so this refuses instead. The Job is already submitted and will sit
    with an unmountable volume until its TTL, which is a Job with NO VERDICT —
    not a red tree.
    """
    world = _World(
        minted=json.dumps({"private_siblings": [_PRIVATE], "token": _TOKEN}),
        created=_CREATED_WITHOUT_UID,
    )
    events, emit = _recorder()

    verdict = run_delegated_gate(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert DELIVER_STEP in verdict.detail
    assert world.secret_stdin() == ""


def test_a_refused_secret_create_refuses_the_push(*, tmp_path: Path) -> None:
    """The credential holds `create` on secrets and nothing else needs to work.

    A cluster that refuses the create — an RBAC that drifted, a quota — leaves
    the pod with a volume it cannot mount, so the run reports no verdict rather
    than waiting out a Job that can never start.
    """
    world = _World(
        minted=json.dumps({"private_siblings": [_PRIVATE], "token": _TOKEN}),
        refuse_secret=True,
    )
    events, emit = _recorder()

    verdict = run_delegated_gate(
        repo_root=_a_repository(root=tmp_path / "widget", config=_SIBLINGS),
        renderer=_RENDERER,
        runner=world,
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert DELIVER_STEP in verdict.detail
