"""Repo-conformance tests for the stray root `embeddeddolt/` store (livespec-dev-tooling-to6hh2).

The creator is EXTERNAL to this repository: nothing under `livespec_dev_tooling/`
writes an embedded-Dolt store, and `.beads/.gitignore` already lists
`embeddeddolt/`, so the beads `bd` binary — upstream code, reached here through
the `livespec-orchestrator-beads-fabro` tenant — is what materializes it, and
that ignore line says where it MEANT to write. Of the two candidate mechanisms
the item names, the evidence picks the first: the store appears at the PROCESS
CWD carrying the name expected inside `.beads/` (the right NAME in the wrong
PARENT, which is what a cwd-resolved path yields), and it is INERT —
`repo_state.json` carries `"branches":{}` — while ledger reads went on being
served by the configured `127.0.0.1:3307` tenant. A fallback that had actually
ignored `dolt.mode: server` would have SERVED queries from this store and left
data in it. An ignore file cannot reach a sibling of its own directory, so
`git status --short` reported `?? embeddeddolt/` indefinitely.

Two invariants are pinned here, neither a string-match for its own sake:

1. The ROOT `.gitignore` actually ignores `embeddeddolt/`, asserted
   BEHAVIORALLY — a hermetic `git init` repo is seeded with the real file's
   bytes and asked the same question the item measured (`git check-ignore -v
   embeddeddolt/` exited 1 before the fix). Hermetic, with global and system
   git config scrubbed, so the assertion holds wherever the suite runs and no
   `core.excludesFile` entry can grant a false pass. The nested case is
   asserted too, because a cwd-resolved path follows whatever directory `bd`
   was invoked from.
2. `AGENTS.md`'s ledger-access guidance names the SILENT signatures beside the
   loud one. An empty embedded store does not error — it answers with a
   valid-looking EMPTY RESULT — so a reader taught only `Error 1045 ... Access
   denied` will not recognise it. The same shape covers `bd list`, which omits
   closed items unless `--all` is passed.
"""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT_GITIGNORE = _REPO_ROOT / ".gitignore"
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"

_STRAY_ENTRY = "embeddeddolt/"
_WORK_ITEM = "livespec-dev-tooling-to6hh2"
_LEDGER_HEADING = "## Ledger access needs the credential wrapper"

# Scrubbing both config scopes is what makes the probe hermetic: a
# `core.excludesFile` on the host that happened to list `embeddeddolt/` would
# otherwise satisfy `check-ignore` while the tracked root `.gitignore` — the
# file under test, and the only one every clone gets — did not.
_SCRUBBED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}


def _seed_repo(*, root: Path) -> None:
    """Create a bare-minimum git repo at `root` carrying the REAL root `.gitignore`."""
    _ = subprocess.run(["git", "init", "--quiet"], cwd=str(root), check=True, env=_SCRUBBED_GIT_ENV)
    _ = (root / ".gitignore").write_bytes(_ROOT_GITIGNORE.read_bytes())


def _check_ignore(*, root: Path, path: str) -> subprocess.CompletedProcess[str]:
    """Ask git whether `path` is ignored, reporting the matching rule (`-v`)."""
    return subprocess.run(
        ["git", "check-ignore", "-v", path],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        env=_SCRUBBED_GIT_ENV,
    )


def _ledger_section() -> str:
    """The `AGENTS.md` ledger-access section body, heading to next `## ` heading."""
    text = _AGENTS_MD.read_text(encoding="utf-8")
    start = text.index(_LEDGER_HEADING)
    rest = text[start + len(_LEDGER_HEADING) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def test_root_gitignore_covers_a_stray_store_at_the_repository_root(*, tmp_path: Path) -> None:
    """The measured failure: `check-ignore embeddeddolt/` exited 1 at the repo root."""
    _seed_repo(root=tmp_path)

    result = _check_ignore(root=tmp_path, path=_STRAY_ENTRY)

    assert result.returncode == 0, (
        "the root .gitignore must ignore a stray embeddeddolt/ store at the repository "
        f"root; git check-ignore exited {result.returncode}"
    )
    assert ".gitignore" in result.stdout, result.stdout


def test_root_gitignore_covers_a_stray_store_in_a_subdirectory(*, tmp_path: Path) -> None:
    """A cwd-resolved path follows the invoking directory, so the rule stays unanchored."""
    _seed_repo(root=tmp_path)

    result = _check_ignore(root=tmp_path, path=f"scripts/{_STRAY_ENTRY}")

    assert result.returncode == 0, (
        "a bd run from a subdirectory resolves embeddeddolt/ there, so the ignore rule "
        f"must not be root-anchored; git check-ignore exited {result.returncode}"
    )


def test_root_gitignore_entry_carries_a_comment_naming_the_work_item() -> None:
    """The entry is explained in place: a bare line reads as unexplained litter."""
    lines = _ROOT_GITIGNORE.read_text(encoding="utf-8").splitlines()
    assert _STRAY_ENTRY in lines, f"root .gitignore must carry a bare `{_STRAY_ENTRY}` entry"
    # `takewhile` over the REVERSED head, rather than a loop with a `break`: the
    # loop's fall-off-the-end arm is unreachable here (the file opens with
    # non-comment entries), which is a partial branch the 100% per-file gate
    # counts against the test itself.
    preamble = itertools.takewhile(
        lambda line: line.startswith("#"), reversed(lines[: lines.index(_STRAY_ENTRY)])
    )
    assert any(
        _WORK_ITEM in line for line in preamble
    ), f"the `{_STRAY_ENTRY}` entry must be preceded by a comment naming {_WORK_ITEM}"


def test_ledger_guidance_names_the_silent_embedded_store_signature() -> None:
    """The silent signature rides beside the loud one, or only the loud one is learned."""
    section = _ledger_section()

    assert "Error 1045" in section, "the documented loud signature must survive"
    assert _STRAY_ENTRY in section, "the silent embedded-store signature must be named"
    assert "empty" in section.lower(), (
        "the silent signature is a valid-looking EMPTY result, and saying so is the "
        "whole point of naming it"
    )
    assert _WORK_ITEM in section, f"the silent signature must cite {_WORK_ITEM}"


def test_ledger_guidance_names_the_bd_list_closed_item_default() -> None:
    """`bd list` hides closed items: absence from a default listing is not absence."""
    section = _ledger_section()

    assert "`bd list`" in section, "the `bd list` default must be named"
    assert "--all" in section, "the flag that reveals closed items must be named"
