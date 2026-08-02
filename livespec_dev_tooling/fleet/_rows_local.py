"""LOCAL-vantage first-touch obligation rows for the fleet contract.

The generalized `just bootstrap` step set, modeled as local obligation
rows so the assert/drift side gains the matching local checks for free
(per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Governed-repo lifecycle"). Each function takes a `LocalContext` and
returns a `RowOutcome`, issuing every host mutation through the
context's command seam so the rows stay hermetically testable.

Two row kinds share this module:

- Rows leaving PERSISTENT, re-checkable state (the commit-refuse hooks,
  the git notes refspec, the worktree-root mise-trust entry) carry a
  real `assert_*` so a drift sweep can re-verify them; the verb asserts
  first and reconciles only an unmet row.
- Pure PROVISIONING rows (toolchain install, dependency sync, the beads
  tenant-dir hardening, plugin registration) carry no meaningful
  persistent drift state; the verb runs their idempotent reconcile
  unconditionally.

Plugin registration delegates to the checkout's OWN `just ensure-plugins`
/ `just ensure-codex-plugins` recipes: the plugin set is repo-specific
(each governed repo declares its own), so its recipe stays the single
source and the verb merely runs it in the target checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`.
# Relying on that ordering is what broke the fleet's release fan-out for seven
# hours (`vzwa`'s `89296e0`), and `test_vendor_update` enforces this preamble on
# every `returns`-importing module for exactly that reason.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._context import (  # noqa: E402
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import (  # noqa: E402
    LocalContext,
    command_answer,
)

__all__: list[str] = [
    "NOTES_REFSPEC",
    "assert_commit_refuse_hooks",
    "assert_git_notes_refspec",
    "assert_worktree_pack",
    "assert_worktree_root_trust",
    "reconcile_beads_dir_perms",
    "reconcile_claude_plugins",
    "reconcile_codex_plugins",
    "reconcile_commit_refuse_hooks",
    "reconcile_git_notes_refspec",
    "reconcile_mise_trust_install",
    "reconcile_uv_sync",
    "reconcile_worktree_pack",
    "reconcile_worktree_root_trust",
]


NOTES_REFSPEC = "+refs/notes/*:refs/notes/*"


def _failed(*, ctx: LocalContext, args: list[str], note: str) -> RowFinding | None:
    """The finding for a command that never ran or ran and exited non-zero, else None.

    The two arms render DIFFERENTLY on purpose. A command that ran and
    failed gets the caller's `note`, which describes the operation that
    did not take effect. A command that never ran gets the seam's own
    reason, because `note` would be a claim about an operation the host
    never attempted — the fabricated-127 collapse in prose form.
    """
    answer = command_answer(outcome=ctx.exec(args=args))
    if isinstance(answer, InvocationNotPerformed):
        return RowFinding(message=answer.reason)
    return None if answer.returncode == 0 else RowFinding(message=note)


def reconcile_mise_trust_install(*, ctx: LocalContext) -> RowOutcome:
    """Trust the checkout's `.mise.toml` and install its pinned tools."""
    trust = _failed(ctx=ctx, args=["mise", "trust"], note="mise trust failed")
    if trust is not None:
        return trust
    install = _failed(ctx=ctx, args=["mise", "install"], note="mise install failed")
    if install is not None:
        return install
    return RowPass(note="mise trusted and pinned tools installed")


def reconcile_uv_sync(*, ctx: LocalContext) -> RowOutcome:
    """Sync the checkout's dependency groups into its venv."""
    failure = _failed(ctx=ctx, args=["uv", "sync", "--all-groups"], note="uv sync failed")
    return failure if failure is not None else RowPass(note="uv dependencies synced")


_WORKTREE_PACK_DIR_NAME = "dev-tooling"


def _worktree_pack_files() -> tuple[tuple[str, str], ...]:
    """The four canonical pack files, from the single installer source."""
    from livespec_dev_tooling.install_worktree_pack import (
        CANONICAL_BRANCH_PROTECTION_BODY,
        CANONICAL_BRANCH_PROTECTION_JUST_BODY,
        CANONICAL_WORKTREE_JUST_BODY,
        CANONICAL_WORKTREE_LIB_BODY,
    )

    return (
        ("branch-protection.just", CANONICAL_BRANCH_PROTECTION_JUST_BODY),
        ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
        ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
        ("worktree.just", CANONICAL_WORKTREE_JUST_BODY),
    )


