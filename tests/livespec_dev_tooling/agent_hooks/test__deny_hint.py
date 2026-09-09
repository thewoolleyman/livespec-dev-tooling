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

It also pins the module's RETURN SHAPE (livespec-dev-tooling-qndn.10).
`deny_hint` composes its prescription by reading files in the venue, so
it is not total, and it now answers on the `IOResult` railway. Nothing
in this repo's aggregate would notice that sliding back:
`checks/public_api_result_typed` is the check that reads the return
annotation and it is a no-op here (`pure_trees` is `not_applicable`),
so the assertions below apply that check's own terminal-name rule
directly, and the failure track is exercised rather than left
uninhabited.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

__all__: list[str] = []

_PACKAGE = "livespec_dev_tooling.agent_hooks"
_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "agent_hooks"

# The two names `checks/public_api_result_typed` accepts as railway-typed.
# Restated here rather than imported so this file pins the PROPERTY that
# check reads, independently of the check's own shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})

# A pack fragment declaring both prescribed recipes, so the probe gets past
# the fragment read and on to the root justfile — the path the unreadable
# -venue test makes unreadable.
_FRAGMENT = "gate-start run_id:\n    @true\ngate-wait run_id:\n    @true\n"


def _terminal_return_name(*, rendered: str) -> str:
    """`IOResult[str, VenueUnreadable]` → `IOResult`.

    Mirrors the reduction `public_api_result_typed` applies to a rendered
    return annotation before comparing it: drop the subscript, then drop
    any dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def test_deny_hint_composition_lives_in_its_own_module(tmp_path: Path) -> None:
    """The hint concern is its own module, not a section of the hook module."""
    module_path = _PACKAGE_DIR / "_deny_hint.py"
    assert module_path.is_file()

    module = importlib.import_module(f"{_PACKAGE}._deny_hint")
    # `tmp_path` is outside any repository, so the pack cannot resolve
    # there and the one-line install command is named FIRST — the
    # venue-awareness the extracted module owns, still owned after the move.
    composed = module.deny_hint(cwd=tmp_path)
    assert isinstance(composed, IOResult)
    hint = unsafe_perform_io(composed.unwrap())
    assert "install_worktree_pack" in hint
    assert hint.index("install_worktree_pack") < hint.index("gate-start")

    guard_source = (_PACKAGE_DIR / "pretooluse_background_guard.py").read_text(encoding="utf-8")
    assert "def _hint(" not in guard_source
    assert "_HINT_PREAMBLE" not in guard_source
    assert f"from {_PACKAGE}._deny_hint import deny_hint" in guard_source


def test_deny_hint_declares_a_railway_return_annotation() -> None:
    """The SOURCE annotation is what the shipped detector reads.

    Asserted against the source rather than the runtime value because
    that is the surface `public_api_result_typed` judges — an annotation
    reverted to a bare `str` while the body still happened to return a
    container would satisfy a runtime check and fail the real one.
    """
    source = (_PACKAGE_DIR / "_deny_hint.py").read_text(encoding="utf-8")
    functions = {
        node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
    }
    annotation = functions["deny_hint"].returns
    assert annotation is not None
    rendered = ast.unparse(annotation)
    assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, rendered


def test_an_unreadable_venue_takes_the_failure_track_and_still_prescribes(tmp_path: Path) -> None:
    """A path that is THERE and unreadable establishes neither prescription arm.

    The distinction the railway buys: an ABSENT justfile is the probe's
    ordinary answer and stays on the success track, while one that cannot
    be read at all used to reach the same empty string — so the hint
    asserted "the runner is NOT installed in this working tree" on the
    strength of a file nobody read. The deny still stands and the remedy
    is still complete; only the claim about the venue changes.
    """
    module = importlib.import_module(f"{_PACKAGE}._deny_hint")
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    pack = root / "dev-tooling"
    pack.mkdir()
    _ = (pack / "worktree.just").write_text(_FRAGMENT, encoding="utf-8")
    _ = (pack / "gate-run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    # A justfile that is a DIRECTORY: present, and refusing to yield text.
    (root / "justfile").mkdir()

    composed = module.deny_hint(cwd=root)

    assert isinstance(composed, IOFailure)
    failure = unsafe_perform_io(composed.failure())
    assert failure.path == str(root / "justfile")
    hint = failure.hint
    assert "could NOT be established" in hint
    assert str(root / "justfile") in hint
    # And the remedy is still named, still ahead of the recipes it installs.
    assert hint.index("install_worktree_pack") < hint.index("gate-start")
