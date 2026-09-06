"""Tests for livespec_dev_tooling/check_failure_digest.py and its dispatcher wiring.

Work-item livespec-dev-tooling-b7dbne. The defect these tests pin is
PRESENTATION, not detection: the worktree-pack arm already emits a good
`worktree_pack_absent` finding carrying its own remedy, but the aggregate
buried it hundreds of lines up and the pre-push hook surfaced only a bare
`exit status 1` after 313s.

The dispatcher-tail test lives HERE rather than in
`test_parallel_check_dispatcher.py` because it asserts the same one thing the
rest of this file asserts — that the failure mode and its remedy are the LAST
thing the aggregate says — and because the Red leg of the Red-Green-Replay
ritual stages exactly one test file.

The dispatcher's private summary entry points are imported directly, the
package-private access model the sibling dispatcher suite already uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.check_failure_digest import (
    FailureFinding,
    collect_failure_findings,
    render_failure_digest,
)
from livespec_dev_tooling.parallel_check_dispatcher import (
    TargetResult,
    _configure_logger,
    _emit_summary,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The real shape the worktree-pack arm emits: structlog's JSONRenderer output
# on stderr, which the dispatcher captures into the target's combined output.
_PACK_REMEDY = (
    "run `just install-worktree-pack` (this checkout's root justfile defines "
    "the recipe; it writes the single canonical bodies byte-for-byte into "
    "`dev-tooling/`)"
)
_PACK_TARGET = "check-primary-checkout-commit-refuse-hook-installed"


def _pack_absent_record() -> str:
    """Return one `worktree_pack_absent` structlog line as the check emits it."""
    return json.dumps(
        {
            "check_id": "primary_checkout_commit_refuse_hook_installed",
            "status": "fail",
            "hook": "",
            "failure_mode": "worktree_pack_absent",
            "hooks_dir": "/repo/.git/hooks",
            "hint": _PACK_REMEDY,
            "path": "/repo/dev-tooling",
            "line": 0,
            "event": "primary-checkout-commit-refuse-hook-installed: worktree-pack drift",
            "level": "error",
            "timestamp": "2026-09-06T10:31:00.000000Z",
        }
    )


# ---------------------------------------------------------------------------
# collect_failure_findings
# ---------------------------------------------------------------------------


def test_collect_lifts_the_worktree_pack_absent_finding_out_of_captured_output() -> None:
    """The failure mode and its remedy are recovered from a target's captured output."""
    output = "\n".join(["just check-...", _pack_absent_record(), "error: Recipe failed"])
    findings = collect_failure_findings(target=_PACK_TARGET, output=output)
    assert findings == [
        FailureFinding(
            target=_PACK_TARGET,
            failure_mode="worktree_pack_absent",
            hint=_PACK_REMEDY,
            path="/repo/dev-tooling",
        )
    ]


def test_collect_ignores_lines_that_are_not_json_objects() -> None:
    """Prose, pytest output and bare JSON scalars carry no findings."""
    output = "\n".join(["ruff: 3 files checked", "", "5", '"a string"', "not json {"])
    assert collect_failure_findings(target="check-lint", output=output) == []


def test_collect_ignores_records_that_are_not_failures() -> None:
    """A record without `status=fail`, or without a usable failure mode, is not a finding."""
    records = [
        json.dumps({"status": "pass", "failure_mode": "worktree_pack_absent"}),
        json.dumps({"status": "fail", "failure_mode": None}),
        json.dumps({"status": "fail", "failure_mode": ""}),
    ]
    assert collect_failure_findings(target="check-x", output="\n".join(records)) == []


def test_collect_falls_back_when_a_finding_carries_no_remedy_and_no_path() -> None:
    """A `status=fail` record missing `hint`/`path` still names its failure mode."""
    record = json.dumps({"status": "fail", "failure_mode": "git_probe_failed", "hint": ""})
    findings = collect_failure_findings(target="check-x", output=record)
    assert len(findings) == 1
    assert findings[0].failure_mode == "git_probe_failed"
    assert findings[0].path == ""
    assert "no remedy" in findings[0].hint


