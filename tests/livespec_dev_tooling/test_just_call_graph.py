"""`_just_call_graph` — the edges between justfile recipes and the scripts they call.

The unit tier for the reading half of the delegated Job route trace. What is
asserted here is which edges the reader sees and which it refuses to invent: a
computed invocation, a quoted mention and a printed message are not calls.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling._just_call_graph import (
    CallGraph,
    Node,
    build_call_graph,
    callees,
    invoked_nodes,
    node_text,
)

__all__: list[str] = []


def _graph(*, root: Path, justfile: str, scripts: dict[str, str] | None = None) -> CallGraph:
    """Lay out a fixture repository and read its call graph."""
    _ = (root / "justfile").write_text(justfile, encoding="utf-8")
    for relative, text in (scripts or {}).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
    graph = build_call_graph(repo_root=root)
    assert graph is not None
    return graph


def _recipe(*, name: str) -> Node:
    """The node for a recipe."""
    return Node(kind="recipe", name=name)


def _script(*, name: str) -> Node:
    """The node for a script."""
    return Node(kind="script", name=name)


def test_a_repository_without_a_justfile_has_no_graph(*, tmp_path: Path) -> None:
    """No readable justfile means nothing to trace."""
    assert build_call_graph(repo_root=tmp_path) is None


def test_node_labels_name_recipes_as_just_invocations() -> None:
    """A recipe prints as the command that runs it; a script prints as its path."""
    assert _recipe(name="check").label() == "just check"
    assert _script(name="scripts/x.sh").label() == "scripts/x.sh"


def test_imports_are_read_and_a_missing_or_looping_import_is_tolerated(*, tmp_path: Path) -> None:
    """Imported recipes join the graph; a missing import is skipped; a loop is bounded."""
    _ = (tmp_path / "pack.just").write_text("from-pack:\n    true\n", encoding="utf-8")
    graph = _graph(
        root=tmp_path,
        justfile=(
            "import 'pack.just'\nimport? 'absent.just'\nimport 'justfile'\n\nlocal:\n    true\n"
        ),
    )

    assert set(graph.recipes) == {"from-pack", "local"}


def test_recipe_headers_carry_parameters_dependencies_and_bodies(*, tmp_path: Path) -> None:
    """Parameters are counted, a variadic one is flagged, and settings are not recipes."""
    graph = _graph(
        root=tmp_path,
        justfile=(
            "set shell := ['bash', '-c']\n"
            "version := '1'\n"
            "\n"
            "[positional-arguments]\n"
            "@run first second='x' *rest: build (lint arg) && finish\n"
            "    # a comment, not a call\n"
            "    echo hi\n"
            "\n"
            "build:\n"
            "    true\n"
        ),
    )

    run = graph.recipes["run"]
    assert (run.parameter_count, run.variadic) == (3, True)
    assert run.dependencies == ("build", "lint", "arg", "finish")
    assert "comment" not in run.body
    assert set(graph.recipes) == {"run", "build"}


def test_node_text_reads_recipes_and_scripts_and_degrades_to_empty(*, tmp_path: Path) -> None:
    """An unknown recipe, a missing script and an undecodable script all read as empty."""
    graph = _graph(
        root=tmp_path,
        justfile="known:\n    echo body\n",
        scripts={"scripts/ok.sh": "# comment\nrun it\n"},
    )
    _ = (tmp_path / "scripts" / "binary.sh").write_bytes(b"\xff\xfe")

    assert "echo body" in node_text(graph=graph, node=_recipe(name="known"))
    assert node_text(graph=graph, node=_recipe(name="unknown")) == ""
    assert node_text(graph=graph, node=_script(name="scripts/ok.sh")) == "run it"
    assert node_text(graph=graph, node=_script(name="scripts/missing.sh")) == ""
    assert node_text(graph=graph, node=_script(name="scripts/binary.sh")) == ""


def test_callees_of_an_unknown_recipe_are_empty(*, tmp_path: Path) -> None:
    """A node the justfile does not define reaches nothing."""
    graph = _graph(root=tmp_path, justfile="known:\n    true\n")

    assert callees(graph=graph, node=_recipe(name="unknown")) == []


def test_recipe_callees_follow_dependencies_invocations_and_scripts(*, tmp_path: Path) -> None:
    """Dependencies, `just` invocations with their arguments, and script paths are edges."""
    graph = _graph(
        root=tmp_path,
        justfile=(
            "entry: dep missing\n"
            "    just --quiet mode=1 beta\n"
            "    just wide one two && just gamma\n"
            "    bash scripts/run.sh\n"
            "dep:\n    true\n"
            "beta:\n    true\n"
            "gamma:\n    true\n"
            "wide *args:\n    true\n"
            "one:\n    true\n"
        ),
        scripts={"scripts/run.sh": "true\n"},
    )

    reached = callees(graph=graph, node=_recipe(name="entry"))

    assert reached == [
        _recipe(name="dep"),
        _recipe(name="beta"),
        _recipe(name="wide"),
        _recipe(name="gamma"),
        _script(name="scripts/run.sh"),
    ]


def test_fixed_parameters_consume_the_arguments_that_follow(*, tmp_path: Path) -> None:
    """After a one-parameter recipe, the next token is a recipe again; a computed one stops."""
    graph = _graph(
        root=tmp_path,
        justfile=(
            "entry:\n"
            "    just takes arg second\n"
            '    just "$target" never\n'
            "takes x:\n    true\n"
            "second:\n    true\n"
            "never:\n    true\n"
        ),
    )

    assert callees(graph=graph, node=_recipe(name="entry")) == [
        _recipe(name="takes"),
        _recipe(name="second"),
    ]


def test_a_quoted_mention_and_a_printed_message_are_not_calls(*, tmp_path: Path) -> None:
    """Text inside an open quote, and an echo or printf line, invoke nothing."""
    graph = _graph(
        root=tmp_path,
        justfile=(
            "entry:\n"
            '    echo "running just beta"\n'
            "    printf 'just beta'\n"
            "    bash -c 'just beta'\n"
            '    log "to run: just beta"\n'
            "beta:\n    true\n"
        ),
    )

    assert callees(graph=graph, node=_recipe(name="entry")) == []


def test_unbalanced_quotes_fall_back_to_whitespace_splitting(*, tmp_path: Path) -> None:
    """A `just` argv whose quotes do not balance still names its recipe."""
    graph = _graph(root=tmp_path, justfile='entry:\n    just beta "open\nbeta:\n    true\n')

    assert callees(graph=graph, node=_recipe(name="entry")) == [_recipe(name="beta")]


def test_script_paths_resolve_from_the_root_or_the_calling_script(*, tmp_path: Path) -> None:
    """A path is tried from the root, then beside the caller, and never outside the root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (tmp_path / "outside.sh").write_text("true\n", encoding="utf-8")
    graph = _graph(
        root=repo,
        justfile="entry:\n    bash tools/outer.sh\n",
        scripts={
            "tools/outer.sh": (
                'bash "${here}/sibling.sh"\nbash ../outside.sh\nbash missing.sh\nuv run tools/x.py\n'
            ),
            "tools/sibling.sh": "true\n",
            "tools/x.py": "pass\n",
        },
    )

    assert callees(graph=graph, node=_recipe(name="entry")) == [_script(name="tools/outer.sh")]
    assert callees(graph=graph, node=_script(name="tools/outer.sh")) == [
        _script(name="tools/sibling.sh"),
        _script(name="tools/x.py"),
    ]


def test_invoked_nodes_reads_arbitrary_text_as_seen_from_a_node(*, tmp_path: Path) -> None:
    """The line-level reader the aggregate-runner detection reuses."""
    graph = _graph(
        root=tmp_path,
        justfile="check:\n    true\nother:\n    true\n",
        scripts={"scripts/agg.sh": "true\n"},
    )

    reached = invoked_nodes(
        graph=graph,
        node=_recipe(name="check"),
        text='bash scripts/agg.sh "${skip_targets[@]}"\njust other',
    )

    assert reached == [_script(name="scripts/agg.sh"), _recipe(name="other")]
