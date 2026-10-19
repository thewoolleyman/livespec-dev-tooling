"""The delegated gate's PER-REPO OPT-IN and its recipe entry point — R4.S7c.

S7a drives one gate run on the cluster and S7b decides it; neither is reachable
from a git hook, and neither should be reachable from every repository at once.
This module is what stands between them and a push: the SWITCH that says whether
THIS repository delegates its pre-push aggregate, and the `python -m` entry point
a repository's own `check-pre-push` recipe calls to act on the answer. The module
is SHARED — one client, shipped once — and the wiring is per repository, so a
rollout is a sequence of small, separately reviewable edits rather than one flip
that moves the whole fleet's gate at the same instant.

DELEGATION IS SELECTED BY TWO FACTS, NOT ONE, and the second was missing until
2026-10-11. The switch below travels with the CODE and describes no host, so an
opted-in repository delegated from every host that cloned it; a host holding no
gates credential then failed closed, which is correct for a gate and fatal for a
factory — the push is refused and nothing says why. So the switch is now ANDed
with host eligibility (`gate_credential.gates_kubeconfig_readable`): the pushing
user must be able to read the gates kubeconfig on this host. A host that is
genuinely ineligible takes the local `just check` fall-through and SAYS SO
(`GATED_LOCALLY`), because an opted-in repository that quietly gates somewhere
else is the one shape an operator cannot tell apart after the fact. Nothing about
the fail-closed rule moves: once delegation IS selected, every no-verdict shape
still refuses.

HOST ELIGIBILITY HAS A THIRD ANSWER, added 2026-10-19, and reading it as the
second one was a defect: the HOST is eligible and only the PROCESS is not. On the
VPS the credential is group-readable and the group database lists the pushing
user, but a login session started before that membership was granted does not
carry the group — so the read failed, this module printed `GATED_LOCALLY`, and
the push ran the full local aggregate while looking correctly routed. Nothing
said the host was eligible and nothing named the remedy. `gate_group_repair`
recognises that exact state, says which group the gate will run under, and
re-runs the gate once under it; its own docstring carries why that grants nothing
a fresh login would not. It is a THIRD answer rather than a WIDENING of
eligibility — a host with no credential, and a user the group database does not
list, keep the fall-through and the line they have today — and it is fail-closed
like every other arm: a re-execution that cannot start, or that runs and still
cannot read the credential, refuses the push rather than falling through to a
local run nobody announced.

THE SWITCH IS PER-REPOSITORY AND DEFAULTS OFF. It is `delegated_gate` in the
consuming repository's own `[tool.livespec_dev_tooling]` block — the same place
`plan_lifecycle_anchor` and `file_lloc_hard_gate` live, read by its own dedicated
loader rather than as a role key, exactly as this repository's own
`SPECIFICATION/contracts.md` (livespec-dev-tooling) sanctions for keys outside
the role-key inventory. A repository that says nothing keeps the local
aggregate it runs today, so this slice landing changes nothing anywhere until
someone writes `delegated_gate = true` into one repository's diff.

OFF IS THE STRICT PATH, WHICH IS WHY EVERY DOUBT RESOLVES TO IT. `enabled`
answers yes only for a literal `true`; an absent key, a `false`, a malformed
`pyproject.toml`, and a value of the wrong type all answer no, and the caller
then runs the full local aggregate it would have run anyway. That asymmetry is
the mirror image of S7b's and lands in the same place. There, an unrecognised
shape must not AUTHORISE a push, so it refuses; here, an unrecognised shape must
not silently DELEGATE a gate to a cluster nobody has proven yet, so it stays
local. Both defaults reduce to "run the checks", which is the only direction in
which a mistake is merely expensive rather than unsound.

WHAT THIS MODULE DOES NOT TOUCH IS THE GREEN-TOKEN SKIP. `check-pre-push`
consults `green_token` first and exits 0 on a match; that path is deliberately
untouched, because it is sound for either gate — a byte-identical tree has
already been gated by whichever path gated it, and S7b writes the SAME token a
local aggregate writes, through the same CLI. The switch replaces the
FALL-THROUGH and nothing else.

THE RUN IS FAIL-CLOSED FROM ITS FIRST STEP, not just at S7b's verdict. Assembling
the request reaches the world twice — to read the tree under test and to render
the Job for it — and either reach can fail before any gate exists to have an
opinion. Both land on `GATE_NO_VERDICT`, the same state a lost cluster produces,
so a push is never completed on the strength of a gate that was never submitted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from livespec_dev_tooling.config import (
    ConfigParseError,
    load_delegated_gate,
    load_gate_check_suite,
)
from livespec_dev_tooling.gate_credential import gates_kubeconfig_path, gates_kubeconfig_readable
from livespec_dev_tooling.gate_group_repair import (
    GATE_RUNS_UNDER_GROUP,
    group_repair_group,
    group_repair_status,
)
from livespec_dev_tooling.gate_remote_client import GateRunRequest
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandResult,
    GateCommandRunner,
    GateStepFailed,
    Sleeper,
    default_gate_command_runner,
    default_sleeper,
    require_success,
)
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT, GateVerdict, run_gated_push

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure, Result, Success  # noqa: E402  — same.

__all__: list[str] = [
    "GATED_LOCALLY",
    "GATE_CHECK_SUITE_FALL_THROUGH",
    "GATE_MIRROR_ROOT",
    "GATE_RENDERER_INSTALLED",
    "GATE_RENDERER_IN_REPO",
    "declared_gate_check_suite",
    "delegated_gate_enabled",
    "delegated_gate_selected",
    "gate_remote_request",
    "main",
    "resolve_renderer",
    "run_delegated_gate",
]

# The one mirror the fleet has (R4.S4), named here rather than threaded through
# every caller — the same choice S7a makes for its namespace. A caller that needs
# another mirror builds its own `GateRunRequest`; this is the default path's.
GATE_MIRROR_ROOT = "cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gates-mirror"

# The renderer, in the two places it exists: a checkout of THIS repository, which
# carries it in-tree, and the converged host path the reconstruct unit installs.
# A repository with neither renders nothing, the run reaches no verdict, and the
# push is refused — which is why no third "guess a path" case is wanted here.
GATE_RENDERER_IN_REPO = Path("ci-runner/k3s/phase2/gates/render-gate-job.sh")
GATE_RENDERER_INSTALLED = Path("/usr/local/lib/ci-runner-k3s/gates/render-gate-job.sh")

_READ_TREE_STEP = "read-tree-hash"
_RENDER_STEP = "render-gate-job"
_REPO_NAME_STEP = "derive-repo-name"
_CHECK_SUITE_STEP = "read-gate-check-suite"

# What a consuming repository that declares no gate suite gets: the SHARED
# PRE-PUSH SEQUENCE its own local fall-through runs, which is three steps rather
# than one (freeze-driver rulings R92 and R100, 2026-10-17). `lefthook.yml`'s
# `pre-push` block installs the worktree pack, this repository's own gate adds
# the commit-refuse-hook install, and that hook then calls exactly ONE recipe:
# `check-pre-push`.
#
# THE LAST ENTRY IS A RECIPE NAME AND CARRIES NO JUST-VARIABLE OVERRIDE, which
# is what R100 corrected. R92 wrote `hook_gate=1 check` here on the premise that
# every fleet consumer's pre-push ends in THIS repository's
# `scripts/just/check-pre-push.sh` and therefore in that invocation. It does
# not: each repository ships its own pre-push script —
# livespec-orchestrator-beads-fabro's ends in
# `just check-skipping check-codex-skill-picker` — and `hook_gate` is a `just`
# variable only this repository's justfile declares (`export hook_gate := ""`).
# `just` REFUSES a command-line override of an undeclared variable, so every
# consumer lacking that declaration was red before its aggregate ran at all:
# measured 2026-10-17, Job gate-livespec-orchestrator-beads-fabro-ee118f8fd5dc
# died with `error: Variable 'hook_gate' overridden on the command line but not
# present in justfile` on a tree whose master CI was green.
#
# WHAT IS ACTUALLY UNIFORM ACROSS THE FLEET IS THE RECIPE NAME. Every
# repository's lefthook `pre-push` calls `just check-pre-push` — verified in
# livespec, livespec-overseer, livespec-driver-claude,
# livespec-console-beads-fabro and livespec-orchestrator-beads-fabro — and the
# renderer's preflight tests for a RECIPE, never for a variable, so a consumer
# that lacks it gets the existing red verdict naming the missing recipe rather
# than `just`'s own refusal to parse an override.
#
# THE TWO INSTALLS STAY, and the single `check` this default once was is why.
# `/workspace` in the gate pod is a `git init` + fetch, not a bootstrapped
# clone, so without them the pack and the commit-refuse hooks are simply absent
# and `check-primary-checkout-commit-refuse-hook-installed` and
# `check-no-workflow-edits` judge the SANDBOX rather than the tree under test.
#
# NOTHING RE-DELEGATES INSIDE THE POD, which is the one new question
# `check-pre-push` raises: it is the recipe that consults this module's own
# switch, so the default now runs it on the far side of a delegation. It cannot
# delegate again, because `delegated_gate_selected` also requires a READABLE
# gates kubeconfig and the gate pod holds none. The group repair does not reopen
# that door either: it needs a credential FILE whose owning group resolves, and
# a pod holding no credential at all has no group to re-run under — so the pod's
# `check-pre-push` takes its own local fall-through there exactly as a laptop's
# does.
#
# It is still the FALL-THROUGH's sequence and never this repository's own
# declaration: `livespec-dev-tooling` adds `warm-typecheck` and its own
# `hook_gate=1 check`, which no other repository carries, and baking those into
# the shared Job made every consumer red on every green tree
# (livespec-dev-tooling-saxz). The sequence is pinned to `lefthook.yml` by
# `tests.consumer.test_delegated_gate_declared_recipe_scenarios`, which reads
# each step back out of the file that owns it, so a step that moves there fails
# that test rather than silently reddening a consumer's gate.
GATE_CHECK_SUITE_FALL_THROUGH: tuple[str, ...] = (
    "install-worktree-pack",
    "install-commit-refuse-hooks",
    "check-pre-push",
)

# What `_answered` reads back when a probe did not answer at all — a git that is
# not on PATH, a spawn that failed. Non-zero rather than empty stdout so the one
# reader below needs no second branch for a shape it treats identically.
_UNANSWERED = GateCommandResult(returncode=1, stdout="", stderr="")

# The renderer's own default job name, computed here rather than parsed back out
# of the manifest — and passed to it explicitly, so the name this client waits on
# is the name it asked for even if that default ever moves.
_JOB_NAME_TREE_CHARS = 12

# What an OPTED-IN repository says when the host it is being pushed from holds no
# readable gates credential. Printed rather than left silent because an opted-in
# repository that quietly gates somewhere else is the one shape an operator
# cannot tell apart afterwards: a locally-gated push and a cluster-gated one look
# identical once they have completed.
GATED_LOCALLY = (
    "delegated gate is switched on for this repository, but this host cannot read the "
    "gates kubeconfig, so this push is gating locally on the full just check aggregate"
)


def delegated_gate_enabled(*, repo_root: Path) -> bool:
    """Answer whether `repo_root` has opted in to the delegated gate.

    A `ConfigParseError` is swallowed INTO the "no" rather than raised, because
    this answer is read by a git hook whose alternative branch is the full local
    aggregate: a repository whose `pyproject.toml` cannot be parsed is a
    repository that should run its checks locally, not one that should fail to
    push. Nothing is hidden by that — the same malformed file fails the
    aggregate's own config-reading members a moment later, loudly.
    """
    try:
        declared = load_delegated_gate(repo_root=repo_root)
    except ConfigParseError:
        return False
    return declared is True


def delegated_gate_selected(*, repo_root: Path) -> bool:
    """Answer whether THIS push, from THIS host, delegates its gate.

    Two independent facts, and the switch is only one of them. `delegated_gate`
    lives in the repository's own `pyproject.toml`, so it travels with the CODE
    and describes no host; whether the pushing user can read the gates
    credential is a property of the HOST and is read from it. A host that holds
    no credential — a factory sandbox, a fresh laptop — therefore keeps gating
    locally in an opted-in repository instead of delegating and failing closed.

    The ordering matters for silence, not for the answer: the switch is read
    first, so a repository that has not opted in never reaches the credential
    question and nothing is narrated at the overwhelming majority of pushes.
    """
    return delegated_gate_enabled(repo_root=repo_root) and gates_kubeconfig_readable()


def declared_gate_check_suite(*, repo_root: Path) -> Result[tuple[str, ...], GateStepFailed]:
    """Name the `just` invocations THIS repository declares for its gate.

    The gate Job runs the gated repository's OWN recipes and nothing else, so
    this is the one place the command is decided — and `GATE_CHECK_SUITE_FALL_THROUGH`
    is the documented default a repository that declares nothing gets: the
    shared pre-push sequence its own local fall-through runs, never a recipe
    only some other repository has.

    A MALFORMED DECLARATION FAILS THE STEP rather than falling back, which is
    the opposite disposition from `delegated_gate_enabled` above and
    deliberately so. There, a doubt resolves to "run the full local aggregate",
    which is strict. Here, the run has ALREADY delegated, so the only thing a
    fallback could do is gate the tree on a recipe the repository did not
    declare — which the contract forbids in as many words. A step that did not
    complete reaches `GATE_NO_VERDICT`, and the push is refused.
    """
    try:
        declared = load_gate_check_suite(repo_root=repo_root)
    except ConfigParseError as unreadable:
        return Failure(
            GateStepFailed(
                step=_CHECK_SUITE_STEP,
                argv=(),
                returncode=None,
                detail=(
                    "gate_check_suite in the [tool.livespec_dev_tooling] block of "
                    f"{repo_root}/pyproject.toml cannot be read: {unreadable}"
                ),
            )
        )
    return Success(declared or GATE_CHECK_SUITE_FALL_THROUGH)


def _check_suite_argv(*, suite: tuple[str, ...]) -> list[str]:
    """The renderer flags that carry one declared suite, in declaration order.

    Repeated rather than one delimited value: a `just` invocation may carry
    spaces (`hook_gate=1 check`), so any single-argument spelling would need a
    separator the entries are then forbidden to contain.
    """
    return [flag for recipe in suite for flag in ("--check-suite", recipe)]


def resolve_renderer(*, repo_root: Path) -> Path:
    """Name the `render-gate-job.sh` this run should use.

    Prefers the repository's own copy when it has one, so a change to the
    renderer is gated by the same push that makes it — and falls back to the
    converged host path, which is what every other repository has. The fallback
    is returned unconditionally rather than checked: a path that is not there
    fails at the seam, as a step that did not run, with the argv in the report.
    """
    in_repo = repo_root / GATE_RENDERER_IN_REPO
    if in_repo.is_file():
        return in_repo
    return GATE_RENDERER_INSTALLED


def _answered(*, repo_root: Path, runner: GateCommandRunner, argv: list[str]) -> str:
    """One probe's stdout, with every did-not-answer shape as the empty string.

    A command that never RAN and a command that ran and REFUSED are kept apart
    everywhere a gate's verdict depends on the difference. Here they do not
    differ: either way this probe named nothing, and the caller's next move is
    the same — ask the other probe, and fail closed if it is silent too.
    """
    ran = runner(argv=argv, cwd=repo_root).value_or(_UNANSWERED)
    return ran.stdout.strip() if ran.returncode == 0 else ""


def _repo_name_from_url(*, url: str) -> str:
    """The last path component of a remote URL, without its `.git` suffix.

    Both canonical forms reduce the same way, so no regex is wanted: the
    separator after the host is `/` for https and `:` for the scp-style form,
    and splitting on each in turn reaches the final segment of either. A URL
    carrying credentials — a Fabro sandbox's origin does — contributes nothing
    past the host, so no secret can reach the name this returns.
    """
    tail = url.rstrip("/").rsplit("/", maxsplit=1)[-1].rsplit(":", maxsplit=1)[-1]
    return tail.removesuffix(".git")


def _gate_repo_name(*, repo_root: Path, runner: GateCommandRunner) -> Result[str, GateStepFailed]:
    """Name the REPOSITORY this push gates — never the directory it runs in.

    `repo_root.name` was that name until 2026-10-11, and it is right only for a
    primary checkout. A LINKED WORKTREE'S DIRECTORY IS ITS BRANCH, so a push
    from `~/.worktrees/<repo>/<branch>` named the mirror, the Job and the
    renderer's `--repo` after the branch. The gate mirror holds one bare
    repository per repository, so that push was refused with
    `'<branch>.git' does not appear to be a git repository` — and since the
    primary checkout refuses pushes outright, the opt-in was unusable from every
    checkout it was meant to gate.

    The origin remote is asked FIRST because it is the repository's own
    identity rather than a fact about this host's directory layout, and it reads
    identically in a worktree and in the checkout the worktree was added from.
    `--git-common-dir` is the fallback for a clone with no origin: from inside a
    worktree it answers the PRIMARY checkout's `.git`, so its parent is the
    repository directory even there. A clone that answers neither names nothing,
    and naming nothing is a step that did not complete — the gate is never
    submitted against a guessed mirror.
    """
    origin_argv = ["git", "remote", "get-url", "origin"]
    from_origin = _repo_name_from_url(
        url=_answered(repo_root=repo_root, runner=runner, argv=origin_argv)
    )
    if from_origin:
        return Success(from_origin)
    common_argv = ["git", "rev-parse", "--git-common-dir"]
    common_dir = _answered(repo_root=repo_root, runner=runner, argv=common_argv)
    from_common_dir = (repo_root / common_dir).resolve().parent.name if common_dir else ""
    if from_common_dir:
        return Success(from_common_dir)
    return Failure(
        GateStepFailed(
            step=_REPO_NAME_STEP,
            argv=tuple(common_argv),
            returncode=None,
            detail=(
                "neither the origin remote URL nor the parent of the git common "
                f"directory names a repository for {repo_root}"
            ),
        )
    )


def gate_remote_request(
    *, repo_root: Path, renderer: Path, runner: GateCommandRunner
) -> Result[GateRunRequest, GateStepFailed]:
    """Assemble the one request S7a needs, out of the repository itself.

    Every reach into the world goes through the SAME seam the client uses, so a
    caller that can stub the cluster can stub the assembly too — and a failure
    here arrives in the shape the run's own failures arrive in, carrying the step
    that could not be completed rather than an exception nobody up the stack is
    positioned to interpret. The one reach that does NOT is the declaration read:
    it is a read of the repository's own `pyproject.toml`, which the opt-in above
    already reads the same way, and a caller that can write a fixture repository
    can vary it without a seam.
    """
    tree_argv = ["git", "rev-parse", "HEAD^{tree}"]
    tree = require_success(
        step=_READ_TREE_STEP, argv=tree_argv, outcome=runner(argv=tree_argv, cwd=repo_root)
    )
    if isinstance(tree, Failure):
        return Failure(tree.failure())
    tree_hash = tree.unwrap().stdout.strip()
    named = _gate_repo_name(repo_root=repo_root, runner=runner)
    if isinstance(named, Failure):
        return Failure(named.failure())
    repo = named.unwrap()
    suite = declared_gate_check_suite(repo_root=repo_root)
    if isinstance(suite, Failure):
        return Failure(suite.failure())
    job_name = f"gate-{repo}-{tree_hash[:_JOB_NAME_TREE_CHARS]}"
    render_argv = [
        str(renderer),
        "--repo-root",
        str(repo_root),
        "--tree-hash",
        tree_hash,
        "--repo",
        repo,
        "--job-name",
        job_name,
        *_check_suite_argv(suite=suite.unwrap()),
    ]
    rendered = require_success(
        step=_RENDER_STEP, argv=render_argv, outcome=runner(argv=render_argv, cwd=repo_root)
    )
    if isinstance(rendered, Failure):
        return Failure(rendered.failure())
    return Success(
        GateRunRequest(
            repo_root=repo_root,
            mirror_url=f"{GATE_MIRROR_ROOT}/{repo}.git",
            manifest=rendered.unwrap().stdout,
            job_name=job_name,
        )
    )


def run_delegated_gate(
    *,
    repo_root: Path,
    renderer: Path,
    runner: GateCommandRunner = default_gate_command_runner,
    sleeper: Sleeper = default_sleeper,
) -> GateVerdict:
    """Gate this repository's HEAD on the cluster and report S7b's verdict.

    An assembly that failed is reported as NO_VERDICT rather than as FAILED: no
    Job was ever submitted, so there is nothing that could have been red, and the
    distinction is the one a delegated gate exists to keep — a plumbing fault and
    a red tree want opposite responses from whoever reads the message.
    """
    built = gate_remote_request(repo_root=repo_root, renderer=renderer, runner=runner)
    if isinstance(built, Failure):
        failure = built.failure()
        return GateVerdict(
            state=GATE_NO_VERDICT,
            detail=f"{failure.step} did not complete, so no gate was submitted: {failure.detail}",
            token_written=False,
        )
    return run_gated_push(request=built.unwrap(), runner=runner, sleeper=sleeper)


def main() -> int:
    """The two answers a repository's `check-pre-push` recipe needs.

    `enabled` answers whether THIS push delegates — the repository's switch AND
    this host's credential — because the exit code is the whole branch the recipe
    takes and a recipe cannot read the host for itself. It stays SILENT for a
    repository that has not opted in, so such a repository sees a pre-push
    byte-for-byte the one it saw before this slice landed.

    IT SPEAKS IN TWO CASES, and they are opposites that used to be the same
    answer. Switched ON and the host genuinely INELIGIBLE is the local
    fall-through, which says so and exits non-zero. Switched ON and the host
    ELIGIBLE while only this PROCESS lacks the credential's owning group is a
    push that delegates after all, so it exits ZERO and names the group it will
    run under — `gate_group_repair` carries why that re-execution grants nothing
    a fresh login would not. Before that split, the second case printed the
    first's line and ran the full local aggregate while looking correctly routed.
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("gate_remote_delegate")

    parser = argparse.ArgumentParser(
        description="Per-repo delegated-gate opt-in, and the client that acts on it.",
    )
    _ = parser.add_argument(
        "command",
        choices=["enabled", "run"],
        help="'enabled' tests this repo's opt-in; 'run' gates HEAD on the cluster.",
    )
    parsed = parser.parse_args()
    repo_root = Path.cwd()

    if parsed.command == "enabled":
        if delegated_gate_selected(repo_root=repo_root):
            return 0
        opted_in = delegated_gate_enabled(repo_root=repo_root)
        group = group_repair_group(opted_in=opted_in)
        if group is not None:
            log.warning(GATE_RUNS_UNDER_GROUP, group=group)
            return 0
        if opted_in:
            log.warning(GATED_LOCALLY, kubeconfig=str(gates_kubeconfig_path()))
        return 1

    decided = group_repair_status(opted_in=delegated_gate_enabled(repo_root=repo_root))
    if decided is not None:
        return decided
    verdict = run_delegated_gate(
        repo_root=repo_root, renderer=resolve_renderer(repo_root=repo_root)
    )
    if verdict.refuses_push:
        log.error(
            "delegated gate refuses this push",
            state=verdict.state,
            detail=verdict.detail,
        )
        return 1
    log.info("delegated gate passed", state=verdict.state, detail=verdict.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
