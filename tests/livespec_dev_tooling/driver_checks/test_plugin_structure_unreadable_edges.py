"""Every remaining arm the read/absent/malformed split added to both profiles.

The sibling `test_plugin_structure_unreadable.py` pins the ruling itself —
a can't-READ is not a violation, and absence/malformation still are. This
file reaches the arms that ruling created at each individual read site.

⛔ THESE LINES ARE STRUCTURALLY UNREACHABLE FROM THE EXISTING SUITE, and
not by accident. Every fixture in `test_plugin_structure_claude.py` and
`test_plugin_structure_codex.py` builds a tree that is fully READABLE —
that is what those suites are for — so no canned tree can enter a
failure arm. The five tests there NAMED `*_unreadable` all wrote
`{ not json`, which is malformed rather than unreadable, so the check
shipped with ZERO coverage of a genuinely unreadable file. That absence is
why the collapse survived to be found here.

Unreadability is spelled as a DIRECTORY where a file is expected
(`IsADirectoryError`, an `OSError` that is NOT `FileNotFoundError`),
never `chmod 000`, which is a lie when the suite runs as root.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.driver_checks import plugin_structure
from livespec_dev_tooling.driver_checks._plugin_structure_claude import (
    _relative,
    claude_profile_violations,
    fenced_invocation_violations,
    read_profile_text,
)
from livespec_dev_tooling.driver_checks._plugin_structure_codex import (
    codex_profile_violations,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

__all__: list[str] = []


def test_a_path_outside_the_root_falls_back_to_its_bare_name(*, tmp_path: Path) -> None:
    """The diagnostic must never leak an absolute host path into a CI log."""
    assert _relative(path=tmp_path / "x" / "SKILL.md", root=tmp_path / "other") == "SKILL.md"


def test_reading_an_absent_file_is_a_success_carrying_none(*, tmp_path: Path) -> None:
    """`None` on the SUCCESS track is how absence stays definitive."""
    outcome = read_profile_text(path=tmp_path / "nope.json", root=tmp_path)
    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()) is None


def test_a_globbed_skill_md_that_vanished_is_reported_absent(*, tmp_path: Path) -> None:
    """Absence reached through the fenced reader is a violation, not a failure."""
    outcome = fenced_invocation_violations(skill_md=tmp_path / "gone" / "SKILL.md", root=tmp_path)
    assert isinstance(outcome, IOSuccess)
    assert any("absent" in v for v in unsafe_perform_io(outcome.unwrap()))


def _claude_root(*, tmp_path: Path, plugin: object = None, marketplace: object = None) -> Path:
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(
        json.dumps(plugin if plugin is not None else {"name": "livespec", "description": "d"}),
        encoding="utf-8",
    )
    _ = (plugin_dir / "marketplace.json").write_text(
        json.dumps(
            marketplace
            if marketplace is not None
            else {
                "name": "livespec-driver-claude",
                "plugins": [{"name": "livespec", "source": "./.claude-plugin", "description": "d"}],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_a_manifest_that_parses_to_a_non_object_is_a_violation(*, tmp_path: Path) -> None:
    """Valid JSON is not the same claim as a valid MANIFEST."""
    root = _claude_root(tmp_path=tmp_path, plugin=[1, 2, 3])
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess)
    assert any("MUST be a JSON object" in v for v in unsafe_perform_io(outcome.unwrap()))


def test_a_marketplace_entry_that_is_not_an_object_is_a_violation(*, tmp_path: Path) -> None:
    root = _claude_root(
        tmp_path=tmp_path,
        marketplace={"name": "livespec-driver-claude", "plugins": ["not-an-object"]},
    )
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess)
    assert any("entry MUST be a JSON object" in v for v in unsafe_perform_io(outcome.unwrap()))


def test_an_unreadable_marketplace_short_circuits_the_claude_profile(*, tmp_path: Path) -> None:
    """The SECOND manifest read has its own failure arm."""
    root = _claude_root(tmp_path=tmp_path)
    (root / ".claude-plugin" / "marketplace.json").unlink()
    (root / ".claude-plugin" / "marketplace.json").mkdir()
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOFailure)
    assert "marketplace.json" in unsafe_perform_io(outcome.failure()).path


def test_an_unreadable_skill_md_short_circuits_the_claude_skill_set(*, tmp_path: Path) -> None:
    """Reached through `_claude_skill_set_violations`, not the fenced reader."""
    root = _claude_root(tmp_path=tmp_path)
    skills = root / ".claude-plugin" / "skills"
    (skills / "seed").mkdir(parents=True)
    (skills / "seed" / "SKILL.md").mkdir()
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOFailure)
    assert "SKILL.md" in unsafe_perform_io(outcome.failure()).path


def _codex_root(*, tmp_path: Path) -> Path:
    plugins_dir = tmp_path / ".agents" / "plugins"
    plugins_dir.mkdir(parents=True)
    _ = (plugins_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "livespec-driver-codex",
                "plugins": [
                    {
                        "name": "livespec",
                        "source": {"source": "local", "path": "./livespec"},
                        "description": "d",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_dir = tmp_path / "livespec" / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    _ = (manifest_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "livespec",
                "version": "1",
                "skills": "./skills/",
                "hooks": "./hooks/hooks.json",
                "description": "d",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_an_unreadable_codex_manifest_short_circuits(*, tmp_path: Path) -> None:
    root = _codex_root(tmp_path=tmp_path)
    (root / "livespec" / ".codex-plugin" / "plugin.json").unlink()
    (root / "livespec" / ".codex-plugin" / "plugin.json").mkdir()
    outcome = codex_profile_violations(root=root)
    assert isinstance(outcome, IOFailure)
    assert "plugin.json" in unsafe_perform_io(outcome.failure()).path


def test_an_unreadable_codex_skill_md_short_circuits(*, tmp_path: Path) -> None:
    root = _codex_root(tmp_path=tmp_path)
    skills = root / "livespec" / "skills"
    (skills / "seed").mkdir(parents=True)
    (skills / "seed" / "SKILL.md").mkdir()
    outcome = codex_profile_violations(root=root)
    assert isinstance(outcome, IOFailure)
    assert "SKILL.md" in unsafe_perform_io(outcome.failure()).path


def test_an_unreadable_codex_hooks_json_short_circuits(*, tmp_path: Path) -> None:
    root = _codex_root(tmp_path=tmp_path)
    hooks = root / "livespec" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").mkdir()
    outcome = codex_profile_violations(root=root)
    assert isinstance(outcome, IOFailure)
    assert "hooks.json" in unsafe_perform_io(outcome.failure()).path


def test_an_absent_codex_hooks_json_is_a_violation(*, tmp_path: Path) -> None:
    """The converse at the hook bundle: absent stays definitive."""
    root = _codex_root(tmp_path=tmp_path)
    outcome = codex_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess)
    assert any("hooks.json absent" in v for v in unsafe_perform_io(outcome.unwrap()))


def test_run_check_reports_an_unreadable_bundle_as_neither_clean_nor_violating(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third exit code, and the reason it had to exist.

    With unreadability off the violation list, a two-answer `run_check`
    would have reached `0` — reporting a run that measured NOTHING as a run
    that measured everything and found nothing.
    """
    root = _claude_root(tmp_path=tmp_path)
    (root / ".claude-plugin" / "marketplace.json").unlink()
    (root / ".claude-plugin" / "marketplace.json").mkdir()
    log = plugin_structure.structlog.get_logger("t")
    exit_code = plugin_structure.run_check(root=root, log=log)
    assert exit_code not in (0, 1)
    # `run_check` does not configure structlog — `main()` does — so the
    # default console renderer writes to stdout here. Both streams are read
    # so the assertion cannot pass by looking at the wrong one.
    captured = capsys.readouterr()
    logged = captured.out + captured.err
    assert "could not be read" in logged
    assert "plugin-structure violation" not in logged


