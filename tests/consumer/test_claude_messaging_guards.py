"""Consumer-tier proof for the interactive hosts' Claude Code managed policy.

The `claude_distributed_sendmessage` role (plan distributed-sendmessage, epic
livespec-dev-tooling-rlwppp) installs a managed-settings drop-in and managed
CLAUDE.md guidance that make SendMessage the preferred channel between Claude
sessions. By maintainer ruling 2026-11-14 it blocks no pane input: it wires no
hook, and keeps only an allow-all stub at the retired pane-input guard's path. The
`claude_code_hooks` role installs the tmux-fleet guard, an installed host
payload under the `_vendor` exemption, so its own regression corpus runs here
(livespec-dev-tooling-6z3ccv).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLES = _REPO_ROOT / "ansible" / "roles"
_TMUX_GUARD = _ROLES / "claude_code_hooks" / "files" / "_vendor" / "tmux-fleet-guard.py"
_ROLE = _ROLES / "claude_distributed_sendmessage"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_MEMORY = _ROLE / "files" / "managed-memory.md"


def test_the_tmux_fleet_guard_passes_its_own_regression_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p5")
    spec = importlib.util.spec_from_file_location("tmux_fleet_guard", _TMUX_GUARD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._selftest() == 0  # noqa: SLF001 - the corpus entry point is the contract


def test_the_managed_dropin_forces_remote_control_and_blocks_no_pane_input() -> None:
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    settings = defaults["claude_distributed_sendmessage_settings"]

    # Maintainer ruling 2026-11-14: SendMessage is guidance, never a block on
    # typing into a pane, so the managed drop-in carries these two keys and no
    # hook or other policy.
    assert settings == {"remoteControlAtStartup": True, "crossSessionInbound": "accept"}


def test_the_managed_memory_prefers_sendmessage_and_allows_pane_typing() -> None:
    memory = _MEMORY.read_text(encoding="utf-8")

    assert "prefer SendMessage" in memory
    assert "Typing into a pane is still ALLOWED and nothing blocks it." in memory
    assert "Never type" not in memory


def test_every_seat_shell_exports_the_dangerous_rm_no_prompt_variable() -> None:
    # Measured 2026-11-14 (livespec-dev-tooling-6tgd2z): only the PROCESS
    # environment suppresses Claude Code's built-in dangerous-rm prompt in
    # bypass mode, so the role must export it where a seat's shell reads it.
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    assert defaults["claude_distributed_sendmessage_seat_env"] == {
        "CLAUDE_CODE_EVEN_MORE_DANGEROUSLY_SKIP_PERMISSIONS": "1"
    }
    assert set(defaults["claude_distributed_sendmessage_shell_rcs"]) >= {
        "/etc/bash.bashrc",
        "/etc/zsh/zshenv",
    }
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    for key in (
        "claude_distributed_sendmessage_profile_snippet",
        "claude_distributed_sendmessage_shell_rcs",
        "claude_distributed_sendmessage_environment_d",
    ):
        assert key in tasks
