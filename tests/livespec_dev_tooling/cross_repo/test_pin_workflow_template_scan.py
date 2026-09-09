"""The `uses:` ref format's WIDENED scan set — directory, suffix, exclusion.

Companion to `test_pin_directory_scan_formats.py`, which pins the format's
original root-only / `*.yml`-only behavior. This file covers the three axes
`SPECIFICATION/contracts.md` section "Pin autodiscovery rules" defines for the
same ONE format (livespec-dev-tooling-ep8n):

- **DIRECTORY** — every `.github/workflows/` directory at ANY DEPTH beneath
  the walk root, not only the one at the repository root.
- **SUFFIX** — `*.jinja` workflow-TEMPLATE files alongside `*.yml` / `*.yaml`
  workflow files.
- **EXCLUSION** — never descend into a directory carrying a `.git` entry (a
  DIRECTORY for a nested clone, a FILE for a linked worktree), because such a
  tree belongs to a DIFFERENT repository.

The exclusion is not a hypothetical. Measured 2026-08-21 in the real fleet, an
any-depth walk WITHOUT it reached vendored clones under `livespec`'s `.pi/git/`
cache and agent worktrees under `livespec-overseer`'s `.claude/worktrees/` —
real pins belonging to real other repositories. The walk is purely
filesystem-based (no git index, no ignore filtering), so neither tracking nor
`.gitignore` prevents that on its own and the `.git`-entry test is the
operative discrimination.

Fixture paths here are deliberately GENERIC (`templates/plugin/...`). The
scanner is UPSTREAM of every consumer, so no consumer's directory layout may
be written into this repository — not into the implementation and not into
the fixtures that judge it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import pin_autodiscovery, pin_rewrite

__all__: list[str] = []

_TEMPLATE_PARTS: tuple[str, ...] = ("templates", "plugin", ".github", "workflows")
_ROOT_PARTS: tuple[str, ...] = (".github", "workflows")


def _walk(*, root: Path, source_repo: str | None = None) -> list[dict[str, str]]:
    """The walk's records, failing loud if a pin file could not be READ."""
    return unsafe_perform_io(
        pin_autodiscovery.discover(root=root, source_repo=source_repo).unwrap()
    )


def _uses_lines(*, repo: str, workflow: str, ref: str) -> str:
    """One reusable-workflow `uses:` line, the shape both a workflow and a template carry."""
    return f"    uses: thewoolleyman/{repo}/.github/workflows/{workflow}@{ref}\n"


def _write_workflow(*, root: Path, parts: tuple[str, ...], name: str, body: str) -> Path:
    """Write `body` to `root/<parts>/<name>`, creating the directory chain."""
    directory = root.joinpath(*parts)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _seed_nested_repository(*, root: Path, parts: tuple[str, ...], linked_worktree: bool) -> Path:
    """Seed ANOTHER repository's tree under the walk root, carrying its own pins.

    `linked_worktree=False` writes the `.git` DIRECTORY a nested clone carries;
    `linked_worktree=True` writes the `.git` FILE a linked worktree carries.
    Both are the same signal — this subtree is not the consumer repository —
    and the walk must honor them identically.
    """
    nested = root.joinpath(*parts)
    nested.mkdir(parents=True)
    if linked_worktree:
        (nested / ".git").write_text(
            "gitdir: /elsewhere/.git/worktrees/agent-a1e564573\n", encoding="utf-8"
        )
    else:
        (nested / ".git").mkdir()
    return _write_workflow(
        root=nested,
        parts=_ROOT_PARTS,
        name="ci.yml",
        body=_uses_lines(repo="some-other-repo", workflow="reusable-ci.yml", ref="v9.9.9"),
    )


# ---------------------------------------------------------------------------
# DIRECTORY axis — any depth, not only the repository root
# ---------------------------------------------------------------------------


def test_walk_uses_discovers_a_nested_workflows_directory(*, tmp_path: Path) -> None:
    """A `.github/workflows/` directory BELOW the root is scanned, not only the root one."""
    _write_workflow(
        root=tmp_path,
        parts=_TEMPLATE_PARTS,
        name="release-dispatch.yml",
        body=_uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-release-dispatch.yml", ref="v1.20.4"
        ),
    )
    result = _walk(root=tmp_path)
    assert len(result) == 1
    assert result[0]["file_path"] == "templates/plugin/.github/workflows/release-dispatch.yml"
    assert result[0]["current_value"] == "v1.20.4"
    assert result[0]["pin_format"] == "github_workflow_uses_ref"


def test_walk_uses_requires_the_github_parent_directory(*, tmp_path: Path) -> None:
    """A directory merely NAMED `workflows` is not a scan target — its parent must be `.github`."""
    _write_workflow(
        root=tmp_path,
        parts=("docs", "workflows"),
        name="how-we-release.yml",
        body=_uses_lines(repo="livespec-dev-tooling", workflow="reusable-a.yml", ref="v1.20.4"),
    )
    assert _walk(root=tmp_path) == []


