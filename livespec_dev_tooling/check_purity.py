"""check_purity — which members of a check set the green token may memoize.

The token-memoization contract of livespec-dev-tooling's own
`SPECIFICATION/contracts.md`, in its delegated pre-push gate section,
ratified v080. The green token is keyed on the `HEAD` tree's hash, which makes
it a MEMOIZATION — and memoization is sound only for a PURE function. `just
check` is not one: several of its members read state that lives outside the
pushed tree and can change without the tree changing, so a token that was
honest when written can assert a verdict that is no longer true when read.
Measured 2026-09-08 on the livespec primary checkout: a token seven weeks old,
carrying `{"tree_hash": ...}` and nothing else — no expiry, no note of what was
checked, no note of what external state the memoized run observed.

The vocabulary, from the ratified bullet:

- **tree-pure** — the same tree always yields the member's same verdict, so the
  token may memoize it.
- **world-reading** — the member's verdict can change while the tree does not,
  because it reads state outside the tree. The bullet's own examples: a remote
  service's status, live repository settings, the work-items ledger, other
  clones or worktrees, the tooling installed on the host, and the commits
  around the tree.

WHERE A DECLARATION LIVES, and why it is per member rather than one list. A
check this repository SHIPS declares its own purity as a `CHECK_PURITY` module
constant in its own `livespec_dev_tooling/checks/<slug>.py`, so the declaration
reaches every consuming repository with the library. A member that exists only
in one repository is declared BY that repository, as a `# purity: <value>`
annotation on its `check-targets.txt` line. The alternative — one curated
exempt list — is a second source of truth that drifts: this repository already
keeps such a list (`canonical_checks._WORLD_GATE_CHECK_SLUGS`) and it already
misses `check-plugin-resolution` (installed plugin builds) and
`check-local-memory-drift-audit` (the `~/.claude` store), so a new member that
reads outside the tree would join the memoized set with nobody noticing. That
is the failure this module exists to close.

THE DECLARATION IS READ STATICALLY, never imported. `_declaration_in_module`
parses the module with `ast`, so resolving a check set's purity costs one file
read per member and triggers no check module's import-time work. That is also
why `CHECK_PURITY` is deliberately absent from each check module's `__all__`:
nothing imports it, so declaring it an export would claim a consumption that
does not exist.

TWO SAFEGUARDS, both in the direction where a mistake is merely expensive:

- A member with NO declaration is reported as `undeclared`, and every caller
  treats that as world-reading. Absence of evidence is never read as evidence
  of purity — that is the one direction in which an error memoizes an impure
  verdict.
- A declaration naming neither purity reaches the FAILURE track rather than
  falling back to the default. A typo'd declaration is a registry bug, and "I
  cannot read this" must not be spelled the same way as "this says
  world-reading", because the first is something `just check` has to name.

Public API:

- `audit_check_purity(*, targets, repo_root) -> IOResult[PurityAudit,
  PurityDeclarationMalformed]` — split a check set's members by declared
  purity, each tuple in the order the targets were given. `IOResult` because
  every declaration is a filesystem read.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.

__all__: list[str] = []

TREE_PURE = "tree-pure"
WORLD_READING = "world-reading"
DECLARATION_NAME = "CHECK_PURITY"

_CHECKS_PACKAGE_DIR = Path(__file__).resolve().parent / "checks"
_INVENTORY_NAME = "check-targets.txt"
_SLUG_PREFIX = "check-"

# A repo-private member's declaration: a trailing `# purity: <value>` comment on
# its inventory line. `scripts/just/check.sh` already strips every `#`-comment
# from that file before mirroring it against the justfile's literal array, so an
# annotation is invisible to the inventory's existing reader.
_INVENTORY_DECLARATION = re.compile(r"#\s*purity:\s*(?P<value>\S+)")

# What a `CHECK_PURITY` that is not a static string literal resolves to. It
# names neither purity, so it reaches the malformed track — a computed
# declaration cannot be read without importing the module, and a declaration
# nothing can read is worse than none at all, because it LOOKS declared.
_NOT_A_STRING_LITERAL = "<not-a-string-literal>"


@dataclass(frozen=True, kw_only=True)
class PurityDeclarationMalformed:
    """A member's declaration names neither `tree-pure` nor `world-reading`.

    A registry bug — a typo, or a value that is not a static string literal —
    not an expected runtime condition of a correctly-declared repository. It
    rides the failure track rather than folding into the world-reading default
    so that something is obliged to name it: folded, a mistyped declaration
    would behave exactly like a correct `world-reading` one and never be fixed.
    """

    target: str
    value: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class PurityAudit:
    """How a check set's members split by declared purity, in the given order.

    The three tuples PARTITION the audited targets: a member reaches exactly
    one of them, and a value outside the vocabulary reaches none of them because
    it fails the audit instead. Callers that need "every member the token must
    not memoize" take `world_reading` together with `undeclared`.
    """

    tree_pure: tuple[str, ...]
    world_reading: tuple[str, ...]
    undeclared: tuple[str, ...]


def _module_path_for(*, target: str) -> Path | None:
    """The shipped check module backing `target`, when one exists.

    `check-kebab-case` maps to `checks/snake_case.py` — the same mapping
    `canonical_checks` walks in the other direction. A target that is not a
    `check-` slug, or whose module this installed library does not ship, has no
    module to ask and falls through to the consumer's own inventory.
    """
    if not target.startswith(_SLUG_PREFIX):
        return None
    module = target[len(_SLUG_PREFIX) :].replace("-", "_")
    path = _CHECKS_PACKAGE_DIR / f"{module}.py"
    if not path.is_file():
        return None
    return path


def _declared_constant(*, node: ast.stmt) -> str | None:
    """The `CHECK_PURITY` value this module-level statement declares, if any.

    Both spellings are accepted — the bare `CHECK_PURITY = "..."` assignment and
    the annotated `CHECK_PURITY: str = "..."` — because the two say the same
    thing and a resolver that read only one would report a correctly-declared
    module as undeclared. A statement that assigns the name something other than
    a string literal returns `_NOT_A_STRING_LITERAL`, which no vocabulary value
    matches, so it is convicted rather than passed over.
    """
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return None
    if not any(isinstance(item, ast.Name) and item.id == DECLARATION_NAME for item in targets):
        return None
    assigned = node.value
    if isinstance(assigned, ast.Constant) and isinstance(assigned.value, str):
        return assigned.value
    return _NOT_A_STRING_LITERAL


def _declaration_in_module(*, path: Path) -> str | None:
    """The module's own `CHECK_PURITY` declaration, read statically.

    A module that cannot be read or parsed has made NO claim, and the safe
    reading of no claim is the world-reading default — so this returns None
    rather than guessing. It never imports the module: a purity resolution runs
    on the pre-push path, where importing every check module to read one
    constant would pay that whole import cost for a classification.
    """
    try:
        parsed = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None
    for node in parsed.body:
        declared = _declared_constant(node=node)
        if declared is not None:
            return declared
    return None


def _inventory_declarations(*, repo_root: Path) -> dict[str, str]:
    """Every `# purity: <value>` annotation in the consumer's target inventory.

    An absent or unreadable inventory yields an EMPTY map rather than a failure:
    a repository that declares no repo-private member has none to annotate, and
    a member the map does not carry is undeclared, which is already the safe
    classification. Returning a failure here would refuse the aggregate of every
    consumer whose members are all shipped checks.
    """
    try:
        raw = (repo_root / _INVENTORY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    declarations: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_SLUG_PREFIX):
            continue
        matched = _INVENTORY_DECLARATION.search(stripped)
        if matched is None:
            continue
        declarations[stripped.split("#", 1)[0].strip()] = matched.group("value")
    return declarations


def _declared_purity(*, target: str, inventory: dict[str, str]) -> str | None:
    """The purity `target` declares, preferring its own shipped module.

    A shipped check's own module OUTRANKS the consumer's inventory, and the
    precedence is load-bearing rather than arbitrary: the module declaration is
    the one that reaches every consuming repository, so an inventory line must
    not be able to demote a shipped world-reading check to tree-pure in one
    repository while the library says otherwise everywhere else.
    """
    module_path = _module_path_for(target=target)
    if module_path is not None:
        return _declaration_in_module(path=module_path)
    return inventory.get(target)


def audit_check_purity(
    *, targets: tuple[str, ...], repo_root: Path
) -> IOResult[PurityAudit, PurityDeclarationMalformed]:
    """Split `targets` by declared purity, or name the one declaration that is wrong.

    Each returned tuple holds its members in the order `targets` gave them, so a
    caller can report "the members that ran" in the aggregate's own order rather
    than a sorted one. The FIRST malformed declaration fails the whole audit:
    a caller must not act on a partial classification whose remainder was never
    examined.
    """
    inventory = _inventory_declarations(repo_root=repo_root)
    tree_pure: list[str] = []
    world_reading: list[str] = []
    undeclared: list[str] = []
    for target in targets:
        declared = _declared_purity(target=target, inventory=inventory)
        if declared is None:
            undeclared.append(target)
        elif declared == TREE_PURE:
            tree_pure.append(target)
        elif declared == WORLD_READING:
            world_reading.append(target)
        else:
            return IOFailure(
                PurityDeclarationMalformed(
                    target=target,
                    value=declared,
                    reason=(
                        f"a purity declaration must be the string {TREE_PURE!r} or "
                        f"{WORLD_READING!r}; a value outside that vocabulary cannot be "
                        f"acted on, and treating it as the world-reading default would "
                        f"spell a registry bug exactly like a correct declaration"
                    ),
                )
            )
    return IOSuccess(
        PurityAudit(
            tree_pure=tuple(tree_pure),
            world_reading=tuple(world_reading),
            undeclared=tuple(undeclared),
        )
    )
