"""Mirror-paired test for `livespec_dev_tooling/check_failure_digest.py`.

The digest exists because a self-describing failure stopped being visible.
Measured 2026-08-20 in `livespec-console-beads-fabro`: a fresh worktree failed
the pre-push aggregate at check-baseline with failure mode
`worktree_pack_absent`, whose remedy is one command, and the hook surfaced a
bare `exit status 1` after 313 seconds of output with the finding scrolled
off. So the assertions here are about POSITION as much as content — the mode
and its remedy have to be readable at the TAIL, after any amount of preceding
output.

⛔ THE `worktree_pack_absent` FIXTURE IS EMITTED, NOT TYPED. It is produced by
calling the real narration emitter,
`checks/_primary_checkout_narration._emit_failures`, through the dispatcher's
own structlog configuration and capturing what it wrote. A hand-typed JSON
line would pass this file while the digest silently stopped parsing the shape
the check actually emits — which is the only way this module can fail without
anyone noticing, since it changes no verdict and its absence looks exactly
like a check that had nothing to say.

The `just check` invocation inside the two hook scripts is pinned here too,
and that is not an incidental assertion. The tail presentation lives in
`parallel_check_dispatcher` PRECISELY so that both local git-hook gates
inherit it through the bare aggregate line they already run. Rewrite either
hook to reach the aggregate some other way — a `tee`, a wrapper, a second
copy of the target list — and the pre-commit half of the acceptance criteria
silently stops holding.

Private names are accessed via a direct import (the package-private access
model used by `test_parallel_check_dispatcher.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.check_failure_digest import (
    _fail_record,
    _mode_groups,
    failure_digest_lines,
)
from livespec_dev_tooling.checks._primary_checkout_narration import _emit_failures
from livespec_dev_tooling.checks._primary_checkout_worktree_pack import (
    WORKTREE_PACK_DIR_NAME,
    pack_failure_hint,
)
from livespec_dev_tooling.parallel_check_dispatcher import (
    TargetResult,
    _configure_logger,
    _emit_summary,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACK_ABSENT_MODE = "worktree_pack_absent"
# The scrollback the defect is about. 313 seconds of aggregate output is far
# more than this, but any amount is enough to prove the digest's position does
# not depend on how much came before it.
_PRECEDING_OUTPUT = "\n".join(f":: some earlier check line {index}" for index in range(400))


def _emitted_pack_absent_output(*, repo_root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Return what the real check writes when the worktree pack is absent.

    Drives `_emit_failures` — the check's single narration surface — with the
    one pack failure this work-item names, through the same structlog
    configuration the dispatcher installs, and hands back the captured stderr.
    That text is the digest's actual input in production: the dispatcher runs
    each target with `stderr=subprocess.STDOUT`, so a target's structlog
    records land in the captured output beside its prose.
    """
    log = _configure_logger()
    _emit_failures(
        log=log,
        hooks_dir=repo_root / ".git" / "hooks",
        repo_root=repo_root,
        hook_failures=[],
        vendored_copies=[],
        pack_failures=[(WORKTREE_PACK_DIR_NAME, _PACK_ABSENT_MODE)],
    )
    return capsys.readouterr().err


# ---------------------------------------------------------------------------
# The acceptance criteria: mode + remedy, at the tail, after any output
# ---------------------------------------------------------------------------


def test_worktree_pack_absent_names_its_mode_and_remedy_in_the_final_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The digest's tail carries the mode and the check's own remedy verbatim."""
    finding = _emitted_pack_absent_output(repo_root=tmp_path, capsys=capsys)
    captured_output = f"{_PRECEDING_OUTPUT}\n{finding}"

    lines = failure_digest_lines(
        failures=[("check-primary-checkout-commit-refuse-hook-installed", captured_output)]
    )

    remedy = pack_failure_hint(failure_mode=_PACK_ABSENT_MODE, repo_root=tmp_path)
    assert len(lines) >= 3, "a failed target must contribute a mode line, a path and a remedy"
    assert lines[-1] == f"      remedy: {remedy}"
    assert (
        lines[-3] == f"  check-primary-checkout-commit-refuse-hook-installed: {_PACK_ABSENT_MODE}"
    )
    # tmp_path carries no justfile, so the composer takes its unwired branch —
    # the text the work-item quotes, naming `just bootstrap` first.
    assert "just bootstrap" in lines[-1]


def test_the_digest_is_the_tail_of_what_the_aggregate_prints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_emit_summary` ends its stdout with the mode and remedy.

    This is the acceptance criterion measured where the operator reads it: the
    dispatcher's summary is the last thing `scripts/just/check.sh` runs, so its
    final lines are the hook's final lines.
    """
    finding = _emitted_pack_absent_output(repo_root=tmp_path, capsys=capsys)
    results = [
        TargetResult(
            name="check-primary-checkout-commit-refuse-hook-installed",
            skipped=False,
            exit_code=4,
            wall_time_s=1.0,
            output=f"{_PRECEDING_OUTPUT}\n{finding}",
        ),
        TargetResult(name="check-lint", skipped=False, exit_code=0, wall_time_s=0.5, output="ok"),
    ]

    exit_code = _emit_summary(results=results, log=_configure_logger())

    assert exit_code == 1
    tail = capsys.readouterr().out.rstrip("\n").splitlines()[-3:]
    assert tail[0].endswith(f": {_PACK_ABSENT_MODE}")
    assert tail[2] == (
        f"      remedy: {pack_failure_hint(failure_mode=_PACK_ABSENT_MODE, repo_root=tmp_path)}"
    )


