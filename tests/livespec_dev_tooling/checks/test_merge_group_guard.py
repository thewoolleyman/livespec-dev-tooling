"""Branch-level tests for `livespec_dev_tooling/checks/_merge_group_guard.py`.

The outside-in cases live in `test_self_hosted_routing.py`; these drive the
pure recognizer directly over each condition of the guarded `merge_group`
shape (SPECIFICATION/contracts.md, the `self_hosted_routing` check, (a)-(f)).
"""

from __future__ import annotations

from livespec_dev_tooling.checks._merge_group_guard import (
    guarded_merge_group_is_valid,
    routes_merge_group_to_self_hosted,
)

__all__: list[str] = []

_LABELS = frozenset({"local-ci"})
_ALLOW = ("dependabot[bot]",)

_GUARD = (
    "  guard:\n"
    "    runs-on: ubuntu-latest\n"
    "    permissions:\n"
    "      contents: read\n"
    "      pull-requests: read\n"
    "    outputs:\n"
    "      trusted: ${{ steps.r.outputs.trusted }}\n"
    "    steps:\n"
    "      - id: r\n"
    "        run: echo trusted=true\n"
)
_CHECK = (
    "  check:\n"
    "    needs: [guard]\n"
    "    if: ${{ !cancelled() }}\n"
    "    runs-on: ${{ needs.guard.outputs.trusted == 'true' && 'local-ci' || 'ubuntu-latest' }}\n"
    "    steps:\n"
    "      - run: just check\n"
)
_HEADER = "name: CI\non:\n  pull_request:\n  merge_group:\njobs:\n"


def _valid(*, source: str, allow: tuple[str, ...] = _ALLOW) -> bool:
    return guarded_merge_group_is_valid(
        source=source, gating_labels=_LABELS, author_allowlist=allow
    )


def test_the_canonical_shape_is_valid() -> None:
    assert _valid(source=_HEADER + _GUARD + _CHECK)


def test_jobs_block_ends_at_the_next_column_zero_key() -> None:
    assert _valid(source=_HEADER + _GUARD + _CHECK + "permissions:\n  contents: read\n")


def test_no_jobs_is_not_valid() -> None:
    assert not _valid(source=_HEADER)


def test_empty_allowlist_is_not_valid() -> None:
    assert not _valid(source=_HEADER + _GUARD + _CHECK, allow=())


def test_read_all_guard_permissions_are_read_only() -> None:
    guard = _GUARD.replace(
        "    permissions:\n      contents: read\n      pull-requests: read\n",
        "    permissions: read-all\n",
    )
    assert _valid(source=_HEADER + guard + _CHECK)


def test_guard_without_permissions_is_not_valid() -> None:
    guard = _GUARD.replace(
        "    permissions:\n      contents: read\n      pull-requests: read\n", ""
    )
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_guard_with_an_empty_permissions_block_is_not_valid() -> None:
    guard = _GUARD.replace("      contents: read\n      pull-requests: read\n", "")
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_guard_with_a_write_permission_is_not_valid() -> None:
    guard = _GUARD.replace("pull-requests: read", "pull-requests: write")
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_self_hosted_guard_is_not_valid() -> None:
    guard = _GUARD.replace("runs-on: ubuntu-latest", "runs-on: [self-hosted, local-ci]")
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_guard_without_runs_on_is_not_valid() -> None:
    guard = _GUARD.replace("    runs-on: ubuntu-latest\n", "")
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_indented_needs_list_is_read() -> None:
    check = _CHECK.replace("    needs: [guard]\n", "    needs:\n      - guard\n")
    assert _valid(source=_HEADER + _GUARD + check)


def test_scalar_needs_is_read() -> None:
    check = _CHECK.replace("    needs: [guard]\n", "    needs: guard\n")
    assert _valid(source=_HEADER + _GUARD + check)


def test_a_needs_cycle_that_never_reaches_the_guard_is_not_valid() -> None:
    cycle = (
        "  a:\n    needs: [b]\n    runs-on: ubuntu-latest\n"
        "  b:\n    needs: [a, missing]\n    runs-on: ubuntu-latest\n"
    )
    assert not _valid(source=_HEADER + _GUARD + _CHECK + cycle)


def test_no_gating_job_is_not_valid() -> None:
    check = _CHECK.replace("'local-ci'", "'ubuntu-22.04'").replace("'ubuntu-latest'", "'x'")
    assert not _valid(source=_HEADER + _GUARD + check)


def test_gating_route_not_conditioned_on_the_guard_output_is_not_valid() -> None:
    check = _CHECK.replace("needs.guard.outputs.trusted", "github.event_name")
    assert not _valid(source=_HEADER + _GUARD + check)


