"""§"Hooks and CI" — the mirrored ORDER, and the one ordering constraint that is not cosmetic.

The section names the members of three lefthook stages and the order they run
in, "per livespec `contracts.md` section 'Pre-commit step ordering'". Most of
that order is a mirror obligation: it exists so every governed repository fails
the same way in the same place. One clause in it is load-bearing on its own, and
the section states it separately:

> The `00-install-worktree-pack` command delegates to `just
> install-worktree-pack`, which materializes the canonical worktree-discipline
> pack this repository ships into the checkout's gitignored `dev-tooling/` [...]
> No hook command that reads the pack MAY precede it.

That is the clause with a real failure mode. A worktree created by a raw `git
worktree add`, or one predating a pin bump, reaches the gate with the pack
absent or stale. If a pack-reading member runs FIRST, the whole aggregate runs
before anything discovers it — the operator pays the full gate runtime to be
told `worktree_pack_absent`. Order alone is what makes that impossible, and
order is exactly the property no check can defend from inside a member: a
member cannot observe what ran before it.

The numeric prefixes are the mechanism, not decoration — lefthook runs a stage's
commands in name order, so the mirror is enforced by the `NN-` naming, and a
member renamed without its prefix silently relocates itself in the sequence.

The commit-msg stage is asserted as a PREFIX rather than an exact set: this
repository adds `02-shipped-path-release-guard` after the two the section names,
which is an addition the section's ordering does not forbid. What is asserted is
that the two it DOES name are present, in the named order, at the named
positions.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# The three stages and the members the section names, in the order it names
# them. `commit-msg` is a prefix (this repo appends a release guard).
_PRE_COMMIT_ORDER = (
    "00-install-worktree-pack",
    "01-lint-autofix-staged",
    "02-commit-pairs-source-and-test",
    "03-check-pre-commit",
)
_COMMIT_MSG_PREFIX = ("00-no-commit-on-master", "01-red-green-replay")
_PRE_PUSH_ORDER = ("00-install-worktree-pack", "01-check-pre-push")

_PACK_INSTALLER = "00-install-worktree-pack"
_PACK_INSTALLER_RECIPE = "just install-worktree-pack"

_STAGE = re.compile(r"^(?P<stage>[a-z][a-z-]*):$", re.MULTILINE)
_COMMAND = re.compile(r"^    (?P<name>[0-9]{2}-[a-z-]+):$")


def _stage_bodies() -> dict[str, dict[str, str]]:
    """Each lefthook stage mapped to its commands, in file order, with their bodies."""
    stages: dict[str, dict[str, str]] = {}
    current_stage: str | None = None
    current_command: str | None = None
    for line in _LEFTHOOK.read_text(encoding="utf-8").splitlines():
        stage = _STAGE.match(line)
        if stage is not None:
            current_stage = stage.group("stage")
            current_command = None
            stages[current_stage] = {}
            continue
        command = _COMMAND.match(line)
        if command is not None and current_stage is not None:
            current_command = command.group("name")
            stages[current_stage][current_command] = ""
            continue
        if current_stage is not None and current_command is not None and line.startswith("      "):
            stages[current_stage][current_command] += f"{line.strip()}\n"
    return stages


def _stage_commands() -> dict[str, list[str]]:
    """Each lefthook stage mapped to its command names, in file order."""
    return {stage: list(commands) for stage, commands in _stage_bodies().items()}


def _command_body(*, stage: str, command: str) -> str:
    """The raw `run:` text of one lefthook command."""
    return _stage_bodies()[stage][command]


def test_each_hook_stage_runs_the_members_the_section_names_in_that_order() -> None:
    """The mirrored order, read off the naming that produces it."""
    stages = _stage_commands()
    assert tuple(stages.get("pre-commit", ())) == _PRE_COMMIT_ORDER, (
        f"pre-commit must mirror livespec's ordering exactly — lefthook runs a stage's "
        f"commands in NAME order, so the `NN-` prefixes are the mechanism and a member "
        f"renamed without one relocates itself silently; "
        f"wired={tuple(stages.get('pre-commit', ()))} expected={_PRE_COMMIT_ORDER}"
    )
    commit_msg = tuple(stages.get("commit-msg", ()))
    assert commit_msg[: len(_COMMIT_MSG_PREFIX)] == _COMMIT_MSG_PREFIX, (
        f"the commit-msg gates the section names must be its first two members, in that "
        f"order; wired={commit_msg} expected_prefix={_COMMIT_MSG_PREFIX}"
    )
    assert tuple(stages.get("pre-push", ())) == _PRE_PUSH_ORDER, (
        f"pre-push must be the pack installer then the full aggregate; "
        f"wired={tuple(stages.get('pre-push', ()))} expected={_PRE_PUSH_ORDER}"
    )


def test_the_pack_installer_precedes_every_hook_command_and_delegates_to_the_recipe() -> None:
    """ "No hook command that reads the pack MAY precede it" — asserted as position 0."""
    stages = _stage_commands()
    for stage, members in stages.items():
        if _PACK_INSTALLER not in members:
            continue
        assert members[0] == _PACK_INSTALLER, (
            f"`{_PACK_INSTALLER}` must be the FIRST command of `{stage}`. A pack-reading "
            f"member that precedes it makes the operator pay the whole gate runtime "
            f"before anything discovers the pack is absent or stale — which is what a "
            f"worktree made by a raw `git worktree add`, or one predating a pin bump, "
            f"arrives with; wired={members}"
        )
        body = _command_body(stage=stage, command=_PACK_INSTALLER)
        assert _PACK_INSTALLER_RECIPE in body, (
            f"the section requires `{_PACK_INSTALLER}` to DELEGATE to "
            f"`{_PACK_INSTALLER_RECIPE}` — the single materializer whose bytes the "
            f"aggregate's byte-identity verifier then re-asserts. A hook that inlines the "
            f"install instead is a second copy of it; stage={stage} body={body!r}"
        )


def test_the_pack_installer_is_wired_in_both_hooks_that_gate_a_push() -> None:
    """One install point per hook — pre-commit and pre-push each read the pack."""
    stages = _stage_commands()
    carrying = sorted(stage for stage, members in stages.items() if _PACK_INSTALLER in members)
    assert carrying == ["pre-commit", "pre-push"], (
        f"both gating hooks run members that read the pack, so both must install it "
        f"first; the commit-msg stage reads the message and not the pack, so it "
        f"correctly does not; carrying={carrying}"
    )
