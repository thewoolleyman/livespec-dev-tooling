"""A push refused for host authority leaves no green token behind.

Measured 2026-11-17 (livespec-orchestrator-git-jsonl#1225, work item
livespec-dev-tooling-d2fm3g): a push refused for host authority still had its
green Job write the token, and the next push of the same tree matched it and
skipped the full aggregate, a workflow-edit check included. The authority half
runs BEFORE the Job, so the client knows the refusal when the Job turns green and
must not write the token; the retry then runs every member.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling._gate_host_authority import GATE_HOST_AUTHORITY_REFUSED
from tests.livespec_dev_tooling import test_gate_remote_delegate as world

# The sibling module's canned cluster is shared rather than copied: one fake of
# the delegated push, so the two files cannot drift on what a push issues.
_StubWorld = world._StubWorld  # noqa: SLF001
_verdict_line = world._verdict_line  # noqa: SLF001
_AUTHORITY_MEMBER = world._AUTHORITY_MEMBER  # noqa: SLF001
_JOB_COMPLETE_TIMED = world._JOB_COMPLETE_TIMED  # noqa: SLF001


def test_a_refused_host_authority_member_leaves_no_green_token_behind(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    _ = (repo_root / "check-targets.txt").write_text(
        "# Canonical check inventory for `just check`.\n"
        f"{_AUTHORITY_MEMBER}  # purity: world-reading  # authority: ledger\n",
        encoding="utf-8",
    )
    runner = _StubWorld(terminal=_JOB_COMPLETE_TIMED, refuse=("authority-member",))

    status, refused = _verdict_line(
        repo_root=repo_root, runner=runner, monkeypatch=monkeypatch, capsys=capsys
    )

    token_writes = [argv for argv in runner.argvs if "livespec_dev_tooling.green_token" in argv]
    assert all(
        [status == 1, refused.get("state") == GATE_HOST_AUTHORITY_REFUSED, token_writes == []]
    )
