"""The `SPECIFICATION/contracts.md` §"Role keys" consumer enumerations, made derivable.

That section is the single source of truth a consumer reads to decide what
declaring a role key will arm — or what declaring it absent will disarm. Its
per-key `**Consumers:**` clauses were prose, connected to the code by nothing but
a reader's memory, and they drifted in BOTH directions: naming checks that never
read the key, and omitting checks that did (livespec-dev-tooling-3q2c). A list
that over-reports hands a consumer an exemption that never takes effect; one that
under-reports lets a consumer disarm three checks believing it disarmed one.

So the clause is DERIVED here rather than asserted. This module recomputes each
key's consumer set from the checks' own syntax on every run and fails when it
differs from what the section documents, in both directions:

- **Under-reporting** — a check that reads the key and is not named.
- **Over-reporting** — a check named in the clause that does not read the key.
- **A stale negative claim** — a check the bullet's surrounding prose names as a
  NON-consumer while the derivation says it reads the key. That is the exact shape
  the `io_trees` bullet carried: it stated `public_api_result_typed` reads neither
  the key nor any notion derived from it, while that check reached
  `config.io_trees` through `_public_api_exempt_universe`.

THE DERIVATION RULE IS STATED IN THE SPECIFICATION, not invented here. This module
is its executable form; the section carries the same four rules in prose, because
a reader checking a clause by hand needs them and a test nobody reads cannot supply
them.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

from livespec_dev_tooling.config import Config

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "livespec_dev_tooling"
_CONTRACTS = _REPO_ROOT / "SPECIFICATION" / "contracts.md"

# The role-key inventory: the bolded-backtick bullets of §"Role keys".
_ROLE_KEYS_SECTION = re.compile(r"^### Role keys\n(?P<body>.*?)(?=^### )", re.MULTILINE | re.DOTALL)
_ROLE_KEY_BULLET = re.compile(r"^- \*\*`(?P<name>[a-z_]+)`\*\*")
# The canonical clause. It runs to the first sentence end, so the enumeration has
# exactly one spelling and the explanatory prose after it cannot be mistaken for
# part of the list.
_CONSUMERS_CLAUSE = re.compile(r"\*\*Consumers:\*\*(?P<listed>[^.]*)\.")
_BACKTICKED = re.compile(r"`([a-z_][a-z0-9_]*)`")

# Rule 1: the consumer universe is the CHECK modules of the two invocation sets.
_CHECK_TREES = ("checks", "workflow_checks")
# Rule 4: the two structural meta-checks read nearly every key to audit the
# partition itself, so naming them per-key would carry no information.
_META_CHECKS = frozenset({"partition_completeness", "source_trees_scoped_to_consumer"})
# The one documented key the inventory itself says the loader never parses, so it
# has no parsed value for any check to read and carries no clause.
_NOT_LOADER_IMPLEMENTED = "repo"


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Function:
    """One top-level function of a first-party module, as the derivation sees it."""

    module: str
    reads: frozenset[str]
    called: frozenset[str]
    # Rule 3: only a function that RECEIVES the `Config` from its caller
    # propagates its reads outward. `load_config` and the git-index universe
    # primitives resolve their own `Config` from a repo root, so they propagate
    # nothing — otherwise every check would consume every key.
    propagates: bool


def _module_name(*, path: Path) -> str:
    return ".".join(path.relative_to(_REPO_ROOT).with_suffix("").parts)


def _first_party_modules() -> dict[str, ast.Module]:
    """Every first-party module of the shipped package, parsed."""
    return {
        _module_name(path=path): ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(_PACKAGE.rglob("*.py"))
        if "_vendor" not in path.parts and "__pycache__" not in path.parts
    }


def _gate_key_names(*, call: ast.Call, keys: frozenset[str]) -> set[str]:
    """The role keys this call names through the shared gate's `key="<key>"` argument."""
    return {
        kw.value.value
        for kw in call.keywords
        if kw.arg == "key" and isinstance(kw.value, ast.Constant) and kw.value.value in keys
    }


def _role_key_reads(*, node: ast.AST, keys: frozenset[str]) -> set[str]:
    """Rule 2: the role keys `node` READS — from its syntax, never from its prose.

    A read is an access of the parsed value (`config.<key>`) or the gate spelling
    (`key="<key>"`). A mention in a docstring or a comment is NOT a read, which is
    why this walks the AST rather than the text: several check modules name a role
    key only to explain why they do NOT read it, and a grep names every one of them.
    """
    reads: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in keys:
            reads.add(child.attr)
        elif isinstance(child, ast.Call):
            reads |= _gate_key_names(call=child, keys=keys)
    return reads


