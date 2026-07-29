"""Unit test for `checks/_public_api_consumption.py` — the v178 consumption oracle.

`livespec` v178 (`non-functional-requirements.md` §"ROP composition") makes a
top-level function PUBLIC API for the Result-return rule only when it is
CONSUMED ACROSS A BOUNDARY. This module owns the two forms a REPO-LOCAL vantage
can compute: a product import across a module boundary inside this repo, and a
process entry point.

The load-bearing property under test is that the oracle resolves an import to
its DEFINING MODULE. A bare-name oracle was measured WRONG on this very repo:
it scored `merged_branch_sweep.fetch_manifest` public on two consumers that
both import a DIFFERENT `fetch_manifest`, and produced 51 false `parse_argv`
hits against a sibling's homonym.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks._public_api_consumption import repo_local_public_names

__all__: list[str] = []


_CONSUMER_IMPORT = "from __future__ import annotations\n\nfrom pkg.a import compute\n\n\ndef use() -> int:\n    return compute()\n"


def test_a_cross_module_product_import_makes_the_name_public() -> None:
    """`from pkg.a import compute` in another module makes `compute` public."""
    sources = {
        Path("pkg/a.py"): "def compute() -> int:\n    return 1\n",
        Path("pkg/b.py"): _CONSUMER_IMPORT,
    }
    assert (Path("pkg/a.py"), "compute") in repo_local_public_names(sources=sources)


def test_a_name_used_only_inside_its_own_module_is_not_public() -> None:
    """A same-module caller is not a boundary — the name stays non-public.

    v178 draws the line at a MODULE boundary for the declaring repo, so a
    helper its own module calls is scaffolding, not API.
    """
    sources = {
        Path(
            "pkg/a.py"
        ): "def compute() -> int:\n    return 1\n\n\ndef other() -> int:\n    return compute()\n",
    }
    assert (Path("pkg/a.py"), "compute") not in repo_local_public_names(sources=sources)


def test_the_oracle_resolves_an_import_to_its_defining_module() -> None:
    """Two modules define the same name; only the IMPORTED one is public.

    This is the measured defect a bare-name oracle produced, pinned as a test
    so no later simplification can reintroduce it.
    """
    sources = {
        Path("pkg/one.py"): "def fetch_manifest() -> int:\n    return 1\n",
        Path("pkg/two.py"): "def fetch_manifest() -> int:\n    return 2\n",
        Path(
            "pkg/consumer.py"
        ): "from pkg.one import fetch_manifest\n\n\ndef use() -> int:\n    return fetch_manifest()\n",
    }
    public = repo_local_public_names(sources=sources)
    assert (Path("pkg/one.py"), "fetch_manifest") in public and (
        Path("pkg/two.py"),
        "fetch_manifest",
    ) not in public


def test_an_attribute_call_on_an_imported_module_counts_as_consumption() -> None:
    """`import pkg.a` + `pkg.a.compute()` consumes `compute` across the boundary."""
    sources = {
        Path("pkg/a.py"): "def compute() -> int:\n    return 1\n",
        Path("pkg/b.py"): "import pkg.a\n\n\ndef use() -> int:\n    return pkg.a.compute()\n",
    }
    assert (Path("pkg/a.py"), "compute") in repo_local_public_names(sources=sources)


def test_an_aliased_module_import_counts_as_consumption() -> None:
    """`import pkg.a as mod` + `mod.compute()` resolves through the alias."""
    sources = {
        Path("pkg/a.py"): "def compute() -> int:\n    return 1\n",
        Path("pkg/b.py"): "import pkg.a as mod\n\n\ndef use() -> int:\n    return mod.compute()\n",
    }
    assert (Path("pkg/a.py"), "compute") in repo_local_public_names(sources=sources)


def test_an_aliased_name_import_is_attributed_to_the_defining_name() -> None:
    """`from pkg.a import compute as c` makes `compute`, not `c`, public."""
    sources = {
        Path("pkg/a.py"): "def compute() -> int:\n    return 1\n",
        Path("pkg/b.py"): "from pkg.a import compute as c\n\n\ndef use() -> int:\n    return c()\n",
    }
    public = repo_local_public_names(sources=sources)
    assert (Path("pkg/a.py"), "compute") in public and (Path("pkg/a.py"), "c") not in public


def test_a_relative_import_resolves_to_its_package_module() -> None:
    """`from .a import compute` inside `pkg/b.py` resolves to `pkg.a`."""
    sources = {
        Path("pkg/a.py"): "def compute() -> int:\n    return 1\n",
        Path("pkg/b.py"): "from .a import compute\n\n\ndef use() -> int:\n    return compute()\n",
    }
    assert (Path("pkg/a.py"), "compute") in repo_local_public_names(sources=sources)


def test_a_submodule_import_from_a_package_binds_the_module_not_a_name() -> None:
    """`from pkg import a` binds the MODULE `pkg.a`, so `pkg/__init__.py` gains nothing.

    Measured on the real fleet: every imported-but-undeclared name at v178's
    ratification was a SUBMODULE, so mistaking one for a function import is
    the likeliest way this oracle over-reports.
    """
    sources = {
        Path("pkg/__init__.py"): "",
        Path("pkg/a.py"): "def compute() -> int:\n    return 1\n",
        Path("pkg/b.py"): "from pkg import a\n\n\ndef use() -> int:\n    return a.compute()\n",
    }
    public = repo_local_public_names(sources=sources)
    assert (Path("pkg/a.py"), "compute") in public and (
        Path("pkg/__init__.py"),
        "a",
    ) not in public


def test_a_main_guard_entry_point_declared_in_all_is_public() -> None:
    """A `main` reached as a process and listed in `__all__` stays in scope.

    Form 3 exists to stop "nobody imports it, therefore it is not public" from
    becoming an escape for a process entry point.
    """
    sources = {
        Path(
            "pkg/cli.py"
        ): '__all__: list[str] = ["main"]\n\n\ndef main() -> int:\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
    }
    assert (Path("pkg/cli.py"), "main") in repo_local_public_names(sources=sources)


def test_a_main_guard_entry_point_absent_from_all_is_not_public() -> None:
    """Form 3 is `__all__`-scoped, unlike forms 1, 2 and 4.

    v178's tightening clause enumerates forms 1, 2 and 4 as `__all__`-INDEPENDENT
    and deliberately omits form 3. Reading form 3 as independent too would make
    every undeclared `main()` in the fleet public API overnight, which is not what
    the ratified criterion was measured to do.
    """
    sources = {
        Path(
            "pkg/cli.py"
        ): '__all__: list[str] = []\n\n\ndef main() -> int:\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
    }
    assert (Path("pkg/cli.py"), "main") not in repo_local_public_names(sources=sources)


def test_a_consumed_name_that_is_not_a_top_level_function_is_ignored() -> None:
    """The rule reaches top-level FUNCTIONS; an imported constant is not one."""
    sources = {
        Path("pkg/a.py"): "CONSTANT = 1\n",
        Path(
            "pkg/b.py"
        ): "from pkg.a import CONSTANT\n\n\ndef use() -> int:\n    return CONSTANT\n",
    }
    assert (Path("pkg/a.py"), "CONSTANT") not in repo_local_public_names(sources=sources)


def test_a_module_level_if_that_is_not_a_main_guard_is_ignored() -> None:
    """Only the `__main__` guard supplies form 3 — any other module-level `if` does not.

    A `if TYPE_CHECKING:` block is the common shape, and reading it as an entry
    point would pull every conditionally-imported name into scope.
    """
    sources = {
        Path(
            "pkg/cli.py"
        ): '__all__: list[str] = ["main"]\n\n\ndef main() -> int:\n    return 0\n\n\nif __debug__:\n    _ = main\n',
    }
    assert (Path("pkg/cli.py"), "main") not in repo_local_public_names(sources=sources)


def test_a_relative_import_from_a_top_level_module_resolves_by_its_own_name() -> None:
    """A relative import with no package above it anchors on the imported name itself."""
    sources = {
        Path("a.py"): "def compute() -> int:\n    return 1\n",
        Path("b.py"): "from .a import compute\n\n\ndef use() -> int:\n    return compute()\n",
    }
    assert (Path("a.py"), "compute") in repo_local_public_names(sources=sources)


def test_an_import_of_a_module_outside_the_universe_is_ignored() -> None:
    """A third-party or absent module resolves to nothing rather than guessing."""
    sources = {
        Path("pkg/b.py"): "from json import loads\n\n\ndef use() -> int:\n    return loads('1')\n",
    }
    assert repo_local_public_names(sources=sources) == frozenset()


def test_an_attribute_on_a_local_instance_is_not_consumption() -> None:
    """A local object named like a module must not manufacture a consumption.

    The oracle's resolution now lives in the shared `_import_resolution`
    module, so this pins the property at the level a CALLER of the oracle
    cares about: `config.pure_trees` on a `Config` INSTANCE matched the module
    path `livespec_dev_tooling.config` by name and produced 19 phantom
    consumptions here. Phantom consumption is the TIGHTENING direction — it
    invents public API — and it is the mirror of the bare-name defect above.
    """
    sources = {
        Path("pkg/config.py"): "def pure_trees() -> int:\n    return 1\n",
        Path("pkg/b.py"): "def use(*, config: object) -> object:\n    return config.pure_trees()\n",
    }
    assert (Path("pkg/config.py"), "pure_trees") not in repo_local_public_names(sources=sources)
