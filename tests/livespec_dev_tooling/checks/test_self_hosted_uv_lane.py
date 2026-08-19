"""Outside-in test for `livespec_dev_tooling/checks/self_hosted_uv_lane.py`.

The check is a RELIABILITY guard over a repo's own `.github/workflows/*.yml` /
`*.yaml`. A workflow that routes gating jobs to self-hosted capacity through
`vars.CI_RUNNER_LABELS` AND invokes uv must declare `UV_CONCURRENT_DOWNLOADS`
and `UV_HTTP_TIMEOUT` in its top-level `env:`, lane-selected against the SAME
fallback literal its `runs-on` expressions use.

Two tests here are REGRESSION tests for defects that a straightforward reading
of the specification would have shipped, and they are the reason this file
exists in its current shape:

* `test_hosted_only_repo_naming_the_variable_in_a_comment_passes` encodes the
  precondition defect. `livespec-orchestrator-beads-fabro` is hosted-only BY
  DESIGN and carries a header comment that NAMES `vars.CI_RUNNER_LABELS` while
  explaining why it refuses to route self-hosted. A raw-substring precondition
  flags exactly the repo the precondition exists to exempt. The fixture
  reproduces that real header rather than simply omitting the string — a
  fixture without the string would pass every candidate precondition and prove
  nothing.
* `test_routing_fallback_is_not_the_last_or_alternative` encodes the parser
  defect. The shipped `repo_variable_fallback` returns the LAST `||`
  alternative, which on the lane-selection `env` shape is the uv VALUE (`4`),
  not the routing literal. Reusing it would mismatch every correctly
  configured repo and fail the whole fleet.

`main()` is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `rc = main()`)
rather than via a `sys.executable` subprocess, mirroring the
`test_self_hosted_routing` sibling — no `COVERAGE_PROCESS_START` child, no
`.coverage.*` race under the parallel dispatcher, and materially faster. The
pure parsers in the private sibling `_self_hosted_uv_lane_parse` are exercised
directly for precise branch coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from livespec_dev_tooling.checks import self_hosted_uv_lane
from livespec_dev_tooling.checks._self_hosted_routing_parse import repo_variable_fallback
from livespec_dev_tooling.checks._self_hosted_uv_lane_parse import (
    env_assignments,
    references_variable,
    uses_uv,
    variable_fallback_literal,
)

__all__: list[str] = []

_ROUTING = "CI_RUNNER_LABELS"

# The canonical fleet expressions, byte-identical to what every routed fleet
# `ci.yml` carries on origin/master.
_RUNS_ON = "${{ fromJSON(vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]') }}"
_UV_DOWNLOADS = (
    "${{ contains(vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]', 'ubuntu') " "&& '50' || '4' }}"
)
_UV_TIMEOUT = (
    "${{ contains(vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]', 'ubuntu') " "&& '30' || '60' }}"
)


def _write_workflow(*, tmp_path: Path, name: str, body: str) -> Path:
    """Write a workflow file under `tmp_path/.github/workflows/`."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / name
    _ = path.write_text(body, encoding="utf-8")
    return path


def _routed_workflow(*, env_lines: str) -> str:
    """A workflow that routes self-hosted and runs uv, with the given `env:` block."""
    return f"""name: CI
on:
  push:
    branches: [master]

env:
{env_lines}
  LIVESPEC_CI_LANE: fixed

jobs:
  build:
    runs-on: {_RUNS_ON}
    steps:
      - run: uv sync --locked
"""


_CORRECT_ENV = f"  UV_CONCURRENT_DOWNLOADS: {_UV_DOWNLOADS}\n  UV_HTTP_TIMEOUT: {_UV_TIMEOUT}"


