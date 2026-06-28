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

from livespec_dev_tooling.fleet._context import RowFinding, RowOutcome, RowPass, RowSkip
from livespec_dev_tooling.fleet._local_context import LocalContext

__all__: list[str] = [
    "NOTES_REFSPEC",
    "assert_commit_refuse_hooks",
    "assert_git_notes_refspec",
    "assert_worktree_root_trust",
    "reconcile_beads_dir_perms",
    "reconcile_claude_plugins",
    "reconcile_codex_plugins",
    "reconcile_commit_refuse_hooks",
    "reconcile_git_notes_refspec",
    "reconcile_mise_trust_install",
    "reconcile_uv_sync",
    "reconcile_worktree_root_trust",
]


NOTES_REFSPEC = "+refs/notes/*:refs/notes/*"


def reconcile_mise_trust_install(*, ctx: LocalContext) -> RowOutcome:
    """Trust the checkout's `.mise.toml` and install its pinned tools."""
    trust = ctx.exec(args=["mise", "trust"])
    if trust.returncode != 0:
        return RowFinding(message="mise trust failed")
    install = ctx.exec(args=["mise", "install"])
    if install.returncode != 0:
        return RowFinding(message="mise install failed")
    return RowPass(note="mise trusted and pinned tools installed")


def reconcile_uv_sync(*, ctx: LocalContext) -> RowOutcome:
    """Sync the checkout's dependency groups into its venv."""
    result = ctx.exec(args=["uv", "sync", "--all-groups"])
    if result.returncode != 0:
        return RowFinding(message="uv sync failed")
    return RowPass(note="uv dependencies synced")


def assert_commit_refuse_hooks(*, ctx: LocalContext) -> RowOutcome:
    """The canonical commit-refuse hook is installed at the primary's shared hooks dir."""
    result = ctx.exec(
        args=[
            "uv",
            "run",
            "python",
            "-m",
            "livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed",
        ]
    )
    if result.returncode == 0:
        return RowPass(note="commit-refuse hooks installed")
    return RowFinding(message="commit-refuse hooks absent or non-canonical")


def reconcile_commit_refuse_hooks(*, ctx: LocalContext) -> RowOutcome:
    """Install the canonical commit-refuse hook via the shared installer module."""
    result = ctx.exec(
        args=["uv", "run", "python", "-m", "livespec_dev_tooling.install_commit_refuse_hooks"]
    )
    if result.returncode != 0:
        return RowFinding(message="installing commit-refuse hooks failed")
    return RowPass(note="commit-refuse hooks installed")


def assert_git_notes_refspec(*, ctx: LocalContext) -> RowOutcome:
    """The advisory `refs/notes/*` fetch refspec is configured on origin."""
    result = ctx.exec(args=["git", "config", "--get-all", "remote.origin.fetch"])
    if NOTES_REFSPEC in result.stdout.splitlines():
        return RowPass(note="notes refspec present")
    return RowFinding(message="notes refspec absent from remote.origin.fetch")


def reconcile_git_notes_refspec(*, ctx: LocalContext) -> RowOutcome:
    """Add the advisory `refs/notes/*` fetch refspec to origin."""
    result = ctx.exec(args=["git", "config", "--add", "remote.origin.fetch", NOTES_REFSPEC])
    if result.returncode != 0:
        return RowFinding(message="adding notes refspec failed")
    return RowPass(note="notes refspec added")


def _worktree_root(*, ctx: LocalContext) -> str:
    """The per-user worktree root path (`<home>/.worktrees`)."""
    return str(ctx.home / ".worktrees")


def assert_worktree_root_trust(*, ctx: LocalContext) -> RowOutcome:
    """The worktree root is registered as a mise trusted config path."""
    result = ctx.exec(args=["mise", "settings", "get", "trusted_config_paths"])
    if _worktree_root(ctx=ctx) in result.stdout:
        return RowPass(note="worktree root is a mise trusted config path")
    return RowFinding(message="worktree root absent from mise trusted_config_paths")


def reconcile_worktree_root_trust(*, ctx: LocalContext) -> RowOutcome:
    """Create the worktree root and register it as a mise trusted config path."""
    root = _worktree_root(ctx=ctx)
    made = ctx.exec(args=["mkdir", "-p", root])
    if made.returncode != 0:
        return RowFinding(message="creating the worktree root failed")
    added = ctx.exec(args=["mise", "settings", "add", "trusted_config_paths", root])
    if added.returncode != 0:
        return RowFinding(message="adding worktree root to mise trusted_config_paths failed")
    return RowPass(note="worktree root created and trusted")


def reconcile_beads_dir_perms(*, ctx: LocalContext) -> RowOutcome:
    """Harden the beads tenant-pointer directory to owner-only, when present."""
    beads = ctx.checkout / ".beads"
    if not beads.is_dir():
        return RowSkip(reason="no .beads tenant directory")
    result = ctx.exec(args=["chmod", "700", str(beads)])
    if result.returncode != 0:
        return RowFinding(message="hardening .beads permissions failed")
    return RowPass(note=".beads hardened to owner-only")


def _recipe_present(*, ctx: LocalContext, recipe: str) -> bool:
    """True when the checkout's justfile defines `recipe` (`just --show` exits 0)."""
    return ctx.exec(args=["just", "--show", recipe]).returncode == 0


def reconcile_claude_plugins(*, ctx: LocalContext) -> RowOutcome:
    """Register the checkout's Claude marketplaces + plugins via its own recipe.

    A member whose justfile has no `ensure-plugins` recipe declares no Claude
    plugin surface — the verb has nothing to delegate, so it SKIPs rather than
    failing on `just`'s recipe-not-found error (the verb delegates to the
    member's own recipe; an absent recipe is nothing to do, not a fault).
    """
    if not _recipe_present(ctx=ctx, recipe="ensure-plugins"):
        return RowSkip(reason="no ensure-plugins recipe (member declares no Claude plugin surface)")
    result = ctx.exec(args=["just", "ensure-plugins"])
    if result.returncode != 0:
        return RowFinding(message="claude plugin registration (just ensure-plugins) failed")
    return RowPass(note="claude marketplaces + plugins registered")


def reconcile_codex_plugins(*, ctx: LocalContext) -> RowOutcome:
    """Register the checkout's Codex plugins via its own (self-skipping) recipe.

    A member whose justfile has no `ensure-codex-plugins` recipe (e.g.
    livespec-driver-codex) declares no Codex plugin surface for the verb to
    delegate to — it SKIPs rather than failing on the recipe-not-found error.
    """
    if not _recipe_present(ctx=ctx, recipe="ensure-codex-plugins"):
        return RowSkip(
            reason="no ensure-codex-plugins recipe (member declares no Codex plugin surface)"
        )
    result = ctx.exec(args=["just", "ensure-codex-plugins"])
    if result.returncode != 0:
        return RowFinding(message="codex plugin registration (just ensure-codex-plugins) failed")
    return RowPass(note="codex plugins registered (recipe self-skips when codex absent)")