def test_gating_route_without_a_hosted_literal_is_not_valid() -> None:
    check = _CHECK.replace("|| 'ubuntu-latest'", "|| 'macos-latest'")
    assert not _valid(source=_HEADER + _GUARD + check)


def test_required_legs_gate_must_name_its_own_job_id() -> None:
    check = _CHECK.replace("    if: ${{ !cancelled() }}\n", "")
    gate = (
        "  ci-green:\n"
        "    needs: [check]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: python3 -m livespec_dev_tooling.ci_green_required_legs --gate-job {gate}\n"
    )
    assert _valid(source=_HEADER + _GUARD + check + gate.format(gate="ci-green"))
    assert not _valid(source=_HEADER + _GUARD + check + gate.format(gate="ci-green-2"))


def test_routes_merge_group_to_self_hosted() -> None:
    assert routes_merge_group_to_self_hosted(
        source=_HEADER + _GUARD + _CHECK, gating_labels=_LABELS
    )
    hosted = _CHECK.replace("'local-ci'", "'ubuntu-22.04'")
    assert not routes_merge_group_to_self_hosted(
        source=_HEADER + _GUARD + hosted, gating_labels=_LABELS
    )
    no_queue = (_HEADER + _GUARD + _CHECK).replace("  merge_group:\n", "")
    assert not routes_merge_group_to_self_hosted(source=no_queue, gating_labels=_LABELS)


# --- Reviewer-reproduced fail-opens (livespec-dev-tooling#4734 grade) --------


def test_a_block_list_self_hosted_job_beside_a_valid_one_is_not_valid() -> None:
    """Fix 1: a block-list `runs-on` is read, so an unconditioned self-hosted job is caught."""
    rogue = (
        "  rogue:\n"
        "    needs: [guard]\n"
        "    if: ${{ !cancelled() }}\n"
        "    runs-on:\n"
        "      - self-hosted\n"
        "      - local-ci\n"
        "    steps:\n"
        "      - run: just check\n"
    )
    assert not _valid(source=_HEADER + _GUARD + _CHECK + rogue)


def test_a_write_all_guard_echoing_read_all_is_not_valid() -> None:
    """Fix 2: the read-only test reads the guard's own `permissions` key, not its body text."""
    guard = _GUARD.replace(
        "    permissions:\n      contents: read\n      pull-requests: read\n",
        "    permissions: write-all\n",
    ).replace("        run: echo trusted=true\n", '        run: echo "permissions: read-all"\n')
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_a_route_selecting_self_hosted_on_another_condition_is_not_valid() -> None:
    """Fix 3: self-hosted capacity is selected ONLY under the guard-output condition."""
    check = _CHECK.replace(
        "    runs-on: ${{ needs.guard.outputs.trusted == 'true' && 'local-ci' || 'ubuntu-latest' }}\n",
        "    runs-on: ${{ github.event_name == 'merge_group' && 'local-ci'"
        " || needs.guard.outputs.trusted == 'true' && 'ubuntu-latest' || 'ubuntu-latest' }}\n",
    )
    assert not _valid(source=_HEADER + _GUARD + check)


def test_a_guard_routed_by_a_repository_variable_is_not_valid() -> None:
    """Fix 4: a guard whose `runs-on` comes from a variable does not name hosted capacity only."""
    guard = _GUARD.replace(
        "    runs-on: ubuntu-latest\n",
        "    runs-on: ${{ fromJSON(vars.GUARD_RUNNER || '\"ubuntu-latest\"') }}\n",
    )
    assert not _valid(source=_HEADER + guard + _CHECK)


def test_a_route_whose_fallback_is_a_variable_is_not_valid() -> None:
    """Fix 3: the non-guard arm must be the hosted literal itself."""
    check = _CHECK.replace("|| 'ubuntu-latest' }}", "|| vars.FALLBACK || 'ubuntu-latest' }}")
    assert not _valid(source=_HEADER + _GUARD + check)


def test_a_route_with_a_compound_guard_condition_is_not_valid() -> None:
    """Fix 3: the condition is the guard output alone, not the guard output AND more."""
    check = _CHECK.replace("== 'true' && 'local-ci'", "== 'true' && github.actor && 'local-ci'")
    assert not _valid(source=_HEADER + _GUARD + check)


def test_a_route_that_is_not_an_expression_is_not_valid() -> None:
    check = _CHECK.replace(
        "    runs-on: ${{ needs.guard.outputs.trusted == 'true' && 'local-ci' || 'ubuntu-latest' }}\n",
        "    runs-on: [self-hosted, local-ci] # needs.guard.outputs. ubuntu-latest\n",
    )
    assert not _valid(source=_HEADER + _GUARD + check)
