"""Outside-in tests for `cross_repo/_pin_directory_scan_formats.py`.

The directory-scanning pin formats — the `.github/workflows/*.yml`
`uses:` ref and the fabro-sandbox docker image tag, which appears both
in `.fabro` `workflow.toml` files and (per job `container:` block) in
`.github/workflows/*.yml` — each scan a directory of files rather than
reading one well-known file. This mirror file exercises each format
individually, the source-repo filter, the missing-directory tolerance,
and the multi-file / multi-workflow coexistence cases. The walks are
driven through the public `_walk()` entry point (the
same outside-in surface these tests used before the decomposition).

Coverage target: 100% line + branch of `_pin_directory_scan_formats.py`.
"""

from __future__ import annotations

from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import pin_autodiscovery

__all__: list[str] = []


def _walk(*, root: Path, source_repo: str | None = None) -> list[dict[str, str]]:
    """The walk's records, failing loud if a pin file could not be READ.

    `discover` returns `IOResult` since livespec-dev-tooling-9sl0. Every
    test below drives readable fixtures, so `.unwrap()` is the right
    accessor: an unexpected read failure raises here instead of degrading
    to an empty record list, which is the shape that reads as "this repo
    carries no pins" and would make a broken walk look like a passing one.
    The `unreadable` sibling file pins the failure track itself.
    """
    return unsafe_perform_io(
        pin_autodiscovery.discover(root=root, source_repo=source_repo).unwrap()
    )


# ---------------------------------------------------------------------------
# .github/workflows/ uses: ref tests (fourth pin format)
# ---------------------------------------------------------------------------


def test_discover_github_workflow_uses_emits_record(*, tmp_path: Path) -> None:
    """A `.github/workflows/*.yml` file with a reusable `uses:` line emits one record."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "bump-pin.yml").write_text(
        "jobs:\n"
        "  bump:\n"
        "    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-bump.yml@master\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "github_workflow_uses_ref"
    assert record["file_path"] == ".github/workflows/bump-pin.yml"
    assert (
        record["pin_key"]
        == "thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-bump.yml"
    )
    assert record["current_value"] == "master"
    assert record["source_repo"] == "livespec-dev-tooling"


def test_discover_github_workflow_uses_missing_dir_yields_nothing(*, tmp_path: Path) -> None:
    """A consumer repo without `.github/workflows/` yields no records from this format."""
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_github_workflow_uses_skips_simple_action_uses(*, tmp_path: Path) -> None:
    """An action-style `uses: actions/checkout@v4` (no path segment) is not emitted."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "steps:\n" "  - uses: actions/checkout@v4\n" "  - uses: jdx/mise-action@v2\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_github_workflow_uses_multiple_files(*, tmp_path: Path) -> None:
    """Multiple workflow files each with a matching `uses:` line emit one record each."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "bump-pin.yml").write_text(
        "    uses: owner/repo-a/.github/workflows/reusable.yml@v0.1.0\n",
        encoding="utf-8",
    )
    (workflows_dir / "freshness.yml").write_text(
        "    uses: owner/repo-b/.github/workflows/reusable.yml@v0.2.0\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 2
    source_repos = sorted(r["source_repo"] for r in result)
    assert source_repos == ["repo-a", "repo-b"]


def test_discover_github_workflow_uses_multiple_per_file(*, tmp_path: Path) -> None:
    """A single workflow file with multiple matching `uses:` lines emits one record per line."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "release.yml").write_text(
        "    uses: owner/repo-a/.github/workflows/step1.yml@v1\n"
        "    uses: owner/repo-b/.github/workflows/step2.yml@v2\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 2
    refs = sorted(r["current_value"] for r in result)
    assert refs == ["v1", "v2"]


def test_discover_github_workflow_uses_source_repo_filter(*, tmp_path: Path) -> None:
    """`--source-repo` filters to only `uses:` lines where the repo segment matches."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "dispatch.yml").write_text(
        "    uses: owner/livespec-dev-tooling/.github/workflows/reusable-a.yml@master\n"
        "    uses: owner/other-repo/.github/workflows/reusable-b.yml@v1\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo="livespec-dev-tooling")
    assert len(result) == 1
    assert result[0]["source_repo"] == "livespec-dev-tooling"


def test_discover_github_workflow_uses_yaml_extension(*, tmp_path: Path) -> None:
    """Workflow files with a `.yaml` extension are also discovered."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "dispatch.yaml").write_text(
        "    uses: owner/some-repo/.github/workflows/reusable.yml@v0.3.0\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["current_value"] == "v0.3.0"


# ---------------------------------------------------------------------------
# fabro-sandbox docker image tag tests (fifth pin format)
# ---------------------------------------------------------------------------


_FABRO_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"


def _write_fabro_workflow(
    *, root: Path, base_parts: tuple[str, ...], workflow: str, tag: str
) -> None:
    """Write a minimal Fabro `workflow.toml` carrying the docker image pin."""
    workflow_dir = root.joinpath(*base_parts, workflow)
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "workflow.toml").write_text(
        "[image]\n" 'provider = "docker"\n' f'docker = "{_FABRO_IMAGE}:{tag}"\n',
        encoding="utf-8",
    )


