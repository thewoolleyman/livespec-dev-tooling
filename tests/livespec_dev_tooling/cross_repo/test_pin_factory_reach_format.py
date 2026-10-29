"""The factory-reach env-file line is a fabro-sandbox docker image tag pin.

`SPECIFICATION/contracts.md` section "Pin autodiscovery rules" names the
`FACTORY_REACH_SANDBOX_IMAGE=<ref>` line of
`ci-runner/k3s/phase2/factory/factory-reach-image.env` as a THIRD surface of the
`fabro_sandbox_docker_image` format. The file carries a second copy of the
workflow `container:` `image:` pin, and `fabro_image_pin_lockstep` fails when the
two differ, so a release bump that rewrites only the workflow copy is red by
construction (work-item livespec-dev-tooling-7enfyd). These tests pin the walk
half (the line is a record, a present file the walk cannot parse is a typed
failure) and, in the scenario test, the whole bump: walk, then rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import fabro_image_pin_rewrite, pin_autodiscovery

__all__: list[str] = []

_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"
_ENV_PATH = Path("ci-runner/k3s/phase2/factory/factory-reach-image.env")
_ENV_REL = str(_ENV_PATH)
_OLD_TAG = "python-v1.110.0"


def _write_env(*, root: Path, text: str) -> None:
    path = root / _ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _write_ci(*, root: Path, jobs: int, tag: str = _OLD_TAG) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    body = "jobs:\n" + "".join(
        f"  job{index}:\n    runs-on: ubuntu-latest\n    container:\n      image: {_IMAGE}:{tag}\n"
        for index in range(jobs)
    )
    _ = (workflows / "ci.yml").write_text(body, encoding="utf-8")


def _env_records(*, root: Path, source_repo: str | None = None) -> list[dict[str, str]]:
    walked = pin_autodiscovery.discover(root=root, source_repo=source_repo).unwrap()
    return [record for record in unsafe_perform_io(walked) if record["file_path"] == _ENV_REL]


def test_walk_reports_the_factory_reach_line_as_a_fabro_sandbox_pin(*, tmp_path: Path) -> None:
    _write_env(
        root=tmp_path,
        text=(
            f"# FACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:python-v0.0.1 (a comment)\n"
            "\n"
            f"FACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:{_OLD_TAG}\n"
        ),
    )
    assert _env_records(root=tmp_path) == [
        {
            "pin_format": "fabro_sandbox_docker_image",
            "file_path": _ENV_REL,
            "pin_key": _IMAGE,
            "current_value": _OLD_TAG,
            "source_repo": "livespec-dev-tooling",
        }
    ]


def test_walk_yields_no_record_when_the_env_file_is_absent(*, tmp_path: Path) -> None:
    assert _env_records(root=tmp_path) == []


def test_walk_ignores_a_factory_reach_line_naming_another_image(*, tmp_path: Path) -> None:
    _write_env(root=tmp_path, text="FACTORY_REACH_SANDBOX_IMAGE=docker.io/library/alpine:3\n")
    assert _env_records(root=tmp_path) == []


def test_walk_honours_the_source_repo_filter(*, tmp_path: Path) -> None:
    _write_env(root=tmp_path, text=f"FACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:{_OLD_TAG}\n")
    assert _env_records(root=tmp_path, source_repo="livespec") == []
    assert len(_env_records(root=tmp_path, source_repo="livespec-dev-tooling")) == 1


def test_walk_surfaces_two_image_values_as_unparseable(*, tmp_path: Path) -> None:
    _write_env(
        root=tmp_path,
        text=(
            f"FACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:{_OLD_TAG}\n"
            f"FACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:python-v1.111.0\n"
        ),
    )
    walked = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert isinstance(walked, IOFailure)
    failure = unsafe_perform_io(walked.failure())
    assert isinstance(failure, pin_autodiscovery.PinFileUnparseable)
    assert failure.pin_walk == "walk_factory_reach_sandbox_image"
    assert failure.file_path == _ENV_REL


def test_walk_surfaces_an_undecodable_env_file_as_unreadable(*, tmp_path: Path) -> None:
    path = tmp_path / _ENV_PATH
    path.parent.mkdir(parents=True)
    _ = path.write_bytes(b"\xff\xfe\x00 not utf-8")
    walked = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert isinstance(walked, IOFailure)
    failure = unsafe_perform_io(walked.failure())
    assert isinstance(failure, pin_autodiscovery.PinFileUnreadable)
    assert failure.pin_walk == "walk_factory_reach_sandbox_image"
    assert failure.file_path == str(path)


@pytest.mark.integration
def test_release_bump_rewrites_the_factory_reach_pin_with_the_workflow_pins(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_ci(root=tmp_path, jobs=2)
    _write_env(
        root=tmp_path,
        text=(
            "# Bump BOTH, in the same change.\n"
            f"FACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:{_OLD_TAG}\n"
        ),
    )
    walked = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec-dev-tooling").unwrap()
    records = unsafe_perform_io(walked)
    assert {record["file_path"] for record in records} == {".github/workflows/ci.yml", _ENV_REL}

    monkeypatch.setenv("PIN_TAG", "v1.134.5")
    for record in records:
        monkeypatch.setenv("PIN_FILE", str(tmp_path / record["file_path"]))
        monkeypatch.setenv("PIN_KEY", record["pin_key"])
        monkeypatch.setenv("PIN_CURRENT", record["current_value"])
        assert fabro_image_pin_rewrite.main() == 0

    new_tag = "python-v1.134.5"
    workflow_text = (tmp_path / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert workflow_text.count(f"image: {_IMAGE}:{new_tag}\n") == 2
    assert (tmp_path / _ENV_PATH).read_text(encoding="utf-8") == (
        f"# Bump BOTH, in the same change.\nFACTORY_REACH_SANDBOX_IMAGE={_IMAGE}:{new_tag}\n"
    )
    assert _OLD_TAG not in workflow_text
