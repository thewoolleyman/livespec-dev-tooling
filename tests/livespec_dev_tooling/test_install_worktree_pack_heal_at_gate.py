"""Heal-at-gate proof for `livespec_dev_tooling/install_worktree_pack.py`.

The sibling `test_install_worktree_pack.py` proves the installer WRITES the
canonical pack. This file proves the mechanism the fleet actually relies on:
`just install-worktree-pack` wired as the FIRST lefthook command of
`pre-commit` and `pre-push`, so a worktree reaches the gate with a present,
current pack whether it was created by `just worktree-create`, by a RAW
`git worktree add`, or before a pin bump — with NO `just bootstrap` anywhere
in the path (livespec `plan/optimize-gates`, epic livespec-xms725).

WHY A REAL FIXTURE REPO AND REAL HOOKS. The claim under test is not "the
installer writes files" — that is already covered in-process next door. It is
that the WIRING carries the installer to the gate. Every link in that chain
lives outside Python: git fires `.git/hooks/pre-push`, the installed
commit-refuse hook body execs `mise exec -- lefthook run --no-auto-install
pre-push`, lefthook runs `just install-worktree-pack`, and the recipe runs the
installer under `uv run` so the installed bodies are the BRANCH's pinned
package. A test that stubbed any of those links would prove the stub. So this
suite builds a real git repo wired exactly as the fleet template wires one,
installs the real commit-refuse hooks into it, adds a linked worktree with a
raw `git worktree add`, and drives a real `git push` / `git commit`.

THE CHILDREN THIS FILE SPAWNS ARE `git` and `mise which` — no Python
subprocess, so the file is deliberately NOT on the
`subprocess_spawn_allowlist`; both installers are invoked in-process through
their `main()`. The hook chain does eventually reach a real `uv run python`,
and that is precisely why `_child_env` scrubs `COVERAGE_PROCESS_START` /
`COV_CORE_*`: an instrumented grandchild writes `.coverage.*` that races
concurrent coverage runs under the parallel check dispatcher (the 7us.6
flake).

ANTI-DRIFT. The fixture does not RESTATE the wiring — it is BUILT from the
wiring this repository itself carries, read out of the committed
`lefthook.yml` and `justfile` by `_repo_wiring`. The central
`worktree-pack-wired` row (the sibling work item) enforces that same shape
across the fleet; until it lands,
`test_this_repo_is_wired_as_the_central_row_will_require` asserts the shape
here. An edit to either file that moved the installer out of first position,
or dropped an `import?` line, reds this proof at the same moment it would red
that row — the two cannot drift apart, because they read one source.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import install_commit_refuse_hooks, install_worktree_pack
from livespec_dev_tooling.checks._primary_checkout_worktree_pack import (
    inspect_worktree_pack,
)
from livespec_dev_tooling.install_worktree_pack import WORKTREE_PACK_FILES, main

__all__: list[str] = []


# This repository's own root, resolved from the imported module exactly as the
# installer resolves its package data. The fixture's recipe runs the installer
# out of THIS tree, so the proof exercises the branch's package rather than
# whatever a stale site-packages happens to hold.
_PACKAGE_ROOT = Path(install_worktree_pack.__file__).resolve().parent.parent
_LEFTHOOK_NAME = "lefthook.yml"
_JUSTFILE_NAME = "justfile"
_PACK_DIR_NAME = "dev-tooling"

# The wiring shape the central `worktree-pack-wired` row requires. Asserted
# against this repository below rather than assumed, and then USED to build the
# fixture — so the fixture carries this repo's shape, not a second copy of it.
_INSTALLER_RECIPE = "install-worktree-pack"
_INSTALLER_RUN_LINE = f"just {_INSTALLER_RECIPE}"
_INSTALLER_COMMAND_NAME = f"00-{_INSTALLER_RECIPE}"
_GATE_HOOKS: tuple[str, ...] = ("pre-commit", "pre-push")
_PACK_FRAGMENTS: tuple[str, ...] = ("worktree.just", "branch-protection.just")
_IMPORT_LINE_PATTERN = re.compile(r"^import\? '" + _PACK_DIR_NAME + r"/[\w.-]+\.just'$")

# The ONE divergence between the fixture's `install-worktree-pack` recipe and
# this repository's: the fixture is a throwaway directory with no project of
# its own, so a bare `uv run` there would resolve nothing. Re-pointing it at
# this package root is what makes the fixture install THIS branch's bodies,
# which is the whole point of running the installer under `uv run`. The
# divergence is a single inserted flag pair, and
# `test_fixture_wiring_equals_the_wiring_this_repo_carries` pins it to exactly
# that by round-tripping the substitution away.
_UV_RUN = "uv run "
_FIXTURE_UV_FLAGS = f"--project {_PACKAGE_ROOT} --no-sync "

# A distinctive past timestamp. The no-write proofs stamp every installed file
# with it and assert the stamp SURVIVES a re-install: filesystem mtime
# granularity makes "the mtime did not advance" unreliable within a single
# second, while "the mtime is still 2001-09-09" cannot be produced by a write.
_STALE_EPOCH = 1_000_000_000

# The bytes a pin-drifted pack file carries — distinctive enough that a healed
# file cannot be mistaken for an unhealed one.
_STALE_BODY = "#!/usr/bin/env bash\n# stale body from an older pin\n"

# The tools the fixture's hook chain EXECS, in the order it reaches them: the
# installed pre-push body runs `mise exec -- lefthook`, lefthook runs its `run:`
# line under a bare `sh` (so `just` has to be on PATH, not merely a mise-managed
# name), and the recipe runs the installer under `uv run`.
_HOOK_CHAIN_TOOLS: tuple[str, ...] = ("lefthook", "just", "uv")

# A name no host can resolve, used to prove the missing-tool diagnostic.
_ABSENT_TOOL = "livespec-no-such-tool"

# The pack member the drift cases corrupt. `gate-run.sh` is the honest choice:
# it is the largest pack script, it is executable, and it is the one a stale
# worktree most plausibly carries from before a pin bump.
_DRIFT_TARGET = "gate-run.sh"


@dataclass(frozen=True, kw_only=True)
class _Wiring:
    """The gate wiring read out of a repository's `lefthook.yml` + `justfile`."""

    first_gate_commands: tuple[tuple[str, str, str], ...]
    import_lines: tuple[str, ...]
    installer_recipe_body: str


