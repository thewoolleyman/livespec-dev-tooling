"""The hooks-and-CI push-gating path of `SPECIFICATION/non-functional-requirements.md`, for the
one push that publishes NO TREE: a deletion.

The section's sibling, `tests.spec.test_self_application_safety_net`, asserts
the other direction — that the push gate runs the FULL `just check` aggregate
and routes to no reduced one, because a change-class predicate there makes the
branch gate weaker than the master gate. That is a statement about a push that
PUBLISHES something. A delete-only push publishes nothing:

> git feeds the pre-push hook one `<local ref> <local oid> <remote ref> <remote
> oid>` line per ref update on standard input, and spells a deletion as an
> ALL-ZERO local oid.

With every line such a deletion there is no tree for any gate to judge, so the
aggregate runs against whatever happens to be checked out — a tree unrelated to
the ref being removed — and charges the operator its full runtime for an answer
about the wrong thing. Measured 2026-10-12 on the VPS: a remote-branch delete
from a livespec-dev-tooling worktree held its pre-push hook about 272 s
(work-item livespec-dev-tooling-r4oj47).

Why this is NOT the retired doc-only subset the sibling convicts: that branch
ran FEWER checks over a tree it was still publishing, and it failed by PASSING
— the smaller gate was green and master reddened anyway. Here nothing is
published, so there is no weaker verdict to issue; the gate is not narrowed,
it is INAPPLICABLE. The discrimination is keyed on the refs git itself names on
standard input, not on a change class read off the working tree, so there is no
predicate that can rot into a subset.

Two halves are asserted, because either one alone leaves the skip dead:

1. **The script.** The real `check-pre-push.sh` is driven against stub `uv` and
   `just` executables on `PATH` that record their argv, so what the script
   INVOKES is the observable — a delete-only push must reach NEITHER the
   green-token probe, NOR the delegated-gate switch, NOR `just check`, and must
   say why. Every other input shape — a create, an update, a deletion travelling
   BESIDE either, and no input at all — must reach them exactly as before.
2. **The wiring.** lefthook forwards a hook's standard input to a command only
   when that command declares `use_stdin: true`. Without it the hook is handed
   nothing, every push looks like "no input", and the skip above can never fire
   — silently, because the gate still runs and still passes.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_PUSH = _REPO_ROOT / "scripts" / "just" / "check-pre-push.sh"
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# git's spelling of "this ref has no local object": an all-zero oid. The local
# ref field of a deletion is the literal `(delete)`.
_ZERO_OID = "0" * 40
_LIVE_OID = "b3d4f1a90c7e25486fd1c0b8a7e6554321098765"
_OTHER_OID = "ac1e5d0f3b729648175e2c9a0d4f6b8172635409"

# The stub `uv` answers every probe with a MISS (non-zero), which is the input
# shape that makes the full path maximally observable: a token miss consults the
# delegated switch, and a switch that is off falls through to the aggregate.
_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
exit 1
"""

