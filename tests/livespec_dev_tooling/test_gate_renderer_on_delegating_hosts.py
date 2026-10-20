"""A delegating host reaches NO renderer copy that only a hand-run playbook updates.

WHAT THIS FILE USED TO HOLD, AND WHY IT DOES NOT (2026-10-17 → 2026-10-20). A
consuming repository delegates its pre-push gate by running
`livespec_dev_tooling.gate_remote_delegate run`, which renders the gate Job with
`render-gate-job.sh`. The client prefers the repository's own
`ci-runner/k3s/phase2/gates/render-gate-job.sh`, which only livespec-dev-tooling
carries, and otherwise falls back. That fallback used to be a copy on the pushing
HOST at `/usr/local/lib/ci-runner-k3s/gates/render-gate-job.sh`, and these tests
held `ansible/gates-kubeconfig.yml` to installing it — because for a while that
copy was installed ONLY by `ci_converge_unit`, a `ci_pool` role, so on the
control node vps (a `dev_hosts` member that holds the gates kubeconfig) the
fallback did not exist at all and no consumer had ever been able to delegate from
there (livespec-dev-tooling-saxz's host leg).

INSTALLING IT WAS NOT ENOUGH, AND THE SECOND FAILURE WAS WORSE THAN THE FIRST. A
missing renderer fails loudly and at once; a PRESENT-BUT-STALE one fails on the
next argument the client learns to pass. Nothing re-converges that playbook — no
timer, unit or release hook runs it on the dev host, where only
`gate-optin-expiry.timer` runs — while the CLIENT moves with every package
release. So when livespec-dev-tooling-44fglo made the client pass `--gate-ref`
and that client shipped in 1.118.5 and 1.118.6, the host copy stayed at
2026-10-18 and every delegated push from every OTHER fleet repository was refused
with `render-gate-job did not complete ... FATAL: unknown argument --gate-ref`,
from the release until an operator ran the apply by hand on 2026-10-20
(stop-the-line R283, work-item livespec-dev-tooling-vurvjl).

WHAT THESE TESTS HOLD IT TO NOW. The renderer ships INSIDE the wheel, beside the
client that drives it (`pyproject.toml`'s
`[tool.hatch.build.targets.wheel.force-include]`, asserted end to end by
`tests/consumer/test_delegated_gate_renderer_lockstep.py`), so writer and reader
move as ONE artifact. This file guards the other half of that repair: the
delegating-hosts play installs the gates CREDENTIAL and no renderer, no role
remains for a later edit to wire back in, and the client's own fallback names a
path the wheel carries. A renderer copy a release cannot reach is the defect, so
its ABSENCE is the invariant.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_dev_tooling.gate_remote_delegate import GATE_RENDERER_PACKAGED

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAY = _REPO_ROOT / "ansible" / "gates-kubeconfig.yml"
_ROLES = _REPO_ROOT / "ansible" / "roles"
_RETIRED_ROLE = "gate_renderer"
_RENDERER = "render-gate-job.sh"

# The renderer path the retired role installed. Spelled HERE, and nowhere in the
# product code any more, so a return of that fallback has to pass this file
# first.
#
# WHAT THIS DELIBERATELY DOES NOT CATCH, AND WHY THAT IS RIGHT: `ci_converge_unit`
# still installs a `gates/render-gate-job.sh` under its own
# `ci_converge_unit_lib_dir`, composed rather than spelled, so the literal below
# does not match it. That is the CI POOL's reconstruct tree — the files the k3s
# server rebuilds its own stack from, converged by a boot unit on every start —
# and no gate client reads it. The defect was never "a renderer exists on a
# host"; it was "the client falls back to a renderer no release can reach".
_CONVERGED_HOST_COPY = "/usr/local/lib/ci-runner-k3s/gates"


def _role_text(*, role: Path) -> str:
    """Every YAML file of one ansible role, concatenated.

    Read as text rather than parsed because the claim is about a PATH appearing
    ANYWHERE in the role — a task, a default, a handler — and a parse would have
    to know in advance which key could carry it.
    """
    return "\n".join(found.read_text(encoding="utf-8") for found in sorted(role.rglob("*.yml")))


def test_the_delegating_hosts_play_installs_the_credential_and_no_renderer() -> None:
    """`ansible/gates-kubeconfig.yml` targets `dev_hosts` and runs `gates_kubeconfig` alone."""
    play = _PLAY.read_text(encoding="utf-8")
    assert re.search(r"^  hosts: dev_hosts$", play, re.MULTILINE), play
    roles = re.search(r"^  roles:\n(?P<body>(?:    .*\n)+)", play, re.MULTILINE)
    assert roles is not None, f"{_PLAY} declares no roles block:\n{play}"
    declared = re.findall(r"^    - (?:role: )?([a-z_]+)\s*$", roles["body"], re.MULTILINE)
    assert "gates_kubeconfig" in declared, declared
    assert _RETIRED_ROLE not in declared, (
        f"{_PLAY} must install no gate renderer: nothing re-converges this playbook, so a "
        f"renderer installed here goes stale against a client that ships with every "
        f"release; roles: {declared}"
    )


def test_no_role_remains_to_install_a_renderer_a_release_cannot_reach() -> None:
    """The retired role is GONE, not merely unwired — an unwired role invites a re-wire."""
    assert not (_ROLES / _RETIRED_ROLE).exists(), f"{_ROLES / _RETIRED_ROLE} must not exist"
    naming = [
        role.name
        for role in sorted(_ROLES.iterdir())
        if role.is_dir() and f"{_CONVERGED_HOST_COPY}/{_RENDERER}" in _role_text(role=role)
    ]
    assert naming == [], (
        f"no role may install the gate client's renderer at {_CONVERGED_HOST_COPY}/{_RENDERER}: "
        f"the client resolves the copy its own release ships. Roles naming it: {naming}"
    )


def test_the_client_resolves_its_renderer_inside_the_package_it_ships_in() -> None:
    """The fallback names a path the wheel carries, never one a host converge writes."""
    assert GATE_RENDERER_PACKAGED.name == _RENDERER
    assert not str(GATE_RENDERER_PACKAGED).startswith(_CONVERGED_HOST_COPY), (
        f"{GATE_RENDERER_PACKAGED} is the copy an operator must converge by hand; the client "
        "must resolve the copy its own release ships"
    )
