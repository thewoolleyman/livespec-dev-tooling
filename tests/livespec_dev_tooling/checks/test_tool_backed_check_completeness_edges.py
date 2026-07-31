"""Green-leg edge for `tool_backed_check_completeness.py`'s railway conversion.

A `*_edges.py` sibling rather than an addition to
`test_tool_backed_check_completeness.py`, which is byte-identity-bound to its
own Red commit.

The branch is one the conversion CREATED. `collect_ci_matrix_targets` reached
`path.read_text` UNGUARDED, so a workflow file whose bytes will not decode
raised out of the check. The replacement is a finding — deliberately NOT a
skipped contribution, because this check asserts CI RUNS what the justfile
WIRES, so silently dropping a workflow makes a slug that IS run look unrun and
manufactures a gap that does not exist.

Driven IN-PROCESS through `main()`, per `check-tests-no-subprocess-spawn`.
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks.tool_backed_check_completeness import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_EXIT_VIOLATIONS = 4

_JUSTFILE = textwrap.dedent(
    """\
    check:
        #!/usr/bin/env bash
        targets=(
          check-lint
        )
    """
)

_GOOD_WORKFLOW = textwrap.dedent(
    """\
    jobs:
      gate:
        strategy:
          matrix:
            target:
              - check-lint
    """
)


def _checkout(*, tmp_path: Path) -> Path:
    _ = (tmp_path / "justfile").write_text(_JUSTFILE, encoding="utf-8")
    _ = (tmp_path / "tool-backed.json").write_text(
        json.dumps({"slugs": ["check-lint"]}), encoding="utf-8"
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    return workflows


def _run(*, monkeypatch: pytest.MonkeyPatch, cwd: Path) -> int:
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        "sys.argv",
        ["tool_backed_check_completeness.py", "--tool-backed-from", "tool-backed.json"],
    )
    return main()


def _modes(*, stderr: str) -> list[object]:
    return [
        json.loads(line).get("failure_mode")
        for line in stderr.splitlines()
        if line.strip().startswith("{")
    ]


def test_undecodable_workflow_file_is_a_finding_not_a_raise(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """⛔ INVALID UTF-8, NOT `chmod 000` — this suite runs as ROOT.

    A permission-stripped file is still readable as root, so that fixture
    would pass while proving nothing. Undecodable bytes fail identically for
    every user.
    """
    workflows = _checkout(tmp_path=tmp_path)
    _ = (workflows / "ci.yml").write_bytes(b"jobs:\n  \xff\xfe not utf-8\n")

    exit_code = _run(monkeypatch=monkeypatch, cwd=tmp_path)

    assert exit_code == _EXIT_VIOLATIONS
    assert "workflow_file_unreadable" in _modes(stderr=capsys.readouterr().err)


def test_the_unreadable_workflow_is_not_read_as_a_missing_slug(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The wrong conversion would have manufactured a `missing_from_ci` finding.

    POSITIVE CONTROL ON THE FIXTURE: the good workflow DOES wire `check-lint`,
    so if the undecodable sibling were skipped rather than failed, the union
    would still be complete and the check would exit 0 — meaning this test
    would pass for the wrong reason. It is the file that CANNOT be read that
    must stop the run, and `missing_from_ci` must NOT appear: that finding
    would accuse the consumer of a gap the check never established.
    """
    workflows = _checkout(tmp_path=tmp_path)
    _ = (workflows / "a-good.yml").write_text(_GOOD_WORKFLOW, encoding="utf-8")
    _ = (workflows / "b-broken.yml").write_bytes(b"jobs:\n  \xff\xfe not utf-8\n")

    exit_code = _run(monkeypatch=monkeypatch, cwd=tmp_path)

    modes = _modes(stderr=capsys.readouterr().err)
    assert exit_code == _EXIT_VIOLATIONS
    assert "workflow_file_unreadable" in modes
    assert "missing_from_ci" not in modes