def test_a_green_aggregate_prints_no_digest() -> None:
    """Nothing failed means there is no remedy to keep on screen."""
    assert failure_digest_lines(failures=[]) == []


# ---------------------------------------------------------------------------
# Both hook gates inherit the tail through the bare aggregate line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script_name",
    ["check-pre-push.sh", "check-pre-commit.sh"],
)
def test_both_hook_aggregates_route_through_the_dispatcher(script_name: str) -> None:
    """Each hook gate reaches the aggregate as a bare `just … check` line.

    The digest is emitted by the dispatcher, so the pre-commit half of the
    acceptance criteria holds only while both gates keep running the SAME
    aggregate the dispatcher owns. Asserted as the invocation line rather than
    as an output shape because that is the property that can regress: a hook
    that pipes, tees or re-implements the aggregate would still print
    something, just not this.
    """
    script = (_REPO_ROOT / "scripts" / "just" / script_name).read_text(encoding="utf-8")
    invocations = [
        line.strip()
        for line in script.splitlines()
        if line.strip().startswith("just ") and line.strip().endswith(" check")
    ]

    assert invocations, f"{script_name} no longer invokes the `just check` aggregate"
    assert all(
        "|" not in line for line in invocations
    ), f"{script_name} pipes the aggregate; the dispatcher's tail would no longer be the tail"
    dispatcher_line = "uv run python -m livespec_dev_tooling.parallel_check_dispatcher"
    check_sh = (_REPO_ROOT / "scripts" / "just" / "check.sh").read_text(encoding="utf-8")
    assert dispatcher_line in check_sh


# ---------------------------------------------------------------------------
# Parsing: what counts as a finding, and what the digest does with the rest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (":: just check-lint [FAILED, wall: 3.1s]", "prose, not JSON"),
        ('{"event": "unterminated', "JSON that does not parse"),
        ("[1, 2, 3]", "JSON that is not an object"),
        ('{"status": "fail"', "an object with no closing brace parses as nothing"),
        ('{"level": "warning", "file": "x.py", "lloc": 214}', "a warning is not a failure"),
        ('{"status": "fail", "hint": "do the thing"}', "a failure with no mode to restate"),
        ('{"status": "fail", "failure_mode": ""}', "an empty mode names nothing"),
        ('{"status": "fail", "failure_mode": 7}', "a non-string mode"),
    ],
)
def test_lines_that_are_not_findings_are_ignored(line: str, reason: str) -> None:
    """Only a structlog `fail` record carrying a failure mode is a finding."""
    assert _fail_record(line=line) is None, reason


def test_a_finding_with_no_hint_or_path_still_yields_its_mode() -> None:
    """Absent `hint`/`path` degrade to empty strings rather than to a non-finding."""
    assert _fail_record(line='{"status": "fail", "failure_mode": "core_bare_set"}') == (
        "core_bare_set",
        "",
        "",
    )


def test_a_mode_with_neither_path_nor_remedy_renders_one_line() -> None:
    """The mode alone is still worth restating; the empty fields are not printed."""
    output = '{"status": "fail", "failure_mode": "core_bare_set", "hint": "", "path": ""}'

    assert failure_digest_lines(failures=[("check-thing", output)])[2:] == [
        "  check-thing: core_bare_set"
    ]


def test_repeated_findings_of_one_mode_collapse_to_a_count_and_one_example() -> None:
    """A 40-violation target contributes three lines, not 120."""
    output = "\n".join(
        f'{{"status": "fail", "failure_mode": "kwonly", "hint": "add `*`", "path": "f{n}.py"}}'
        for n in range(40)
    )

    assert _mode_groups(output=output) == [("kwonly", "add `*`", "f0.py", 40)]
    assert failure_digest_lines(failures=[("check-keyword-only-args", output)])[2:] == [
        "  check-keyword-only-args: kwonly (40 findings)",
        "      path: f0.py",
        "      remedy: add `*`",
    ]


def test_one_mode_with_two_remedies_stays_two_entries() -> None:
    """Grouping is keyed on `(mode, hint)`, so a routed remedy is never merged away."""
    output = (
        '{"status": "fail", "failure_mode": "unreadable", "hint": "fix access", "path": "a"}\n'
        '{"status": "fail", "failure_mode": "unreadable", "hint": "reinstall", "path": "b"}\n'
    )

    assert _mode_groups(output=output) == [
        ("unreadable", "fix access", "a", 1),
        ("unreadable", "reinstall", "b", 1),
    ]


def test_a_failed_target_with_no_structured_finding_is_reported_as_that() -> None:
    """Never silently omitted: a partial digest must not read as a complete one."""
    tail = failure_digest_lines(failures=[("check-types", "pyright: 3 errors\n")])[2:]

    assert len(tail) == 1, "the target must appear in the digest even with nothing to parse"
    assert tail[0].startswith("  check-types: failed without a structured failure_mode")
