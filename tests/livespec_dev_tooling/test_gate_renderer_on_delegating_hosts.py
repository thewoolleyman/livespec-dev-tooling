"""The gate renderer is installed on every host that may delegate a pre-push gate.

WHY IT EXISTS (2026-10-17). A consuming repository delegates its pre-push gate by
running `livespec_dev_tooling.gate_remote_delegate run`, which renders the gate Job
with `render-gate-job.sh`. The client prefers the repository's own
`ci-runner/k3s/phase2/gates/render-gate-job.sh`, which only livespec-dev-tooling
carries, and otherwise falls back to the installed copy at
`GATE_RENDERER_INSTALLED`. That installed copy was put in place ONLY by
`ci_converge_unit`, a `ci_pool` role, so on the control node vps (a `dev_hosts`
member that holds the gates kubeconfig) the fallback did not exist. A delegated gate
from a livespec-orchestrator-beads-fabro checkout there returned
`NO_VERDICT: render-gate-job did not complete, so no gate was submitted:
/usr/local/lib/ci-runner-k3s/gates/render-gate-job.sh not on PATH` (livespec plan
factory-worker-nodes-gitops, the host leg of livespec-dev-tooling-saxz). No consumer
had ever been able to delegate from vps.

WHAT THESE TESTS HOLD IT TO. The `dev_hosts` play that installs the gates credential
also installs the renderer, at exactly the path the client falls back to, with the
template it renders beside it, because `render-gate-job.sh` resolves its template
next to itself. The path is read from the client's own constant, never respelled, so
moving one breaks this test rather than silently stranding the other.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_dev_tooling.gate_remote_delegate import GATE_RENDERER_INSTALLED

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAY = _REPO_ROOT / "ansible" / "gates-kubeconfig.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "gate_renderer"
_GATES_SRC = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates"
_RENDERER = "render-gate-job.sh"
_TEMPLATE = "gate-job-template.yaml"


def test_the_delegating_hosts_play_installs_the_gate_renderer() -> None:
    """`ansible/gates-kubeconfig.yml` targets `dev_hosts` and runs `gate_renderer`."""
    play = _PLAY.read_text(encoding="utf-8")
    assert re.search(r"^  hosts: dev_hosts$", play, re.MULTILINE), play
    roles = re.search(r"^  roles:\n(?P<body>(?:    .*\n)+)", play, re.MULTILINE)
    assert roles is not None, f"{_PLAY} declares no roles block:\n{play}"
    declared = re.findall(r"^    - (?:role: )?([a-z_]+)\s*$", roles["body"], re.MULTILINE)
    assert "gates_kubeconfig" in declared, declared
    assert (
        "gate_renderer" in declared
    ), f"{_PLAY} must install the gate renderer beside the gates credential; roles: {declared}"


def test_the_renderer_lands_where_the_gate_client_falls_back_to() -> None:
    """The role's install directory is the parent of the client's GATE_RENDERER_INSTALLED."""
    defaults = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    match = re.search(r"^gate_renderer_install_dir: (?P<dir>\S+)$", defaults, re.MULTILINE)
    assert match is not None, defaults
    assert Path(match["dir"]) == GATE_RENDERER_INSTALLED.parent
    assert GATE_RENDERER_INSTALLED.name == _RENDERER


def test_the_role_installs_the_renderer_and_its_template_root_owned() -> None:
    """Both files are copied from the committed gates tree, the renderer executable."""
    defaults = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    for name, mode in ((_RENDERER, "0755"), (_TEMPLATE, "0644")):
        assert (_GATES_SRC / name).is_file(), f"{name} must exist in {_GATES_SRC}"
        assert re.search(
            rf"^  - src: {re.escape(name)}\n    mode: \"{mode}\"$", defaults, re.MULTILINE
        ), f"{name} must be installed with mode {mode}:\n{defaults}"
    assert "ansible.builtin.copy:" in tasks, tasks
    assert re.search(r"^\s+owner: root$", tasks, re.MULTILINE), tasks
    assert re.search(r"^\s+group: root$", tasks, re.MULTILINE), tasks
    assert "become: true" in tasks, tasks
