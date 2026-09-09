"""Mirror-paired test for `livespec_dev_tooling/checks/_primary_checkout_worktree_pack.py`.

The arm's INSPECTION behaviour is exercised outside-in through the parent
check's subprocess contract in
`test_primary_checkout_commit_refuse_hook_installed.py`, and directly against
the installer's enumeration in `tests/livespec_dev_tooling/
test_install_worktree_pack.py`. THIS file unit-tests the one part of the arm
neither of those reads: the REMEDY COMPOSER, `pack_failure_hint`.

The composer used to be a lookup returning one fixed sentence for the three
pack modes, and that sentence named `just bootstrap` first because the
standalone `install-worktree-pack` recipe exists only in repos already wired
for it. In a linked worktree of a WIRED repo — which is what every observed
occurrence was — that sends the reader through the entire local first-touch
reconcile (mise, uv sync, four plugin install-and-update rounds, beads
hardening, hooks) to reach one installer invocation. Two livespec sessions
paid it on 2026-09-06 and then re-ran the whole aggregate.

So the composer now READS the checkout, and both branches are pinned here:
a justfile that DEFINES the recipe names it first, and one that only mentions
it in prose — like a checkout carrying no justfile at all — keeps the
`just bootstrap` text with its UNWIRED repair steps. The fallback DIRECTION is
the safety property: `bootstrap` reaches the installer in a wired repo and in
an unwired one, the standalone recipe only in a wired one, so an ABSENT
justfile — which is definitively unwired — lands on `bootstrap`.

READING THE CHECKOUT IS WHAT MAKES THE COMPOSER NON-TOTAL, and it now says so
(livespec-dev-tooling-qndn.11). A justfile that is THERE and refuses to be read
establishes neither branch, and it used to be spelled as the unwired branch —
the same value absence yields — so a route chosen on the strength of a file
nobody read was indistinguishable from one chosen on evidence. It is the
`IOResult` FAILURE track now, carrying the `CheckInputUnreadable` every other
read in this arm already uses. Nothing in this repo's aggregate would notice
that sliding back: `checks/public_api_result_typed` is the check that reads the
return annotation and it is a no-op here (`pure_trees` is `not_applicable`), so
the assertion below applies that check's own terminal-name rule directly.

THE CONSUMER IS PINNED HERE TOO, because a failure track no caller consumes is
a defect wearing a railway. `_primary_checkout_narration._pack_hint` takes it,
and what it must NOT do is drop the pack finding: the drift, the absent
sibling, the missing pack were all OBSERVED, and only the remedy's first named
command rested on the unread justfile. So the finding still narrates, with the
route claim degraded to the text that is true either way.
"""

from __future__ import annotations

import ast
import errno
from pathlib import Path

import pytest
from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._primary_checkout_narration import _pack_hint
from livespec_dev_tooling.checks._primary_checkout_worktree_pack import (
    WORKTREE_PACK_UNWIRED_REMEDY,
    pack_failure_hint,
)

__all__: list[str] = []

_ARM_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_primary_checkout_worktree_pack.py"
)

# The two names `checks/public_api_result_typed` accepts as railway-typed.
# Restated here rather than imported so this file pins the PROPERTY that check
# reads, independently of the check's own shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})


# The two failure modes the acceptance criteria name explicitly, plus the
# third that shares their remedy — all three say "the pack on disk is not the
# pack the installer writes", so all three route to the composed text.
_PACK_MODES: tuple[str, ...] = (
    "worktree_pack_absent",
    "worktree_pack_file_missing",
    "worktree_pack_body_mismatch",
)

# A WIRED root justfile: it DEFINES the recipe. The leading comment names the
# recipe in prose as this repo's own justfile does three times over, so a
# composer keying on a bare substring would read the unwired fixture below as
# wired and this pair of tests could not tell the branches apart.
_WIRED_JUSTFILE = """\
# Install the pack: `just install-worktree-pack` is the standalone repair path.
import? 'dev-tooling/worktree.just'

install-worktree-pack:
    uv run python -m livespec_dev_tooling.install_worktree_pack
"""

# An UNWIRED root justfile: it mentions `just install-worktree-pack` in prose
# and defines no such recipe. This is the state the original remedy text was
# written for — 5 of 9 fleet repos when the pack arm landed.
_UNWIRED_JUSTFILE = """\
# The pack is reached through `just bootstrap`; there is no standalone
# `just install-worktree-pack` recipe in this repo.
import? 'dev-tooling/worktree.just'
"""

