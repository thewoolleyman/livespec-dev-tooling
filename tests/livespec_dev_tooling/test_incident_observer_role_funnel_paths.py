"""The incident_observer role publishes exactly its declared public paths, and refuses any other.

livespec-dev-tooling-jpfdcx. The master-health reconciler runs on GitHub-hosted
runners, which cannot reach the tailnet, so the maintainer ruled (option A,
2026-11-10) that the observer's read-only `POST /ordinary-action` is published
through the same path-scoped Tailscale Funnel as `POST /callback`. The role
therefore declares a LIST of exact paths. An apply publishes each declared path
that is not yet public, leaves a public one alone, refuses when a publish left a
declared path unpublished, and refuses whenever the funnel port publishes a path
the list does not name.

These tests run the role's own funnel tasks, as committed, through the pinned
`ansible-playbook` against a fake `tailscale` that serves a recorded funnel
status and records every publish. The one change to the tasks is that `become`
is dropped, because the test runs as an ordinary account.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest
import yaml

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base
from tests.livespec_dev_tooling import test_incident_observer_role_scratch_refusals as refusals

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-jpfdcx
_FIRST = "Read this node's tailscale serve and funnel configuration"
_LAST = "Refuse a funnel port that publishes a path beyond the declared list"
_PLAYBOOK_TIMEOUT_SECONDS = 600
_DNS = "node.example.ts.net"
_HOST = _DNS + ":10000"
_CALLBACK = "/callback"
_ORDINARY = "/ordinary-action"
_PRODUCTION = "http://127.0.0.1:8765"
_SCRATCH = "http://127.0.0.1:8766"
_ROLE_VARIABLES = (
    "incident_observer_scratch",
    "incident_observer_target_branch",
    "incident_observer_port",
    "incident_observer_funnel_https_port",
    "incident_observer_funnel_paths",
)
# The fake `tailscale`: `status --json --peers=false` answers the node's DNS
# name and capability map, `funnel status --json` answers the recorded serve
# configuration, and a `funnel --bg --yes --https=P --set-path=X URL` publish is
# logged and, unless the node is recorded as discarding publishes, adds the
# path's proxy handler and turns the funnel on for the port.
_FAKE_TAILSCALE = r"""#!/usr/bin/env python3
import json
import os
import sys

state_path = os.environ["FAKE_TAILSCALE_STATE"]
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
argv = sys.argv[1:]
host = state["dns"].rstrip(".")
if argv == ["status", "--json", "--peers=false"]:
    capabilities = {"funnel": None} if state["granted"] else {}
    print(json.dumps({"Self": {"DNSName": state["dns"], "CapMap": capabilities}}))
elif argv == ["funnel", "status", "--json"]:
    print(json.dumps(state["serve"]))