def test_walk_uses_ignores_a_sibling_github_directory(*, tmp_path: Path) -> None:
    """A `.github/` subtree other than `workflows/` is descended but yields nothing."""
    _write_workflow(
        root=tmp_path,
        parts=(".github", "actions", "bump-pin-rewrite"),
        name="action.yml",
        body=_uses_lines(repo="livespec-dev-tooling", workflow="reusable-a.yml", ref="v1.20.4"),
    )
    assert _walk(root=tmp_path) == []


def test_walk_uses_tolerates_an_absent_root(*, tmp_path: Path) -> None:
    """A root that does not exist yields no records rather than raising."""
    assert _walk(root=tmp_path / "no-such-checkout") == []


# ---------------------------------------------------------------------------
# SUFFIX axis — `*.jinja` workflow templates alongside `*.yml` / `*.yaml`
# ---------------------------------------------------------------------------


def test_walk_uses_discovers_a_jinja_workflow_template(*, tmp_path: Path) -> None:
    """A `*.jinja` workflow TEMPLATE carries the same pin in the same format."""
    _write_workflow(
        root=tmp_path,
        parts=_ROOT_PARTS,
        name="pin-freshness.yml.jinja",
        body=_uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-pin-freshness.yml", ref="v1.20.4"
        ),
    )
    result = _walk(root=tmp_path)
    assert len(result) == 1
    assert result[0]["file_path"] == ".github/workflows/pin-freshness.yml.jinja"
    assert (
        result[0]["pin_key"]
        == "thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-pin-freshness.yml"
    )
    assert result[0]["source_repo"] == "livespec-dev-tooling"


def test_walk_uses_ignores_a_non_workflow_suffix(*, tmp_path: Path) -> None:
    """A file in the workflows directory whose suffix is not a covered one yields nothing."""
    _write_workflow(
        root=tmp_path,
        parts=_ROOT_PARTS,
        name="README.md",
        body=_uses_lines(repo="livespec-dev-tooling", workflow="reusable-a.yml", ref="v1.20.4"),
    )
    (tmp_path / ".github" / "workflows" / "scratch").mkdir()
    assert _walk(root=tmp_path) == []


def test_walk_uses_discovers_nested_templates_together_with_root_workflows(
    *, tmp_path: Path
) -> None:
    """Both axes at once — the shape a real copier-template consumer carries.

    The root workflows and the nested templates pin DIFFERENT refs, which is
    exactly the silent rot this widening exists to end: correcting a template
    pin from a moving branch to a release tag made it reproducible AND
    invisible to the automation that would bump it.
    """
    _write_workflow(
        root=tmp_path,
        parts=_ROOT_PARTS,
        name="pin-freshness.yml",
        body=_uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-pin-freshness.yml", ref="v1.67.2"
        ),
    )
    _write_workflow(
        root=tmp_path,
        parts=_TEMPLATE_PARTS,
        name="pin-freshness.yml.jinja",
        body=_uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-pin-freshness.yml", ref="v1.20.4"
        ),
    )
    _write_workflow(
        root=tmp_path,
        parts=_TEMPLATE_PARTS,
        name="auto-enable-merge.yml.jinja",
        body=_uses_lines(
            repo="livespec", workflow="reusable-spec-pr-merge-policy.yml", ref="v0.32.0"
        ),
    )
    result = _walk(root=tmp_path)
    assert sorted((r["file_path"], r["current_value"]) for r in result) == [
        (".github/workflows/pin-freshness.yml", "v1.67.2"),
        ("templates/plugin/.github/workflows/auto-enable-merge.yml.jinja", "v0.32.0"),
        ("templates/plugin/.github/workflows/pin-freshness.yml.jinja", "v1.20.4"),
    ]


def test_walk_uses_honors_the_source_repo_filter_for_a_template_pin(*, tmp_path: Path) -> None:
    """A template pin obeys the standard source-repo-filter semantics unchanged."""
    _write_workflow(
        root=tmp_path,
        parts=_TEMPLATE_PARTS,
        name="auto-enable-merge.yml.jinja",
        body=_uses_lines(
            repo="livespec", workflow="reusable-spec-pr-merge-policy.yml", ref="v0.32.0"
        )
        + _uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-release-park.yml", ref="v1.20.4"
        ),
    )
    result = _walk(root=tmp_path, source_repo="livespec")
    assert len(result) == 1
    assert result[0]["source_repo"] == "livespec"


