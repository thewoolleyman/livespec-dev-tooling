"""`_delegated_job_routes` — which Job routes reach an authority member unskipped.

The unit tier for the judging half of the delegated Job route trace. Each case
is one route shape from the fleet sweep of 2026-11-08: a justfile `check` recipe
that reads the skip list, a script that reads it, a route that appends to it, a
runner that skips under the gate Job's context variable, and the bypass that
reads nothing.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling._delegated_job_routes import (
    RouteFinding,
    job_recipe_name,
    unhonoured_routes,
)

__all__: list[str] = []

_MEMBER = "check-ledger-thing"
_VARIABLE = "SKIP_TARGETS"

# The aggregate recipe every fixture shares: it reads the skip list and hands it
# to a runner script, the shape most of the fleet's `check` recipes take.
_CHECK = (
    "check:\n"
    "    #!/usr/bin/env bash\n"
    '    read -ra skip_targets <<< "${SKIP_TARGETS:-}"\n'
    '    bash scripts/runner.sh "${skip_targets[@]}"\n'
    "\n"
    "check-skipping *skip_targets:\n"
    '    bash scripts/runner.sh "$@"\n'
    "\n"
    f"{_MEMBER}:\n"
    "    true\n"
    "\n"
    "check-fixed:\n"
    "    true\n"
)


def _trace(
    *,
    root: Path,
    justfile: str,
    scripts: dict[str, str],
    job_recipes: tuple[str, ...],
    members: tuple[str, ...] = (_MEMBER,),
) -> list[RouteFinding]:
    """Lay out a fixture repository and trace `job_recipes` through it."""
    _ = (root / "justfile").write_text(justfile, encoding="utf-8")
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    for name, text in {"runner.sh": "true\n", **scripts}.items():
        _ = (scripts_dir / name).write_text(text, encoding="utf-8")
    return unhonoured_routes(
        repo_root=root, job_recipes=job_recipes, members=members, skip_variable=_VARIABLE
    )


def test_a_suite_entry_names_its_first_token_that_is_not_an_assignment() -> None:
    """Leading `name=value` assignments are not the recipe."""
    assert job_recipe_name(entry="hook_gate=1 check") == "check"
    assert job_recipe_name(entry="check-pre-push") == "check-pre-push"
    assert job_recipe_name(entry="a=1 b=2") is None
    assert job_recipe_name(entry="") is None


def test_a_repository_without_a_justfile_has_no_routes(*, tmp_path: Path) -> None:
    """Nothing can be traced without a justfile."""
    found = unhonoured_routes(
        repo_root=tmp_path, job_recipes=("check",), members=(_MEMBER,), skip_variable=_VARIABLE
    )

    assert found == []


def test_a_job_recipe_the_justfile_does_not_define_is_skipped(*, tmp_path: Path) -> None:
    """The Job's own preflight reports a recipe the tree lacks; this check does not."""
    found = _trace(
        root=tmp_path, justfile=_CHECK, scripts={}, job_recipes=("install-worktree-pack",)
    )

    assert found == []


def test_a_route_into_the_check_recipe_honours_the_list_it_reads(*, tmp_path: Path) -> None:
    """The `check` recipe reads the variable by definition, so arriving there is honouring."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    just hook_gate=1 check\n",
        scripts={},
        job_recipes=("gated", "check"),
    )

    assert found == []


def test_a_route_that_overwrites_the_list_before_check_is_reported(*, tmp_path: Path) -> None:
    """Assigning the variable a literal drops the members the client put in it."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    SKIP_TARGETS='check-fixed' just check\n",
        scripts={},
        job_recipes=("gated",),
    )

    assert found == [
        RouteFinding(job_recipe="gated", member=_MEMBER, route=("just gated", "just check"))
    ]


def test_a_route_that_appends_or_unions_into_check_is_honoured(*, tmp_path: Path) -> None:
    """Reading the inherited list while assigning is carrying it, not overwriting it."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK
        + 'gated:\n    SKIP_TARGETS="${SKIP_TARGETS:+$SKIP_TARGETS }check-fixed" just check\n',
        scripts={},
        job_recipes=("gated",),
    )

    assert found == []


def test_a_bypass_of_the_check_recipe_is_reported_for_every_member(*, tmp_path: Path) -> None:
    """A route to the runner that never names the variable runs every authority member."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    bash scripts/gated.sh\n",
        scripts={"gated.sh": "just check-skipping check-fixed\n"},
        job_recipes=("gated",),
        members=(_MEMBER, "check-other"),
    )

    route = ("just gated", "scripts/gated.sh", "just check-skipping", "scripts/runner.sh")
    assert found == [
        RouteFinding(job_recipe="gated", member=_MEMBER, route=route),
        RouteFinding(job_recipe="gated", member="check-other", route=route),
    ]


