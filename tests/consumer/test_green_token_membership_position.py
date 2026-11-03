"""A world-reading member's position in the purity resolver's answer must not decide whether it runs.

Governing scenario, `SPECIFICATION/scenarios.md`: "a push of a tree holding a
green token still runs the members that read state outside the tree" — the
world-reading member and the member carrying no purity declaration MUST run on
the pushing host.

THE DEFECT (livespec-dev-tooling-iiu3dp). `scripts/just/check.sh` runs under
`set -euo pipefail`, and its memoized-run membership test piped the resolver's
answer into `grep -Fqx`. `grep -q` exits on its first match, so a member named
on an early line left `printf` writing into a closed pipe; the SIGPIPE made the
pipeline's status 141, and the `if` read that as "not world-reading" — the
member was silently MEMOIZED AWAY on a token-matched push. Measured in CI run
41646894193 at 55ccc6bb, where `check-fixture-bare` (line 1 of a two-line
answer) was skipped and `check-fixture-world` (the last line) ran.

A two-line answer loses that race only sometimes. An answer longer than a pipe
buffer loses it every time, which is what makes this module a deterministic
reproduction rather than a flaky one: the stub resolver names the member under
test FIRST, then pads its answer with names of members the run never asked
about.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_SH = _REPO_ROOT / "scripts" / "just" / "check.sh"

_FIRST_MEMBER = "check-fixture-first"
_PURE_MEMBER = "check-fixture-pure"
_TARGETS = (_FIRST_MEMBER, _PURE_MEMBER)

# Well past any pipe buffer: about 3 MB of answer after the first line.
_PADDING_LINES = "200000"

# Stub `uv`. The world-reading query answers with the first member, then the
# padding; every other invocation records its argv and succeeds.
_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
case "$*" in
    *"green_token world-reading"*)
        printf '%s\\n' "check-fixture-first"
        seq -f 'check-fixture-padding-%g' 1 "${PADDING_LINES}"
        exit 0
        ;;
esac
exit 0
"""


def _run_memoized(*, tmp_path: Path) -> tuple[str, list[str]]:
    """Run the real `check.sh` on the token-match path; return its output and invocations."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "uv"
    _ = stub.write_text(_UV_STUB, encoding="utf-8")
    stub.chmod(0o755)
    _ = (tmp_path / "check-targets.txt").write_text(
        "# Fixture inventory.\n" + "".join(f"{member}\n" for member in _TARGETS),
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(tmp_path / "invocations.log"),
            "PADDING_LINES": _PADDING_LINES,
            "skip": "",
            "red_staged": "",
            "hook_gate": "1",
            "token_match": "1",
        }
    )
    completed = subprocess.run(
        ["bash", str(_CHECK_SH), *_TARGETS],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = (tmp_path / "invocations.log").read_text(encoding="utf-8").splitlines()
    return completed.stdout + completed.stderr, invoked


def test_a_world_reading_member_named_first_in_a_long_answer_still_runs(*, tmp_path: Path) -> None:
    """The first member of the resolver's answer runs and never reaches the skip list."""
    output, invoked = _run_memoized(tmp_path=tmp_path)

    dispatched = [line for line in invoked if "parallel_check_dispatcher" in line]
    skipped = " ".join(dispatched).split(" --skip ", 1)[-1].split(" -- ", 1)[0].split()
    facts = {
        "named as run": f"running world-reading member {_FIRST_MEMBER}" in output,
        "not skipped": _FIRST_MEMBER not in skipped,
        "one dispatch": len(dispatched) == 1,
        "pure member skipped": _PURE_MEMBER in skipped,
    }
    assert all(facts.values()), f"facts={facts} skip={skipped} output={output!r}"
