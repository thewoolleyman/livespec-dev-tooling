"""Edge coverage for malformed Codex plugin hook declarations."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import codex_hook_reconcilable

__all__: list[str] = []


def _git(*, root: Path) -> None:
    """Initialize and stage the fixture tree."""
    for args in (("init", "--quiet"), ("add", ".")):
        completed = subprocess.run(("git", *args), cwd=root, capture_output=True, check=False)
        assert completed.returncode == 0


def _json(*, path: Path, value: object) -> None:
    """Write a JSON declaration under a fixture repository."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value), encoding="utf-8")


def _run(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[dict[str, object]]]:
    """Run the check and decode its JSON findings."""
    _git(root=root)
    monkeypatch.chdir(root)
    result = codex_hook_reconcilable.main()
    return result, [json.loads(line) for line in capsys.readouterr().err.splitlines()]


_MALFORMED_SHAPES: tuple[tuple[object, str], ...] = (
    ([], "malformed_hooks_file"),
    ({}, "malformed_hooks_file"),
    ({"hooks": {"Stop": [{}]}}, "malformed_hooks_file"),
    ({"hooks": {"Stop": [{"hooks": ["bad"]}]}}, "malformed_hooks_file"),
)


@pytest.mark.parametrize(("hooks", "mode"), _MALFORMED_SHAPES)
def test_rejects_every_malformed_hooks_shape(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hooks: object,
    mode: str,
) -> None:
    """The check fails malformed matcher and entry shapes instead of crashing."""
    _json(path=tmp_path / ".codex-plugin" / "plugin.json", value={})
    _json(path=tmp_path / "hooks" / "hooks.json", value=hooks)

    result, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 4
    assert findings[0]["failure_mode"] == mode


def test_checks_declared_and_default_hooks_files(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manifest declaration supplements rather than replaces the default declaration."""
    _json(path=tmp_path / ".codex-plugin" / "plugin.json", value={"hooks": "custom.json"})
    _json(
        path=tmp_path / "custom.json",
        value={"hooks": {"Stop": [{"hooks": [{"command": "echo harmless"}]}]}},
    )
    _json(
        path=tmp_path / "hooks" / "hooks.json",
        value={"hooks": {"Stop": [{"hooks": [{"command": "echo also-harmless"}]}]}},
    )

    result, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 0
    assert findings[0]["commands_checked"] == 2


def test_rejects_entrypoint_outside_plugin_payload(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lexically escaping a plugin root remains an absent payload entrypoint."""
    _json(path=tmp_path / ".codex-plugin" / "plugin.json", value={})
    _json(
        path=tmp_path / "hooks" / "hooks.json",
        value={
            "hooks": {
                "Stop": [{"hooks": [{"command": 'python3 "${CLAUDE_PLUGIN_ROOT}/../shared.py"'}]}]
            }
        },
    )
    _ = (tmp_path / "shared.py").write_text("", encoding="utf-8")

    result, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 4
    assert findings[0]["failure_mode"] == "entrypoint_missing"


def test_accepts_null_manifest_hooks_and_non_root_commands(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A null declaration is absent and commands without the root token need no path."""
    _json(path=tmp_path / ".codex-plugin" / "plugin.json", value={"hooks": None})
    _json(
        path=tmp_path / "hooks" / "hooks.json",
        value={"hooks": {"Stop": [{"hooks": [{"command": "echo ready"}]}]}},
    )

    result, findings = _run(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result == 0
    assert findings[0]["commands_checked"] == 1