def test_a_script_that_reads_the_list_before_the_bypass_is_honoured(*, tmp_path: Path) -> None:
    """The skip read may live in a script the Job recipe calls."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    bash scripts/gated.sh\n",
        scripts={
            "gated.sh": (
                'read -ra delegated <<< "${SKIP_TARGETS:-}"\n'
                'just check-skipping check-fixed "${delegated[@]}"\n'
            )
        },
        job_recipes=("gated",),
    )

    assert found == []


def test_a_comment_naming_the_variable_is_not_a_read(*, tmp_path: Path) -> None:
    """Only code reads the list; a comment mentioning it must not stand in for the read."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    bash scripts/gated.sh\n",
        scripts={"gated.sh": "# SKIP_TARGETS is honoured downstream\njust check-skipping\n"},
        job_recipes=("gated",),
    )

    assert [finding.member for finding in found] == [_MEMBER]


def test_a_runner_that_skips_under_the_gate_context_is_honoured(*, tmp_path: Path) -> None:
    """The runner may skip every authority member whenever the Job's context variable is set."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    bash scripts/gated.sh\n",
        scripts={
            "gated.sh": "just check-skipping\n",
            "runner.sh": 'if [[ -n "${LIVESPEC_GATE_CONTEXT:-}" ]]; then skip_authority; fi\n',
        },
        job_recipes=("gated",),
    )

    assert found == []


def test_a_gate_context_read_outside_the_runner_does_not_honour_the_route(
    *, tmp_path: Path
) -> None:
    """A script that tests the context only to decide whether to delegate skips nothing."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    bash scripts/gated.sh\n",
        scripts={"gated.sh": 'test -z "${LIVESPEC_GATE_CONTEXT:-}"\njust check-skipping\n'},
        job_recipes=("gated",),
    )

    assert [finding.member for finding in found] == [_MEMBER]


def test_a_member_recipe_run_directly_is_reported_for_that_member_only(*, tmp_path: Path) -> None:
    """Calling the authority member's own recipe runs it, whatever else is declared."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + f"gated:\n    just {_MEMBER}\n",
        scripts={},
        job_recipes=("gated",),
        members=(_MEMBER, "check-other"),
    )

    assert found == [
        RouteFinding(job_recipe="gated", member=_MEMBER, route=("just gated", f"just {_MEMBER}"))
    ]


def test_a_fixed_list_holding_no_authority_member_is_not_reported(*, tmp_path: Path) -> None:
    """A route that runs only other members reaches no aggregate and no authority member."""
    found = _trace(
        root=tmp_path,
        justfile=_CHECK + "gated:\n    just check-fixed\n",
        scripts={},
        job_recipes=("gated",),
    )

    assert found == []


def test_routes_through_a_cycle_terminate_and_one_finding_is_kept_per_terminal(
    *, tmp_path: Path
) -> None:
    """Mutually calling recipes are walked once, and two routes to one runner give one finding."""
    found = _trace(
        root=tmp_path,
        justfile="".join(
            (
                _CHECK,
                "gated: ping pong\n    just ping\n",
                "ping:\n    just pong\n    just gated\n",
                "pong:\n    just ping\n    just check-skipping\n",
            )
        ),
        scripts={},
        job_recipes=("gated",),
    )

    assert [(finding.job_recipe, finding.member) for finding in found] == [("gated", _MEMBER)]


def test_without_a_check_recipe_only_direct_member_runs_are_reported(*, tmp_path: Path) -> None:
    """No `check` recipe means no aggregate runner to bypass."""
    found = _trace(
        root=tmp_path,
        justfile=f"gated:\n    just {_MEMBER}\n    just other\n{_MEMBER}:\n    true\nother:\n    true\n",
        scripts={},
        job_recipes=("gated",),
    )

    assert [finding.member for finding in found] == [_MEMBER]
