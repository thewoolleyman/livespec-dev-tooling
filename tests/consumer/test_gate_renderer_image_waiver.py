"""Consumer scenarios for a waived multi-image CI workflow reaching the gate renderer.

A consumer that WAIVES `check-ci-single-container-image` in its own `pyproject.toml`
declares several job images on purpose: console's `check-fuzz` job needs a nightly
toolchain the other jobs must not carry. The delegated renderer used to refuse such a
workflow ("declares 2 distinct container images"), so the consumer's pre-push gate
returned NO_VERDICT on a tree its own CI accepts. The renderer now honours the same
waiver and runs the gate in the image of the workflow's job named `check`, which is the
job that runs `just check`. These drive the REAL renderer over fixture consumer trees;
nothing here reaches a cluster, a mirror or a host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_RENDERER = (
    Path(__file__).resolve().parents[2]
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "gates"
    / "render-gate-job.sh"
)
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_GATE_IMAGE = "ghcr.io/example/sandbox:python-rust-v1"
_FUZZ_IMAGE = "ghcr.io/example/sandbox:python-rust-fuzz-v1"
_SLUG = "check-ci-single-container-image"


def _job(*, name: str, image: str) -> str:
    return (
        f"  {name}:\n    runs-on: ubuntu-latest\n    container:\n      image: {image}\n"
        f"    steps:\n      - run: just {name}\n"
    )


def _consumer(*, root: Path, gate_job: str, waiver: str) -> Path:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    body = "name: ci\njobs:\n" + _job(name=gate_job, image=_GATE_IMAGE)
    _ = workflow.write_text(body + _job(name="check-fuzz", image=_FUZZ_IMAGE), encoding="utf-8")
    _ = (root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\ndelegated_gate = true\n{waiver}", encoding="utf-8"
    )
    return root


def _waiver(*, slug: str = _SLUG, reason: str = "the fuzz leaf needs a nightly toolchain") -> str:
    return f'canonical_check_waivers = [{{ slug = "{slug}", reason = "{reason}" }}]\n'


def _render(*, root: Path) -> tuple[int, str, str]:
    done = run_under_hang_guard(
        [str(_RENDERER), "--repo-root", str(root), "--tree-hash", _TREE],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout, done.stderr


def test_a_waived_multi_image_workflow_runs_the_gate_in_the_check_jobs_image(
    *, tmp_path: Path
) -> None:
    root = _consumer(root=tmp_path, gate_job="check", waiver=_waiver())

    code, stdout, stderr = _render(root=root)

    assert code == 0, stderr
    assert _GATE_IMAGE in stdout
    assert _FUZZ_IMAGE not in stdout
    assert f"waives {_SLUG}" in stderr
    assert _GATE_IMAGE in stderr


def test_the_same_workflow_without_the_waiver_is_still_refused_naming_both_images(
    *, tmp_path: Path
) -> None:
    root = _consumer(root=tmp_path, gate_job="check", waiver="")

    code, _, stderr = _render(root=root)

    assert code == 1
    assert "declares 2 distinct container images" in stderr
    assert f"  {_GATE_IMAGE}" in stderr
    assert f"  {_FUZZ_IMAGE}" in stderr


def test_a_waiver_of_another_check_does_not_waive_the_single_image_rule(*, tmp_path: Path) -> None:
    root = _consumer(root=tmp_path, gate_job="check", waiver=_waiver(slug="check-heading-coverage"))

    code, _, stderr = _render(root=root)

    assert code == 1
    assert "declares 2 distinct container images" in stderr


def test_a_waiver_with_a_blank_reason_is_not_a_waiver(*, tmp_path: Path) -> None:
    root = _consumer(root=tmp_path, gate_job="check", waiver=_waiver(reason="  "))

    code, _, stderr = _render(root=root)

    assert code == 1
    assert "declares 2 distinct container images" in stderr


def test_a_waived_workflow_with_no_check_job_is_still_refused_rather_than_guessed(
    *, tmp_path: Path
) -> None:
    root = _consumer(root=tmp_path, gate_job="check-metadata", waiver=_waiver())

    code, _, stderr = _render(root=root)

    assert code == 1
    assert "declares 2 distinct container images" in stderr
    assert "Refusing to guess" in stderr
