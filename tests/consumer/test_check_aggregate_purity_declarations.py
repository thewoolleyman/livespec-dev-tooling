"""The ratified scenario "a check aggregate member with no purity declaration fails the aggregate".

From `SPECIFICATION/scenarios.md` (v080), quoted:

> Given a member of livespec-dev-tooling's check aggregate that carries no
> purity declaration
> When livespec-dev-tooling's full `just check` aggregate runs
> Then the aggregate MUST exit non-zero
> And its output MUST name that member

WHY THE AGGREGATE HAS TO REFUSE at all, given that an undeclared member is
already treated as world-reading and therefore still RUNS. Without the
refusal the default is silent: a new member that declares nothing joins the
set the green token may not memoize, every push pays for it, and the saving
the token exists for shrinks with nobody noticing. The refusal is what makes
the safe default visible rather than free.

TWO HALVES, because either alone leaves the gate dead:

1. **The decision** — which members carry no declaration — is asserted
   in-process against the real resolver by
   `tests.livespec_dev_tooling.test_check_purity` and by the `undeclared`
   subcommand tests in `tests.livespec_dev_tooling.test_green_token`. It is
   not re-decided here.
2. **The wiring** — that the aggregate ASKS, asks about every one of its own
   members, asks BEFORE it dispatches anything, and refuses while naming the
   member — is asserted here, by driving the real `scripts/just/check.sh`
   against stub `uv` and `just` executables on `PATH` that record their argv.
   What the script invokes, and in what order, is the observable.

The script is driven rather than `just check` itself: running the aggregate
from inside the suite it gates would be a second execution of it rather than
a test of it, and the recipe's only content is the literal target mirror the
script already validates.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_SH = _REPO_ROOT / "scripts" / "just" / "check.sh"

# A fixture inventory, deliberately NOT this repository's own: the scenario is
# about a member carrying no declaration, and this repository's own aggregate
# must never hold one. The mirror check inside the script compares argv against
# this file entry-for-entry, so the two always travel together.
_FIXTURE_MEMBERS = (
    "check-fixture-pure",
    "check-fixture-world",
    "check-fixture-bare",
)

# Stub `uv`. Every invocation is recorded; the purity probe answers from the
# environment so a test can drive either arm without the stub deciding
# anything. A probe that reports undeclared members prints them, as the real
# subcommand does, and exits non-zero.
_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
case "$*" in
    *"green_token undeclared"*)
        if [ -n "${UNDECLARED_MEMBERS:-}" ]; then
            printf '%s\\n' "${UNDECLARED_MEMBERS}"
            exit 1
        fi
        exit 0
        ;;
    *"green_token world-reading"*)
        printf '%s\\n' "${WORLD_READING_MEMBERS:-}"
        exit 0
        ;;
esac
exit 0
"""

_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
exit 0
"""


def _run_check_sh(
    *,
    tmp_path: Path,
    undeclared: str = "",
    world_reading: str = "",
    token_match: str = "",
) -> tuple[int, str, list[str]]:
    """Run the real `check.sh` over the fixture inventory against stub tooling.

    Returns the script's exit code, its combined output, and every command it
    invoked, in order.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    _ = (tmp_path / "check-targets.txt").write_text(
        "# Fixture inventory.\n" + "".join(f"{member}\n" for member in _FIXTURE_MEMBERS),
        encoding="utf-8",
    )
    log = tmp_path / "invocations.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
            "UNDECLARED_MEMBERS": undeclared,
            "WORLD_READING_MEMBERS": world_reading,
            "skip": "",
            "red_staged": "",
            "hook_gate": "",
            "token_match": token_match,
        }
    )
    completed = subprocess.run(
        ["bash", str(_CHECK_SH), *_FIXTURE_MEMBERS],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def _index_of(*, invoked: list[str], needle: str) -> int:
    """The position of the first invocation carrying `needle`, or -1."""
    for position, line in enumerate(invoked):
        if needle in line:
            return position
    return -1


def test_the_aggregate_audits_every_one_of_its_own_members_before_dispatching_any(
    *, tmp_path: Path
) -> None:
    """The population is the aggregate's OWN member list, and the audit comes first."""
    code, output, invoked = _run_check_sh(tmp_path=tmp_path)

    assert code == 0, f"a fully-declared aggregate must proceed; output={output!r}"
    audit = _index_of(invoked=invoked, needle="green_token undeclared")
    dispatch = _index_of(invoked=invoked, needle="parallel_check_dispatcher")
    assert audit >= 0, (
        f"the aggregate must ASK which of its members declare no purity; without the "
        f"question the world-reading default is silent and the token's saving shrinks "
        f"unnoticed; invoked={invoked}"
    )
    assert dispatch >= 0, f"invoked={invoked}"
    assert audit < dispatch, (
        f"the audit must precede dispatch: a registry defect found after a full aggregate "
        f"run has already cost the operator the run it was meant to make trustworthy; "
        f"audit={audit} dispatch={dispatch} invoked={invoked}"
    )
    for member in _FIXTURE_MEMBERS:
        assert member in invoked[audit], (
            f"every member of the aggregate must be audited — an audit over a subset "
            f"reports a pass for members it never examined; member={member} "
            f"audit_argv={invoked[audit]!r}"
        )


def test_a_member_with_no_purity_declaration_fails_the_aggregate_and_is_named(
    *, tmp_path: Path
) -> None:
    """The scenario's two Then-lines: exit non-zero, and name that member."""
    code, output, invoked = _run_check_sh(tmp_path=tmp_path, undeclared="check-fixture-bare")

    assert code != 0, (
        f"the aggregate must exit non-zero when one of its members carries no purity "
        f"declaration; output={output!r} invoked={invoked}"
    )
    assert "check-fixture-bare" in output, (
        f"the output must NAME the member: a refusal that does not say which member is "
        f"undeclared leaves the operator to re-derive the audit by hand; output={output!r}"
    )
    assert _index_of(invoked=invoked, needle="parallel_check_dispatcher") < 0, (
        f"nothing may be dispatched after the refusal — the aggregate's member list is "
        f"not in a state it can report a verdict about; invoked={invoked}"
    )
    assert _index_of(invoked=invoked, needle="green_token write") < 0, (
        f"and NO green token may be recorded: a token written by a run that refused its "
        f"own member list would memoize a verdict the aggregate never reached; "
        f"invoked={invoked}"
    )