def assert_worktree_pack(*, ctx: LocalContext) -> RowOutcome:
    """The four canonical pack files exist, byte-identical, in THIS worktree.

    Uses `ctx.invoked_worktree`, not `ctx.checkout`: the pack is per-worktree
    (the root justfile `import?`s it relative to the checkout you stand in),
    unlike the shared hooks/refspec/mise-trust rows.
    """
    pack_dir = ctx.invoked_worktree / _WORKTREE_PACK_DIR_NAME
    for name, body in _worktree_pack_files():
        outcome = ctx.file_text(path=pack_dir / name)
        if isinstance(outcome, IOFailure):
            # can't-read is not absent: a pack file present but undecodable
            # used to raise `UnicodeDecodeError` straight out of this row and
            # abort the whole reconcile (livespec-dev-tooling-a6et).
            not_read = unsafe_perform_io(outcome.failure())
            return RowSkip(reason=f"worktree pack file unreadable: {name} ({not_read.kind})")
        if unsafe_perform_io(outcome.unwrap()) != body:
            return RowFinding(message=f"worktree pack file absent or drifted: {name}")
    return RowPass(note="worktree pack installed")


def reconcile_worktree_pack(*, ctx: LocalContext) -> RowOutcome:
    """Materialize the pack via the shared installer, in the INVOKED worktree."""
    answer = command_answer(
        outcome=ctx.exec_in_worktree(
            args=["uv", "run", "python", "-m", "livespec_dev_tooling.install_worktree_pack"]
        )
    )
    if isinstance(answer, InvocationNotPerformed):
        return RowFinding(message=answer.reason)
    if answer.returncode != 0:
        return RowFinding(message="installing the worktree pack failed")
    return RowPass(note="worktree pack installed")


def assert_commit_refuse_hooks(*, ctx: LocalContext) -> RowOutcome:
    """The canonical commit-refuse hook is installed at the primary's shared hooks dir."""
    answer = command_answer(
        outcome=ctx.exec(
            args=[
                "uv",
                "run",
                "python",
                "-m",
                "livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed",
            ]
        )
    )
    if isinstance(answer, InvocationNotPerformed):
        return RowFinding(message=answer.reason)
    if answer.returncode == 0:
        return RowPass(note="commit-refuse hooks installed")
    return RowFinding(message="commit-refuse hooks absent or non-canonical")


def reconcile_commit_refuse_hooks(*, ctx: LocalContext) -> RowOutcome:
    """Install the canonical commit-refuse hook via the shared installer module."""
    failure = _failed(
        ctx=ctx,
        args=["uv", "run", "python", "-m", "livespec_dev_tooling.install_commit_refuse_hooks"],
        note="installing commit-refuse hooks failed",
    )
    return failure if failure is not None else RowPass(note="commit-refuse hooks installed")


def assert_git_notes_refspec(*, ctx: LocalContext) -> RowOutcome:
    """The advisory `refs/notes/*` fetch refspec is configured on origin."""
    answer = command_answer(
        outcome=ctx.exec(args=["git", "config", "--get-all", "remote.origin.fetch"])
    )
    if isinstance(answer, InvocationNotPerformed):
        # An unread config file is not a config file without the refspec.
        # Reporting absence from output that was never produced is the
        # `can't-read is not absent` collapse (livespec-dev-tooling-6ge).
        return RowFinding(message=answer.reason)
    if NOTES_REFSPEC in answer.stdout.splitlines():
        return RowPass(note="notes refspec present")
    return RowFinding(message="notes refspec absent from remote.origin.fetch")


def reconcile_git_notes_refspec(*, ctx: LocalContext) -> RowOutcome:
    """Add the advisory `refs/notes/*` fetch refspec to origin."""
    failure = _failed(
        ctx=ctx,
        args=["git", "config", "--add", "remote.origin.fetch", NOTES_REFSPEC],
        note="adding notes refspec failed",
    )
    return failure if failure is not None else RowPass(note="notes refspec added")


def _worktree_root(*, ctx: LocalContext) -> str:
    """The per-user worktree root path (`<home>/.worktrees`)."""
    return str(ctx.home / ".worktrees")


