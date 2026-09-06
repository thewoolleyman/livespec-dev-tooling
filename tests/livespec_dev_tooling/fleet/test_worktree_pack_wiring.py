"""Tests for `livespec_dev_tooling/fleet/worktree_pack_wiring.py`.

The pure wiring predicate over the four committed file texts: fully wired
yields no gaps, and each of the five wiring facts missing yields a gap naming
the file and the exact missing line. No `FleetContext` appears here — the
central-vantage half (and its can't-read-is-not-absent lattice) is the row's
job and is tested in `test_rows_worktree_pack.py`.

The last test is a LOCKSTEP test rather than a unit test, and it is the one
that would catch a predicate quietly wrong about the fleet's real shape: it
runs the predicate against THIS repository's own committed wiring files — the
rendered fleet shape, the same shape livespec's copier template renders and
its lockstep test imports this predicate to assert.

The WIRED_* fixture texts are written LITERALLY rather than derived from
`WORKTREE_PACK_FILES`: a fixture computed from the same constant the code
reads would agree with it however wrong it was. They are shared with the row
tests and the two conformance-engine fixtures, which import them from here.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.fleet.worktree_pack_wiring import (
    GITIGNORE_PATH,
    JUSTFILE_PATH,
    LEFTHOOK_PATH,
    LIVESPEC_JSONC_PATH,
    worktree_pack_wiring_gaps,
)

__all__: list[str] = []


WIRED_JUSTFILE = """\
# The pack fragments are gitignored-and-installed, so the imports are optional.
import? 'dev-tooling/worktree.just'
import? 'dev-tooling/branch-protection.just'

install-worktree-pack:
    # Reuse the shared installer — the single canonical source.
    uv run python -m livespec_dev_tooling.install_worktree_pack

check:
    echo ok
"""
WIRED_GITIGNORE = """\
# Worktree-discipline pack.
/dev-tooling/worktree-lib.sh
/dev-tooling/branch-protection.sh
/dev-tooling/gate-run.sh
/dev-tooling/check-no-workflow-edits.sh
/dev-tooling/worktree.just
/dev-tooling/branch-protection.just
"""
WIRED_LEFTHOOK = """\
pre-commit:
  commands:
    00-install-worktree-pack:
      run: just install-worktree-pack
    01-check-pre-commit:
      run: just check-pre-commit

commit-msg:
  commands:
    00-no-commit-on-master:
      run: |
        branch=$(git rev-parse --abbrev-ref HEAD)
        exit 0

pre-push:
  commands:
    00-install-worktree-pack:
      run: just install-worktree-pack
    01-check-pre-push:
      run: just check-pre-push