# ---------------------------------------------------------------------------
# render_failure_digest
# ---------------------------------------------------------------------------


def test_render_returns_empty_text_when_there_are_no_findings() -> None:
    """No structured findings means no digest block — the target output stands alone."""
    assert render_failure_digest(findings=[]) == ""


def test_render_puts_the_remedy_on_the_last_line_of_each_entry() -> None:
    """The failure mode heads the entry and its remedy is the entry's final line."""
    rendered = render_failure_digest(
        findings=collect_failure_findings(target=_PACK_TARGET, output=_pack_absent_record())
    )
    assert "worktree_pack_absent" in rendered
    lines = [line for line in rendered.splitlines() if line.strip()]
    assert "failure mode" in lines[0].lower()
    assert f"{_PACK_TARGET}: worktree_pack_absent (1 finding)" in lines[1]
    assert lines[2] == "    path: /repo/dev-tooling"
    assert lines[-1] == f"    remedy: {_PACK_REMEDY}"


def test_render_groups_repeats_and_caps_the_paths_it_lists() -> None:
    """Many findings sharing one mode and remedy collapse to one bounded entry.

    An unbounded digest would re-create the very scroll-off this work-item
    fixes, so a mode reported against many files lists the first few paths and
    counts the rest.
    """
    findings = [
        FailureFinding(target="check-x", failure_mode="body_mismatch", hint="reinstall", path=name)
        for name in ("a.sh", "b.sh", "c.sh", "d.sh", "e.sh")
    ]
    rendered = render_failure_digest(findings=findings)
    assert "check-x: body_mismatch (5 findings)" in rendered
    assert "    path: c.sh\n" in rendered
    assert "d.sh" not in rendered
    assert "    ... and 2 more\n" in rendered
    assert rendered.endswith("    remedy: reinstall\n")


# ---------------------------------------------------------------------------
# Dispatcher wiring — the tail of what the hook actually prints
# ---------------------------------------------------------------------------


def test_aggregate_summary_ends_with_the_failure_mode_and_its_remedy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The aggregate's LAST lines name `worktree_pack_absent` and its remedy.

    The measured defect: 313s of preceding output scrolled the finding away and
    the hook reported a bare `exit status 1`. Preceding output is simulated at
    a scale no terminal scrollback survives, and the assertion is on the TAIL.
    """
    noise = "\n".join(f"... check output line {index}" for index in range(5000))
    results = [
        TargetResult(
            name=_PACK_TARGET,
            skipped=False,
            exit_code=1,
            wall_time_s=12.5,
            output=f"{noise}\n{_pack_absent_record()}\n",
        )
    ]
    exit_code = _emit_summary(results=results, log=_configure_logger())
    printed = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert exit_code == 1
    assert printed[-1] == f"    remedy: {_PACK_REMEDY}"
    assert "worktree_pack_absent" in printed[-3]


def test_aggregate_summary_adds_no_digest_when_every_target_passed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A green aggregate keeps its existing tail — the digest is a failure surface."""
    results = [
        TargetResult(name="check-lint", skipped=False, exit_code=0, wall_time_s=1.0, output="ok")
    ]
    exit_code = _emit_summary(results=results, log=_configure_logger())
    assert exit_code == 0
    assert "remedy:" not in capsys.readouterr().out


def test_both_hook_aggregates_route_through_the_dispatcher() -> None:
    """Pre-push AND pre-commit reach `just check`, so both get the same tail.

    Acceptance criterion 2 is satisfied structurally rather than by a second
    presentation path: the two hook entry scripts both delegate to the bare
    `check` aggregate, whose dispatcher owns the digest.
    """
    for script in ("check-pre-push.sh", "check-pre-commit.sh"):
        body = (_REPO_ROOT / "scripts" / "just" / script).read_text(encoding="utf-8")
        assert "\njust check\n" in body, script
