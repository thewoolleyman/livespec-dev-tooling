"""Every remaining "the invocation did not happen" arm of the local seam.

The sibling `test_local_command_invocation_railway.py` pins the seam
itself plus the two rows whose collapse motivated the conversion. This
file exists because EVERY converted call site adds a branch no existing
test reaches: the canned tables the row suites already carry are all in
the SUCCESS vocabulary — a command that ran and answered — which is what
those rows are about, so none of them can reach a failure-track arm.

⛔ That is not an accident of these fixtures, it is the shape of the
seam: `fleet/CLAUDE.md` mandates hermetic testing through a canned
runner, so the suite's every existing fake is a program that RAN. A
conversion here therefore lands its uncovered lines in a place the
existing suite structurally cannot reach, and the `*_edges.py` sibling is
not optional.

`local_reconcile.main()` is driven IN-PROCESS (`monkeypatch.setattr` on
`sys.argv` and on the module's runner) rather than spawned, because
`check-tests-no-subprocess-spawn` rejects a spawning edges test.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOResult, IOSuccess

from livespec_dev_tooling.fleet import local_reconcile
from livespec_dev_tooling.fleet._context import RowFinding
from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import CommandResult, LocalContext
from livespec_dev_tooling.fleet._rows_local import (
    assert_commit_refuse_hooks,
    assert_worktree_root_trust,
    reconcile_codex_plugins,
    reconcile_uv_sync,
    reconcile_worktree_pack,
)
from livespec_dev_tooling.fleet._rows_local_beads import (
    reconcile_beads_bd_binary,
    reconcile_beads_config_committed,
    reconcile_beads_dolt_server,
    reconcile_beads_tenant_secret,
)
from livespec_dev_tooling.fleet.local_reconcile import (
    _resolve_checkout_root,
    _resolve_invoked_worktree,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

__all__: list[str] = []


def _nothing_runs(
    *, args: list[str], cwd: Path | None = None
) -> IOResult[CommandResult, InvocationNotPerformed]:
    """A runner reporting every invocation as never performed."""
    del cwd
    return IOFailure(
        InvocationNotPerformed(
            argv=tuple(args), kind=BINARY_ABSENT, detail=f"{args[0]} not on PATH"
        )
    )


def _ctx(*, checkout: Path) -> LocalContext:
    """A `LocalContext` whose every command fails to be invoked at all."""
    return LocalContext(checkout=checkout, home=checkout / "home", run=_nothing_runs)


def test_uv_sync_reports_the_seam_reason_rather_than_its_own_note(*, tmp_path: Path) -> None:
    """`_failed`'s two arms render DIFFERENTLY — this is the not-performed one.

    "uv sync failed" would be a claim about an operation the host never
    attempted. The finding names the uninvokable program instead.
    """
    outcome = reconcile_uv_sync(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "uv" in outcome.message
    assert "uv sync failed" not in outcome.message


def test_worktree_pack_install_that_never_ran_is_a_finding(*, tmp_path: Path) -> None:
    outcome = reconcile_worktree_pack(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "uv" in outcome.message


def test_commit_refuse_hook_verifier_that_never_ran_is_not_absence(*, tmp_path: Path) -> None:
    """A verifier that never ran is not a verifier reporting the hooks absent."""
    outcome = assert_commit_refuse_hooks(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "absent or non-canonical" not in outcome.message


def test_worktree_root_trust_that_never_read_settings_is_not_absence(*, tmp_path: Path) -> None:
    """Unread mise settings are not settings that omit the worktree root."""
    outcome = assert_worktree_root_trust(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "absent from mise trusted_config_paths" not in outcome.message


def test_uninvokable_just_does_not_declare_an_absent_codex_surface(*, tmp_path: Path) -> None:
    """The Codex half of the `_recipe_present` collapse the sibling pins for Claude."""
    outcome = reconcile_codex_plugins(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "just" in outcome.message


def _beads_ctx(*, checkout: Path) -> LocalContext:
    """A beads-applicable checkout whose probes cannot be invoked."""
    (checkout / ".beads").mkdir()
    return _ctx(checkout=checkout)


def test_bd_binary_probe_that_never_ran_is_unprobed_not_unmet(*, tmp_path: Path) -> None:
    """An unrunnable probe measured nothing, so the prerequisite is neither met nor unmet.

    The guided TODO the unmet-prerequisite finding carries would be wrong
    advice here: it tells the operator to install `bd`, when what actually
    happened is that the probe itself never ran.
    """
    outcome = reconcile_beads_bd_binary(ctx=_beads_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "UNPROBED" in outcome.message
    assert "LIVESPEC_BD_PATH" not in outcome.message


def test_dolt_server_probe_that_never_ran_is_unprobed(*, tmp_path: Path) -> None:
    outcome = reconcile_beads_dolt_server(ctx=_beads_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "UNPROBED" in outcome.message


def test_tenant_secret_probe_that_never_ran_is_unprobed(*, tmp_path: Path) -> None:
    """Still probe-ONLY: the failure carries argv, and argv never holds the value."""
    outcome = reconcile_beads_tenant_secret(ctx=_beads_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "UNPROBED" in outcome.message


def test_config_committed_probe_that_never_ran_is_unprobed(*, tmp_path: Path) -> None:
    outcome = reconcile_beads_config_committed(ctx=_beads_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "UNPROBED" in outcome.message


def test_resolve_checkout_root_separates_never_ran_from_not_a_checkout(*, tmp_path: Path) -> None:
    """The third answer: `None` means git said no, not that git never spoke."""
    resolved = _resolve_checkout_root(target=tmp_path, run=_nothing_runs)
    assert isinstance(resolved, InvocationNotPerformed)


def test_resolve_invoked_worktree_is_exercised_at_its_own_seam(*, tmp_path: Path) -> None:
    """UNREACHABLE through `main()`, so it is driven directly.

    `main()` resolves the checkout root FIRST and bails when that fails,
    so by the time this runs `git` is known invocable. A test driving the
    composed entry point would look thorough and leave this line uncovered
    forever — the `walk_github_workflow_container_image` finding.
    """
    assert _resolve_invoked_worktree(target=tmp_path, run=_nothing_runs) is None


def test_main_reports_an_uninvokable_git_rather_than_a_bad_target(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` used to advise `--checkout` for a host that simply has no `git`."""
    monkeypatch.setattr(sys, "argv", ["local-reconcile", "--checkout", str(tmp_path)])
    monkeypatch.setattr(local_reconcile, "default_command_runner", _nothing_runs)
    assert local_reconcile.main() == 1
    stderr = capsys.readouterr().err
    assert "git could not be invoked" in stderr
    assert "target is not a git checkout" not in stderr


def test_a_worktree_that_resolves_still_reaches_the_rows(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control for the fixtures above.

    Every other test here asserts a failure, so all of them would still
    pass if the seam had collapsed to "nothing ever runs". This one proves
    the same wiring reports success when the invocations DO happen.
    """
    import sys

    def runs(
        *, args: list[str], cwd: Path | None = None
    ) -> IOResult[CommandResult, InvocationNotPerformed]:
        del cwd
        stdout = ".git\n" if args[:3] == ["git", "rev-parse", "--git-common-dir"] else ""
        return IOSuccess(CommandResult(returncode=0, stdout=stdout, stderr=""))

    monkeypatch.setattr(sys, "argv", ["local-reconcile", "--checkout", str(tmp_path)])
    monkeypatch.setattr(local_reconcile, "default_command_runner", runs)
    assert local_reconcile.main() == 0
