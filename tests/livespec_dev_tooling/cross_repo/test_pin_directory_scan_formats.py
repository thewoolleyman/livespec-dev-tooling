"""Outside-in tests for `cross_repo/_pin_directory_scan_formats.py`.

The directory-scanning pin formats — the `.github/workflows/*.yml`
`uses:` ref and the fabro-sandbox docker image tag in `.fabro`
`workflow.toml` files — each scan a directory of files rather than
reading one well-known file. This mirror file exercises each format
individually, the source-repo filter, the missing-directory tolerance,
and the multi-file / multi-workflow coexistence cases. The walks are
driven through the public `pin_autodiscovery.discover()` entry point (the
same outside-in surface these tests used before the decomposition).

Coverage target: 100% line + branch of `_pin_directory_scan_formats.py`.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.cross_repo import pin_autodiscovery

__all__: list[str] = []


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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_github_workflow_uses_skips_simple_action_uses(*, tmp_path: Path) -> None:
    """An action-style `uses: actions/checkout@v4` (no path segment) is not emitted."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "steps:\n" "  - uses: actions/checkout@v4\n" "  - uses: jdx/mise-action@v2\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec-dev-tooling")
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_fabro_docker_workflow_without_docker_line_yields_nothing(
    *, tmp_path: Path
) -> None:
    """A `workflow.toml` present but carrying no docker line yields no record."""
    workflow_dir = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "workflow.toml").write_text('[run]\ngoal = "do a thing"\n', encoding="utf-8")
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_fabro_docker_empty_workflows_dir_yields_nothing(*, tmp_path: Path) -> None:
    """A `.fabro/workflows/` dir with no `*/workflow.toml` yields no record."""
    (tmp_path / ".fabro" / "workflows").mkdir(parents=True)
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec-dev-tooling")
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
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="other")
    assert result == []
