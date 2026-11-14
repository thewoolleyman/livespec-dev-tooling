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
