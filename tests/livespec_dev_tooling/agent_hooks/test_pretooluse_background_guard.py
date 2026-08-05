"""Tests for `livespec_dev_tooling/agent_hooks/pretooluse_background_guard.py`.

Per work-item livespec-dev-tooling-7us.2, the PreToolUse guard denies
(exit 2) any Bash tool call that combines `run_in_background` with a
gate command (`just check*`, `git commit`, `git push`, `gh pr`), and
fails open (exit 0) on every other input including unparseable stdin.

Covered behaviors:

- gate-pattern matching including wrapper prefixes
  (`mise exec -- git commit`, `git -C <path> push`) and non-matches
  (`git log`, plain `ls`, separated compound commands);
- the pure deny decision (`_should_deny`) over tool name /
  `run_in_background` / command-shape combinations;
- the end-to-end hook protocol via in-process `main()` calls plus
  one subprocess invocation of the script exactly as the Claude Code
  hook runs it.

Private names are imported via from-imports (the package-private
access model, mirroring `tests/livespec_dev_tooling/fleet/`);
monkeypatch seams use the string-target form.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.agent_hooks.pretooluse_background_guard import (
    _load_hook_input,
    _matched_gate,
    _should_deny,
    main,
)

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.agent_hooks.pretooluse_background_guard"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "livespec_dev_tooling" / "agent_hooks" / "pretooluse_background_guard.py"


# ---------------------------------------------------------------------------
# _matched_gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("just check", "just check"),
        ("just check-types", "just check"),
        ('just skip="check-coverage" check', "just check"),
        ("mise exec -- git commit -m 'feat: x'", "git commit"),
        ("git -C /data/projects/x/worktrees/wt push -u origin work", "git push"),
        ("gh pr create --base master --head work", "gh pr"),
        ("gh pr merge 7 --auto --rebase --delete-branch", "gh pr"),
    ],
)
def test_matched_gate_recognizes_gate_commands(command: str, expected: str) -> None:
    assert _matched_gate(command=command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git log --oneline -5",
        "git status",
        "just --list",
        "gh run list --workflow CI",
        # Separator-bounded filler: `git` in the first segment must not
        # bridge to `push` in a later segment.
        "git log && echo push",
    ],
)
def test_matched_gate_ignores_non_gate_commands(command: str) -> None:
    assert _matched_gate(command=command) is None


def test_matched_gate_matches_gate_segment_inside_compound_command() -> None:
    assert _matched_gate(command="echo start && mise exec -- git push") == "git push"


# ---------------------------------------------------------------------------
# _should_deny (pure decision)
# ---------------------------------------------------------------------------


def test_should_deny_requires_bash_tool() -> None:
    tool_input: dict[str, object] = {"command": "git push", "run_in_background": True}
    assert _should_deny(tool_name="Read", tool_input=tool_input) is None


def test_should_deny_requires_run_in_background_true() -> None:
    assert _should_deny(tool_name="Bash", tool_input={"command": "git push"}) is None
    falsy: dict[str, object] = {"command": "git push", "run_in_background": False}
    assert _should_deny(tool_name="Bash", tool_input=falsy) is None
    truthy_string: dict[str, object] = {"command": "git push", "run_in_background": "yes"}
    assert _should_deny(tool_name="Bash", tool_input=truthy_string) is None


def test_should_deny_requires_string_command() -> None:
    tool_input: dict[str, object] = {"command": 42, "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) is None


def test_should_deny_allows_backgrounded_non_gate_command() -> None:
    tool_input: dict[str, object] = {"command": "sleep 600", "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) is None


def test_should_deny_denies_backgrounded_gate_command() -> None:
    tool_input: dict[str, object] = {"command": "just check", "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) == "just check"


def test_should_deny_allows_the_sanctioned_detached_gate_runner() -> None:
    """Backgrounding `scripts/gate-run.sh` is the SUPPORTED way to run a long gate.

    The commit aggregate can outlast the harness's 20-minute tool-call
    ceiling, and a bare foreground re-issue then dies with no verdict.
    The detached runner keeps the gate in its own session and records a
    durable verdict, so its waiter is safe to background: killing the
    waiter loses nothing and it can simply be re-issued. Denying the
    runner would leave NO way to run a gate that outlasts the ceiling.
    """
    start: dict[str, object] = {
        "command": "scripts/gate-run.sh start -- mise exec -- git commit --amend --no-edit",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=start) is None

    waiter: dict[str, object] = {
        "command": "mise exec -- just gate-wait 20260805T051456Z-4055481",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=waiter) is None


def test_should_deny_does_not_let_naming_the_runner_launder_a_bare_gate() -> None:
    """The command must BE a runner invocation, not merely mention one.

    A bare backgrounded gate keeps its original hazard — the tool output
    is the only record, so a killed task leaves no verdict behind. That
    deny must not be escapable by putting the runner's name in a commit
    message or a comment.
    """
    in_message: dict[str, object] = {
        "command": "mise exec -- git commit -m 'feat(gate): add scripts/gate-run.sh'",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=in_message) == "git commit"

    in_comment: dict[str, object] = {
        "command": "just check  # supersedes gate-run.sh",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=in_comment) == "just check"


# ---------------------------------------------------------------------------
# main() — in-process hook-protocol behavior
# ---------------------------------------------------------------------------


def _run_main(*, monkeypatch: pytest.MonkeyPatch, stdin_text: str) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    return main()


def test_main_fails_open_on_unparseable_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch=monkeypatch, stdin_text="{nope") == 0


def test_main_fails_open_on_non_dict_hook_input(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch=monkeypatch, stdin_text="[1, 2]") == 0


def test_main_fails_open_on_non_dict_tool_input(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": "not a dict"})
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_fails_open_on_missing_tool_name(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {"tool_input": {"command": "git push", "run_in_background": True}},
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_allows_foreground_gate_command(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "mise exec -- git push"}},
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_denies_backgrounded_gate_command(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "just check", "run_in_background": True},
        },
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 2


def test_main_fails_open_on_internal_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_load(*, raw: str) -> dict[str, object] | None:
        _ = raw
        raise RuntimeError("boom")

    monkeypatch.setattr(f"{_MODULE}._load_hook_input", exploding_load)
    assert _run_main(monkeypatch=monkeypatch, stdin_text="{}") == 0


# ---------------------------------------------------------------------------
# subprocess end-to-end — exactly as the Claude Code hook invokes it
# ---------------------------------------------------------------------------


def test_script_denies_then_allows_end_to_end() -> None:
    deny_payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "mise exec -- git commit -m 'feat: x'",
                "run_in_background": True,
            },
        },
    )
    denied = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=deny_payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert denied.returncode == 2
    assert "DENIED" in denied.stderr
    # The deny must ROUTE the caller, not just refuse. It names the
    # detached runner rather than telling them to re-issue foreground —
    # that advice is what walks into the silent kill under load.
    assert "gate-start" in denied.stderr
    assert "DIED_WITHOUT_VERDICT" in denied.stderr

    allow_payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "tail -f build.log", "run_in_background": True},
        },
    )
    allowed = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=allow_payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert allowed.returncode == 0


def test_load_hook_input_rejects_bad_json_and_non_dict() -> None:
    assert _load_hook_input(raw="{nope") is None
    assert _load_hook_input(raw="[1, 2]") is None
    assert _load_hook_input(raw='{"a": 1}') == {"a": 1}