def _called_names(*, node: ast.AST) -> set[str]:
    """Every bare or attribute call name appearing anywhere under `node`."""
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            names.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


def _takes_config(*, func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    arguments = func.args
    return any(
        isinstance(arg.annotation, ast.Name) and arg.annotation.id == Config.__name__
        for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    )


def _function_table(
    *, modules: dict[str, ast.Module], keys: frozenset[str]
) -> dict[str, _Function]:
    """Every first-party top-level function, keyed by its qualified name."""
    table: dict[str, _Function] = {}
    for module, tree in modules.items():
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            table[f"{module}.{node.name}"] = _Function(
                module=module,
                reads=frozenset(_role_key_reads(node=node, keys=keys)),
                called=frozenset(_called_names(node=node)),
                propagates=_takes_config(func=node),
            )
    return table


def _alias_maps(
    *, modules: dict[str, ast.Module], functions: dict[str, _Function]
) -> dict[str, dict[str, str]]:
    """Per module, the local names that resolve to a first-party function."""
    aliases: dict[str, dict[str, str]] = {module: {} for module in modules}
    for module, tree in modules.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module not in modules:
                continue
            for imported in node.names:
                qualified = f"{node.module}.{imported.name}"
                if qualified in functions:
                    aliases[module][imported.asname or imported.name] = qualified
    for qualified, function in functions.items():
        # A module's OWN top-level functions resolve without an import. An
        # imported binding of the same spelling wins, so this fills gaps only.
        local = qualified.rsplit(".", 1)[1]
        if local not in aliases[function.module]:
            aliases[function.module][local] = qualified
    return aliases


def _resolve(
    *, called: frozenset[str], module: str, aliases: dict[str, dict[str, str]]
) -> set[str]:
    return {aliases[module][name] for name in called if name in aliases[module]}


def _propagated_reads(
    *, functions: dict[str, _Function], aliases: dict[str, dict[str, str]]
) -> dict[str, set[str]]:
    """Close each function's read set over the Config-taking functions it calls."""
    reads = {qualified: set(function.reads) for qualified, function in functions.items()}
    changed = True
    while changed:
        changed = False
        for qualified, function in functions.items():
            for target in _resolve(called=function.called, module=function.module, aliases=aliases):
                if functions[target].propagates and not reads[target] <= reads[qualified]:
                    reads[qualified] |= reads[target]
                    changed = True
    return reads


def _check_slugs(*, modules: dict[str, ast.Module]) -> dict[str, str]:
    """Rule 1: slug to module name, for every non-helper module of the two check trees."""
    slugs: dict[str, str] = {}
    for module in modules:
        parts = module.split(".")
        if len(parts) != 3 or parts[1] not in _CHECK_TREES or parts[2].startswith("_"):
            continue
        if parts[2] not in _META_CHECKS:
            slugs[parts[2]] = module
    return slugs


def _derived_consumers(*, keys: frozenset[str]) -> dict[str, set[str]]:
    """Each role key's consumer set, derived from the checks' own syntax."""
    modules = _first_party_modules()
    functions = _function_table(modules=modules, keys=keys)
    aliases = _alias_maps(modules=modules, functions=functions)
    reads = _propagated_reads(functions=functions, aliases=aliases)
    consumers: dict[str, set[str]] = {key: set() for key in keys}
    for slug, module in _check_slugs(modules=modules).items():
        direct = _role_key_reads(node=modules[module], keys=keys)
        called = frozenset(_called_names(node=modules[module]))
        for target in _resolve(called=called, module=module, aliases=aliases):
            if functions[target].propagates:
                direct |= reads[target]
        for key in direct:
            consumers[key].add(slug)
    return consumers


def _role_key_bullets() -> dict[str, str]:
    """Each role key's bullet body, keyed by the key it documents."""
    matched = _ROLE_KEYS_SECTION.search(_CONTRACTS.read_text(encoding="utf-8"))
    assert matched is not None, 'contracts.md must carry the "### Role keys" inventory'
    bullets: dict[str, str] = {}
    for paragraph in matched.group("body").split("\n\n"):
        named = _ROLE_KEY_BULLET.match(paragraph)
        if named is not None:
            bullets[named.group("name")] = paragraph
    assert bullets, "the role-key inventory must declare at least one key"
    return bullets


def _documented_consumers(*, bullet: str) -> set[str]:
    clause = _CONSUMERS_CLAUSE.search(bullet)
    assert clause is not None, "every loader-recognized role key needs a `**Consumers:**` clause"
    return set(_BACKTICKED.findall(clause.group("listed")))


def _guarded_keys() -> frozenset[str]:
    """The documented role keys the loader recognizes — the ones a check can read."""
    fields = {field.name for field in dataclasses.fields(Config)}
    return frozenset(_role_key_bullets()) & fields - {_NOT_LOADER_IMPLEMENTED}


def test_every_role_key_consumer_clause_matches_the_checks_that_read_the_key() -> None:
    """The documented enumeration equals the derived one, key by key, both directions."""
    keys = _guarded_keys()
    assert keys, "the inventory must document at least one loader-recognized role key"
    derived = _derived_consumers(keys=keys)
    bullets = _role_key_bullets()

    drift = {
        key: (sorted(derived[key] - documented), sorted(documented - derived[key]))
        for key, documented in (
            (key, _documented_consumers(bullet=bullets[key])) for key in sorted(keys)
        )
        if derived[key] != documented
    }
    assert not drift, (
        f'§"Role keys" is what a consumer reads to decide what declaring a key will arm, so '
        f"an enumeration that disagrees with the code is a correctness defect, not cosmetic "
        f"drift. Each entry is key -> (reads the key but is UNNAMED, named but does NOT read "
        f"it); re-derive the clause from the checks rather than editing it by hand: {drift}"
    )


def _denied_consumers(
    *, bullets: dict[str, str], derived: dict[str, set[str]], slugs: set[str]
) -> dict[str, list[str]]:
    """Per key, the checks a bullet names OUTSIDE its clause that do read the key.

    Any check slug mentioned outside the `**Consumers:**` clause is read as a
    claim that the check is NOT a consumer. Split out from its test so the
    detector can be exercised against a fabricated denial: a guard whose
    reporting path never runs on real data is a guard nobody has watched fire.
    """
    denied: dict[str, list[str]] = {}
    for key, bullet in sorted(bullets.items()):
        mentioned = set(_BACKTICKED.findall(bullet)) & slugs
        contradicted = sorted((mentioned - _documented_consumers(bullet=bullet)) & derived[key])
        if contradicted:
            denied[key] = contradicted
    return denied


def test_no_bullet_denies_a_consumer_the_derivation_finds() -> None:
    """A check the prose names as a NON-consumer must not be one.

    The positive clause alone leaves a hole: a bullet may also state that some
    check does NOT read the key, and that claim drifts the same way. `io_trees`
    carried exactly such a claim about `public_api_result_typed` while the check
    reached `config.io_trees` through `_public_api_exempt_universe`.
    """
    keys = _guarded_keys()
    bullets = _role_key_bullets()
    denied = _denied_consumers(
        bullets={key: bullets[key] for key in keys},
        derived=_derived_consumers(keys=keys),
        slugs=set(_check_slugs(modules=_first_party_modules())),
    )
    assert not denied, (
        f"a bullet names these checks outside its `**Consumers:**` clause while the derivation "
        f"says they read the key — a stale non-consumer claim reads as a guarantee that "
        f"declaring the key leaves them alone, and it does not: {denied}"
    )


def test_the_denial_detector_reports_a_bullet_that_contradicts_the_derivation() -> None:
    """The detector fires on the exact shape `io_trees` carried before this change.

    On a correct inventory the reporting path never runs, so without this the
    guard's only evidence of working is that it stays quiet — which an always-quiet
    stub also does.
    """
    denied = _denied_consumers(
        bullets={
            "io_trees": (
                "- **`io_trees`** — array of strings. **Consumers:** `no_except_outside_io`. "
                "It is NOT consumed by `public_api_result_typed`."
            )
        },
        derived={"io_trees": {"no_except_outside_io", "public_api_result_typed"}},
        slugs={"no_except_outside_io", "public_api_result_typed"},
    )
    assert denied == {"io_trees": ["public_api_result_typed"]}


def test_an_imported_binding_outranks_a_module_s_own_function_of_the_same_name() -> None:
    """Rule 3's alias resolution: a same-named import wins over the local definition.

    The gap-fill that maps a module's own functions must not overwrite a binding
    the import pass already resolved, or a call would be attributed to the local
    definition and its propagated reads lost.
    """
    modules = {
        "pkg.a": ast.parse("def shared(*, config: Config) -> None:\n    print(config.io_trees)\n"),
        "pkg.b": ast.parse("from pkg.a import shared\n\n\ndef shared() -> None:\n    pass\n"),
    }
    aliases = _alias_maps(
        modules=modules,
        functions=_function_table(modules=modules, keys=frozenset({"io_trees"})),
    )
    assert aliases["pkg.b"]["shared"] == "pkg.a.shared"
