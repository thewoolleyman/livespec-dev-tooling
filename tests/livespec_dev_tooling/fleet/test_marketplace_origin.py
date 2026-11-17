"""ensure-plugins repairs a marketplace clone whose origin names a stale owner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._marketplace_origin import (
    OriginReport,
    git_origin,
    git_set_origin,
    repair_marketplace_origins,
)

GH = {"source": "github", "repo": "livespec-ai/livespec", "ref": "release"}
# The owner the fleet moved away from; the clone origins below name it as the stale owner.
_STALE_ACCOUNT = "thewoolleyman"


def _known(**entries: dict[str, object]) -> str:
    return json.dumps(
        {
            name: {"source": source, "installLocation": f"/m/{name}"}
            for name, source in entries.items()
        }
    )


def _run(*, known: str, origins: dict[str, str]) -> tuple[OriginReport, list[tuple[str, str]]]:
    sets: list[tuple[str, str]] = []

    def set_origin(*, clone: str, url: str) -> bool:
        sets.append((clone, url))
        return True

    def read_origin(*, clone: str) -> str | None:
        return origins.get(clone)

    report = repair_marketplace_origins(
        known_text=known, read_origin=read_origin, set_origin=set_origin
    )
    return report, sets


def test_stale_https_origin_is_rewritten_to_declared_https() -> None:
    report, sets = _run(
        known=_known(livespec=GH),
        origins={"/m/livespec": f"https://github.com/{_STALE_ACCOUNT}/livespec.git"},
    )
    assert sets == [("/m/livespec", "https://github.com/livespec-ai/livespec.git")]
    assert report.findings == ()
    assert len(report.notices) == 1


def test_stale_ssh_origin_keeps_ssh_form() -> None:
    _, sets = _run(
        known=_known(livespec=GH),
        origins={"/m/livespec": f"git@github.com:{_STALE_ACCOUNT}/livespec.git"},
    )
    assert sets == [("/m/livespec", "git@github.com:livespec-ai/livespec.git")]


def test_matching_origin_is_untouched_in_either_form() -> None:
    for origin in (
        "https://github.com/livespec-ai/livespec.git",
        "https://github.com/livespec-ai/livespec",
        "git@github.com:livespec-ai/livespec.git",
    ):
        report, sets = _run(known=_known(livespec=GH), origins={"/m/livespec": origin})
        assert sets == []
        assert report.notices == ()
        assert report.findings == ()


def test_third_party_and_missing_clones_are_never_touched() -> None:
    known = _known(
        official={"source": "github", "repo": "anthropics/claude-plugins-official"},
        livespec=GH,
    )
    report, sets = _run(known=known, origins={"/m/official": "https://github.com/x/y.git"})
    assert sets == []
    assert report.findings == ()


def test_unmappable_livespec_ai_source_is_reported_not_rewritten() -> None:
    known = _known(odd={"source": "git", "url": "https://gitlab.com/livespec-ai/odd.git"})
    report, sets = _run(known=known, origins={"/m/odd": "https://github.com/old/odd.git"})
    assert sets == []
    assert len(report.notices) == 1
    assert "odd" in report.notices[0]


def test_git_source_on_github_is_mapped() -> None:
    known = _known(g={"source": "git", "url": "https://github.com/livespec-ai/g.git"})
    _, sets = _run(known=known, origins={"/m/g": "https://github.com/old/g.git"})
    assert sets == [("/m/g", "https://github.com/livespec-ai/g.git")]


def test_failed_rewrite_is_a_finding_and_bad_json_is_inert() -> None:
    def read_origin(*, clone: str) -> str | None:
        return f"https://github.com/old/{clone}.git"

    def refuse(*, clone: str, url: str) -> bool:
        return clone == url

    report = repair_marketplace_origins(
        known_text=_known(livespec=GH), read_origin=read_origin, set_origin=refuse
    )
    assert len(report.findings) == 1
    inert = repair_marketplace_origins(
        known_text="{not json", read_origin=read_origin, set_origin=refuse
    )
    assert inert.findings == ()
    assert inert.notices == ()


def test_real_git_clone_origin_round_trip(tmp_path: Path) -> None:
    clone = tmp_path / "livespec"
    old = "https://github.com/old/livespec.git"
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(
        ["git", "-C", str(clone), "remote", "add", "origin", old],
        check=True,
    )
    known = json.dumps({"livespec": {"source": GH, "installLocation": str(clone)}})
    report = repair_marketplace_origins(
        known_text=known, read_origin=git_origin, set_origin=git_set_origin
    )
    assert report.findings == ()
    assert git_origin(clone=str(clone)) == "https://github.com/livespec-ai/livespec.git"
    assert git_origin(clone=str(tmp_path / "absent")) is None
