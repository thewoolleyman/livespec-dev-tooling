"""Both sides of the gate-context disposition, in the two checks that carry it.

R4.S6 (livespec-dev-tooling-ul61). The unit tests in `test_gate_context.py` prove
the predicate; these prove the two targets actually CONSULT it, which is the part
that could silently regress if a future edit drops the call.

Outside a gate both checks keep the warn-and-pass behaviour a contributor without
a forge token depends on. Inside a gate both refuse to report a pass they did not
earn.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.checks import branch_protection_alignment, master_ci_green
from livespec_dev_tooling.checks._gate_context import GATE_CONTEXT_ENV

if TYPE_CHECKING:
    import pytest


def _failed_read(*, stderr: str) -> GhRead:
    """One budgeted read that came back non-zero, carrying `stderr`.

    The seam these tests stub is `master_ci_green.gh_read`, the budgeted
    boundary the check now reads GitHub through (livespec-dev-tooling-z69s);
    before the retrofit it was `master_ci_green.subprocess.run`. Same shape,
    same three fields, so the dispositions below are unchanged.
    """
    return GhRead(returncode=1, stdout="", stderr=stderr)


def _unreadable_master_ci(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `gh api` call that fails because no credential is stored.

    Driven through `main()` rather than the private classifier: the exit code is
    the contract a gate actually observes, and a test that reaches past it would
    keep passing if the classifier stopped being consulted.
    """
    monkeypatch.setattr(master_ci_green, "_gh_has_stored_credential", lambda: False)
    monkeypatch.setattr(master_ci_green, "gh_read", lambda **_kwargs: _failed_read(stderr=""))


def test_master_ci_green_passes_without_a_credential_outside_a_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The developer-laptop case: warn and exit 0, exactly as before."""
    monkeypatch.delenv(GATE_CONTEXT_ENV, raising=False)
    _unreadable_master_ci(monkeypatch=monkeypatch)
    assert master_ci_green.main() == 0


def test_master_ci_green_fails_without_a_credential_inside_a_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: the tree is not called green by a run that never looked."""
    monkeypatch.setenv(GATE_CONTEXT_ENV, "1")
    _unreadable_master_ci(monkeypatch=monkeypatch)
    assert master_ci_green.main() == 1


def test_master_ci_green_fails_on_a_rejected_credential_inside_a_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential that exists but is refused is no better than none, in a gate."""
    monkeypatch.setenv(GATE_CONTEXT_ENV, "1")
    monkeypatch.setattr(master_ci_green, "_gh_has_stored_credential", lambda: True)
    monkeypatch.setattr(
        master_ci_green,
        "_gh_failed_due_to_invalid_credential",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        master_ci_green, "gh_read", lambda **_kwargs: _failed_read(stderr="HTTP 401")
    )
    assert master_ci_green.main() == 1


def _stage_unreadable_protection(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A repo whose ci.yml parses fine but whose protection state cannot be read.

    `monkeypatch.chdir` is required, not incidental: `main()` resolves ci.yml
    against `Path.cwd()`, so without it the test reads THIS repository's own
    workflow and its verdict would depend on the tree it runs in.
    """
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("on: push\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        branch_protection_alignment, "_fetch_required_contexts", lambda **_kwargs: None
    )
    monkeypatch.setattr(branch_protection_alignment, "parse_ci_matrix", lambda **_kwargs: ["x"])
    monkeypatch.setattr(
        branch_protection_alignment, "parse_top_level_jobs", lambda **_kwargs: ["x"]
    )


def test_branch_protection_exits_zero_when_it_cannot_read_outside_a_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The developer-laptop case: an unreadable protection state is not a failure."""
    monkeypatch.delenv(GATE_CONTEXT_ENV, raising=False)
    _stage_unreadable_protection(monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert branch_protection_alignment.main() == 0


def test_branch_protection_fails_when_it_cannot_read_inside_a_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The whole point: no pass reported from a gate that never read protection."""
    monkeypatch.setenv(GATE_CONTEXT_ENV, "1")
    _stage_unreadable_protection(monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert branch_protection_alignment.main() == 1
