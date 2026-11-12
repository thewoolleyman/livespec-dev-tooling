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
_OTHER_REPOSITORY_IMAGE = "ghcr.io/example/other-sandbox:python-v1.175.0"
_RUST_IMAGE = "ghcr.io/example/livespec-fabro-sandbox:python-rust-v1.197.0"
_FUZZ_IMAGE = "ghcr.io/example/livespec-fabro-sandbox:python-rust-fuzz-v1.197.0"
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


def _write_justfile(*, root: Path, targets: tuple[str, ...]) -> None:
    target_lines = "\n".join(f"        {target}" for target in targets)
    (root / "justfile").write_text(
        f"check:\n    targets=(\n{target_lines}\n    )\n",
        encoding="utf-8",
    )


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


@pytest.mark.parametrize(
    ("first", "second"),
    [(_IMAGE_A, _IMAGE_B), (_IMAGE_B, _OTHER_REPOSITORY_IMAGE)],
)
def test_different_image_versions_or_repositories_name_every_image_and_line(
    *,
    first: str,
    second: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_ci(
        root=tmp_path,
        body="jobs:\n"
        + _job(name="first", container=_block(image=first))
        + _job(name="second", container=_block(image=second)),
    )
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    errors = [
        record for record in _records(stderr=capsys.readouterr().err) if record["level"] == "error"
    ]
    assert code == 1
    assert {str(record["image"]): record["lines"] for record in errors} == {
        first: [5],
        second: [11],
    }


def test_a_layered_fuzz_job_off_the_aggregate_path_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "jobs:\n" + _job(name="check", container=_block(image=_RUST_IMAGE))
    source += _job(name="fuzz", container=_block(image=_FUZZ_IMAGE)).replace(
        "      - run: true", "      - run: just check-fuzz"
    )
    _write_ci(root=tmp_path, body=source)
    _write_justfile(root=tmp_path, targets=("check-lint", "check-test"))
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    assert code == 0
    assert [
        record for record in _records(stderr=capsys.readouterr().err) if record["level"] == "error"
    ] == []


@pytest.mark.parametrize(
    ("fuzz_image", "fuzz_command"),
    [
        (_FUZZ_IMAGE, "just check-lint"),
        (_RUST_IMAGE.removesuffix("rust-v1.197.0") + "agent-v1.197.0", "just check-fuzz"),
    ],
)
def test_a_non_gate_aggregate_job_or_missing_gate_flavor_fails_naming_images(
    *,
    fuzz_image: str,
    fuzz_command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = "jobs:\n" + _job(name="check", container=_block(image=_RUST_IMAGE))
    source += _job(name="fuzz", container=_block(image=fuzz_image)).replace(
        "      - run: true", f"      - run: {fuzz_command}"
    )
    _write_ci(root=tmp_path, body=source)
    _write_justfile(root=tmp_path, targets=("check-lint",))
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    errors = [
        record for record in _records(stderr=capsys.readouterr().err) if record["level"] == "error"
    ]
    assert code == 1
    assert {str(record["image"]) for record in errors} == {_RUST_IMAGE, fuzz_image}


def test_a_workflow_with_no_job_container_has_nothing_to_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_ci(
        root=tmp_path,
        body="jobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: just check-lint\n",
    )
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    assert code == 0
    assert [
        record for record in _records(stderr=capsys.readouterr().err) if record["level"] == "error"
    ] == []


def test_a_container_outside_a_job_does_not_count_as_a_job_image(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_ci(
        root=tmp_path,
        body=f"container: {_IMAGE_A}\njobs:\n"
        + _job(name="check", container=_block(image=_RUST_IMAGE)),
    )
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    assert code == 0
    assert [
        record for record in _records(stderr=capsys.readouterr().err) if record["level"] == "error"
    ] == []


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/example/livespec-fabro-sandbox:python",
        "ghcr.io/example/livespec-fabro-sandbox:python-v1.197.0-extra",
        "ghcr.io/example/livespec-fabro-sandbox:-v1.197.0",
    ],
)
def test_an_image_without_a_release_flavor_pin_fails(
    *,
    image: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_ci(root=tmp_path, body="jobs:\n" + _job(name="check", container=_block(image=image)))
    monkeypatch.chdir(tmp_path)

    code = _check().main()

    errors = [
        record for record in _records(stderr=capsys.readouterr().err) if record["level"] == "error"
    ]
    assert code == 1
    assert {str(record["image"]) for record in errors} == {image}