def assert_worktree_root_trust(*, ctx: LocalContext) -> RowOutcome:
    """The worktree root is registered as a mise trusted config path."""
    answer = command_answer(
        outcome=ctx.exec(args=["mise", "settings", "get", "trusted_config_paths"])
    )
    if isinstance(answer, InvocationNotPerformed):
        # Same collapse as the notes refspec: unread settings are not
        # settings that omit the path.
        return RowFinding(message=answer.reason)
    if _worktree_root(ctx=ctx) in answer.stdout:
        return RowPass(note="worktree root is a mise trusted config path")
    return RowFinding(message="worktree root absent from mise trusted_config_paths")


def reconcile_worktree_root_trust(*, ctx: LocalContext) -> RowOutcome:
    """Create the worktree root and register it as a mise trusted config path."""
    root = _worktree_root(ctx=ctx)
    made = _failed(ctx=ctx, args=["mkdir", "-p", root], note="creating the worktree root failed")
    if made is not None:
        return made
    added = _failed(
        ctx=ctx,
        args=["mise", "settings", "add", "trusted_config_paths", root],
        note="adding worktree root to mise trusted_config_paths failed",
    )
    return added if added is not None else RowPass(note="worktree root created and trusted")


def reconcile_beads_dir_perms(*, ctx: LocalContext) -> RowOutcome:
    """Harden the beads tenant-pointer directory to owner-only, when present."""
    beads = ctx.checkout / ".beads"
    if not beads.is_dir():
        return RowSkip(reason="no .beads tenant directory")
    failure = _failed(
        ctx=ctx, args=["chmod", "700", str(beads)], note="hardening .beads permissions failed"
    )
    return failure if failure is not None else RowPass(note=".beads hardened to owner-only")


def _recipe_present(*, ctx: LocalContext, recipe: str) -> bool | InvocationNotPerformed:
    """Whether the justfile defines `recipe`, or the record of a `just` that never ran.

    An absent `just` is NOT "no such recipe". It used to read as one,
    because the seam's fabricated 127 is indistinguishable from `just`'s
    own recipe-not-found exit — and the caller turned that into a SKIP
    saying the member declares no plugin surface, which is a confident
    statement about the member that an uninvokable `just` cannot support.
    """
    answer = command_answer(outcome=ctx.exec(args=["just", "--show", recipe]))
    if isinstance(answer, InvocationNotPerformed):
        return answer
    return answer.returncode == 0


def reconcile_claude_plugins(*, ctx: LocalContext) -> RowOutcome:
    """Register the checkout's Claude marketplaces + plugins via its own recipe.

    A member whose justfile has no `ensure-plugins` recipe declares no Claude
    plugin surface — the verb has nothing to delegate, so it SKIPs rather than
    failing on `just`'s recipe-not-found error (the verb delegates to the
    member's own recipe; an absent recipe is nothing to do, not a fault).
    """
    present = _recipe_present(ctx=ctx, recipe="ensure-plugins")
    if isinstance(present, InvocationNotPerformed):
        return RowFinding(message=present.reason)
    if not present:
        return RowSkip(reason="no ensure-plugins recipe (member declares no Claude plugin surface)")
    failure = _failed(
        ctx=ctx,
        args=["just", "ensure-plugins"],
        note="claude plugin registration (just ensure-plugins) failed",
    )
    if failure is not None:
        return failure
    return RowPass(note="claude marketplaces + plugins registered")


def reconcile_codex_plugins(*, ctx: LocalContext) -> RowOutcome:
    """Register the checkout's Codex plugins via its own (self-skipping) recipe.

    A member whose justfile has no `ensure-codex-plugins` recipe declares no
    Codex plugin surface for the verb to delegate to — it SKIPs rather than
    failing on the recipe-not-found error.
    """
    present = _recipe_present(ctx=ctx, recipe="ensure-codex-plugins")
    if isinstance(present, InvocationNotPerformed):
        return RowFinding(message=present.reason)
    if not present:
        return RowSkip(
            reason="no ensure-codex-plugins recipe (member declares no Codex plugin surface)"
        )
    failure = _failed(
        ctx=ctx,
        args=["just", "ensure-codex-plugins"],
        note="codex plugin registration (just ensure-codex-plugins) failed",
    )
    if failure is not None:
        return failure
    return RowPass(note="codex plugins registered (recipe self-skips when codex absent)")
