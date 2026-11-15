"""Per-repository delegation selection and gate-renderer resolution."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.config import ConfigParseError, load_delegated_gate
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable

__all__: list[str] = [
    "GATE_RENDERER_IN_REPO",
    "GATE_RENDERER_PACKAGED",
    "delegated_gate_enabled",
    "delegated_gate_selected",
    "resolve_renderer",
]

# The renderer, in the two places it exists — AND BOTH OF THEM MOVE WITH THIS
# CODE, which is the whole point. A checkout of THIS repository carries it
# in-tree, so a renderer change is gated by the same push that makes it; every
# OTHER repository reaches the copy the wheel ships INSIDE this package, beside
# the client that drives it.
#
# THERE USED TO BE A THIRD PLACE, AND IT COST THE FLEET A DAY (stop-the-line
# R283, 2026-10-20). The fallback was `/usr/local/lib/ci-runner-k3s/gates/
# render-gate-job.sh`, installed only by the `gate_renderer` role in
# `ansible/gates-kubeconfig.yml` — a playbook NOTHING re-converges: no timer,
# unit or release hook ran it on the dev host. So when livespec-dev-tooling-44fglo
# made this client pass `--gate-ref` and that client shipped in releases 1.118.5
# and 1.118.6, the renderer reading it stayed at 2026-10-18, and every delegated
# push from every other fleet repository was refused with `render-gate-job did
# not complete ... FATAL: unknown argument --gate-ref` until an operator ran the
# apply by hand. The writer of the arguments moved through the package release;
# the reader moved only on a manual apply. That is the ordering class AGENTS.md
# records as "confirm the reader before you write", and the repair is to leave
# no reader that a release cannot reach.
#
# THE PACKAGED COPY IS NOT A SECOND SOURCE OF TRUTH. `pyproject.toml`'s
# `[tool.hatch.build.targets.wheel.force-include]` carries the COMMITTED files
# into the wheel — the renderer and the `gate-job-template.yaml` beside it,
# because the renderer resolves its template next to itself — so one tree is
# edited and the release carries it to every consumer.
# `tests/consumer/test_delegated_gate_renderer_lockstep.py` holds that
# declaration and this constant to each other, and runs the client's own argv
# through the file the declaration ships.
GATE_RENDERER_IN_REPO = Path("ci-runner/k3s/phase2/gates/render-gate-job.sh")
GATE_RENDERER_PACKAGED = Path(__file__).resolve().parent / "gates" / "render-gate-job.sh"


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


def resolve_renderer(*, repo_root: Path) -> Path:
    """Name the `render-gate-job.sh` this run should use.

    Prefers the repository's own copy when it has one, so a change to the
    renderer is gated by the same push that makes it — and falls back to the
    copy inside THIS PACKAGE, which is what every other repository has. That
    fallback cannot be older than the arguments this client passes, because it
    arrives in the same wheel as this function; the converged host path it
    replaces could, and was (see `GATE_RENDERER_PACKAGED` above). The fallback
    is returned unconditionally rather than checked: a path that is not there
    fails at the seam, as a step that did not run, with the argv in the report.
    """
    in_repo = repo_root / GATE_RENDERER_IN_REPO
    if in_repo.is_file():
        return in_repo
    return GATE_RENDERER_PACKAGED
