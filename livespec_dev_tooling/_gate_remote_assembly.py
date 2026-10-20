"""The pieces ONE delegated gate request is assembled out of — R4.S7c's workshop.

`gate_remote_delegate` owns two questions: whether THIS push delegates, and what
the run it drives reports. This module owns the third — what the request it
submits is MADE of — and it is here rather than beside them because the three
answer to different readers. The switch is read by a git hook, the verdict by
whoever is pushing; everything below is read by `render-gate-job.sh` and by the
cluster, and it is the part that grows: each flag the renderer learns, each
identity a clone can be named by, each refusal that deserves its own sentence.

WHAT HOLDS THESE TOGETHER is that every one of them turns a REPOSITORY into part
of a render argv, or turns a failed attempt at that into something an operator
can act on. The declared suite becomes `--check-suite` flags; the clone's own
identity becomes `--repo` and the mirror it is pushed to; the per-run nonce
becomes `--gate-ref`; and the two refusal helpers decide what a run says when
the renderer it reached could not answer. `declared_gate_check_suite` reads the
consumer's `pyproject.toml` exactly as the opt-in switch does, and still lives
here rather than with that switch: its answer is an ARGUMENT, and the module
that assembles the argv is the only caller it has.

A PRIVATE MODULE WITH A PUBLIC SURFACE, per this package's own convention for a
cohesion split (`fleet/_lanes.py` and its siblings). The names in `__all__` are
the interface `gate_remote_delegate` composes; the helpers below them are
private because exactly one of those entry points uses each, and a private name
may never cross a module boundary here.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

from livespec_dev_tooling.config import ConfigParseError, load_gate_check_suite
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandResult,
    GateCommandRunner,
    GateStepFailed,
)

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GATE_CHECK_SUITE_FALL_THROUGH",
    "assembly_refusal",
    "check_suite_argv",
    "declared_gate_check_suite",
    "gate_repo_name",
    "per_run_gate_ref",
    "renderer_refusal",
]

_REPO_NAME_STEP = "derive-repo-name"
_CHECK_SUITE_STEP = "read-gate-check-suite"

# The one render failure that is NOT "the step did not complete": the renderer
# ran, understood its own argument loop, and refused a flag THIS CLIENT passes.
# It carries its own step name so the refusal below can say what happened
# instead of restating the step, and the pattern is `render-gate-job.sh`'s own
# wording for an argument it does not know (`FATAL: unknown argument <flag>`).
_RENDER_SKEW_STEP = "renderer-older-than-client"
_UNKNOWN_ARGUMENT = re.compile(r"unknown argument (?P<flag>\S+)")

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

# The mirror-ref namespace the gate pod fetches from and `prune-gate-refs.sh`
# sweeps. A run's own ref is this, the gated tree, and a nonce — see
# `per_run_gate_ref`.
_GATE_REF_ROOT = "refs/gates"


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


def per_run_gate_ref(*, tree_hash: str) -> str:
    """Name the mirror ref THIS run owns, and no other run can be using.

    THE NONCE IS THE WHOLE POINT. The ref was `refs/gates/<tree hash>` for every
    gate of one tree, and the client deletes the refs it created in a `finally`
    — so when two gates of one tree overlapped, whichever reached its cleanup
    first deleted the ref the other run's pod had not fetched yet. Measured
    2026-10-19: two post-merge janitors gated master tree 228727afbe95 five
    seconds apart, the losing run's collection removed the winner's input, that
    pod died with `couldn't find remote ref`, and a correct merged tree read as a
    RED janitor. One collision cost BOTH gates their verdicts, and concurrent
    same-tree gating is routine rather than exotic: every post-merge janitor in a
    repository gates the master tip.

    FLAT rather than `refs/gates/<tree>/<nonce>`, because git cannot hold a ref
    at a path and a ref under it at the same time: an orphan `refs/gates/<tree>`
    left behind by an older client — the exact litter the mirror's sweep exists
    to collect — would make every nested push a directory/file conflict, which
    is a refused push and so a NO_VERDICT.

    `uuid4` rather than a counter or a clock: the runs that collide are in
    DIFFERENT PROCESSES on different hosts, so nothing shared is available to
    them, and a second-resolution timestamp is exactly what two janitors five
    seconds apart can tie on.
    """
    return f"{_GATE_REF_ROOT}/{tree_hash}-{uuid.uuid4().hex}"


def check_suite_argv(*, suite: tuple[str, ...]) -> list[str]:
    """The renderer flags that carry one declared suite, in declaration order.

    Repeated rather than one delimited value: a `just` invocation may carry
    spaces (`hook_gate=1 check`), so any single-argument spelling would need a
    separator the entries are then forbidden to contain.
    """
    return [flag for recipe in suite for flag in ("--check-suite", recipe)]


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


def gate_repo_name(*, repo_root: Path, runner: GateCommandRunner) -> Result[str, GateStepFailed]:
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


def renderer_refusal(*, renderer: Path, failure: GateStepFailed) -> GateStepFailed:
    """Recognise the render failure that means the RENDERER is older than this client.

    `render-gate-job did not complete` is the right thing to say about a step
    that could not run. It is the WRONG thing to say about one that ran and
    refused a flag this client passes, because it names neither the renderer
    reached nor the flag rejected — so it reads identically for a renderer that
    is MISSING and one that is merely OLD, and those two want opposite
    responses. That indistinguishability is what every consuming repository's
    refused push carried for a day on 2026-10-20 (stop-the-line R283).

    THE FLAG MUST BE ONE THIS RUN ACTUALLY PASSED. A renderer whose stderr
    merely carries the phrase has told us nothing about OUR argv, and naming a
    flag the run never sent would be a confident wrong diagnosis — worse than
    the generic sentence, because an operator would go looking for a skew that
    is not there. Such a refusal keeps the sentence every other step gets.
    """
    named = _UNKNOWN_ARGUMENT.search(failure.detail)
    if named is None or named["flag"] not in failure.argv:
        return failure
    return GateStepFailed(
        step=_RENDER_SKEW_STEP,
        argv=failure.argv,
        returncode=failure.returncode,
        detail=(
            f"the gate Job renderer at {renderer} rejected {named['flag']}, which this gate "
            "client passes, so that renderer is older than the client driving it"
        ),
    )


def assembly_refusal(*, failure: GateStepFailed) -> str:
    """What a run says about an assembly that produced no request.

    Every step but one is reported as the step that did not complete, which is
    all that can be said about a command that was never able to answer. The
    renderer-skew case HAS more to say and says it instead: restating the step
    there would bury the one sentence an operator needs behind the sentence that
    hid the cause in the first place.
    """
    if failure.step == _RENDER_SKEW_STEP:
        return f"no gate was submitted: {failure.detail}"
    return f"{failure.step} did not complete, so no gate was submitted: {failure.detail}"
