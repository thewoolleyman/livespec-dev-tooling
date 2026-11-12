"""The flake-retry path analyzer is shipped as a mirrored source module."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_the_path_analyzer_module_is_shipped() -> None:
    """The focused analyzer module remains available to the retry plugin."""
    assert (
        Path(__file__).resolve().parents[2] / "livespec_dev_tooling/flake_retry_paths.py"
    ).is_file()


def test_the_path_analyzer_joins_consecutive_literal_segments() -> None:
    """A path expression exposes its complete literal directory prefixes."""
    module_path = Path(__file__).resolve().parents[2] / "livespec_dev_tooling/flake_retry_paths.py"

    assert module_path.is_file()

    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, undeterminable = analyzer.path_literals(
        tree=ast.parse("_ROOT / 'ci-runner' / 'k3s' / 'phase2' / 'gates' / 'gate.sh'")
    )

    assert paths == {"ci-runner/k3s/phase2/gates", "ci-runner/k3s/phase2/gates/gate.sh"}
    assert not undeterminable


def test_a_dynamic_operand_after_the_first_operand_and_before_a_literal_is_undeterminable() -> None:
    """Only the first operand may be a dynamic root; a later one hides path components."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    _, undeterminable = analyzer.path_literals(tree=ast.parse("_ROOT / segment / 'gates'"))

    assert undeterminable


def test_a_dynamic_first_operand_is_a_root_and_stays_determinable() -> None:
    """A dynamic root before the literal components is the normal repository-root shape."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    _, undeterminable = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates'"))

    assert not undeterminable


def test_a_repository_root_name_keeps_a_dynamic_segment_undeterminable(*, tmp_path: Path) -> None:
    """A root bound from this test file can name a changed repository directory."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")
    source_path = tmp_path / "tests" / "test_anchor.py"
    source_path.parent.mkdir()

    _, undeterminable = analyzer.path_literals(
        tree=ast.parse(
            "from pathlib import Path\n"
            "_ROOT = Path(__file__).resolve().parents[1]\n"
            "_TARGET = _ROOT / 'ci-runner' / segment\n"
        ),
        repo_root=tmp_path,
        source_path=source_path,
    )

    assert undeterminable


def test_a_path_parent_index_outside_the_source_path_is_not_a_repository_root(
    *, tmp_path: Path
) -> None:
    """An out-of-range ``parents`` index does not make an unknown root unsafe."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")
    source_path = tmp_path / "test_anchor.py"

    _, undeterminable = analyzer.path_literals(
        tree=ast.parse(
            "from pathlib import Path\n"
            "_ROOT = Path(__file__).resolve().parents[100]\n"
            "_TARGET = _ROOT / 'ci-runner' / segment\n"
        ),
        repo_root=tmp_path,
        source_path=source_path,
    )

    assert not undeterminable


def test_a_suffixless_terminal_component_names_its_own_directory() -> None:
    """A terminal such as Makefile may be a file, so it names its directory too."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, _ = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates' / 'Makefile'"))

    assert "ci-runner/gates" in paths
    assert "ci-runner/gates/Makefile" in paths


def test_a_suffixless_terminal_component_is_also_a_file_name_literal() -> None:
    """A terminal such as Makefile touches a changed file of that name anywhere."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, _ = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates' / 'Makefile'"))

    assert "Makefile" in paths


def test_a_dynamic_terminal_operand_adds_no_file_name_literal() -> None:
    """Only a literal final operand can be a file name."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, _ = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates' / name"))

    assert "gates" not in paths


def test_ordinary_arithmetic_division_is_not_an_undeterminable_path() -> None:
    """A division with no string-literal operand is arithmetic, not a path expression."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, undeterminable = analyzer.path_literals(tree=ast.parse("elapsed.total_seconds() / 60"))

    assert not undeterminable
    assert paths == set()


def test_a_fully_dynamic_division_chain_is_not_an_undeterminable_path() -> None:
    """Without any string literal operand a chain cannot be identified as a path."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    _, undeterminable = analyzer.path_literals(tree=ast.parse("total / count / 2"))

    assert not undeterminable


