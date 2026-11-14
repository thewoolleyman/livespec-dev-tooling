"""Tests for livespec_dev_tooling/checks/ci_single_container_image.

A delegated gate Job runs in the one image `render-gate-job.sh` resolves from the
consumer's `.github/workflows/ci.yml`, so that file may declare only one distinct
job `container:` image. The check fails when it declares two or more, naming each
distinct image and the line(s) that declare it, and passes when every job
`container:` image is the same reference.

The check is driven in-process (`monkeypatch.chdir` + `capsys` + `main()`), the
fixture being a bare directory holding a `ci.yml`: the check reads that one file
and nothing else.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []

_IMAGE_A = "ghcr.io/example/livespec-fabro-sandbox:python-v1.174.0"
_IMAGE_B = "ghcr.io/example/livespec-fabro-sandbox:python-v1.175.0"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "ci_single_container_image.py"
)


def _check() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.checks.ci_single_container_image")


def _write_ci(*, root: Path, body: str) -> None:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(body, encoding="utf-8")


def _records(*, stderr: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]


def _job(*, name: str, container: str) -> str:
    return f"  {name}:\n    runs-on: ubuntu-latest\n{container}    steps:\n      - run: true\n"


def _block(*, image: str) -> str:
    return f"    container:\n      image: {image}\n"


def test_two_distinct_images_fail_naming_each_image_and_its_line(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "jobs:\n" + _job(name="a", container=_block(image=_IMAGE_A))
    source += _job(name="b", container=_block(image=_IMAGE_B))
    _write_ci(root=tmp_path, body=source)
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    errors = _records(stderr=capsys.readouterr().err)
    assert code == 1
    by_image = {str(record["image"]): record for record in errors if record["level"] == "error"}
    assert set(by_image) == {_IMAGE_A, _IMAGE_B}
    assert by_image[_IMAGE_A]["lines"] == [5]
    assert by_image[_IMAGE_B]["lines"] == [11]


def test_one_image_declared_by_several_jobs_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "jobs:\n" + _job(name="a", container=_block(image=_IMAGE_B))
    source += _job(name="b", container=_block(image=_IMAGE_B))
    _write_ci(root=tmp_path, body=source)
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    assert code == 0
    assert [r for r in _records(stderr=capsys.readouterr().err) if r["level"] == "error"] == []


def test_scalar_quoted_commented_and_non_leading_image_forms_are_all_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = (
        "jobs:\n"
        + _job(name="scalar", container=f"    container: {_IMAGE_A}  # comment\n")
        + _job(
            name="quoted",
            container=f"    container:\n      options: --init\n      image: '{_IMAGE_B}'\n",
        )
        + _job(
            name="double",
            container=f'    container:\n      # note\n\n      image: "{_IMAGE_B}" # pin\n',
        )
    )
    _write_ci(root=tmp_path, body=source)
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    errors = [r for r in _records(stderr=capsys.readouterr().err) if r["level"] == "error"]
    assert code == 1
    by_image = {str(record["image"]): record["lines"] for record in errors}
    assert by_image == {_IMAGE_A: [4], _IMAGE_B: [11, 19]}


def test_only_the_container_blocks_image_counts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = (
        "jobs:\n"
        "  a:\n"
        "    runs-on: ubuntu-latest\n"
        "    container:\n"
        f"      image: {_IMAGE_B}\n"
        "      credentials:\n"
        "        image: not-an-image\n"
        "    services:\n"
        "      db:\n"
        "        image: postgres:16\n"
        "    steps:\n"
        "      - uses: some/action\n"
        "        with:\n"
        "          image: another\n"
        "  empty:\n"
        "    container:\n"
        "  b:\n"
        "    runs-on: ubuntu-latest\n"
        "    # container: commented-out-image\n"
        "    steps:\n"
        "      - run: true\n"
    )
    _write_ci(root=tmp_path, body=source)
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    assert code == 0
    assert [r for r in _records(stderr=capsys.readouterr().err) if r["level"] == "error"] == []


def test_a_repository_with_no_ci_workflow_has_nothing_to_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    assert code == 0
    assert [r for r in _records(stderr=capsys.readouterr().err) if r["level"] == "error"] == []