"""
WIRED_LIVESPEC_JSONC = """\
{
  // Worktree-discipline pack policy.
  "worktree_discipline": { "pack": "required" },
  "template": "livespec"
}
"""


def _gaps(
    *,
    justfile: str = WIRED_JUSTFILE,
    gitignore: str = WIRED_GITIGNORE,
    lefthook: str = WIRED_LEFTHOOK,
    livespec_jsonc: str = WIRED_LIVESPEC_JSONC,
) -> tuple[str, ...]:
    """The rendered `<path> :: <missing line>` gaps for one file-text set."""
    return tuple(
        f"{gap.path} :: {gap.missing}"
        for gap in worktree_pack_wiring_gaps(
            justfile_text=justfile,
            gitignore_text=gitignore,
            lefthook_text=lefthook,
            livespec_jsonc_text=livespec_jsonc,
        )
    )


def test_missing_import_line_names_the_file_and_the_line() -> None:
    justfile = WIRED_JUSTFILE.replace("import? 'dev-tooling/branch-protection.just'\n", "")
    assert _gaps(justfile=justfile) == ("justfile :: import? 'dev-tooling/branch-protection.just'",)


def test_import_line_mentioned_only_in_a_comment_is_not_wiring() -> None:
    # Several fleet members carry a comment naming the fragment right above
    # the real import; a substring match would accept the comment alone.
    justfile = WIRED_JUSTFILE.replace(
        "import? 'dev-tooling/worktree.just'",
        "# import? 'dev-tooling/worktree.just' — commented out",
    )
    assert _gaps(justfile=justfile) == ("justfile :: import? 'dev-tooling/worktree.just'",)


def test_missing_install_recipe_names_the_delegation() -> None:
    justfile = WIRED_JUSTFILE.replace("install-worktree-pack:", "install-something-else:")
    gaps = _gaps(justfile=justfile)
    assert len(gaps) == 1
    assert "install-worktree-pack:" in gaps[0]
    assert "python -m livespec_dev_tooling.install_worktree_pack" in gaps[0]


def test_install_recipe_that_does_not_delegate_is_a_gap() -> None:
    justfile = WIRED_JUSTFILE.replace(
        "    uv run python -m livespec_dev_tooling.install_worktree_pack\n",
        "    bash dev-tooling/install-pack.sh\n",
    )
    gaps = _gaps(justfile=justfile)
    assert len(gaps) == 1
    assert gaps[0].startswith("justfile :: an `install-worktree-pack:` recipe")


def test_install_recipe_as_the_last_stanza_in_the_file_still_reads() -> None:
    # The recipe body ends at the end of the file rather than at the next
    # non-indented line; several fleet justfiles put a recipe last.
    justfile = (
        "import? 'dev-tooling/worktree.just'\n"
        "import? 'dev-tooling/branch-protection.just'\n"
        "install-worktree-pack:\n"
        "    uv run python -m livespec_dev_tooling.install_worktree_pack\n"
    )
    assert _gaps(justfile=justfile) == ()


def test_missing_gitignore_entry_is_a_warning_gap_naming_the_line() -> None:
    gitignore = WIRED_GITIGNORE.replace("/dev-tooling/gate-run.sh\n", "")
    assert _gaps(gitignore=gitignore) == (".gitignore :: /dev-tooling/gate-run.sh",)


def test_unanchored_gitignore_entry_satisfies_the_obligation() -> None:
    gitignore = WIRED_GITIGNORE.replace("/dev-tooling/gate-run.sh", "dev-tooling/gate-run.sh")
    assert _gaps(gitignore=gitignore) == ()


def test_hook_without_the_installer_first_names_the_hook() -> None:
    lefthook = WIRED_LEFTHOOK.replace(
        "    00-install-worktree-pack:\n      run: just install-worktree-pack\n    01-check-pre-push:",
        "    01-check-pre-push:",
    )
    gaps = _gaps(lefthook=lefthook)
    assert len(gaps) == 1
    assert gaps[0].startswith("lefthook.yml :: `pre-push` whose name-sorted FIRST command")


def test_installer_command_not_sorted_first_is_a_gap() -> None:
    # lefthook runs a hook's commands in NAME-sorted order, so a step written
    # first in the file but named `99-` does not run first.
    lefthook = WIRED_LEFTHOOK.replace("    00-install-worktree-pack:", "    99-install-pack:")
    gaps = _gaps(lefthook=lefthook)
    assert len(gaps) == 2
    assert all(gap.startswith("lefthook.yml ::") for gap in gaps)


def test_hook_absent_entirely_is_a_gap() -> None:
    lefthook = WIRED_LEFTHOOK.replace("pre-push:", "post-push:")
    assert len(_gaps(lefthook=lefthook)) == 1


def test_hook_without_a_commands_block_is_a_gap() -> None:
    lefthook = WIRED_LEFTHOOK.replace("pre-push:\n  commands:\n", "pre-push:\n  scripts:\n")
    assert len(_gaps(lefthook=lefthook)) == 1


def test_hook_with_an_empty_commands_block_is_a_gap() -> None:
    lefthook = "pre-commit:\n  commands:\n\npre-push:\n  commands:\n    # only a comment\n"
    assert len(_gaps(lefthook=lefthook)) == 2


def test_block_scalar_run_value_is_read_from_its_first_line() -> None:
    lefthook = WIRED_LEFTHOOK.replace(
        "    00-install-worktree-pack:\n      run: just install-worktree-pack\n    01-check-pre-push:",
        "    00-install-worktree-pack:\n      run: |\n        just install-worktree-pack\n"
        "    01-check-pre-push:",
    )
    assert _gaps(lefthook=lefthook) == ()


def test_empty_block_scalar_run_value_is_a_gap() -> None:
    lefthook = "pre-commit:\n  commands:\n    00-install-worktree-pack:\n      run: just install-worktree-pack\npre-push:\n  commands:\n    00-install-worktree-pack:\n      run: |\n"
    assert len(_gaps(lefthook=lefthook)) == 1


def test_missing_worktree_discipline_declaration_names_the_key() -> None:
    livespec_jsonc = '{\n  "template": "livespec"\n}\n'
    assert _gaps(livespec_jsonc=livespec_jsonc) == (
        '.livespec.jsonc :: "worktree_discipline": { "pack": "required" }',
    )


def test_unparseable_or_non_object_config_is_a_gap() -> None:
    assert len(_gaps(livespec_jsonc="{ not json at all")) == 1
    assert len(_gaps(livespec_jsonc="[1, 2, 3]")) == 1


def test_this_repository_is_wired_by_the_public_predicate() -> None:
    # The green lockstep half, run against the rendered fleet shape this
    # repository itself carries — the same four files livespec's copier
    # template renders, and the same public predicate that test imports.
    root = Path(__file__).resolve().parents[3]
    assert (root / JUSTFILE_PATH).is_file()
    assert (
        worktree_pack_wiring_gaps(
            justfile_text=(root / JUSTFILE_PATH).read_text(encoding="utf-8"),
            gitignore_text=(root / GITIGNORE_PATH).read_text(encoding="utf-8"),
            lefthook_text=(root / LEFTHOOK_PATH).read_text(encoding="utf-8"),
            livespec_jsonc_text=(root / LIVESPEC_JSONC_PATH).read_text(encoding="utf-8"),
        )
        == ()
    )