def _run(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Drive `main()` in-process with `tmp_path` as the repo root."""
    monkeypatch.chdir(tmp_path)
    return self_hosted_uv_lane.main()


# --------------------------------------------------------------------------
# Precondition — the check must stay silent outside its scope.
# --------------------------------------------------------------------------


def test_no_workflows_dir_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 0


def test_hosted_only_repo_naming_the_variable_in_a_comment_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hosted-only repo whose COMMENT names the routing variable is exempt.

    Reproduces `livespec-orchestrator-beads-fabro`'s real header block. This is
    the regression the raw-substring precondition would have caused: the check
    would demand the uv variables in a workflow whose header says in as many
    words not to add them.
    """
    body = """name: CI
on:
  push:
    branches: [master]

# RUNNER ROUTING - deliberately PLAIN `runs-on: ubuntu-latest` everywhere.
#
# Do NOT "restore uniformity" by introducing the flippable
# `runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '["self-hosted","local-ci"]') }}`
# form that the other fleet repos use. This repo hosts the fleet's PRIVILEGED
# on-demand gate-runner lane.

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: uv sync --locked
"""
    _ = _write_workflow(tmp_path=tmp_path, name="ci.yml", body=body)
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 0


def test_routed_workflow_that_never_invokes_uv_is_out_of_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Routing alone is not enough — the invariant is about uv's fetch concurrency."""
    body = f"""name: Release
on:
  push:
    branches: [master]

jobs:
  build:
    runs-on: {_RUNS_ON}
    steps:
      - run: make dist
"""
    _ = _write_workflow(tmp_path=tmp_path, name="release.yml", body=body)
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 0


def test_correctly_configured_routed_workflow_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _write_workflow(
        tmp_path=tmp_path, name="ci.yml", body=_routed_workflow(env_lines=_CORRECT_ENV)
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 0


def test_yaml_extension_workflow_is_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both `*.yml` and `*.yaml` are in scope, as for the routing sibling."""
    _ = _write_workflow(
        tmp_path=tmp_path,
        name="ci.yaml",
        body=_routed_workflow(env_lines=f"  UV_HTTP_TIMEOUT: {_UV_TIMEOUT}"),
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


# --------------------------------------------------------------------------
# Presence — step 2.
# --------------------------------------------------------------------------


def test_missing_concurrent_downloads_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _write_workflow(
        tmp_path=tmp_path,
        name="ci.yml",
        body=_routed_workflow(env_lines=f"  UV_HTTP_TIMEOUT: {_UV_TIMEOUT}"),
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


def test_missing_http_timeout_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _write_workflow(
        tmp_path=tmp_path,
        name="ci.yml",
        body=_routed_workflow(env_lines=f"  UV_CONCURRENT_DOWNLOADS: {_UV_DOWNLOADS}"),
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


def test_missing_both_variables_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _write_workflow(
        tmp_path=tmp_path, name="ci.yml", body=_routed_workflow(env_lines="  UNRELATED: '1'")
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


def test_no_top_level_env_block_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = f"""name: CI
on: push

jobs:
  build:
    runs-on: {_RUNS_ON}
    env:
      UV_CONCURRENT_DOWNLOADS: {_UV_DOWNLOADS}
      UV_HTTP_TIMEOUT: {_UV_TIMEOUT}
    steps:
      - run: uv sync --locked
"""
    _ = _write_workflow(tmp_path=tmp_path, name="ci.yml", body=body)
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


# --------------------------------------------------------------------------
# Lockstep — step 3, the part a presence check would satisfy vacuously.
# --------------------------------------------------------------------------


def test_stale_fallback_literal_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy-paste carrying a different literal routes self-hosted on hosted values."""
    stale = (
        "${{ contains(vars.CI_RUNNER_LABELS || '[\"ubuntu-24.04\"]', 'ubuntu') " "&& '50' || '4' }}"
    )
    _ = _write_workflow(
        tmp_path=tmp_path,
        name="ci.yml",
        body=_routed_workflow(
            env_lines=f"  UV_CONCURRENT_DOWNLOADS: {stale}\n  UV_HTTP_TIMEOUT: {_UV_TIMEOUT}"
        ),
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


def test_hardcoded_variable_is_not_lane_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _write_workflow(
        tmp_path=tmp_path,
        name="ci.yml",
        body=_routed_workflow(
            env_lines=f"  UV_CONCURRENT_DOWNLOADS: '50'\n  UV_HTTP_TIMEOUT: {_UV_TIMEOUT}"
        ),
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


def test_unresolvable_env_fallback_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    unresolvable = "${{ contains(vars.CI_RUNNER_LABELS || , 'ubuntu') && '50' || '4' }}"
    _ = _write_workflow(
        tmp_path=tmp_path,
        name="ci.yml",
        body=_routed_workflow(
            env_lines=f"  UV_CONCURRENT_DOWNLOADS: {unresolvable}\n  UV_HTTP_TIMEOUT: {_UV_TIMEOUT}"
        ),
    )
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1


# --------------------------------------------------------------------------
# Pure parsers.
# --------------------------------------------------------------------------


def test_routing_fallback_is_not_the_last_or_alternative() -> None:
    """Regression: the shipped sibling parser answers the wrong question here.

    `repo_variable_fallback` deliberately returns the LAST `||` alternative,
    which is correct for `runs-on` (one operator) and wrong for the
    lane-selection `env` shape (two operators), where it yields the uv VALUE.
    """
    assert repo_variable_fallback(value=_UV_DOWNLOADS) == "4"
    assert variable_fallback_literal(value=_UV_DOWNLOADS, variable=_ROUTING) == '["ubuntu-latest"]'
    assert variable_fallback_literal(value=_RUNS_ON, variable=_ROUTING) == '["ubuntu-latest"]'


def test_variable_fallback_literal_three_outcomes() -> None:
    assert variable_fallback_literal(value="ubuntu-latest", variable=_ROUTING) is None
    assert (
        variable_fallback_literal(value="${{ vars.CI_RUNNER_LABELS }}", variable=_ROUTING) is None
    )
    assert (
        variable_fallback_literal(value="${{ vars.CI_RUNNER_LABELS || }}", variable=_ROUTING) == ""
    )
    assert (
        variable_fallback_literal(value="${{ vars.CI_RUNNER_LABELS || bare }}", variable=_ROUTING)
        == ""
    )
    assert (
        variable_fallback_literal(value="${{ vars.CI_RUNNER_LABELS || 'x }}", variable=_ROUTING)
        == ""
    )
    assert (
        variable_fallback_literal(value="${{ vars.CI_RUNNER_LABELS || 'ok' }}", variable=_ROUTING)
        == "ok"
    )


def test_references_variable() -> None:
    assert references_variable(value=_RUNS_ON, variable=_ROUTING) is True
    assert references_variable(value="ubuntu-latest", variable=_ROUTING) is False


def test_uses_uv_markers() -> None:
    assert uses_uv(stripped="  - run: uv sync --locked") is True
    assert uses_uv(stripped="  - run: uv run pytest") is True
    assert uses_uv(stripped="  - uses: astral-sh/setup-uv@v5") is True
    assert uses_uv(stripped="  - run: make dist") is False


def test_env_assignments_reads_only_the_top_level_block() -> None:
    source = """name: CI
env:
  A: '1'

  B: '2'
    deeper: ignored
  C: '3'

jobs:
  build:
    env:
      NOT_TOP_LEVEL: '9'
"""
    assert env_assignments(stripped=source) == {"A": "'1'", "B": "'2'", "C": "'3'"}


def test_env_assignments_absent_block() -> None:
    assert env_assignments(stripped="name: CI\njobs:\n  build:\n    runs-on: x\n") == {}


@settings(max_examples=100, deadline=None)
@given(value=st.text(), variable=st.text(min_size=1))
def test_variable_fallback_literal_is_total(value: str, variable: str) -> None:
    """Total over arbitrary text — a guard that fails open by dying is no guard."""
    result = variable_fallback_literal(value=value, variable=variable)
    assert result is None or isinstance(result, str)


@settings(max_examples=100, deadline=None)
@given(source=st.text())
def test_env_assignments_is_total(source: str) -> None:
    assert isinstance(env_assignments(stripped=source), dict)


def test_env_assignments_skips_indented_non_entry_lines() -> None:
    """A block-list continuation inside `env:` is not a `key: value` entry."""
    source = "env:\n  A: '1'\n    - bullet\n  B: '2'\n"
    assert env_assignments(stripped=source) == {"A": "'1'", "B": "'2'"}


def test_env_assignments_block_ending_in_blank_lines() -> None:
    """The block may run to end-of-file with trailing blank lines."""
    assert env_assignments(stripped="env:\n  A: '1'\n\n") == {"A": "'1'"}


def test_unresolvable_runs_on_fallback_yields_no_routing_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `runs-on` referencing the variable with no readable literal still routes.

    The workflow is in scope (it references the variable and runs uv), but
    contributes no routing literal, so a correctly-formed `env` fallback has
    nothing to match and is reported rather than passed.
    """
    body = """name: CI
on: push

env:
  UV_CONCURRENT_DOWNLOADS: ${{ contains(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]', 'ubuntu') && '50' || '4' }}
  UV_HTTP_TIMEOUT: ${{ contains(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]', 'ubuntu') && '30' || '60' }}

jobs:
  build:
    runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || ) }}
    steps:
      - run: uv sync --locked
"""
    _ = _write_workflow(tmp_path=tmp_path, name="ci.yml", body=body)
    assert _run(tmp_path=tmp_path, monkeypatch=monkeypatch) == 1