def _undeterminable_for(*, source: str, tmp_path: Path) -> bool:
    """Run the analyzer on `source` as if it were a test module under `tmp_path`."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")
    source_path = tmp_path / "tests" / "test_anchor.py"
    source_path.parent.mkdir(exist_ok=True)
    _, undeterminable = analyzer.path_literals(
        tree=ast.parse(source), repo_root=tmp_path, source_path=source_path
    )
    return bool(undeterminable)


_ROOT_BINDING = "from pathlib import Path\n"


def test_a_root_bound_in_one_function_does_not_bind_a_parameter_of_another(
    *, tmp_path: Path
) -> None:
    """A parameter named like another function's repository root is an unrelated base."""
    source = (
        _ROOT_BINDING
        + "def bound():\n"
        + "    root = Path(__file__).resolve().parents[1]\n"
        + "    return root / 'ci-runner'\n"
        + "def unrelated(root, name):\n"
        + "    return root / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_local_root_in_one_function_does_not_bind_another_functions_local(
    *, tmp_path: Path
) -> None:
    """Two functions each binding `root` keep their bindings apart."""
    source = (
        _ROOT_BINDING
        + "def bound():\n"
        + "    root = Path(__file__).resolve().parents[1]\n"
        + "    return root / 'ci-runner'\n"
        + "def unrelated(base, name):\n"
        + "    root = base / 'x'\n"
        + "    return root / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_root_bound_in_the_same_function_keeps_a_dynamic_segment_undeterminable(
    *, tmp_path: Path
) -> None:
    """The function that binds the root still withholds on a dynamic segment."""
    source = (
        _ROOT_BINDING
        + "def bound(name):\n"
        + "    root = Path(__file__).resolve().parents[1]\n"
        + "    return root / 'ci-runner' / name\n"
    )

    assert _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_module_level_root_reaches_a_nested_function_that_does_not_rebind_it(
    *, tmp_path: Path
) -> None:
    """A function reading the module-level root through closure still names it."""
    source = (
        _ROOT_BINDING
        + "ROOT = Path(__file__).resolve().parents[1]\n"
        + "def reader(name):\n"
        + "    def inner():\n"
        + "        return ROOT / 'ci-runner' / name\n"
        + "    return inner\n"
    )

    assert _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_function_that_rebinds_the_module_root_name_shadows_it(*, tmp_path: Path) -> None:
    """A local binding of the same name hides the module-level repository root."""
    source = (
        _ROOT_BINDING
        + "ROOT = Path(__file__).resolve().parents[1]\n"
        + "def shadowing(ROOT, name):\n"
        + "    return ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_class_body_root_is_not_visible_to_its_methods(*, tmp_path: Path) -> None:
    """Python resolves a method's free names past the class body."""
    source = (
        _ROOT_BINDING
        + "class Holder:\n"
        + "    root = Path(__file__).resolve().parents[1]\n"
        + "    def method(self, name):\n"
        + "        return root / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_lambda_parameter_shadows_the_module_root_name(*, tmp_path: Path) -> None:
    """A lambda parameter is its own binding scope."""
    source = (
        _ROOT_BINDING
        + "ROOT = Path(__file__).resolve().parents[1]\n"
        + "join = lambda ROOT, name: ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


_MODULE_ROOT = _ROOT_BINDING + "ROOT = Path(__file__).resolve().parents[1]\n"


def test_an_async_function_parameter_shadows_the_module_root_name(*, tmp_path: Path) -> None:
    """An async function is a binding scope like any other function."""
    source = (
        _MODULE_ROOT + "async def shadowing(ROOT, name):\n    return ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_comprehension_variable_shadows_the_module_root_name(*, tmp_path: Path) -> None:
    """A comprehension target binds in the comprehension, not in the module."""
    source = (
        _MODULE_ROOT
        + "def shadowing(names, name):\n"
        + "    return [ROOT / 'ci-runner' / name for ROOT in names]\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_comprehension_variable_does_not_shadow_the_name_outside_it(*, tmp_path: Path) -> None:
    """The enclosing function still reads the module-level root."""
    source = (
        _MODULE_ROOT
        + "def reading(names, name):\n"
        + "    listed = [0 for ROOT in names]\n"
        + "    return ROOT / 'ci-runner' / name\n"
    )

    assert _undeterminable_for(source=source, tmp_path=tmp_path)


def test_an_import_inside_a_function_shadows_the_module_root_name(*, tmp_path: Path) -> None:
    """An import binds the name it introduces in the importing scope."""
    source = (
        _MODULE_ROOT
        + "def shadowing(name):\n"
        + "    from elsewhere import anchor as ROOT\n"
        + "    return ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_dotted_import_binds_its_first_component(*, tmp_path: Path) -> None:
    """``import a.b`` binds ``a``."""
    source = (
        _ROOT_BINDING
        + "a = Path(__file__).resolve().parents[1]\n"
        + "def shadowing(name):\n"
        + "    import a.b\n"
        + "    return a / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_an_exception_name_shadows_the_module_root_name(*, tmp_path: Path) -> None:
    """An ``except ... as`` name is bound in the handling scope."""
    source = (
        _MODULE_ROOT
        + "def shadowing(name):\n"
        + "    try:\n"
        + "        pass\n"
        + "    except Exception as ROOT:\n"
        + "        return ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_nested_definition_shadows_the_module_root_name(*, tmp_path: Path) -> None:
    """A ``def`` or ``class`` statement binds its own name in the enclosing scope."""
    source = (
        _MODULE_ROOT
        + "def shadowing(name):\n"
        + "    def ROOT():\n"
        + "        pass\n"
        + "    return ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_root_declared_global_stays_a_root_in_every_scope(*, tmp_path: Path) -> None:
    """A function assigning a global root makes that name a root wherever it is read."""
    source = (
        _ROOT_BINDING
        + "def setter():\n"
        + "    global ROOT\n"
        + "    ROOT = Path(__file__).resolve().parents[1]\n"
        + "def reader(name):\n"
        + "    return ROOT / 'ci-runner' / name\n"
    )

    assert _undeterminable_for(source=source, tmp_path=tmp_path)


def test_an_attribute_assignment_does_not_bind_a_root_name(*, tmp_path: Path) -> None:
    """Only a plain name target can become a repository-root name."""
    source = (
        _ROOT_BINDING
        + "holder.root = Path(__file__).resolve().parents[1]\n"
        + "def reader(root, name):\n"
        + "    return root / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_default_argument_is_read_in_the_enclosing_scope(*, tmp_path: Path) -> None:
    """A parameter default sees the module root even when the parameter shares its name."""
    source = _MODULE_ROOT + "def reading(ROOT=ROOT / 'ci-runner' / dynamic):\n    return ROOT\n"

    assert _undeterminable_for(source=source, tmp_path=tmp_path)


def test_an_annotated_repository_root_binding_keeps_a_dynamic_segment_undeterminable(
    *, tmp_path: Path
) -> None:
    """A root bound with a type annotation is still a repository-root anchor."""
    source = (
        _ROOT_BINDING
        + "REPO_ROOT: Path = Path(__file__).resolve().parents[1]\n"
        + "def reading(name):\n"
        + "    return REPO_ROOT / 'ci-runner' / name\n"
    )

    assert _undeterminable_for(source=source, tmp_path=tmp_path)


def test_a_bare_annotation_does_not_bind_a_repository_root(*, tmp_path: Path) -> None:
    """An annotation with no value binds no root, so it stays a non-repository base."""
    source = (
        _ROOT_BINDING
        + "REPO_ROOT: Path\n"
        + "def reading(name):\n"
        + "    return REPO_ROOT / 'ci-runner' / name\n"
    )

    assert not _undeterminable_for(source=source, tmp_path=tmp_path)
