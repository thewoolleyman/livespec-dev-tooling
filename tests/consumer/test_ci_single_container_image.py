"""Consumer scenarios for a CI workflow that declares more than one container image.

A delegated gate Job runs in the one image it resolves from the consumer's
`.github/workflows/ci.yml`, so a pull request whose merge with the default branch
declares two distinct job `container:` images must fail its own CI. These drive the
shipped `ci_single_container_image` check against a fixture consumer tree, and
read the repository's own `just check` aggregate for the wiring that makes the
failure reach the required `ci-green` leg.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "livespec_dev_tooling.checks.ci_single_container_image"
_OLD = "livespec-fabro-sandbox:python-v1.174.0"
_NEW = "livespec-fabro-sandbox:python-v1.175.0"


def _workflow(*, images: tuple[str, ...]) -> str:
    jobs = "".join(
        f"  job{index}:\n    runs-on: ubuntu-latest\n    container:\n      image: {image}\n    steps:\n      - run: just check\n"
        for index, image in enumerate(images)
    )
    return f"name: ci\njobs:\n{jobs}"


def _run_check(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[dict[str, object]]]:
    monkeypatch.chdir(root)
    code = importlib.import_module(_MODULE).main()
    lines = capsys.readouterr().err.splitlines()
    return code, [json.loads(line) for line in lines if line.startswith("{")]


def test_a_workflow_declaring_two_container_images_fails_naming_each_image_and_its_line(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(_workflow(images=(_NEW, _OLD, _NEW)), encoding="utf-8")

    code, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    errors = {str(r["image"]): r["lines"] for r in records if r["level"] == "error"}
    assert code == 1
    assert errors == {_NEW: [6, 18], _OLD: [12]}


def test_a_workflow_declaring_one_container_image_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(_workflow(images=(_NEW, _NEW)), encoding="utf-8")

    code, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert code == 0
    assert [r for r in records if r["level"] == "error"] == []


def test_the_check_is_a_member_of_the_just_check_aggregate() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    targets = (_REPO_ROOT / "check-targets.txt").read_text(encoding="utf-8")

    assert "\n        check-ci-single-container-image\n" in justfile
    assert f"\ncheck-ci-single-container-image:\n    uv run python -m {_MODULE}\n" in justfile
    assert "\ncheck-ci-single-container-image  #" in targets


def test_a_container_block_with_no_image_at_the_end_of_the_file_declares_nothing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    source = _workflow(images=(_NEW,)) + "  last:\n    container:\n      options: --init\n"
    _ = workflow.write_text(source, encoding="utf-8")

    code, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert code == 0
    assert [r for r in records if r["level"] == "error"] == []