_STANDALONE_RECIPE = "`just install-worktree-pack`"
_BOOTSTRAP = "`just bootstrap`"


def _write_justfile(*, repo_root: Path, body: str) -> None:
    """Write `<repo_root>/justfile` verbatim."""
    _ = (repo_root / "justfile").write_text(body, encoding="utf-8")


def _composed_hint(*, failure_mode: str, repo_root: Path) -> str:
    """The remedy off the composer's SUCCESS track, asserting it is a railway value.

    Every branch-content test below reads its hint through here, so the return
    SHAPE is asserted by each of them rather than only by the annotation test:
    a composer handing back a bare `str` again fails at the `isinstance` rather
    than at a string comparison whose message would name the wrong defect.
    """
    composed = pack_failure_hint(failure_mode=failure_mode, repo_root=repo_root)
    assert isinstance(composed, IOResult), composed
    return unsafe_perform_io(composed.unwrap())


def _terminal_return_name(*, rendered: str) -> str:
    """`IOResult[str, CheckInputUnreadable]` → `IOResult`.

    Mirrors the reduction `public_api_result_typed` applies to a rendered
    return annotation before comparing it: drop the subscript, then drop any
    dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _assert_unwired_remedy(*, hint: str) -> None:
    """Assert `hint` is the UNWIRED text: `bootstrap` first, then the repair steps.

    The `just install-worktree-pack` COMMAND must be absent entirely — an
    unwired repo does not have it. The recipe NAME still appears, as the thing
    such a repo must add, which is why the order assertion cannot be written
    against the command string here the way the wired one is.
    """
    assert hint.startswith(f"run {_BOOTSTRAP}"), hint
    assert _STANDALONE_RECIPE not in hint, hint
    assert "UNWIRED" in hint, hint
    assert "`import?` lines" in hint, hint
    assert "`install-worktree-pack` recipe" in hint, hint


def _make_reads_fail(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every `Path.read_bytes` raise `OSError` for the rest of the test.

    ⛔ NOT `chmod 000`. This suite runs as ROOT, where a mode-based fixture is
    a lie — every read still succeeds and the test passes proving nothing.
    Patching the read itself is the only instrument that produces the negative.

    Unconditional rather than target-scoped (the shape
    `test_install_worktree_pack.py` uses for the INSPECTION arms) because the
    composer reads exactly one file: a passthrough arm here would be a branch
    no test can reach, and an unreachable arm in a fixture is how a fixture
    starts lying about what it patched.
    """

    def _read_bytes(self: Path) -> bytes:
        raise OSError(errno.EIO, f"read refused: {self}")

    monkeypatch.setattr(Path, "read_bytes", _read_bytes)


@pytest.mark.parametrize("failure_mode", _PACK_MODES)
def test_wired_checkout_names_the_standalone_recipe_first(
    *, tmp_path: Path, failure_mode: str
) -> None:
    """ACCEPTANCE 1. A checkout whose justfile DEFINES the recipe is told to run it.

    The assertion is on ORDER rather than on presence: the unwired text also
    ends by naming `install-worktree-pack` (as the thing an unwired repo must
    ADD), so "the remedy mentions the recipe" was already true and would pass
    against the unfixed composer. What the reader acts on is the FIRST command
    named, and that is what this pins.
    """
    _write_justfile(repo_root=tmp_path, body=_WIRED_JUSTFILE)

    hint = _composed_hint(failure_mode=failure_mode, repo_root=tmp_path)

    assert _STANDALONE_RECIPE in hint, hint
    assert hint.index(_STANDALONE_RECIPE) < hint.index(_BOOTSTRAP), hint


@pytest.mark.parametrize("failure_mode", _PACK_MODES)
def test_unwired_checkout_keeps_bootstrap_first_and_the_repair_steps(
    *, tmp_path: Path, failure_mode: str
) -> None:
    """ACCEPTANCE 2. A justfile that only MENTIONS the recipe is still unwired.

    Both halves matter. `bootstrap` must come first, because it is the only
    command that reaches the installer here; and the UNWIRED repair steps —
    the two `import?` lines and the recipe itself — must survive, because in
    this repo they are the actual fix and the composer is the only place the
    operator is told them.
    """
    _write_justfile(repo_root=tmp_path, body=_UNWIRED_JUSTFILE)

    hint = _composed_hint(failure_mode=failure_mode, repo_root=tmp_path)

    _assert_unwired_remedy(hint=hint)