def test_a_readable_bundle_still_reports_its_violations(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive control.

    Every other test here asserts a failure or a short-circuit, so all of
    them would still pass if the split had collapsed to "nothing is ever
    readable". This one proves the same wiring still reports a real
    violation from a bundle it CAN read.
    """
    root = _claude_root(tmp_path=tmp_path, plugin={"name": "wrong", "description": "d"})
    log = plugin_structure.structlog.get_logger("t")
    assert plugin_structure.run_check(root=root, log=log) == 1
    captured = capsys.readouterr()
    assert "plugin-structure violation" in captured.out + captured.err


def test_the_failure_reason_names_the_file_and_the_cause(*, tmp_path: Path) -> None:
    """The rendered line is what an operator acts on, so it is asserted."""
    (tmp_path / "hooks.json").mkdir()
    outcome = read_profile_text(path=tmp_path / "hooks.json", root=tmp_path)
    assert isinstance(outcome, IOFailure)
    reason = unsafe_perform_io(outcome.failure()).reason
    assert "hooks.json" in reason
    assert "could not be read" in reason


def test_an_absent_codex_marketplace_is_a_violation(*, tmp_path: Path) -> None:
    """Absence at the catalog, which also short-circuits the description compare."""
    (tmp_path / ".agents" / "plugins").mkdir(parents=True)
    outcome = codex_profile_violations(root=tmp_path)
    assert isinstance(outcome, IOSuccess)
    assert any("marketplace.json absent" in v for v in unsafe_perform_io(outcome.unwrap()))


def test_an_absent_codex_manifest_is_a_violation(*, tmp_path: Path) -> None:
    root = _codex_root(tmp_path=tmp_path)
    (root / "livespec" / ".codex-plugin" / "plugin.json").unlink()
    outcome = codex_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess)
    assert any("plugin.json absent" in v for v in unsafe_perform_io(outcome.unwrap()))


def test_a_codex_skill_md_that_vanished_after_globbing_is_reported_absent(
    *, tmp_path: Path
) -> None:
    """The codex binding-body reader's own absence arm."""
    from livespec_dev_tooling.driver_checks._plugin_structure_codex import (
        _codex_binding_body_violations,
    )

    outcome = _codex_binding_body_violations(skill_md=tmp_path / "gone" / "SKILL.md", root=tmp_path)
    assert isinstance(outcome, IOSuccess)
    assert any("absent" in v for v in unsafe_perform_io(outcome.unwrap()))
