"""The ratified scenario "a push of a tree holding a green token still runs the members that read state outside the tree".

From `SPECIFICATION/scenarios.md` (v080), quoted:

> Given a consuming repository's worktree with no uncommitted changes whose
> `HEAD` tree is the tree its green token names
> And the check set the pre-push gate's local fall-through runs holds a
> tree-pure member, a world-reading member, and a member that carries no
> purity declaration
> And the world-reading member fails for that tree
> When a git push of that tree runs the pre-push gate
> Then the world-reading member and the member that carries no purity
> declaration MUST run on the pushing host
> And the tree-pure member MUST NOT run
> And a gate Job MUST NOT be submitted to the `gates` namespace
> And the push MUST be refused

WHAT THE TOKEN USED TO DO, and why that was unsound. A tree-hash key is a
MEMOIZATION, and memoization is sound only for a pure function. `just check`
is not one, so a token that was honest when written could assert a verdict
that was no longer true when read — measured 2026-09-08 on the livespec
primary checkout, where a SEVEN-WEEK-OLD token carrying `{"tree_hash": ...}`
and nothing else would have skipped `check-master-ci-green` and
`check-branch-protection-alignment` outright, landing a push on a red master
on the strength of an observation made weeks earlier (work-item
livespec-dev-tooling-aape).

Driven against the committed scripts rather than by running the aggregate:
running `just check` from inside the suite it gates would be a second
execution of it rather than a test of it. Both halves of the path are
asserted, because either alone leaves the fix dead — the pre-push script has
to ROUTE a token match to the memoized run, and the aggregate has to narrow
that run to the world-reading members and refuse on their failure.

The decision — which members are world-reading — is NOT re-decided here. It
belongs to `livespec_dev_tooling.check_purity` and is asserted in-process by
`tests.livespec_dev_tooling.test_check_purity`. The stub resolver below
answers from a configured declaration set by FILTERING the members it is
asked about, so what the aggregate asks is observable: a query over fewer
members yields fewer answers, which is what makes the hook-path omission
measurable rather than assumed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import NamedTuple

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_SH = _REPO_ROOT / "scripts" / "just" / "check.sh"
_PRE_PUSH = _REPO_ROOT / "scripts" / "just" / "check-pre-push.sh"

# The scenario's Given, as a fixture inventory: a tree-pure member, a
# world-reading member, and a member carrying no purity declaration. The fourth
# entry is the ONE member the two local hook gates omit, present so that the
# omission is measured rather than assumed.
_PURE_MEMBER = "check-fixture-pure"
_WORLD_MEMBER = "check-fixture-world"
_BARE_MEMBER = "check-fixture-bare"
_HOOK_OMITTED = "check-fleet-conformance-admin"
_FIXTURE_MEMBERS = (_BARE_MEMBER, _HOOK_OMITTED, _PURE_MEMBER, _WORLD_MEMBER)

# The declaration set the stub resolver answers from. An undeclared member
# counts as world-reading, so it is here beside the declared one — the ratified
# contract makes the two leave the resolver together.
_WORLD_READING = f"{_BARE_MEMBER} {_HOOK_OMITTED} {_WORLD_MEMBER}"

# Stub `uv`. The purity resolver FILTERS the members it is asked about against
# the configured declaration set, so the aggregate's own question is observable
# through its answer. Everything else records its argv and succeeds, except the
# dispatcher, whose exit code a test drives.
_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
case "$*" in
    *"green_token world-reading"*)
        for arg in "$@"; do
            case " ${WORLD_READING_MEMBERS:-} " in
                *" ${arg} "*) printf '%s\\n' "${arg}" ;;
            esac
        done
        exit 0
        ;;
    *"green_token undeclared"*)   exit 0 ;;
    *"green_token check")         exit "${GREEN_TOKEN_EXIT:-1}" ;;
    *parallel_check_dispatcher*)  exit "${DISPATCH_EXIT:-0}" ;;
    *"gate_remote_delegate enabled") exit "${SWITCH_EXIT:-1}" ;;
esac
exit 0
"""