def test_discover_fabro_docker_claude_plugin_path_emits_record(*, tmp_path: Path) -> None:
    """The orchestrator layout (`.claude-plugin/.fabro/workflows/`) emits one record."""
    _write_fabro_workflow(
        root=tmp_path,
        base_parts=(".claude-plugin", ".fabro", "workflows"),
        workflow="implement-work-item",
        tag="v0.39.0",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "fabro_sandbox_docker_image"
    assert (
        record["file_path"] == ".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml"
    )
    assert record["pin_key"] == _FABRO_IMAGE
    assert record["current_value"] == "v0.39.0"
    assert record["source_repo"] == "livespec-dev-tooling"


def test_discover_fabro_docker_root_fabro_path_emits_record(*, tmp_path: Path) -> None:
    """The console layout (top-level `.fabro/workflows/`) also emits one record."""
    _write_fabro_workflow(
        root=tmp_path,
        base_parts=(".fabro", "workflows"),
        workflow="implement-work-item",
        tag="sha-ea684ad",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "fabro_sandbox_docker_image"
    assert record["file_path"] == ".fabro/workflows/implement-work-item/workflow.toml"
    assert record["pin_key"] == _FABRO_IMAGE
    assert record["current_value"] == "sha-ea684ad"
    assert record["source_repo"] == "livespec-dev-tooling"


def test_discover_fabro_docker_absent_yields_nothing(*, tmp_path: Path) -> None:
    """A consumer repo with no `.fabro` workflow dir yields no docker record."""
    (tmp_path / "unrelated.txt").write_text("no fabro here\n", encoding="utf-8")
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_fabro_docker_workflow_without_docker_line_yields_nothing(
    *, tmp_path: Path
) -> None:
    """A `workflow.toml` present but carrying no docker line yields no record."""
    workflow_dir = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "workflow.toml").write_text('[run]\ngoal = "do a thing"\n', encoding="utf-8")
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_fabro_docker_empty_workflows_dir_yields_nothing(*, tmp_path: Path) -> None:
    """A `.fabro/workflows/` dir with no `*/workflow.toml` yields no record."""
    (tmp_path / ".fabro" / "workflows").mkdir(parents=True)
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_fabro_docker_multiple_workflows(*, tmp_path: Path) -> None:
    """More than one workflow dir each with a docker line emits one record each."""
    _write_fabro_workflow(
        root=tmp_path,
        base_parts=(".claude-plugin", ".fabro", "workflows"),
        workflow="implement-work-item",
        tag="v0.39.0",
    )
    _write_fabro_workflow(
        root=tmp_path,
        base_parts=(".claude-plugin", ".fabro", "workflows"),
        workflow="groom-work-item",
        tag="v0.39.0",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 2
    workflows = sorted(r["file_path"] for r in result)
    assert workflows == [
        ".claude-plugin/.fabro/workflows/groom-work-item/workflow.toml",
        ".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
    ]
    assert all(r["source_repo"] == "livespec-dev-tooling" for r in result)


def test_discover_fabro_docker_source_repo_filter_match(*, tmp_path: Path) -> None:
    """`--source-repo livespec-dev-tooling` includes the fabro docker record."""
    _write_fabro_workflow(
        root=tmp_path,
        base_parts=(".claude-plugin", ".fabro", "workflows"),
        workflow="implement-work-item",
        tag="v0.39.0",
    )
    result = _walk(root=tmp_path, source_repo="livespec-dev-tooling")
    assert len(result) == 1
    assert result[0]["pin_format"] == "fabro_sandbox_docker_image"
    assert result[0]["source_repo"] == "livespec-dev-tooling"


def test_discover_fabro_docker_source_repo_filter_no_match(*, tmp_path: Path) -> None:
    """`--source-repo other` excludes the fabro docker record entirely."""
    _write_fabro_workflow(
        root=tmp_path,
        base_parts=(".claude-plugin", ".fabro", "workflows"),
        workflow="implement-work-item",
        tag="v0.39.0",
    )
    result = _walk(root=tmp_path, source_repo="other")
    assert result == []


def test_discover_fabro_docker_multiple_lines_in_one_workflow_toml(*, tmp_path: Path) -> None:
    """Two docker lines in ONE `workflow.toml` emit one record each, not just the first.

    Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the
    per-matching-line rule binds the WHOLE `fabro_sandbox_docker_image` format,
    not only its `.github/workflows/` surface — so the `workflow.toml` walk is
    find-ALL, removing the latent first-match-per-file assumption.
    """
    workflow_dir = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "workflow.toml").write_text(
        "[image]\n"
        f'docker = "{_FABRO_IMAGE}:python-v0.43.2"\n'
        "[fallback.image]\n"
        f'docker = "{_FABRO_IMAGE}:python-rust-v0.48.2"\n',
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 2
    assert [r["current_value"] for r in result] == ["python-v0.43.2", "python-rust-v0.48.2"]
    assert all(r["pin_format"] == "fabro_sandbox_docker_image" for r in result)
    assert all(
        r["file_path"] == ".fabro/workflows/implement-work-item/workflow.toml" for r in result
    )


# ---------------------------------------------------------------------------
# fabro-sandbox docker image tag — the `.github/workflows/` container: surface
#
# The SAME `fabro_sandbox_docker_image` format, found at a SECOND location: a
# cut-over consumer runs its CI jobs inside the baked sandbox image, so the
# image reference is repeated per job under `container:`. Per
# `SPECIFICATION/contracts.md` §"Pin autodiscovery rules" EVERY such line is
# walked, yielding ONE RECORD PER MATCHING LINE across files AND within one
# file — a walk that stopped at the first match per file would leave jobs 2..N
# pinned to the stale tag.
# ---------------------------------------------------------------------------


def _container_job(*, job: str, tag: str) -> str:
    """Render one CI job whose `container:` block pins the fabro-sandbox image."""
    return (
        f"  {job}:\n"
        "    runs-on: ubuntu-latest\n"
        "    container:\n"
        f"      image: {_FABRO_IMAGE}:{tag}\n"
    )


def test_discover_workflow_container_image_multiple_jobs_one_file(*, tmp_path: Path) -> None:
    """Several `container:`-block `image:` lines in ONE workflow file emit one record each."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "jobs:\n"
        + _container_job(job="check-python", tag="python-v0.43.2")
        + _container_job(job="check-docs", tag="python-v0.43.2"),
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 2
    for record in result:
        assert record["pin_format"] == "fabro_sandbox_docker_image"
        assert record["file_path"] == ".github/workflows/ci.yml"
        assert record["pin_key"] == _FABRO_IMAGE
        assert record["current_value"] == "python-v0.43.2"
        assert record["source_repo"] == "livespec-dev-tooling"


def test_discover_workflow_container_image_multiple_files(*, tmp_path: Path) -> None:
    """Matching lines spread across MORE THAN ONE workflow file are all emitted.

    Mirrors the real `livespec` layout: two jobs in `ci.yml` plus three in
    `ci-selfhosted-shadow.yml`, for five records total.
    """
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "jobs:\n"
        + _container_job(job="check-python", tag="python-v0.43.2")
        + _container_job(job="check-docs", tag="python-v0.43.2"),
        encoding="utf-8",
    )
    (workflows_dir / "ci-selfhosted-shadow.yml").write_text(
        "jobs:\n"
        + _container_job(job="shadow-a", tag="python-v0.43.2")
        + _container_job(job="shadow-b", tag="python-v0.43.2")
        + _container_job(job="shadow-c", tag="python-v0.43.2"),
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 5
    per_file = sorted(r["file_path"] for r in result)
    assert per_file == [
        ".github/workflows/ci-selfhosted-shadow.yml",
        ".github/workflows/ci-selfhosted-shadow.yml",
        ".github/workflows/ci-selfhosted-shadow.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/ci.yml",
    ]


def test_discover_workflow_container_image_one_line_shorthand(*, tmp_path: Path) -> None:
    """The one-line `container: <image>` shorthand is covered by the same scoped match."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yaml").write_text(
        "jobs:\n" "  check:\n" f"    container: {_FABRO_IMAGE}:python-rust-v0.48.2\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "fabro_sandbox_docker_image"
    assert result[0]["file_path"] == ".github/workflows/ci.yaml"
    assert result[0]["current_value"] == "python-rust-v0.48.2"


def test_discover_workflow_container_image_scoped_to_fabro_sandbox(*, tmp_path: Path) -> None:
    """An unrelated `container:` / `image:` line yields NO record — the match is scoped."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "jobs:\n"
        "  build:\n"
        "    container:\n"
        "      image: ghcr.io/thewoolleyman/some-other-image:v1.0.0\n"
        "  publish:\n"
        "    container: ubuntu:24.04\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_workflow_container_image_source_repo_filter_match(*, tmp_path: Path) -> None:
    """`--source-repo livespec-dev-tooling` includes the CI container-image record.

    The source repo is HARDCODED (the image is built and released by
    livespec-dev-tooling), which is what lets a dev-tooling release fan-out
    rewrite the CI image in the SAME bump commit as the pyproject/compat pins.
    """
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "jobs:\n" + _container_job(job="check-python", tag="python-v0.43.2"),
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo="livespec-dev-tooling")
    assert len(result) == 1
    assert result[0]["source_repo"] == "livespec-dev-tooling"


def test_discover_workflow_container_image_source_repo_filter_no_match(*, tmp_path: Path) -> None:
    """`--source-repo other` excludes the CI container-image record entirely."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "jobs:\n" + _container_job(job="check-python", tag="python-v0.43.2"),
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo="other")
    assert result == []
