"""Consumer-tier proof for the managed Claude Code memory-write guard.

The `claude_memory_write_guard` role (livespec-dev-tooling-pik7f2) installs a
managed-settings drop-in whose PreToolUse hooks run a vendored copy of the
livespec Driver's `block_auto_memory` hook in EVERY project on an interactive
host: it refuses Write, Edit and Bash writes into a Claude Code memory
directory and routes the content to AGENTS.md / `.ai/<topic>.md` by pull
request or to the ledger, while reads, `rm` and writes elsewhere pass. The
hook is an installed host payload under the `_vendor` exemption, so it is
exercised here through its own `main()` entry point, fed hook JSON on stdin
exactly as Claude Code feeds it, in a project with no `.livespec.jsonc`.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "claude_memory_write_guard"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_VENDOR = _ROLE / "files" / "_vendor" / "memory-write-guard"
_HOOK = _VENDOR / "block_auto_memory.py"
_PLAYBOOK = _REPO_ROOT / "ansible" / "claude-memory-guard.yml"

_MEMORY_DIR = "~/.claude/projects/-home-ubuntu-workspace-x/memory"
_MEMORY_FILE = "/home/ubuntu/.claude/projects/-home-ubuntu-workspace-x/memory/MEMORY.md"

# Every command below is INERT DATA fed to the hook on stdin; nothing runs it.
_BASH_MEMORY_WRITES = (
    f"cat >> {_MEMORY_DIR}/feedback.md <<'EOF'\nlearned a thing\nEOF",
    f"echo 'a rule' > {_MEMORY_DIR}/rule.md",
    f"echo note | tee -a {_MEMORY_DIR}/MEMORY.md",
    f"sed -i 's/old/new/' {_MEMORY_DIR}/MEMORY.md",
    f"cp /tmp/draft.md {_MEMORY_DIR}/draft.md",
    f"python3 -c \"open('{_MEMORY_DIR}/n.md', 'w').write('x')\"",
    # The cd-relative form (livespec-driver-claude-ivftll).
    f"cd {_MEMORY_DIR} && cat > note.md <<'EOF'\nbody\nEOF",
    f"cd {_MEMORY_DIR}; echo x >> MEMORY.md",
    f"pushd {_MEMORY_DIR} && touch note.md",
)
_BASH_PASSES = (
    f"cat {_MEMORY_DIR}/MEMORY.md",
    f"grep -rn rule {_MEMORY_DIR}/",
    f"ls -la {_MEMORY_DIR}",
    f"cd {_MEMORY_DIR} && cat a.md",
    f"rm {_MEMORY_DIR}/feedback.md",
    "echo x >> /tmp/notes.md",
    f"cd /tmp && echo x >> notes.md && cat {_MEMORY_DIR}/MEMORY.md",
    # A memory path as DATA in a heredoc program whose write lands elsewhere
    # (livespec-driver-claude-zexdsh).
    "\n".join(
        (
            "python3 - <<'EOF'",
            f"memory_directory = '{_MEMORY_DIR}/'",
            "open('/tmp/scratch.json', 'w').write(memory_directory)",
            "EOF",
        )
    ),
)


_SIBLINGS = ("_memory_write", "_shell_io", "_shell_lex", "_result")


@pytest.fixture(scope="module")
def hook() -> Iterator[ModuleType]:
    """The vendored hook, imported with its siblings from the vendor directory.

    Its siblings import as top-level names (`_result`, `_shell_lex`, ...), so
    any module already holding one of those names is set aside for the import
    and restored afterwards.
    """
    saved = {name: sys.modules.pop(name) for name in _SIBLINGS if name in sys.modules}
    bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(_VENDOR))
    try:
        spec = importlib.util.spec_from_file_location("managed_block_auto_memory", _HOOK)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(_VENDOR))
        sys.dont_write_bytecode = bytecode
        for name in _SIBLINGS:
            _ = sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture(autouse=True)
def ungoverned_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # tmp_path carries no .livespec.jsonc: the Driver's governed-project gate
    # would pass every call through here, and the managed copy must not.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))


def _invoke(
    *,
    hook: ModuleType,
    stdin: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    returncode = hook.main()
    return returncode, capsys.readouterr().out


def _run_hook(
    *,
    hook: ModuleType,
    payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    returncode, stdout = _invoke(
        hook=hook, stdin=json.dumps(payload), monkeypatch=monkeypatch, capsys=capsys
    )
    assert returncode == 0
    return stdout


def _refused(*, stdout: str) -> bool:
    if not stdout.strip():
        return False
    decision = json.loads(stdout)
    return decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def _file_tool(*, tool_name: str, file_path: str) -> dict[str, object]:
    return {"tool_name": tool_name, "tool_input": {"file_path": file_path, "content": "x"}}


@pytest.mark.parametrize("tool_name", ["Write", "Edit", "MultiEdit"])
def test_a_file_tool_write_into_memory_is_refused_in_an_ungoverned_project(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
) -> None:
    stdout = _run_hook(
        hook=hook,
        payload=_file_tool(tool_name=tool_name, file_path=_MEMORY_FILE),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert _refused(stdout=stdout)


@pytest.mark.parametrize("command", _BASH_MEMORY_WRITES)
def test_a_bash_write_into_memory_is_refused(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    stdout = _run_hook(
        hook=hook,
        payload={"tool_name": "Bash", "tool_input": {"command": command}},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert _refused(stdout=stdout)


@pytest.mark.parametrize("command", _BASH_PASSES)
def test_reads_rm_and_writes_elsewhere_pass(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    stdout = _run_hook(
        hook=hook,
        payload={"tool_name": "Bash", "tool_input": {"command": command}},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert not _refused(stdout=stdout)


@pytest.mark.parametrize(
    "payload",
    [
        _file_tool(tool_name="Write", file_path="/home/ubuntu/workspace/x/AGENTS.md"),
        _file_tool(tool_name="Edit", file_path="/home/ubuntu/workspace/x/.ai/topic.md"),
        _file_tool(tool_name="Read", file_path=_MEMORY_FILE),
    ],
)
def test_file_tool_writes_elsewhere_and_memory_reads_pass(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    payload: dict[str, object],
) -> None:
    stdout = _run_hook(hook=hook, payload=payload, monkeypatch=monkeypatch, capsys=capsys)
    assert not _refused(stdout=stdout)


def test_the_refusal_routes_content_to_agents_md_by_pr_or_to_the_ledger(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout = _run_hook(
        hook=hook,
        payload=_file_tool(tool_name="Write", file_path=_MEMORY_FILE),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    decision = json.loads(stdout)
    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert decision["reason"] == reason
    for phrase in ("AGENTS.md", ".ai/<topic>.md", "pull request", "ledger"):
        assert phrase in reason


def test_malformed_input_fails_open(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _invoke(hook=hook, stdin="not json", monkeypatch=monkeypatch, capsys=capsys)
    assert result == (0, "")


def test_the_managed_dropin_wires_only_the_two_pretooluse_hooks() -> None:
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    settings = defaults["claude_memory_write_guard_settings"]

    # No allowManagedHooksOnly (it would disable every user, project and
    # plugin hook) and no auto-memory key (auto-memory stays ON).
    assert set(settings) == {"hooks"}
    assert set(settings["hooks"]) == {"PreToolUse"}
    entries = settings["hooks"]["PreToolUse"]
    assert [entry["matcher"] for entry in entries] == ["Write|Edit|MultiEdit|NotebookEdit", "Bash"]
    for entry in entries:
        assert entry["hooks"] == [
            {"type": "command", "command": "{{ claude_memory_write_guard_command }}"}
        ]
    assert defaults["claude_memory_write_guard_dropin"].startswith(
        "{{ claude_memory_write_guard_dropin_dir }}/"
    )
    assert defaults["claude_memory_write_guard_dropin"].endswith(".json")
    assert defaults["claude_memory_write_guard_dropin_dir"] == (
        "{{ claude_memory_write_guard_policy_dir }}/managed-settings.d"
    )
    assert defaults["claude_memory_write_guard_command"] == (
        "{{ claude_memory_write_guard_python }} {{ claude_memory_write_guard_hook }}"
    )
    assert defaults["claude_memory_write_guard_hook"].endswith("/block_auto_memory.py")


def test_every_vendored_hook_file_is_installed() -> None:
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    vendored = sorted(path.name for path in _VENDOR.glob("*.py"))
    assert sorted(defaults["claude_memory_write_guard_hook_files"]) == vendored


def test_the_guard_is_proved_before_the_dropin_wires_it() -> None:
    tasks = yaml.safe_load(_TASKS.read_text(encoding="utf-8"))
    names = [task["name"] for task in tasks]
    assert names.index("Prove the installed guard refuses a memory write") < names.index(
        "Write the managed-settings drop-in"
    )


def test_the_playbook_applies_the_role_to_interactive_claude_hosts() -> None:
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    assert [play["hosts"] for play in plays] == ["interactive_claude_hosts"]
    assert [role["role"] for role in plays[0]["roles"]] == ["claude_memory_write_guard"]