# ---------------------------------------------------------------------------
# EXCLUSION axis — a nested repository's pins are not this consumer's pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("linked_worktree", [False, True])
def test_walk_uses_excludes_a_nested_repository(*, tmp_path: Path, linked_worktree: bool) -> None:
    """A nested clone (`.git` dir) or linked worktree (`.git` file) yields ZERO records.

    The non-repository nested tree beside it — a template directory carrying no
    `.git` entry — still yields its records, so the rule excludes exactly the
    other repository and keeps exactly the target.
    """
    _seed_nested_repository(
        root=tmp_path,
        parts=(".cache", "git", "some-other-repo"),
        linked_worktree=linked_worktree,
    )
    _write_workflow(
        root=tmp_path,
        parts=_TEMPLATE_PARTS,
        name="release-park.yml.jinja",
        body=_uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-release-park.yml", ref="v1.20.4"
        ),
    )
    result = _walk(root=tmp_path)
    assert [r["file_path"] for r in result] == [
        "templates/plugin/.github/workflows/release-park.yml.jinja"
    ]
    assert all(r["source_repo"] != "some-other-repo" for r in result)


def test_walk_uses_does_not_descend_into_the_consumers_own_git_directory(*, tmp_path: Path) -> None:
    """The consumer's OWN `.git/` is git's internal store, never a source of pins.

    The root itself carries a `.git` entry — that is what makes it a
    repository, not a nested one — so the exclusion is applied to the root's
    DESCENDANTS. `.git/` is skipped by name: descending it would walk the
    object store and, for a repository with submodules, another repository's
    git directory under `.git/modules/`.
    """
    _write_workflow(
        root=tmp_path,
        parts=(".git", "modules", "vendored", ".github", "workflows"),
        name="ci.yml",
        body=_uses_lines(repo="some-other-repo", workflow="reusable-ci.yml", ref="v9.9.9"),
    )
    assert _walk(root=tmp_path) == []


def test_walk_uses_does_not_follow_a_directory_symlink(*, tmp_path: Path) -> None:
    """A symlinked directory is not descended — it can escape the tree, or loop forever.

    A symlink may point at another repository's checkout (reintroducing the
    misattribution the `.git` exclusion removes) or at one of its own
    ancestors, which an unguarded recursive walk would follow until it
    exhausted the path limit.
    """
    outside = tmp_path / "outside"
    _write_workflow(
        root=outside,
        parts=_ROOT_PARTS,
        name="ci.yml",
        body=_uses_lines(repo="some-other-repo", workflow="reusable-ci.yml", ref="v9.9.9"),
    )
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "linked").symlink_to(outside, target_is_directory=True)
    (checkout / "loop").symlink_to(checkout, target_is_directory=True)
    assert _walk(root=checkout) == []


# ---------------------------------------------------------------------------
# END-TO-END — a bump rewrites a template pin and touches nothing else
# ---------------------------------------------------------------------------


def test_bump_rewrites_a_template_pin_and_never_touches_a_nested_repository(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery feeds the real rewrite entry point; the nested repository is byte-identical.

    The rewriter was BELIEVED to need no change for a `.jinja` template (its
    pattern is path- and suffix-agnostic). This exercises that belief rather
    than reasoning about it: the record the widened walk emits is handed to
    `pin_rewrite.main()` through the same `PIN_*` environment contract the
    `bump-pin-rewrite` composite Action uses, and the template file must come
    back rewritten.

    The nested repository's workflow is read before and after and compared
    byte for byte, because a rewrite there would MUTATE another repository's
    checkout — the failure the exclusion axis exists to prevent.
    """
    nested_workflow = _seed_nested_repository(
        root=tmp_path, parts=(".cache", "git", "some-other-repo"), linked_worktree=False
    )
    before = nested_workflow.read_bytes()
    template = _write_workflow(
        root=tmp_path,
        parts=_TEMPLATE_PARTS,
        name="release-park.yml.jinja",
        body="jobs:\n  park:\n"
        + _uses_lines(
            repo="livespec-dev-tooling", workflow="reusable-release-park.yml", ref="v1.20.4"
        ),
    )
    records = _walk(root=tmp_path, source_repo="livespec-dev-tooling")
    assert len(records) == 1
    for key, value in {
        "PIN_FORMAT": records[0]["pin_format"],
        "PIN_FILE": str(tmp_path / records[0]["file_path"]),
        "PIN_KEY": records[0]["pin_key"],
        "PIN_CURRENT": records[0]["current_value"],
        "PIN_TAG": "v1.67.3",
    }.items():
        monkeypatch.setitem(os.environ, key, value)
    assert pin_rewrite.main() == 0
    assert "reusable-release-park.yml@v1.67.3\n" in template.read_text(encoding="utf-8")
    assert "@v1.20.4" not in template.read_text(encoding="utf-8")
    assert nested_workflow.read_bytes() == before