_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
exit "${JUST_EXIT:-0}"
"""


class _Run(NamedTuple):
    """One stub-driven script run: its exit code, its output, and what it invoked."""

    code: int
    output: str
    invoked: list[str]


def _carrying(*, run: _Run, needle: str) -> list[str]:
    """Every invocation of `run` whose argv carries `needle`."""
    return [line for line in run.invoked if needle in line]


def _skip_argument(*, run: _Run) -> list[str]:
    """The `--skip` list the one dispatcher invocation of `run` was given."""
    dispatched = _carrying(run=run, needle="parallel_check_dispatcher")
    assert len(dispatched) == 1, f"exactly one dispatch is expected; invoked={run.invoked}"
    return dispatched[0].split(" --skip ", 1)[1].split(" -- ", 1)[0].split()


def _stub_env(*, tmp_path: Path, overrides: dict[str, str]) -> dict[str, str]:
    """A scrubbed environment with the stub executables first on `PATH`."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(tmp_path / "invocations.log"),
            "WORLD_READING_MEMBERS": _WORLD_READING,
            "skip": "",
            "red_staged": "",
            "hook_gate": "",
            "token_match": "",
        }
    )
    env.update(overrides)
    return env


def _run_script(
    *, tmp_path: Path, script: Path, args: tuple[str, ...], overrides: dict[str, str], stdin: str
) -> _Run:
    """Run a committed gate script from `tmp_path` against the stub tooling."""
    env = _stub_env(tmp_path=tmp_path, overrides=overrides)
    completed = subprocess.run(
        ["bash", str(script), *args],
        cwd=str(tmp_path),
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    log = tmp_path / "invocations.log"
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return _Run(
        code=completed.returncode,
        output=completed.stdout + completed.stderr,
        invoked=invoked,
    )


def _run_memoized_aggregate(*, tmp_path: Path, dispatch_exit: str = "0") -> _Run:
    """Run the real `check.sh` on the token-match path the pre-push gate takes."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "# Fixture inventory.\n" + "".join(f"{member}\n" for member in _FIXTURE_MEMBERS),
        encoding="utf-8",
    )
    return _run_script(
        tmp_path=tmp_path,
        script=_CHECK_SH,
        args=_FIXTURE_MEMBERS,
        overrides={"hook_gate": "1", "token_match": "1", "DISPATCH_EXIT": dispatch_exit},
        stdin="",
    )


def _run_pre_push(*, tmp_path: Path, overrides: dict[str, str]) -> _Run:
    """Run the real `check-pre-push.sh` on one ordinary (non-deletion) ref update."""
    live = "b3d4f1a90c7e25486fd1c0b8a7e6554321098765"
    return _run_script(
        tmp_path=tmp_path,
        script=_PRE_PUSH,
        args=(),
        overrides=overrides,
        stdin=f"refs/heads/feature {live} refs/heads/feature {'0' * 40}\n",
    )


def test_a_token_match_routes_the_push_to_the_memoized_run_not_past_every_gate(
    *, tmp_path: Path
) -> None:
    """A matching token narrows the gate; it no longer stands in for the whole of it."""
    run = _run_pre_push(tmp_path=tmp_path, overrides={"GREEN_TOKEN_EXIT": "0"})

    assert _carrying(run=run, needle="token_match=1"), (
        f"a token match must still RUN the aggregate's world-reading members on the pushing "
        f"host. Exiting 0 here is the measured defect: a seven-week-old token skipped "
        f"`check-master-ci-green` outright and would land a push on a red master; "
        f"invoked={run.invoked} output={run.output!r}"
    )
    assert _carrying(run=run, needle="hook_gate=1"), (
        f"the memoized run is still a hook gate, so it still omits the one member the hook "
        f"path omits; invoked={run.invoked}"
    )


def test_a_token_match_submits_no_gate_job(*, tmp_path: Path) -> None:
    """The scenario's third Then-line: the cluster is not consulted on this path."""
    run = _run_pre_push(tmp_path=tmp_path, overrides={"GREEN_TOKEN_EXIT": "0", "SWITCH_EXIT": "0"})

    assert not _carrying(run=run, needle="gate_remote_delegate"), (
        f"the delegated-gate switch must not even be consulted on a token match — the "
        f"world-reading members run HERE, and a tree already gated once must not queue a "
        f"second verdict for the same tree; invoked={run.invoked}"
    )


def test_a_failing_world_reading_member_refuses_the_push(*, tmp_path: Path) -> None:
    """The scenario's fourth Then-line, carried by the exit status the hook reads."""
    run = _run_pre_push(tmp_path=tmp_path, overrides={"GREEN_TOKEN_EXIT": "0", "JUST_EXIT": "4"})

    assert run.code != 0, (
        f"the memoized run's verdict IS the gate's verdict: a world-reading member that "
        f"fails must refuse the push, or the token has merely moved the unsoundness one "
        f"frame; code={run.code} output={run.output!r} invoked={run.invoked}"
    )


def test_a_token_miss_takes_the_unchanged_path(*, tmp_path: Path) -> None:
    """No token, a different tree, or a dirty worktree each keep the prior behaviour."""
    run = _run_pre_push(tmp_path=tmp_path, overrides={"GREEN_TOKEN_EXIT": "1"})

    assert _carrying(
        run=run, needle="gate_remote_delegate enabled"
    ), f"a token miss must still consult the delegated-gate switch; invoked={run.invoked}"
    assert _carrying(run=run, needle="just hook_gate=1 check"), (
        f"and with delegation off it must still run the FULL local fall-through, with no "
        f"token_match narrowing; invoked={run.invoked}"
    )
    assert not _carrying(
        run=run, needle="token_match=1"
    ), f"nothing may be memoized when nothing vouched for this tree; invoked={run.invoked}"


def test_the_memoized_run_runs_every_world_reading_member_the_hook_path_keeps(
    *, tmp_path: Path
) -> None:
    """The first two Then-lines: the world-reading and undeclared members run."""
    run = _run_memoized_aggregate(tmp_path=tmp_path)

    assert run.code == 0, f"output={run.output!r} invoked={run.invoked}"
    skipped = _skip_argument(run=run)
    assert _WORLD_MEMBER not in skipped, (
        f"a member declared world-reading must never be skipped on the strength of a "
        f"tree-keyed token; skip={skipped}"
    )
    assert _BARE_MEMBER not in skipped, (
        f"nor may a member carrying NO declaration: the ratified contract makes no "
        f"declaration mean world-reading, so the safe default has to survive all the way "
        f"to the skip list; skip={skipped}"
    )


def test_the_memoized_run_skips_the_tree_pure_member(*, tmp_path: Path) -> None:
    """The scenario's "And the tree-pure member MUST NOT run"."""
    run = _run_memoized_aggregate(tmp_path=tmp_path)

    assert _PURE_MEMBER in _skip_argument(run=run), (
        f"the whole point of the token is that a tree-pure member is not gated twice for a "
        f"byte-identical tree; a token match that re-ran everything would be no token at "
        f"all; skip={_skip_argument(run=run)}"
    )


def test_the_memoized_run_does_not_ask_about_the_member_the_hook_path_omits(
    *, tmp_path: Path
) -> None:
    """A member this run will not execute must not be reported as having run."""
    run = _run_memoized_aggregate(tmp_path=tmp_path)

    queries = _carrying(run=run, needle="green_token world-reading")
    assert len(queries) == 1, f"invoked={run.invoked}"
    assert _HOOK_OMITTED not in queries[0].split(), (
        f"`{_HOOK_OMITTED}` is omitted from every hook-path run because its verdict is a "
        f"fact about nine OTHER repositories at this instant. Asking about it here would "
        f"put it in the ran-list of a run that never executes it; query={queries[0]!r}"
    )
    assert f":: green token matched: running world-reading member {_HOOK_OMITTED}" not in (
        run.output
    ), f"output={run.output!r}"


def test_the_memoized_run_names_what_it_ran_and_counts_what_it_skipped(*, tmp_path: Path) -> None:
    """A memoized push must never READ as a fully-gated one."""
    run = _run_memoized_aggregate(tmp_path=tmp_path)

    for member in (_WORLD_MEMBER, _BARE_MEMBER):
        assert f"running world-reading member {member}" in run.output, (
            f"each world-reading member the run executes must be NAMED, or the operator "
            f"cannot tell a memoized push from a fully-gated one; member={member} "
            f"output={run.output!r}"
        )
    assert "skipped 1 tree-pure member" in run.output, (
        f"and the number of members skipped on the strength of the token must be reported, "
        f"for the same reason; output={run.output!r}"
    )


def test_the_memoized_run_refuses_on_a_world_reading_failure(*, tmp_path: Path) -> None:
    """The members it did run decide the verdict, exactly as the full aggregate does."""
    run = _run_memoized_aggregate(tmp_path=tmp_path, dispatch_exit="1")

    assert run.code != 0, f"output={run.output!r} invoked={run.invoked}"


def test_the_memoized_run_records_no_new_token(*, tmp_path: Path) -> None:
    """A partial run must not re-stamp the marker that stands for a full one."""
    run = _run_memoized_aggregate(tmp_path=tmp_path)

    assert not _carrying(run=run, needle="green_token write"), (
        f"the token for this tree already exists — that is why this path was taken — and a "
        f"run that executed only part of the check set must not be the thing that writes "
        f"it; invoked={run.invoked}"
    )
