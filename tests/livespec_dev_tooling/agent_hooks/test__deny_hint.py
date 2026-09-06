"""Tests for `livespec_dev_tooling/agent_hooks/_deny_hint.py`.

The venue-aware deny-hint composition moved out of
`pretooluse_background_guard.py` when the command-token-position fix
(livespec-dev-tooling-k169) carried that file into the 201-250 LLOC soft
band. The two concerns it had accreted cut apart cleanly: the hook
itself (protocol, deny decision, gate classification) and the
composition of the hint a deny hands back, whose probe constants and
clause text were the bulk of the file. This module pins that cut; the
composed hint's BEHAVIOR is exercised through the importer, in
`test_pretooluse_background_guard.py`, per the package-private helper
convention (`tests_mirror_pairing` (a): a `_`-prefixed module is
exercised through the public function that imports it).

The module import is performed INSIDE the test body rather than at
module top. A top-level import would make the extraction's Red leg a
COLLECTION error, which proves only that the module is unimportable —
not that the code has yet to move.
"""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []

_PACKAGE = "livespec_dev_tooling.agent_hooks"
_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "agent_hooks"


def test_deny_hint_composition_lives_in_its_own_module(tmp_path: Path) -> None:
    """The hint concern is its own module, not a section of the hook module."""
    module_path = _PACKAGE_DIR / "_deny_hint.py"
    assert module_path.is_file()

    module = importlib.import_module(f"{_PACKAGE}._deny_hint")
    # `tmp_path` is outside any repository, so the pack cannot resolve
    # there and the one-line install command is named FIRST — the
    # venue-awareness the extracted module owns, still owned after the move.
    hint = module.deny_hint(cwd=tmp_path)
    assert "install_worktree_pack" in hint
    assert hint.index("install_worktree_pack") < hint.index("gate-start")

    guard_source = (_PACKAGE_DIR / "pretooluse_background_guard.py").read_text(encoding="utf-8")
    assert "def _hint(" not in guard_source
    assert "_HINT_PREAMBLE" not in guard_source
    assert f"from {_PACKAGE}._deny_hint import deny_hint" in guard_source