else:
    with open(os.environ["FAKE_TAILSCALE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(argv) + "\n")
    port = argv[3].removeprefix("--https=")
    path = argv[4].removeprefix("--set-path=")
    if state["publishes"]:
        serve = state["serve"]
        serve.setdefault("TCP", {})[port] = {"HTTPS": True}
        web = serve.setdefault("Web", {}).setdefault(host + ":" + port, {"Handlers": {}})
        web["Handlers"][path] = {"Proxy": argv[5]}
        serve.setdefault("AllowFunnel", {})[host + ":" + port] = True
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
"""


def _serve(*, handlers: dict[str, str]) -> dict[str, Any]:
    """A `tailscale funnel status --json` reply with these handlers on a funnelled port."""
    return {
        "TCP": {"10000": {"HTTPS": True}, "8765": {"HTTPS": True}},
        "Web": {
            _HOST: {"Handlers": {path: {"Proxy": proxy} for path, proxy in handlers.items()}},
            _DNS + ":8765": {"Handlers": {"/": {"Proxy": _PRODUCTION}}},
        },
        "AllowFunnel": {_HOST: True},
    }


_BOTH = {_CALLBACK: _PRODUCTION + _CALLBACK, _ORDINARY: _PRODUCTION + _ORDINARY}
# Each node the one playbook run applies the funnel tasks to: its recorded
# funnel status, whether the tailnet grants it the funnel attribute, and
# whether a publish on it takes effect.
_NODES: dict[str, tuple[dict[str, Any], bool, bool]] = {
    "live": (_serve(handlers={_CALLBACK: _PRODUCTION + _CALLBACK}), True, True),
    "fresh": ({}, True, True),
    "public": (_serve(handlers=_BOTH), True, True),
    "elsewhere": (
        _serve(handlers={_CALLBACK: _PRODUCTION + _CALLBACK, _ORDINARY: _SCRATCH + _ORDINARY}),
        True,
        True,
    ),
    "extra-root": (_serve(handlers={**_BOTH, "/": _PRODUCTION}), True, True),
    "extra-current": (_serve(handlers={**_BOTH, "/current": _PRODUCTION + "/current"}), True, True),
    "discarding": (_serve(handlers={_CALLBACK: _PRODUCTION + _CALLBACK}), True, False),
    "ungranted": ({}, False, True),
}


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    failed: bool
    published: list[list[str]]
    output: str


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, _Outcome]:
    """Run the role's funnel tasks once over every node; each node's result, by name."""
    root = tmp_path_factory.mktemp("funnel-paths")
    tasks = base.role_yaml(relative="tasks/converge.yml")
    names = [task.get("name") for task in tasks]
    funnel = [
        {key: value for key, value in task.items() if key != "become"}
        for task in tasks[names.index(_FIRST) : names.index(_LAST) + 1]
    ]
    defaults = base.role_yaml(relative="defaults/main.yml")
    bin_dir = root / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "tailscale"
    fake.write_text(_FAKE_TAILSCALE, encoding="utf-8")
    fake.chmod(0o755)
    hosts: dict[str, dict[str, str]] = {}
    for node, (serve, granted, publishes) in _NODES.items():
        state = root / (node + ".json")
        state.write_text(
            json.dumps(
                {"dns": _DNS + ".", "granted": granted, "publishes": publishes, "serve": serve}
            ),
            encoding="utf-8",
        )
        (root / (node + ".jsonl")).touch()
        hosts[node] = {
            "ansible_connection": "local",
            "fake_state": str(state),
            "fake_log": str(root / (node + ".jsonl")),
        }
    inventory = root / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {"hosts": hosts}}), encoding="utf-8")
    play = root / "funnel.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "all",
                    "gather_facts": False,
                    "environment": {
                        "FAKE_TAILSCALE_STATE": "{{ fake_state }}",
                        "FAKE_TAILSCALE_LOG": "{{ fake_log }}",
                    },
                    "vars": {name: defaults[name] for name in _ROLE_VARIABLES},
                    "tasks": funnel,
                }
            ]
        ),
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_LOCALHOST_WARNING": "false",
            "ANSIBLE_STDOUT_CALLBACK": "oneline",
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
        }
    )
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            refusals.ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            "--forks",
            str(len(_NODES)),
            str(play),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    lines = completed.stdout.splitlines()
    return {
        node: _Outcome(
            failed=any(line.startswith(node + " | FAILED!") for line in lines),
            published=[
                json.loads(line)
                for line in (root / (node + ".jsonl")).read_text(encoding="utf-8").splitlines()
            ],
            output="\n".join(line for line in lines if line.startswith(node + " | ")),
        )
        for node in _NODES
    }


def _publish_argv(*, path: str) -> list[str]:
    """The publish argv the role ran for /callback before it declared a list, for any path."""
    return ["funnel", "--bg", "--yes", "--https=10000", "--set-path=" + path, _PRODUCTION + path]


def test_the_committed_defaults_declare_the_callback_and_the_ordinary_action_paths() -> None:
    defaults = base.role_yaml(relative="defaults/main.yml")

    assert defaults["incident_observer_funnel_paths"] == [_CALLBACK, _ORDINARY]
    assert defaults["incident_observer_funnel_https_port"] == 10000
    assert "incident_observer_funnel_path" not in defaults


def test_the_live_shape_publishes_only_the_ordinary_action_path(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["live"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == [_publish_argv(path=_ORDINARY)]


def test_a_fresh_node_publishes_both_paths_with_the_callback_argv_unchanged(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["fresh"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == [_publish_argv(path=_CALLBACK), _publish_argv(path=_ORDINARY)]


def test_a_node_already_publishing_both_paths_publishes_nothing(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["public"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == []
    assert "are already public; nothing to do" in outcome.output


def test_a_path_proxied_anywhere_but_productions_listener_is_published_again(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["elsewhere"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == [_publish_argv(path=_ORDINARY)]


@pytest.mark.parametrize(("node", "extra"), [("extra-root", "/"), ("extra-current", "/current")])
def test_a_funnel_port_publishing_an_undeclared_path_refuses_and_names_it(
    outcomes: dict[str, _Outcome], *, node: str, extra: str
) -> None:
    outcome = outcomes[node]

    assert outcome.failed is True
    assert outcome.published == []
    assert f"funnel port 10000 publishes {extra}, which the role does not declare" in (
        outcome.output
    )


def test_a_publish_that_leaves_a_declared_path_unpublished_refuses(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["discarding"]

    assert outcome.failed is True
    assert outcome.published == [_publish_argv(path=_ORDINARY)]
    assert "tailscale funnel exited 0 but /ordinary-action" in outcome.output


def test_an_ungranted_node_publishes_nothing_and_does_not_fail(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["ungranted"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == []
    assert "cannot be published" in outcome.output
