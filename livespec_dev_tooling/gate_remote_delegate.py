"""The delegated gate's PER-REPO OPT-IN and its recipe entry point — R4.S7c.

S7a drives one gate run on the cluster and S7b decides it; neither is reachable
from a git hook, and neither should be reachable from every repository at once.
This module is what stands between them and a push: the SWITCH that says whether
THIS repository delegates its pre-push aggregate, and the `python -m` entry point
a repository's own `check-pre-push` recipe calls to act on the answer. The module
is SHARED — one client, shipped once — and the wiring is per repository, so a
rollout is a sequence of small, separately reviewable edits rather than one flip
that moves the whole fleet's gate at the same instant.

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

from livespec_dev_tooling.config import ConfigParseError, load_delegated_gate
from livespec_dev_tooling.gate_remote_client import GateRunRequest
from livespec_dev_tooling.gate_remote_invocation import (
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
    "GATE_MIRROR_ROOT",
    "GATE_RENDERER_INSTALLED",
    "GATE_RENDERER_IN_REPO",
    "delegated_gate_enabled",
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

# The renderer's own default job name, computed here rather than parsed back out
# of the manifest — and passed to it explicitly, so the name this client waits on
# is the name it asked for even if that default ever moves.
_JOB_NAME_TREE_CHARS = 12


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


def gate_remote_request(
    *, repo_root: Path, renderer: Path, runner: GateCommandRunner
) -> Result[GateRunRequest, GateStepFailed]:
    """Assemble the one request S7a needs, out of the repository itself.

    Both reaches into the world go through the SAME seam the client uses, so a
    caller that can stub the cluster can stub the assembly too — and a failure
    here arrives in the shape the run's own failures arrive in, carrying the step
    that could not be completed rather than an exception nobody up the stack is
    positioned to interpret.
    """
    tree_argv = ["git", "rev-parse", "HEAD^{tree}"]
    tree = require_success(
        step=_READ_TREE_STEP, argv=tree_argv, outcome=runner(argv=tree_argv, cwd=repo_root)
    )
    if isinstance(tree, Failure):
        return Failure(tree.failure())
    tree_hash = tree.unwrap().stdout.strip()
    repo = repo_root.name
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

    `enabled` is SILENT and reports through its exit code alone, so a repository
    that has not opted in — every repository, today — sees a pre-push that is
    byte-for-byte the one it saw before this slice landed.
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
        return 0 if delegated_gate_enabled(repo_root=repo_root) else 1

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
