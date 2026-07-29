"""Unit test for `checks/_import_resolution.py` — the shared resolution graph.

Extracted from `_public_api_consumption` so livespec v179 member 1's clause-(d)
callee fixpoint can reuse it instead of forking it. This file pins the two
MEASURED defects that shaped it, directly against the extracted functions
rather than only through one consumer — because after the extraction there is
more than one consumer, and a later "simplification" of either function would
otherwise be caught only by whichever consumer happened to have a test for it.

Both defects were in the RELAXING direction, which is the dangerous one: each
made the oracle see LESS consumption than exists, and a smaller count reads as
progress.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.checks._import_resolution import (
    attribute_reaches,
    module_aliases,
    module_name,
    name_imports,
    suffix_index,
)

__all__: list[str] = []


# A LAYERED consumer: the package root sits well below the repo root, so the
# repo-root-relative path and the import path are different strings. This is
# the shape every Driver and orchestrator in the fleet has, and the shape no
# `pkg/a.py` fixture exercises.
_LAYERED = Path(".claude-plugin/scripts/livespec/parse/foo.py")
_LAYERED_CONSUMER = Path(".claude-plugin/scripts/livespec/commands/bar.py")


def test_a_layered_package_resolves_by_dotted_suffix_not_by_repo_path() -> None:
    """`from livespec.parse.foo import compute` resolves though the FILE is deeper.

    A repo-root-relative path is NOT an import path. Under the naive reading
    this module's dotted name would be `.claude-plugin.scripts.livespec.parse.foo`,
    the consumer's import would match nothing, and the oracle would report ZERO
    consumption for a whole repo — silently, which is this fleet's own failure
    mode relocated into its oracle.
    """
    sources = {
        _LAYERED: "def compute() -> int:\n    return 1\n",
        _LAYERED_CONSUMER: "from livespec.parse.foo import compute\n",
    }
    index = suffix_index(sources=sources)
    reached = name_imports(
        tree=ast.parse(sources[_LAYERED_CONSUMER]),
        current=module_name(rel=_LAYERED_CONSUMER),
        index=index,
    )

    assert ("livespec.parse.foo", "compute") in reached


def test_an_ambiguous_suffix_returns_every_candidate() -> None:
    """Two files whose paths end the same way both count — doubt goes toward MORE.

    Returning one candidate, or none, would be the relaxing direction. The
    check that consumes this treats every candidate as reached, so an ambiguous
    suffix over-reports rather than under-reports.
    """
    sources = {
        Path("a/pkg/mod.py"): "def compute() -> int:\n    return 1\n",
        Path("b/pkg/mod.py"): "def compute() -> int:\n    return 2\n",
    }

    assert suffix_index(sources=sources)["pkg.mod"] == frozenset(
        {Path("a/pkg/mod.py"), Path("b/pkg/mod.py")}
    )


def test_an_attribute_base_that_is_not_an_import_binding_reaches_nothing() -> None:
    """A local INSTANCE named like a module must not manufacture a consumption.

    Measured here: `config.pure_trees` on a local `Config` instance matches the
    module path `livespec_dev_tooling.config` by name, and admitting it
    manufactured 19 phantom consumptions in this repo. The base must resolve
    through a name this module actually bound with an `import`.
    """
    consumer = "def use(*, config: object) -> object:\n    return config.pure_trees\n"
    sources = {Path("pkg/config.py"): "PURE_TREES = ()\n", Path("pkg/b.py"): consumer}
    tree = ast.parse(consumer)
    index = suffix_index(sources=sources)
    aliases = module_aliases(tree=tree, current="pkg.b", index=index)

    assert aliases == {} and attribute_reaches(tree=tree, aliases=aliases, index=index) == set()


def test_an_attribute_base_that_is_a_real_import_binding_reaches_the_name() -> None:
    """The same expression DOES count once the base is a real module binding.

    Asserted beside the negative case on purpose: a resolver that reached
    nothing at all would satisfy the test above while breaking the oracle
    entirely, and that failure would look like a clean run.
    """
    consumer = "import pkg.config\n\n\ndef use() -> object:\n    return pkg.config.pure_trees\n"
    sources = {Path("pkg/config.py"): "PURE_TREES = ()\n", Path("pkg/b.py"): consumer}
    tree = ast.parse(consumer)
    index = suffix_index(sources=sources)
    aliases = module_aliases(tree=tree, current="pkg.b", index=index)

    assert ("pkg.config", "pure_trees") in attribute_reaches(
        tree=tree, aliases=aliases, index=index
    )


def test_a_package_init_module_name_drops_the_init_segment() -> None:
    """`pkg/__init__.py` is the module `pkg`, not `pkg.__init__`.

    Getting this wrong makes every `from pkg import a` miss, which is the
    relaxing direction again.
    """
    assert module_name(rel=Path("pkg/__init__.py")) == "pkg"
