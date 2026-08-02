"""Tests for `livespec_dev_tooling/fleet/_rows_local_beads.py`.

Each beads-runtime probe is exercised across its three branches — no `.beads/`
directory (skip), prerequisite present (pass), prerequisite absent (a
WARNING-severity guided finding) — through a canned-response command runner and a
real `tmp_path` checkout. No host mutation, no real subprocess, and (the
probe-only discipline) no secret value is ever read or asserted on.
"""

from __future__ import annotations

from pathlib import Path

from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet._context import (
    EXCLUDED_NOTE_PREFIX,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._local_context import (
    FILE_UNREADABLE,
    CommandOutcome,
    CommandResult,
    FileNotRead,
    LocalContext,
    PathKindOutcome,
)
from livespec_dev_tooling.fleet._rows_local_beads import (
    DOLT_SERVER_HOST,
    DOLT_SERVER_PORT,
    reconcile_beads_bd_binary,
    reconcile_beads_config_committed,
    reconcile_beads_dolt_server,
    reconcile_beads_metadata_present,
    reconcile_beads_tenant_secret,
)

__all__: list[str] = []

_OK = CommandResult(returncode=0, stdout="", stderr="")
_FAIL = CommandResult(returncode=1, stdout="", stderr="x")

_BD_PROBE = (
    "bash",
    "-c",
    'if test -n "${LIVESPEC_BD_PATH:-}"; then '
    'test -x "$LIVESPEC_BD_PATH"; '
    'else bd_path="$(command -v bd 2>/dev/null)" && '
    'test -n "$bd_path" && test -x "$bd_path"; fi',
)
_DOLT_PROBE = (
    "timeout",
    "2",
    "bash",
    "-c",
    f"exec 3<>/dev/tcp/{DOLT_SERVER_HOST}/{DOLT_SERVER_PORT}",
)
_SECRET_PROBE = ("bash", "-c", 'test -n "${BEADS_DOLT_PASSWORD:-}"')
_CONFIG_PROBE = ("git", "ls-files", "--error-unmatch", ".beads/config.yaml")


def _ctx(
    *, checkout: Path, table: dict[tuple[str, ...], CommandResult] | None = None
) -> LocalContext:
    """A `LocalContext` over a canned runner keyed on the full args tuple (default OK)."""
    lookup = table or {}

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        return IOSuccess(lookup.get(tuple(args), _OK))

    return LocalContext(checkout=checkout, home=checkout / "home", run=run)


def _with_beads(*, tmp_path: Path) -> Path:
    """Create a `.beads/` tenant directory so the runtime rows apply."""
    (tmp_path / ".beads").mkdir()
    return tmp_path


def test_dolt_server_constants_force_tcp() -> None:
    assert (DOLT_SERVER_HOST, DOLT_SERVER_PORT) == ("127.0.0.1", 3307)


def test_bd_binary_is_excluded_without_beads(*, tmp_path: Path) -> None:
    """Not a beads-backed repo is INAPPLICABLE, not unevaluable."""
    outcome = reconcile_beads_bd_binary(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_bd_binary_passes_when_present(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_bd_binary(ctx=ctx), RowPass)


def test_bd_binary_absent_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_BD_PROBE: _FAIL})
    outcome = reconcile_beads_bd_binary(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "LIVESPEC_BD_PATH" in outcome.message
    assert "`bd` on PATH" in outcome.message


def test_dolt_server_is_excluded_without_beads(*, tmp_path: Path) -> None:
    """Not a beads-backed repo is INAPPLICABLE, not unevaluable."""
    outcome = reconcile_beads_dolt_server(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_dolt_server_passes_when_reachable(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_dolt_server(ctx=ctx), RowPass)


def test_dolt_server_unreachable_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_DOLT_PROBE: _FAIL})
    outcome = reconcile_beads_dolt_server(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "3307" in outcome.message


def test_tenant_secret_is_excluded_without_beads(*, tmp_path: Path) -> None:
    """Not a beads-backed repo is INAPPLICABLE, not unevaluable."""
    outcome = reconcile_beads_tenant_secret(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_tenant_secret_passes_when_present(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_tenant_secret(ctx=ctx), RowPass)


def test_tenant_secret_absent_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_SECRET_PROBE: _FAIL})
    outcome = reconcile_beads_tenant_secret(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "BEADS_DOLT_PASSWORD" in outcome.message


def test_config_committed_is_excluded_without_beads(*, tmp_path: Path) -> None:
    """Not a beads-backed repo is INAPPLICABLE, not unevaluable."""
    outcome = reconcile_beads_config_committed(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_config_committed_passes_when_tracked(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_config_committed(ctx=ctx), RowPass)


def test_config_committed_untracked_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_CONFIG_PROBE: _FAIL})
    outcome = reconcile_beads_config_committed(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert ".beads/config.yaml" in outcome.message


def test_metadata_is_excluded_without_beads(*, tmp_path: Path) -> None:
    """Not a beads-backed repo is INAPPLICABLE, not unevaluable."""
    outcome = reconcile_beads_metadata_present(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_metadata_passes_when_present(*, tmp_path: Path) -> None:
    beads = _with_beads(tmp_path=tmp_path)
    (beads / ".beads" / "metadata.json").write_text("{}", encoding="utf-8")
    assert isinstance(reconcile_beads_metadata_present(ctx=_ctx(checkout=beads)), RowPass)


def test_metadata_absent_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    outcome = reconcile_beads_metadata_present(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "metadata.json" in outcome.message


# A checkout whose own path carries a 300-character component. Every `stat` under
# it raises `ENAMETOOLONG`, which is how unstattability is spelled in a suite that
# runs as ROOT — a `chmod 000` would not raise here. The PRODUCTION case is
# `EACCES` under an unreadable parent, which `pathlib` likewise does not ignore,
# so the same arm carries both. ⛔ AND THIS FLEET MANUFACTURES THAT CASE ITSELF:
# `reconcile_beads_dir_perms` chmods `.beads` to 700, so a non-owner process
# raises on everything inside it.
def _unstattable_checkout(*, tmp_path: Path) -> Path:
    return tmp_path / ("x" * 300)


def test_metadata_probe_is_not_evaluable_rather_than_crashing(*, tmp_path: Path) -> None:
    """⛔ THE CRASH, AS A TEST. Before the predicate seam this RAISED, uncaught.

    `is_file()` propagates `EACCES` (and here `ENAMETOOLONG`) because `pathlib`
    ignores only `(ENOENT, ENOTDIR, EBADF, ELOOP)`. The row had no `except`
    anywhere, so the exception left the row and aborted the whole local
    reconcile partway through — the `livespec-dev-tooling-a6et` shape.

    `RowSkip` is the ratified meaning of this state, not a workaround: "the row
    could not be definitively evaluated (can't-read is not absent)". Reporting
    it as ABSENT — which is what an unguarded probe would do if the primitive
    returned False rather than raising — would tell the operator to regenerate a
    file that may well be there.
    """
    ctx = _ctx(checkout=_unstattable_checkout(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_metadata_present(ctx=ctx), RowSkip)


def test_every_beads_row_skips_rather_than_crashing_on_an_unstattable_checkout(
    *, tmp_path: Path
) -> None:
    """⛔ THE APPLICABILITY GATE IS THE SHARED CAUSE, so all five rows are asserted.

    `_beads_applicable` called `Path.is_dir()` directly and EVERY beads row calls
    it first. Fixing only the row whose own primitive was named in the offender
    list would have moved the count while leaving the crash live in all five —
    the "fix looks done while changing nothing" shape, arriving one level up the
    call chain. Grep the whole CHAIN, not just the function the report names.
    """
    ctx = _ctx(checkout=_unstattable_checkout(tmp_path=tmp_path))
    rows = (
        reconcile_beads_bd_binary,
        reconcile_beads_config_committed,
        reconcile_beads_dolt_server,
        reconcile_beads_metadata_present,
        reconcile_beads_tenant_secret,
    )
    skipped = [row.__name__ for row in rows if isinstance(row(ctx=ctx), RowSkip)]
    assert skipped == [row.__name__ for row in rows], "every beads row must skip, not raise"


def test_an_absent_beads_directory_is_still_excluded_not_skipped(*, tmp_path: Path) -> None:
    """THE NEGATIVE CONTROL, and it is what keeps the fix from over-reaching.

    A repo that is simply not beads-backed must stay INAPPLICABLE — an excluded
    pass, not a skip. A seam that turned every awkward path into unevaluable
    would make every clean non-beads repo report can't-read, and the suite would
    still be green on the crash tests above.
    """
    outcome = reconcile_beads_metadata_present(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


class _FileProbeRefused(LocalContext):
    """A context whose DIRECTORY predicate answers but whose FILE predicate fails.

    The row has TWO probes and they fail independently: the applicability gate
    (`.beads` itself) and the metadata probe. A checkout that is unstattable
    outright fails the FIRST and returns, so the second arm is never reached —
    which is exactly how it would go untested while looking covered. This double
    isolates the row's OWN probe failure from its gate's.
    """

    def file_present(self, *, path: Path) -> PathKindOutcome:
        return IOFailure(FileNotRead(path=path, kind=FILE_UNREADABLE, detail="probe refused"))


def test_the_metadata_probes_own_failure_is_a_skip_not_an_absence(*, tmp_path: Path) -> None:
    """The row's SECOND probe fails while the applicability gate succeeds.

    Without this the row's own failure arm is unreached — the gate short-circuits
    every unstattable checkout — and an untested arm that renders the WRONG
    variant would ship telling the operator to regenerate a file that is there.
    """
    checkout = _with_beads(tmp_path=tmp_path)
    ctx = _FileProbeRefused(
        checkout=checkout, home=checkout / "home", run=_ctx(checkout=checkout).run
    )
    assert isinstance(reconcile_beads_metadata_present(ctx=ctx), RowSkip)
