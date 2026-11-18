"""The coordinator's factory-delivery report reads merged pull requests, not drive exits."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_REPORT = _ROOT / "scripts" / "coordinator" / "factory-deliveries.sh"


def _pull(
    *, number: int, merged_at: str | None, head: str, title: str, author: str
) -> dict[str, object]:
    return {
        "number": number,
        "merged_at": merged_at,
        "head": {"ref": head},
        "title": title,
        "user": {"login": author},
    }


def _report(
    *, tmp_path: Path, pages: dict[str, list[dict[str, object]]]
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture = tmp_path / "pulls.json"
    _ = fixture.write_text(json.dumps(pages), encoding="utf-8")
    gh = bin_dir / "gh"
    _ = gh.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

request = sys.argv[2]
if "/contents/.livespec-fleet-manifest.jsonc" in request:
    print('\\n// committed roster\\n{"owner":"livespec-ai","fleet":[{"repo":"alpha","class":"core"},{"repo":"beta","class":"library"},{"repo":"gamma","class":"driver-plugin"}]}')
    raise SystemExit(0)
search = next(value.removeprefix("search=") for value in sys.argv if value.startswith("search="))
repository = search.split()[0].split("/")[1]
author = search.rsplit("author:", 1)[1].removeprefix("app/")
pulls = [pull for pull in json.loads(open(os.environ["FACTORY_PULL_FIXTURE"], encoding="utf-8").read()).get(repository, []) if pull["user"]["login"] == author]
print(json.dumps({"data": {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{"number": pull["number"], "mergedAt": pull["merged_at"], "headRefName": pull["head"]["ref"], "title": pull["title"], "author": {"login": pull["user"]["login"]}} for pull in pulls]}}}))
""",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return subprocess.run(
        ["bash", str(_REPORT)],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
        env=os.environ
        | {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FACTORY_PULL_FIXTURE": str(fixture),
            "FACTORY_DELIVERY_NOW": "2026-11-18T08:00:00Z",
        },
    )


def test_report_prints_the_newest_factory_delivery_its_age_and_the_trailing_day_count(
    tmp_path: Path,
) -> None:
    result = _report(
        tmp_path=tmp_path,
        pages={
            "alpha": [
                _pull(
                    number=44,
                    merged_at="2026-11-18T07:00:00Z",
                    head="feat/alpha",
                    title="delivery",
                    author="livespec-ai-factory-bot",
                ),
                _pull(
                    number=43,
                    merged_at="2026-11-17T09:00:00Z",
                    head="fix/alpha",
                    title="older delivery",
                    author="thewoolleyman-factory-bot",
                ),
                _pull(
                    number=42,
                    merged_at="2026-11-17T07:59:59Z",
                    head="feat/alpha-old",
                    title="outside window",
                    author="livespec-ai-factory-bot",
                ),
            ],
            "beta": [
                _pull(
                    number=41,
                    merged_at="2026-11-18T07:30:00Z",
                    head="feat/not-factory",
                    title="wrong author",
                    author="someone-else",
                ),
                _pull(
                    number=40,
                    merged_at=None,
                    head="fix/unmerged",
                    title="unmerged",
                    author="livespec-ai-factory-bot",
                ),
            ],
            "gamma": [
                _pull(
                    number=39,
                    merged_at="2026-11-16T08:00:00Z",
                    head="fix/gamma",
                    title="old",
                    author="livespec-ai-factory-bot",
                ),
            ],
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "alpha: newest #44 merged 2026-11-18T07:00:00Z; age 1h 0m; deliveries-24h 2",
        "beta: newest none; deliveries-24h 0",
        "gamma: newest #39 merged 2026-11-16T08:00:00Z; age 2d 0h; deliveries-24h 0",
    ]


def test_release_please_and_chore_bump_pulls_are_excluded_from_the_newest_and_count(
    tmp_path: Path,
) -> None:
    result = _report(
        tmp_path=tmp_path,
        pages={
            "alpha": [
                _pull(
                    number=55,
                    merged_at="2026-11-18T07:50:00Z",
                    head="release-please--branches--master",
                    title="chore(master): release",
                    author="livespec-ai-factory-bot",
                ),
                _pull(
                    number=54,
                    merged_at="2026-11-18T07:40:00Z",
                    head="chore/bump-pin",
                    title="chore: bump shared pin",
                    author="livespec-ai-factory-bot",
                ),
                _pull(
                    number=53,
                    merged_at="2026-11-18T07:30:00Z",
                    head="feat/but-a-bump",
                    title="chore(deps): bump pin",
                    author="livespec-ai-factory-bot",
                ),
            ],
            "beta": [],
            "gamma": [],
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "alpha: newest none; deliveries-24h 0",
        "beta: newest none; deliveries-24h 0",
        "gamma: newest none; deliveries-24h 0",
    ]
