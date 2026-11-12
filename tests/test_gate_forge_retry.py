"""The gate Job's forge_retry retries a throttled github.com read and never a missing ref.

`ci-runner/k3s/phase2/gates/forge-retry.sh` defines the one bounded retry that
render-gate-job.sh inlines into the gate Job's fetch-livespec-core init container
and into its sibling clones (plan gate-job-resources; the 2026-11-12 anonymous
fetch 401 incident). These tests run the committed function in a real bash, with
a fake `git` first on PATH that answers from a script of exit statuses, so the
claim under test is what the shipped shell does with real git-shaped output.
Spawning bash is allowed here: the subprocess-spawn check forbids only Python
interpreter children.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_FORGE_RETRY = (
    Path(__file__).resolve().parents[1]
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "gates"
    / "forge-retry.sh"
)

_UNAUTHENTICATED = (
    "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
)
_MISSING_REF = "fatal: couldn't find remote ref v9.9.9"
_SERVER_ERROR = "error: RPC failed; HTTP 502 curl 22 The requested URL returned error: 502"


def _fake_git(*, tmp_path: Path, answers: list[tuple[int, str]]) -> Path:
    """Write a `git` that gives the Nth call the Nth (exit status, stderr) answer."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for index, (status, message) in enumerate(answers, start=1):
        _ = (tmp_path / f"answer-{index}").write_text(f"{status}\n{message}\n", encoding="utf-8")
    script = bin_dir / "git"
    lines = [
        "#!/bin/bash",
        f"calls='{tmp_path}/calls'",
        'n=$(( $(cat "$calls" 2>/dev/null || echo 0) + 1 ))',
        'echo "$n" > "$calls"',
        f'[ "$n" -le {len(answers)} ] && pick="$n" || pick={len(answers)}',
        f"answer='{tmp_path}/answer-'\"$pick\"",
        'status=$(sed -n 1p "$answer")',
        'sed -n 2p "$answer" >&2',
        'exit "$status"',
    ]
    _ = script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return bin_dir


def _run_forge_retry(*, tmp_path: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "FORGE_RETRY_BASE_WAIT": "0",
    }
    return subprocess.run(
        [
            "bash",
            "-c",
            f"source '{_FORGE_RETRY}'; forge_retry 'livespec core v1' git fetch --depth 1 origin v1",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _calls(*, tmp_path: Path) -> int:
    return int((tmp_path / "calls").read_text(encoding="utf-8").strip())


def test_a_throttled_401_is_retried_until_the_fetch_succeeds(*, tmp_path: Path) -> None:
    """A 401 from the shared egress is retried, and the next good answer is a pass."""
    bin_dir = _fake_git(tmp_path=tmp_path, answers=[(128, _UNAUTHENTICATED), (0, "")])

    result = _run_forge_retry(tmp_path=tmp_path, bin_dir=bin_dir)

    assert result.returncode == 0
    assert _calls(tmp_path=tmp_path) == 2
    assert "attempt 1/5: 401 (git exit 128)" in result.stderr
    assert "attempt 2/5: ok" in result.stderr


def test_a_missing_ref_is_never_retried(*, tmp_path: Path) -> None:
    """A ref the forge reports missing fails at once with git's own status."""
    bin_dir = _fake_git(tmp_path=tmp_path, answers=[(128, _MISSING_REF), (0, "")])

    result = _run_forge_retry(tmp_path=tmp_path, bin_dir=bin_dir)

    assert result.returncode == 128
    assert _calls(tmp_path=tmp_path) == 1
    assert "attempt 1/5: not-found (git exit 128)" in result.stderr
    assert _MISSING_REF in result.stderr


def test_a_persistent_server_error_stops_at_the_attempt_budget(*, tmp_path: Path) -> None:
    """A 5xx that never clears ends after five attempts with the last failure's status."""
    bin_dir = _fake_git(tmp_path=tmp_path, answers=[(128, _SERVER_ERROR)])

    result = _run_forge_retry(tmp_path=tmp_path, bin_dir=bin_dir)

    assert result.returncode == 128
    assert _calls(tmp_path=tmp_path) == 5
    assert "attempt 5/5: 5xx (git exit 128)" in result.stderr
