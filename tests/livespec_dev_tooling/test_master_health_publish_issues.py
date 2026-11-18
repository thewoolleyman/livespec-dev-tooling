"""The master-health CLI raises and closes the alert issues through the forge, not just a payload.

Work-item livespec-dev-tooling-cslfje, `SPECIFICATION/contracts.md` section "Master-green gate and
external red". Each case runs the module's `__main__` path with a fake `gh` first on PATH, so the
issue seam the publisher drives is proven to reach the forge CLI in production, never a no-op.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ldizae

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling.ci_green_required_legs import required_legs

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_MODULE = "livespec_dev_tooling.master_health_publish"
_LABEL = "master-green-external-red"
_UNREADABLE = "master-green: episode unreadable"

# A stand-in for `gh api`: it logs every call as one JSON line and answers the open-issue listing
# from the state file, so the test sees exactly which reads and writes the CLI issued.
_FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
if "--method" not in args and "-X" not in args:
    with open(os.environ["FAKE_GH_STATE"], encoding="utf-8") as state:
        for issue in json.load(state):
            print(json.dumps(issue))
"""


def _legs() -> list[str]:
    text = _WORKFLOW.read_text(encoding="utf-8")
    return [
        leg
        for _job, names in required_legs(ci_yaml_text=text, gate_job="ci-green")
        for leg in names
    ]


def _jobs(*, failed: str | None) -> list[dict[str, Any]]:
    return [
        {
            "name": leg,
            "status": "completed",
            "conclusion": "failure" if leg == failed else "success",
            "run_attempt": 1,
        }
        for leg in _legs()
    ]


def _run(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed: str | None,
    open_issues: list[dict[str, Any]],
    with_repo: bool = True,
) -> list[list[str]]:
    """Run the CLI against the fake forge and return every `gh` call it made."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text(_FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    state = tmp_path / "issues.json"
    _ = state.write_text(json.dumps(open_issues), encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    pages = tmp_path / "pages.json"
    _ = pages.write_text(json.dumps([{"jobs": _jobs(failed=failed)}]), encoding="utf-8")
    argv = [
        _MODULE,
        "--workflow",
        str(_WORKFLOW),
        "--gate-job",
        "ci-green",
        "--jobs-pages",
        str(pages),
        "--results-dir",
        str(tmp_path / "gate-results"),
        "--head-sha",
        "abc123",
        "--run-id",
        "77",
        "--out",
        str(tmp_path / "payload.json"),
        *(["--repo", "owner/name"] if with_repo else []),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exited:
        _ = runpy.run_module(_MODULE, run_name="__main__")
    assert exited.value.code == 0
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _writes(*, calls: list[list[str]]) -> list[list[str]]:
    return [call for call in calls if "--method" in call or "-X" in call]


def test_a_defect_with_no_readable_episode_creates_the_unreadable_issue(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A defect verdict over an unreadable episode raises the one labelled unreadable issue."""
    calls = _run(tmp_path=tmp_path, monkeypatch=monkeypatch, failed=_legs()[0], open_issues=[])
    writes = _writes(calls=calls)
    assert len(writes) == 1
    flat = " ".join(writes[0])
    assert ("repos/owner/name/issues" in flat, "POST" in flat) == (True, True)
    assert (f"title={_UNREADABLE}" in writes[0], f"labels[]={_LABEL}" in writes[0]) == (True, True)


def test_an_already_open_unreadable_issue_is_not_raised_again(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The title search guards creation: a second publication raises nothing new."""
    existing = [{"number": 9, "title": _UNREADABLE, "pull_request": False}]
    calls = _run(
        tmp_path=tmp_path, monkeypatch=monkeypatch, failed=_legs()[0], open_issues=existing
    )
    assert _writes(calls=calls) == []


def test_a_pull_request_with_the_title_does_not_count_as_the_open_issue(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The issues listing also returns pull requests; one is never the alert."""
    lookalike = [{"number": 4, "title": _UNREADABLE, "pull_request": True}]
    calls = _run(
        tmp_path=tmp_path, monkeypatch=monkeypatch, failed=_legs()[0], open_issues=lookalike
    )
    assert len(_writes(calls=calls)) == 1


def test_a_green_master_health_closes_every_open_labelled_issue_with_a_comment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A green run ends the episode: each open alert gets a comment, then is closed."""
    open_issues = [
        {"number": 5, "title": "master-green: external episode 3", "pull_request": False},
        {"number": 8, "title": _UNREADABLE, "pull_request": False},
    ]
    calls = _run(tmp_path=tmp_path, monkeypatch=monkeypatch, failed=None, open_issues=open_issues)
    writes = [" ".join(call) for call in _writes(calls=calls)]
    assert len(writes) == 4
    assert [("issues/5/comments" in w, "state=closed" in w) for w in writes[:2]] == [
        (True, False),
        (False, True),
    ]
    assert [("issues/8/comments" in w, "state=closed" in w) for w in writes[2:]] == [
        (True, False),
        (False, True),
    ]


def test_the_forge_is_never_called_without_a_repository(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without `--repo` the CLI only writes its payload, as before."""
    calls = _run(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        failed=_legs()[0],
        open_issues=[],
        with_repo=False,
    )
    assert calls == []