@dataclass(frozen=True, kw_only=True)
class _Fixture:
    """A wired fixture repo plus the linked worktree the gate fires in."""

    primary: Path
    worktree: Path
    home: Path
    bootstrap_sentinel: Path


def _first_gate_command(*, source: str, hook: str) -> tuple[str, str]:
    """Return `(command-name, run-line)` for `hook`'s FIRST lefthook command.

    A hand-rolled scan rather than a YAML parse, matching the house idiom in
    `checks/no_direct_tool_invocation.py`: no YAML library is vendored, and the
    only question asked here — which command comes first, and what does it run
    — is answerable from the indentation `lefthook.yml` already uses.
    """
    match = re.search(
        rf"^{re.escape(hook)}:\n  commands:\n {{4}}([\w-]+):\n {{6}}run: (.+)$",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None, f"lefthook hook {hook!r} declares no first command"
    return (match.group(1), match.group(2))


def _installer_recipe_body(*, source: str) -> str:
    """Return the indented body of the `install-worktree-pack` justfile recipe."""
    match = re.search(
        rf"^{re.escape(_INSTALLER_RECIPE)}:\n((?:[ \t]+.*\n)+)", source, flags=re.MULTILINE
    )
    assert match is not None, f"the `{_INSTALLER_RECIPE}` recipe has no body"
    return match.group(1).rstrip("\n")


def _repo_wiring(*, repo_root: Path) -> _Wiring:
    """Read the gate wiring `repo_root` carries in its committed files."""
    lefthook = (repo_root / _LEFTHOOK_NAME).read_text(encoding="utf-8")
    justfile = (repo_root / _JUSTFILE_NAME).read_text(encoding="utf-8")
    return _Wiring(
        first_gate_commands=tuple(
            (hook, *_first_gate_command(source=lefthook, hook=hook)) for hook in _GATE_HOOKS
        ),
        import_lines=tuple(
            line for line in justfile.splitlines() if _IMPORT_LINE_PATTERN.fullmatch(line)
        ),
        installer_recipe_body=_installer_recipe_body(source=justfile),
    )


def _mise_which(*, tool: str) -> str | None:
    """`tool`'s absolute path per `mise which`, or None if mise cannot answer.

    Asked from THIS repository's root rather than the caller's cwd: `mise which`
    answers for the versions the config in scope pins, and the version the gate
    must run is the one `.mise.toml` here pins. A test that has already chdir'd
    into its tmp_path fixture would otherwise be asking mise about a directory
    that pins nothing.

    A host with no `mise` at all answers None rather than raising, so what the
    reader sees is `_tool_dir`'s assertion — which names the tool it wanted —
    instead of a bare `FileNotFoundError: 'mise'`.
    """
    try:
        completed = subprocess.run(
            ["mise", "which", tool],
            cwd=str(_PACKAGE_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _tool_dir(*, tool: str) -> str:
    """The directory holding `tool`, resolved from the OUTER environment.

    PATH first — that is what a host with global installs or mise shims already
    offers, and it costs no subprocess — then mise's install set. The parent
    DIRECTORY is what is resolved, never the binary: a mise shim is a symlink to
    the `mise` binary itself, so resolving the file would hand back a directory
    that does not contain `tool` at all.

    Unresolvable is an assertion naming the tool, because the alternative is the
    nested `mise ERROR "<tool>" couldn't exec process` that started this: a
    message about the fixture's HOME that says nothing about what the host lacks.
    """
    resolved = shutil.which(tool) or _mise_which(tool=tool)
    assert resolved is not None, (
        f"the fixture's hook chain execs `{tool}`, which this host carries "
        f"neither on PATH nor in mise's install set (`mise which {tool}` "
        f"resolved nothing). Run `mise install` from this repository root to "
        f"provision the pinned {tool}."
    )
    return str(Path(resolved).parent.resolve())


@cache
def _outer_tool_path_prefix() -> str:
    """The PATH entries that make the hook chain's tools resolvable in the fixture.

    Cached because every fixture child rebuilds its environment, and on a
    mise-only host each rebuild would otherwise spawn one `mise which` per tool.
    """
    return os.pathsep.join(_tool_dir(tool=tool) for tool in _HOOK_CHAIN_TOOLS)


def _child_env(*, home: Path) -> dict[str, str]:
    """The environment every fixture child runs under.

    Three scrubs, each load-bearing. `GIT_*` because this suite may itself run
    under a lefthook hook, which injects `GIT_DIR` and friends that would drag
    every fixture `git` invocation back to the surrounding repository.
    `COVERAGE_PROCESS_START` / `COV_CORE_*` because the hook chain reaches a
    real `uv run python`, and an instrumented grandchild writes `.coverage.*`
    that races the parallel check dispatcher. `HOME` because the installed
    commit-refuse hook admits commits only from a worktree under
    `$HOME/.worktrees` — pointing HOME at the fixture is what lets this proof
    drive the real, unmodified hook body instead of a weakened copy.

    And one PREPEND, which the HOME redirect makes mandatory. mise resolves its
    install set under `$HOME/.local/share/mise`, and the fixture HOME is empty,
    so on a host where lefthook / just / uv exist ONLY as mise installs the
    redirect hides all three from the hook chain: the nested push dies with
    `mise ERROR "lefthook" couldn't exec process`, and once lefthook is found,
    with `sh: 1: just: not found`. GitHub Actions happens to carry the same
    three on PATH globally, so the suite passed there and failed on the host —
    which means it was asserting the RUNNER's tool layout rather than the pack's
    wiring (livespec-dev-tooling-85cp). Resolving each tool in the outer
    environment and leading the child PATH with its directory makes the fixture
    exercise the hook on any host that can run this repository's gates at all.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE_")) and key != "COVERAGE_PROCESS_START"
    }
    env["HOME"] = str(home)
    env["PATH"] = _outer_tool_path_prefix() + os.pathsep + env.get("PATH", os.defpath)
    return env


def _run(*, args: list[str], cwd: Path, home: Path) -> None:
    """Run a fixture child, failing the test with its full output on non-zero."""
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        env=_child_env(home=home),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"{args} exited {completed.returncode}\n"
        f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
    )


def _fixture_installer_body(*, wiring: _Wiring) -> str:
    """This repo's installer recipe body, re-pointed at this package root."""
    return wiring.installer_recipe_body.replace(_UV_RUN, _UV_RUN + _FIXTURE_UV_FLAGS, 1)


def _fixture_justfile(*, wiring: _Wiring, sentinel: Path) -> str:
    """The fixture root justfile: this repo's wiring plus a bootstrap trap.

    The `bootstrap` recipe RECORDS that it ran and then fails. "No bootstrap
    was invoked" is the load-bearing half of the claim, and an ABSENT recipe
    would establish it only by accident — `just bootstrap` would fail for want
    of a recipe rather than because nothing asked for it. A recipe that leaves
    evidence turns the negative into something a test can actually read.
    """
    return "\n".join(
        [
            *wiring.import_lines,
            "",
            f"{_INSTALLER_RECIPE}:",
            _fixture_installer_body(wiring=wiring),
            "",
            "bootstrap:",
            f"    @touch '{sentinel}'",
            "    @exit 1",
            "",
        ]
    )


def _fixture_lefthook(*, wiring: _Wiring) -> str:
    """The fixture `lefthook.yml`: the installer first in both gate hooks."""
    stanzas: list[str] = []
    for hook, name, run in wiring.first_gate_commands:
        stanzas.extend([f"{hook}:", "  commands:", f"    {name}:", f"      run: {run}", ""])
    return "\n".join(stanzas)


def _git_repo(*, root: Path, home: Path) -> None:
    """Initialize `root` as a git repo with a committer identity."""
    root.mkdir()
    _run(args=["git", "init", "-q", "-b", "master", "."], cwd=root, home=home)
    _run(args=["git", "config", "user.email", "fixture@example.invalid"], cwd=root, home=home)
    _run(args=["git", "config", "user.name", "Fixture"], cwd=root, home=home)


def _wired_fixture(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Fixture:
    """Build a wired fixture repo and add a linked worktree with RAW `git worktree add`.

    RAW on purpose. `just worktree-create` provisions the pack as part of
    creating the worktree, so a worktree made that way could never exhibit the
    absent-pack state this proof is about. The raw command is what a session
    reaches for when `just --list` shows no `worktree-create`, and it is the
    shape the heal-at-gate mechanism exists to survive.
    """
    home = tmp_path / "home"
    home.mkdir()
    primary = tmp_path / "primary"
    sentinel = tmp_path / "bootstrap-was-invoked"
    wiring = _repo_wiring(repo_root=_PACKAGE_ROOT)

    _git_repo(root=primary, home=home)
    _ = (primary / _JUSTFILE_NAME).write_text(
        _fixture_justfile(wiring=wiring, sentinel=sentinel), encoding="utf-8"
    )
    _ = (primary / _LEFTHOOK_NAME).write_text(_fixture_lefthook(wiring=wiring), encoding="utf-8")
    _ = (primary / ".gitignore").write_text(f"/{_PACK_DIR_NAME}/\n", encoding="utf-8")
    _ = (primary / ".livespec.jsonc").write_text(
        '{\n  "worktree_discipline": { "pack": "required" }\n}\n', encoding="utf-8"
    )
    _run(args=["git", "add", "-A"], cwd=primary, home=home)
    _run(args=["git", "commit", "-q", "-m", "chore: wire the fixture"], cwd=primary, home=home)

    # Only NOW. The commit-refuse hook refuses commits at a primary checkout,
    # so the wiring commit above has to land before the hooks are armed.
    monkeypatch.chdir(primary)
    assert install_commit_refuse_hooks.main() == 0

    _run(args=["git", "init", "-q", "--bare", "remote.git"], cwd=tmp_path, home=home)
    worktree = home / ".worktrees" / "fixture" / "feat-heal"
    _run(
        args=["git", "worktree", "add", "-q", "-b", "feat-heal", str(worktree), "master"],
        cwd=primary,
        home=home,
    )
    _run(
        args=["git", "remote", "add", "origin", str(tmp_path / "remote.git")],
        cwd=worktree,
        home=home,
    )
    return _Fixture(primary=primary, worktree=worktree, home=home, bootstrap_sentinel=sentinel)


def _pack_failures(*, repo_root: Path) -> list[tuple[str, str]]:
    """The pack verifier's VIOLATIONS, asserting first that it answered at all."""
    inspected = inspect_worktree_pack(repo_root=repo_root)
    assert isinstance(inspected, IOSuccess), f"the pack arm did not answer: {inspected}"
    return unsafe_perform_io(inspected.unwrap())


def _assert_pack_is_canonical(*, fixture: _Fixture) -> None:
    """Every pack member present, byte-identical and correctly moded; verifier clean."""
    pack_dir = fixture.worktree / _PACK_DIR_NAME
    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        assert path.read_bytes() == pack_file.body.encode("utf-8"), pack_file.name
        assert os.access(path, os.X_OK) is pack_file.executable, pack_file.name
    assert _pack_failures(repo_root=fixture.worktree) == []
    assert not fixture.bootstrap_sentinel.exists(), "the healing path invoked `just bootstrap`"


def _installed_pack(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway git repo with the pack installed in-process; returns the pack dir."""
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _git_repo(root=repo, home=home)
    monkeypatch.chdir(repo)
    assert main() == 0
    return repo / _PACK_DIR_NAME


def _stamp_stale(*, pack_dir: Path) -> None:
    """Stamp every installed pack file with `_STALE_EPOCH`."""
    for pack_file in WORKTREE_PACK_FILES:
        os.utime(pack_dir / pack_file.name, (_STALE_EPOCH, _STALE_EPOCH))


def test_this_repo_is_wired_as_the_central_row_will_require() -> None:
    """This repo carries the shape the `worktree-pack-wired` row enforces.

    Read from the committed `lefthook.yml` / `justfile` — the SAME read the
    fixture builder uses. That is what keeps the proof and the enforcement in
    one piece: the fixture cannot be wired in a shape this repository is not,
    and this repository cannot leave the shape without reddening the proof.
    """
    wiring = _repo_wiring(repo_root=_PACKAGE_ROOT)
    assert wiring.first_gate_commands == tuple(
        (hook, _INSTALLER_COMMAND_NAME, _INSTALLER_RUN_LINE) for hook in _GATE_HOOKS
    )
    assert wiring.import_lines == tuple(
        f"import? '{_PACK_DIR_NAME}/{fragment}'" for fragment in _PACK_FRAGMENTS
    )
    assert _UV_RUN in wiring.installer_recipe_body
    assert install_worktree_pack.__name__ in wiring.installer_recipe_body


def test_fixture_wiring_equals_the_wiring_this_repo_carries(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated fixture is wired identically to this repository.

    Asserted by reading the fixture back through `_repo_wiring`, the same
    reader applied to the real files — so "identical" means identical to the
    reader the central row will use, not merely similar to the eye. The single
    sanctioned divergence, the `uv run` project re-pointing, is round-tripped
    away rather than waived, so any OTHER difference would surface here.
    """
    fixture = _wired_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)
    fixture_wiring = _repo_wiring(repo_root=fixture.worktree)
    repo_wiring = _repo_wiring(repo_root=_PACKAGE_ROOT)
    assert fixture_wiring.first_gate_commands == repo_wiring.first_gate_commands
    assert fixture_wiring.import_lines == repo_wiring.import_lines
    assert (
        fixture_wiring.installer_recipe_body.replace(_FIXTURE_UV_FLAGS, "")
        == repo_wiring.installer_recipe_body
    )


@pytest.mark.parametrize("tool", _HOOK_CHAIN_TOOLS)
def test_every_tool_the_hook_chain_execs_is_reachable_from_the_child_path(*, tool: str) -> None:
    """Each of lefthook, just and uv resolves against the prepended entries ALONE.

    Against the prefix alone, not against the whole child PATH: the outer PATH
    is still appended, so a host that already carries the tools globally would
    satisfy a whole-PATH assertion no matter what the prefix contained. Asking
    the prefix in isolation is what proves the fixture supplies the tools rather
    than inheriting them.
    """
    assert shutil.which(tool, path=_outer_tool_path_prefix()) is not None, tool


def test_the_child_path_leads_with_the_outer_tool_directories(*, tmp_path: Path) -> None:
    """The prefix LEADS, so the fixture's tools win over anything else on PATH."""
    assert _child_env(home=tmp_path)["PATH"].startswith(_outer_tool_path_prefix() + os.pathsep)


def test_a_tool_absent_from_both_path_and_mise_fails_naming_the_tool() -> None:
    """The unresolvable case names the tool, not the fixture's HOME.

    The whole point of resolving up front: the originating failure surfaced as
    `mise ERROR "lefthook" couldn't exec process` from three processes down, a
    message that reads like a broken fixture rather than a host missing a tool.
    """
    with pytest.raises(AssertionError, match=_ABSENT_TOOL):
        _ = _tool_dir(tool=_ABSENT_TOOL)


def test_mise_resolves_a_pinned_tool_the_session_path_need_not_carry() -> None:
    """`mise which` answers for a pinned tool — the fallback the mise-only host needs.

    Exercised directly because on a host that DOES carry the tools on PATH the
    fixture never reaches this arm, and an unexercised fallback is exactly the
    arm that was missing when the host went red.
    """
    resolved = _mise_which(tool="just")
    assert resolved is not None
    assert Path(resolved).name == "just"


def test_mise_which_answers_none_when_the_host_has_no_mise(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `mise` on the host is an ANSWER, so the caller still names the tool."""

    def _no_mise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "mise")

    monkeypatch.setattr(subprocess, "run", _no_mise)
    assert _mise_which(tool="just") is None


def test_raw_worktree_with_no_pack_heals_at_the_real_pre_push_hook(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raw `git worktree add` worktree pushes and commits with NO bootstrap.

    The originating failure: a worktree created outside `just worktree-create`
    reached the gate with `dev-tooling/` entirely absent and failed
    `worktree_pack_absent` only AFTER the whole aggregate had run. The absence
    is asserted first here, so the healing is proven rather than assumed.
    """
    fixture = _wired_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert not (fixture.worktree / _PACK_DIR_NAME).exists()
    assert (_PACK_DIR_NAME, "worktree_pack_absent") in _pack_failures(repo_root=fixture.worktree)

    _run(args=["git", "push", "-q", "origin", "feat-heal"], cwd=fixture.worktree, home=fixture.home)
    _assert_pack_is_canonical(fixture=fixture)

    # And the pre-commit leg of the same wiring, over a pack that is already
    # correct: the second gate hook must be a no-op, not a re-break.
    _ = (fixture.worktree / "note.txt").write_text("heal-at-gate\n", encoding="utf-8")
    _run(args=["git", "add", "note.txt"], cwd=fixture.worktree, home=fixture.home)
    _run(args=["git", "commit", "-q", "-m", "chore: note"], cwd=fixture.worktree, home=fixture.home)
    _assert_pack_is_canonical(fixture=fixture)


def test_pin_drifted_pack_heals_at_the_real_pre_push_hook(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree carrying an OLDER pin's pack is healed by the same hook.

    Distinct from the absent case and not covered by it: a drifted pack is
    PRESENT, so nothing about the worktree looks unprovisioned. Before the
    installer ran at the gate this state survived every commit until the
    byte-identity arm rejected it at the very end of the aggregate.
    """
    fixture = _wired_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.chdir(fixture.worktree)
    assert main() == 0
    _ = (fixture.worktree / _PACK_DIR_NAME / _DRIFT_TARGET).write_text(
        _STALE_BODY, encoding="utf-8"
    )
    assert (_DRIFT_TARGET, "worktree_pack_body_mismatch") in _pack_failures(
        repo_root=fixture.worktree
    )

    _run(args=["git", "push", "-q", "origin", "feat-heal"], cwd=fixture.worktree, home=fixture.home)
    _assert_pack_is_canonical(fixture=fixture)


def test_installer_writes_nothing_when_every_installed_file_already_matches(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-install over a correct pack is a READ, not seven writes.

    This is what makes the per-hook cost acceptable. The installer now runs on
    every commit and every push in every wired repo; an unconditional write
    would churn seven mtimes each time for a pack that is almost always already
    canonical. The stamped `_STALE_EPOCH` surviving is the proof — no write can
    preserve it.
    """
    pack_dir = _installed_pack(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stamp_stale(pack_dir=pack_dir)

    assert main() == 0

    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        assert path.stat().st_mtime == _STALE_EPOCH, f"{pack_file.name} was rewritten unchanged"
        assert path.read_bytes() == pack_file.body.encode("utf-8"), pack_file.name


def test_installer_rewrites_only_the_drifted_member(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping the identical write must not skip the write that matters."""
    pack_dir = _installed_pack(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = (pack_dir / _DRIFT_TARGET).write_text(_STALE_BODY, encoding="utf-8")
    _stamp_stale(pack_dir=pack_dir)

    assert main() == 0

    assert (pack_dir / _DRIFT_TARGET).stat().st_mtime != _STALE_EPOCH
    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        assert path.read_bytes() == pack_file.body.encode("utf-8"), pack_file.name
        if pack_file.name != _DRIFT_TARGET:
            assert path.stat().st_mtime == _STALE_EPOCH, pack_file.name


def test_installer_restores_a_stripped_executable_bit_without_rewriting(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A canonical body carrying the wrong MODE is still repaired.

    The regression the write-skip could have introduced: comparing bytes says
    nothing about the executable bit, and `gate-run.sh` is invoked directly as
    `./dev-tooling/gate-run.sh`. The mode is fixed with a `chmod`, which leaves
    mtime alone — so the file is repaired without being rewritten.
    """
    pack_dir = _installed_pack(tmp_path=tmp_path, monkeypatch=monkeypatch)
    target = pack_dir / _DRIFT_TARGET
    target.chmod(0o644)
    _stamp_stale(pack_dir=pack_dir)

    assert main() == 0

    assert os.access(target, os.X_OK)
    assert target.stat().st_mtime == _STALE_EPOCH