def test_absent_justfile_falls_back_to_the_bootstrap_remedy(*, tmp_path: Path) -> None:
    """No justfile at all is an UNWIRED checkout, not an unanswerable question.

    `bootstrap` reaches the installer in a wired repo AND in an unwired one;
    the standalone recipe reaches it only in a wired one. So the fallback
    direction is the safe one, and a checkout carrying no justfile takes it.

    ⛔ AND IT IS THE SUCCESS TRACK, deliberately. A justfile that is not there
    ANSWERS the question the composer asks — such a checkout cannot define the
    standalone recipe — so absence must not be spelled as the unread justfile
    beside it, which answers nothing.
    """
    hint = _composed_hint(failure_mode="worktree_pack_absent", repo_root=tmp_path)

    _assert_unwired_remedy(hint=hint)


def test_an_unreadable_justfile_takes_the_failure_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route claim rests on a read, so a read that did not happen makes no claim.

    This state used to arrive at the unwired branch — the same value an ABSENT
    justfile yields — which made "this checkout has no standalone recipe" and
    "nobody could tell" the same sentence. The read still must not RAISE out of
    a narration path, and it does not: it answers with a failure the caller
    consumes, carrying the path and the OS diagnostic so the operator learns
    which file refused.
    """
    _write_justfile(repo_root=tmp_path, body=_WIRED_JUSTFILE)
    _make_reads_fail(monkeypatch=monkeypatch)

    composed = pack_failure_hint(failure_mode="worktree_pack_file_missing", repo_root=tmp_path)

    assert isinstance(composed, IOFailure), composed
    failure = unsafe_perform_io(composed.failure())
    assert failure.path == str(tmp_path / "justfile"), failure
    assert "read refused" in failure.detail, failure


def test_pack_failure_hint_declares_a_railway_return_annotation() -> None:
    """The SOURCE annotation is what the shipped detector reads.

    Asserted against the source rather than the runtime value because that is
    the surface `public_api_result_typed` judges — an annotation reverted to a
    bare `str` while the body still happened to return a container would
    satisfy a runtime check and fail the real one.
    """
    functions = {
        node.name: node
        for node in ast.parse(_ARM_PATH.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
    }
    annotation = functions["pack_failure_hint"].returns
    assert annotation is not None
    rendered = ast.unparse(annotation)
    assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, rendered


def test_the_narration_degrades_the_route_claim_rather_than_dropping_the_finding(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The consumer keeps narrating the pack failure it OBSERVED.

    `_pack_hint` is where the check consumes this composer's failure track, and
    the shape of that consumption is the whole safety of putting the composer on
    a railway at all: the pack failure being narrated was observed from bytes on
    disk, and only the remedy's FIRST NAMED COMMAND rested on the justfile read.
    Forwarding the failure would convert a reported violation into a check that
    could not answer and drop the finding entirely.

    So the finding stands, and the degradation is STATED: the hint names the
    path that refused to be read and then gives the `bootstrap` text, which is
    correct in a wired checkout and in an unwired one.
    """
    _write_justfile(repo_root=tmp_path, body=_WIRED_JUSTFILE)
    _make_reads_fail(monkeypatch=monkeypatch)

    hint = _pack_hint(failure_mode="worktree_pack_body_mismatch", repo_root=tmp_path)

    assert "could NOT be established" in hint, hint
    assert str(tmp_path / "justfile") in hint, hint
    assert hint.endswith(WORKTREE_PACK_UNWIRED_REMEDY), hint
    assert _STANDALONE_RECIPE not in hint, hint


@pytest.mark.parametrize(
    ("failure_mode", "expected_fragment"),
    [
        ("worktree_pack_not_imported", "add the missing optional import"),
        ("worktree_discipline_malformed", "`worktree_discipline` block"),
    ],
)
def test_the_separately_routed_modes_ignore_the_wiring(
    *, tmp_path: Path, failure_mode: str, expected_fragment: str
) -> None:
    """The two non-pack modes keep their own remedies in a WIRED checkout.

    They are actionable in the root justfile and in `.livespec.jsonc`
    respectively; reinstalling the pack fixes neither, so the wiring branch
    must not reach them.
    """
    _write_justfile(repo_root=tmp_path, body=_WIRED_JUSTFILE)

    hint = _composed_hint(failure_mode=failure_mode, repo_root=tmp_path)

    assert expected_fragment in hint, hint
    assert _STANDALONE_RECIPE not in hint, hint
