"""Outside-in tests for the Codex hook-cache compatibility release gate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import codex_hook_reconcilable

__all__: list[str] = []


def _git(*, cwd: Path, args: tuple[str, ...]) -> None:
    """Run one fixture-repository Git command and require success."""
    completed = subprocess.run(
        ("git", *args),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def _track_fixture(*, root: Path) -> None:
    """Initialize `root` as a repository and track its plugin payload."""
    _git(cwd=root, args=("init", "--quiet"))
    _git(cwd=root, args=("add", "."))


def _write_json(*, path: Path, value: object) -> None:
    """Write one JSON fixture, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_plugin(
    *, root: Path, manifest: object, hooks: object, hooks_path: str = "hooks/hooks.json"
) -> None:
    """Write a plugin manifest and one hooks declaration below its payload root."""
    _write_json(path=root / ".codex-plugin" / "plugin.json", value=manifest)
    _write_json(path=root / hooks_path, value=hooks)


def _run(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[dict[str, object]]]:
    """Run the check inside a tracked fixture and decode its structured output."""
    _track_fixture(root=root)
    monkeypatch.chdir(root)
    rc = codex_hook_reconcilable.main()
    lines = capsys.readouterr().err.splitlines()
    return rc, [json.loads(line) for line in lines]


def test_rejects_command_with_unbraced_plugin_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A command mentioning only `$CLAUDE_PLUGIN_ROOT` names its event and manifest."""
    command = 'python3 "$CLAUDE_PLUGIN_ROOT/hooks/start.py"'
    _write_plugin(
        root=tmp_path,
        manifest={"name": "fixture"},
        hooks={"hooks": {"SessionStart": [{"hooks": [{"command": command}]}]}},
    )

    rc, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 4
    assert findings[0]["failure_mode"] == "no_plugin_root_path"
    assert findings[0]["manifest"] == ".codex-plugin/plugin.json"
    assert findings[0]["event"] == "SessionStart"
    assert findings[0]["command"] == command


def test_rejects_missing_custom_entrypoint(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first braced path must name a file in the plugin payload."""
    command = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/gone.py"'
    _write_plugin(
        root=tmp_path,
        manifest={"hooks": "declarations/custom.json"},
        hooks={"hooks": {"Stop": [{"hooks": [{"command": command}]}]}},
        hooks_path="declarations/custom.json",
    )

    rc, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 4
    assert findings[0]["failure_mode"] == "entrypoint_missing"
    assert findings[0]["entrypoint"] == "hooks/gone.py"
    assert findings[0]["event"] == "Stop"
    assert findings[0]["command"] == command


@pytest.mark.parametrize(
    ("manifest", "hooks", "expected"),
    [
        ({"hooks": "missing.json"}, None, "hooks_file_missing"),
        ({"hooks": []}, None, "malformed_manifest"),
        ({"name": "fixture"}, "{", "unparseable_hooks_file"),
        ({"name": "fixture"}, {"hooks": {"Stop": {}}}, "malformed_hooks_file"),
    ],
)
def test_rejects_unreadable_or_malformed_declarations(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    manifest: object,
    hooks: object,
    expected: str,
) -> None:
    """Malformed manifests and declarations fail structurally instead of being skipped."""
    _write_json(path=tmp_path / ".codex-plugin" / "plugin.json", value=manifest)
    if hooks is not None:
        hooks_file = tmp_path / "hooks" / "hooks.json"
        hooks_file.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(hooks, str):
            hooks_file.write_text(hooks, encoding="utf-8")
        else:
            _write_json(path=hooks_file, value=hooks)

    rc, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 4
    assert findings[0]["failure_mode"] == expected


def test_accepts_conditional_python_and_bash_hooks(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Conditional shell commands pass when both plugin-root entrypoints are shipped."""
    python_command = (
        'if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; '
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/a.py"'
    )
    bash_command = (
        'if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; '
        'bash "${CLAUDE_PLUGIN_ROOT}/hooks/b.sh"'
    )
    _write_plugin(
        root=tmp_path,
        manifest={"name": "fixture"},
        hooks={
            "hooks": {"Stop": [{"hooks": [{"command": python_command}, {"command": bash_command}]}]}
        },
    )
    (tmp_path / "hooks" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "hooks" / "b.sh").write_text("", encoding="utf-8")

    rc, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert findings[0]["manifests_checked"] == 1
    assert findings[0]["commands_checked"] == 2


def test_passes_without_codex_plugin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository with no Codex manifest reports its zero-manifest pass."""
    (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")

    rc, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert findings[0]["manifests_checked"] == 0
    assert findings[0]["commands_checked"] == 0