_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
exit 0
"""

# The `01-check-pre-push` command, as lefthook must carry it for the hook's
# standard input to reach the script at all.
_PRE_PUSH_COMMAND = re.compile(
    r"^    01-check-pre-push:\n(?P<body>(?:      .*\n)+)",
    re.MULTILINE,
)


def _run_pre_push(*, tmp_path: Path, stdin: str) -> tuple[int, str, list[str]]:
    """Run the real `check-pre-push.sh` on one hook standard-input payload.

    Returns the script's exit code, its stdout, and every command it invoked,
    in order.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    log = tmp_path / "invocations.log"
    env = dict(os.environ)
    env.update({"PATH": f"{stub_dir}{os.pathsep}{env['PATH']}", "STUB_LOG": str(log)})
    completed = subprocess.run(
        ["bash", str(_PRE_PUSH)],
        cwd=str(tmp_path),
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed.returncode, completed.stdout, invoked


def _delete_line(*, ref: str) -> str:
    """One pre-push standard-input line for a ref DELETION."""
    return f"(delete) {_ZERO_OID} {ref} {_LIVE_OID}\n"


def _update_line(*, ref: str, remote_oid: str = _OTHER_OID) -> str:
    """One pre-push standard-input line for a ref CREATE or UPDATE."""
    return f"{ref} {_LIVE_OID} {ref} {remote_oid}\n"


def test_a_delete_only_push_skips_every_gate_and_says_why(*, tmp_path: Path) -> None:
    """A deletion publishes no tree, so NOTHING the script can run is about it."""
    code, stdout, invoked = _run_pre_push(
        tmp_path=tmp_path, stdin=_delete_line(ref="refs/heads/gone")
    )

    assert code == 0, f"a delete-only push must complete; stdout={stdout!r} invoked={invoked}"
    assert invoked == [], (
        f"a delete-only push must reach neither the green-token probe, the delegated-gate "
        f"switch, nor `just check` — there is no published tree for any of them to judge, "
        f"and a measured delete held this hook ~272 s for an answer about whatever "
        f"happened to be checked out; invoked={invoked}"
    )
    assert "only deletes refs" in stdout and "skipp" in stdout, (
        f"the skip must NARRATE itself: a gate that silently does nothing is "
        f"indistinguishable from a gate that ran and passed; stdout={stdout!r}"
    )


def test_a_push_deleting_several_refs_at_once_still_skips(*, tmp_path: Path) -> None:
    """EVERY line being a deletion is the condition, not the first line being one."""
    stdin = _delete_line(ref="refs/heads/gone") + _delete_line(ref="refs/heads/also-gone")
    code, stdout, invoked = _run_pre_push(tmp_path=tmp_path, stdin=stdin)

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert invoked == [], f"invoked={invoked}"
    assert "only deletes refs" in stdout, f"stdout={stdout!r}"


def test_a_deletion_travelling_beside_an_update_runs_the_full_gate(*, tmp_path: Path) -> None:
    """ONE published ref is a published tree — the whole gate is owed, deletions or not."""
    stdin = _delete_line(ref="refs/heads/gone") + _update_line(ref="refs/heads/feature")
    code, stdout, invoked = _run_pre_push(tmp_path=tmp_path, stdin=stdin)

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert "just hook_gate=1 check" in invoked, (
        f"a push carrying any non-deletion must take the unchanged full path — narrowing "
        f"it on the presence of a deletion would be the PR-gate-weaker-than-master hole "
        f"this repository already shipped once; stdout={stdout!r} invoked={invoked}"
    )
    assert "only deletes refs" not in stdout, f"stdout={stdout!r}"


def test_an_update_only_push_runs_the_full_gate(*, tmp_path: Path) -> None:
    """The ordinary publish: green-token probe, delegated switch, then the aggregate."""
    code, stdout, invoked = _run_pre_push(
        tmp_path=tmp_path, stdin=_update_line(ref="refs/heads/feature", remote_oid=_ZERO_OID)
    )

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert [
        line for line in invoked if "green_token check" in line
    ], f"the green-token probe is the first member of the unchanged path; invoked={invoked}"
    assert "just hook_gate=1 check" in invoked, f"invoked={invoked}"


def test_an_absent_standard_input_keeps_the_existing_path(*, tmp_path: Path) -> None:
    """No refs read is NOT "nothing to publish" — it is no evidence, so the gate runs.

    Fail-CLOSED in the only direction a mistake here can be cheap. A hand-run
    `just check-pre-push`, a lefthook build that does not forward standard
    input, or a future transport that stops naming refs all arrive as emptiness;
    reading that as a delete-only push would skip the gate on every push.
    """
    code, stdout, invoked = _run_pre_push(tmp_path=tmp_path, stdin="")

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert "just hook_gate=1 check" in invoked, f"stdout={stdout!r} invoked={invoked}"
    assert "only deletes refs" not in stdout, f"stdout={stdout!r}"


def test_lefthook_forwards_the_hook_standard_input_to_the_gate_command() -> None:
    """Without `use_stdin: true` the script is handed nothing and the skip is dead code."""
    matched = _PRE_PUSH_COMMAND.search(_LEFTHOOK.read_text(encoding="utf-8"))
    assert matched is not None, (
        f"`01-check-pre-push` must be a `pre-push` command of "
        f"{_LEFTHOOK.relative_to(_REPO_ROOT)}"
    )
    body = matched.group("body")
    assert "use_stdin: true" in body, (
        f"lefthook forwards a hook's standard input to a command ONLY when that command "
        f"declares `use_stdin: true`. Without it the gate never sees the `<local ref> "
        f"<local oid> ...` lines git writes, every push reads as no-input, and the "
        f"delete-only skip can never fire — silently, because the gate still runs and "
        f"still passes; body={body!r}"
    )
    assert "run: just check-pre-push" in body, (
        f"the command must still DELEGATE to the recipe (the toolchain-pins rule of "
        f"non-functional-requirements.md: a `run:` field invokes `just <target>` and never "
        f"shells out to an underlying tool directly); body={body!r}"
    )
