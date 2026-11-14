"""Consumer-tier proof for the interactive hosts' Claude Code managed policy.

The `claude_distributed_sendmessage` role (plan distributed-sendmessage, epic
livespec-dev-tooling-rlwppp) installs a PreToolUse pane-input guard and a
managed-settings drop-in; the `claude_code_hooks` role installs the
tmux-fleet guard. Both guards are installed host payloads under the `_vendor`
exemption, so none of this repository's library gates exercise them. These
tests load each guard in-process, run its own regression corpus, and pin the
behaviour the SendMessage protocol promises, so a pull request that breaks
either guard fails CI instead of failing only at apply time
(livespec-dev-tooling-6z3ccv).
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLES = _REPO_ROOT / "ansible" / "roles"
_PANE_GUARD = (
    _ROLES / "claude_distributed_sendmessage" / "files" / "_vendor" / "pane-input-guard.py"
)
_TMUX_GUARD = _ROLES / "claude_code_hooks" / "files" / "_vendor" / "tmux-fleet-guard.py"
_DEFAULTS = _ROLES / "claude_distributed_sendmessage" / "defaults" / "main.yml"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lookup(_globals: list[str], _kind: str, target: str) -> str:
    return {"w1:claude": "claude", "w1:codex": "codex", "w1:shell": ""}[target]


@pytest.mark.parametrize(
    ("guard", "name"),
    [(_PANE_GUARD, "pane_input_guard"), (_TMUX_GUARD, "tmux_fleet_guard")],
    ids=["pane-input", "tmux-fleet"],
)
def test_each_installed_guard_passes_its_own_regression_corpus(
    guard: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p5")
    module = _load(guard, name)

    assert module._selftest() == 0  # noqa: SLF001 - the corpus entry point is the contract


def test_the_pane_guard_denies_text_into_a_claude_pane_and_names_sendmessage() -> None:
    guard = _load(_PANE_GUARD, "pane_input_guard")

    reason = guard.classify("herdr pane send-text w1:claude 'please rebase'", _lookup)

    assert reason is not None
    assert "SendMessage" in reason
    assert "ListAgents" in reason


def test_the_pane_guard_allows_codex_panes_empty_panes_and_key_only_input() -> None:
    guard = _load(_PANE_GUARD, "pane_input_guard")

    assert guard.classify("herdr pane send-text w1:codex 'proceed'", _lookup) is None
    assert guard.classify("herdr pane run w1:shell 'claude --name worker'", _lookup) is None
    assert guard.classify("herdr pane send-keys w1:claude esc", _lookup) is None


def test_the_pane_guard_emits_a_pretooluse_deny_for_a_denied_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _load(_PANE_GUARD, "pane_input_guard")
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "tmux paste-buffer -t seat"}}
    )
    out = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.setattr("sys.stdout", out)

    assert guard.main() == 0

    decision = json.loads(out.getvalue())["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"


def test_the_managed_dropin_forces_remote_control_and_wires_the_guard() -> None:
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    settings = defaults["claude_distributed_sendmessage_settings"]

    assert settings["remoteControlAtStartup"] is True
    assert settings["crossSessionInbound"] == "accept"
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "Bash"
    assert hook["hooks"][0]["command"] == "python3 {{ claude_distributed_sendmessage_guard_dest }}"
    assert defaults["claude_distributed_sendmessage_guard_dest"].endswith("/pane-input-guard.py")
