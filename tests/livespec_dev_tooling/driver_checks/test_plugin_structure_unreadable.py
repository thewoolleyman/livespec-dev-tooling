"""A profile the check could not READ is not a profile that VIOLATES.

`livespec-dev-tooling-8o8e` rows 25-27. Both Driver profiles caught
`(OSError, ValueError)` around every manifest read and returned the
exception AS A VIOLATION STRING — so "this Driver's plugin.json is
malformed", a definitive property of committed bytes an author must fix,
and "this run could not read plugin.json", which says nothing about the
Driver at all, arrived at the operator as the same sentence and the same
non-zero exit.

That is `livespec-dev-tooling-6ge`'s rule at a third surface: A CAN'T-READ
IS NOT A VIOLATION. v039 already ratified the split for pin currency — a
can't-READ skips, a can't-PARSE is a finding — and these two profiles are
the same shape with the two arms fused.

⛔ AND THE CONVERSE IS LOAD-BEARING, which is why
`test_an_absent_manifest_is_still_a_violation` is here rather than
implied. An ABSENT manifest IS definitive: the Driver genuinely does not
ship one, and a conversion that swept `FileNotFoundError` onto the failure
track alongside its `OSError` siblings would turn a real violation into a
silent non-answer — loosening the check while appearing to sharpen it.
`FileNotFoundError` is an `OSError`, so the split has to be deliberate.

⚠️ NO `chmod 000` ANYWHERE HERE: the suite runs as root, where every read
succeeds and such a fixture asserts nothing. Unreadability is spelled as a
DIRECTORY where a file is expected, which raises `IsADirectoryError` (an
`OSError` that is NOT `FileNotFoundError`) identically for every user.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.driver_checks._plugin_structure_claude import (
    claude_profile_violations,
    fenced_invocation_violations,
)
from livespec_dev_tooling.driver_checks._plugin_structure_codex import (
    codex_profile_violations,
)
from livespec_dev_tooling.driver_checks._profile_read_failure import ProfileUnreadable

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


def _claude_root(*, tmp_path: Path) -> Path:
    """A `.claude-plugin/` tree carrying a well-formed manifest pair."""
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "livespec", "description": "d"}), encoding="utf-8"
    )
    _ = (plugin_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "livespec-driver-claude",
                "plugins": [{"name": "livespec", "source": "./.claude-plugin", "description": "d"}],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_an_unreadable_claude_manifest_is_a_failure_not_a_violation(*, tmp_path: Path) -> None:
    """ "could not read plugin.json" is not a statement about the Driver."""
    root = _claude_root(tmp_path=tmp_path)
    (root / ".claude-plugin" / "plugin.json").unlink()
    (root / ".claude-plugin" / "plugin.json").mkdir()
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert isinstance(failure, ProfileUnreadable)
    assert "plugin.json" in failure.path


def test_an_absent_manifest_is_still_a_violation(*, tmp_path: Path) -> None:
    """THE CONVERSE, and it is what keeps the split from loosening the check.

    `FileNotFoundError` is an `OSError`. Sweeping it onto the failure track
    with its siblings would convert a real, definitive violation — this
    Driver ships no marketplace.json — into a non-answer.
    """
    root = _claude_root(tmp_path=tmp_path)
    (root / ".claude-plugin" / "marketplace.json").unlink()
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess)
    violations = unsafe_perform_io(outcome.unwrap())
    assert any("marketplace.json" in v for v in violations)


def test_an_invalid_manifest_is_still_a_violation(*, tmp_path: Path) -> None:
    """Malformed committed bytes are definitive and reproducible — a finding."""
    root = _claude_root(tmp_path=tmp_path)
    _ = (root / ".claude-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")
    outcome = claude_profile_violations(root=root)
    assert isinstance(outcome, IOSuccess)
    violations = unsafe_perform_io(outcome.unwrap())
    assert any("plugin.json" in v for v in violations)


def test_an_unreadable_skill_md_is_a_failure_rather_than_a_raise(*, tmp_path: Path) -> None:
    """`fenced_invocation_violations` read its input with no guard at all.

    Shared byte-for-byte by both profiles, so this raise reached the
    operator as a traceback from either one.
    """
    skill_md = tmp_path / "SKILL.md"
    skill_md.mkdir()
    outcome = fenced_invocation_violations(skill_md=skill_md, root=tmp_path)
    assert isinstance(outcome, IOFailure)
    assert "SKILL.md" in unsafe_perform_io(outcome.failure()).path


def test_an_unreadable_codex_marketplace_is_a_failure_not_a_violation(*, tmp_path: Path) -> None:
    """The codex profile carries the same fused arms, so it moves in lockstep."""
    plugins_dir = tmp_path / ".agents" / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "marketplace.json").mkdir()
    outcome = codex_profile_violations(root=tmp_path)
    assert isinstance(outcome, IOFailure)
    assert "marketplace.json" in unsafe_perform_io(outcome.failure()).path
