"""Consumer-tier contract for fail-closed JIT runner slot preparation.

The local runner supervisor holds a GitHub App credential, so an absent runner
root must be detected and repaired *before* it can mint a JIT configuration.
These tests execute the shipped shell entrypoints against a miniature runner
installation, as the production systemd units do.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _REPO_ROOT / "ci-runner" / "supervisor" / "prepare-runner-slot.sh"
_SUPERVISOR = _REPO_ROOT / "ci-runner" / "supervisor" / "ci-runner-supervisor.sh"


def _write_canonical_runner(*, root: Path) -> None:
    """Create the smallest Actions-runner root required by the preflight."""
    for directory in ("bin", "externals", "container-hooks"):
        (root / directory).mkdir(parents=True)
    listener = root / "bin" / "Runner.Listener"
    listener.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    listener.chmod(0o755)
    for filename in ("run.sh", "run-helper.sh.template", "config.sh", "env.sh", ".env"):
        path = root / filename
        path.write_text("runner file\n", encoding="utf-8")
        path.chmod(0o755)


def _preflight_env(*, canonical: Path, instances: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CI_RUNNER_USER": os.environ.get("USER", "ubuntu"),
            "CI_RUNNER_CANONICAL_ROOT": str(canonical),
            "CI_RUNNER_INSTANCES_ROOT": str(instances),
        }
    )
    return env


def test_preflight_materializes_a_real_hardlinked_runner_root(*, tmp_path: Path) -> None:
    """A missing stable slot is built and verified before it can receive a JIT config."""
    canonical = tmp_path / "actions-runner"
    instances = tmp_path / "runners"
    _write_canonical_runner(root=canonical)

    result = subprocess.run(
        [str(_PREFLIGHT), "owner-repo-1"],
        capture_output=True,
        text=True,
        check=False,
        env=_preflight_env(canonical=canonical, instances=instances),
    )

    assert result.returncode == 0, (
        "slot preflight must create and validate a missing runner root before minting; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    slot = instances / "owner-repo-1"
    assert (slot / "bin" / "Runner.Listener").samefile(canonical / "bin" / "Runner.Listener")
    assert (slot / "run.sh").is_file()
    assert (slot / "_work").is_dir()
    assert (slot / "_diag").is_dir()


def test_supervisor_aborts_before_mint_when_any_slot_preflight_fails(*, tmp_path: Path) -> None:
    """A failed slot preflight is terminal and produces no mint invocation or retry loop."""
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "systemctl.log"
    minted = tmp_path / "minted"
    systemctl = commands / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        'case "$*" in\n'
        "  'start runner-slot-preflight@'*) exit 1 ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    mint = commands / "mint"
    mint.write_text(f"#!/bin/sh\ntouch {minted}\nprintf jit\n", encoding="utf-8")
    mint.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "GITHUB_APP_ID_CI_RUNNER": "test-app",
            "GITHUB_APP_INSTALLATION_ID_CI_RUNNER": "test-installation",
            "GITHUB_PRIVATE_KEY_CI_RUNNER": "test-key",
            "PATH": f"{commands}:{env['PATH']}",
        }
    )

    result = subprocess.run(
        [str(_SUPERVISOR), "--repos", "owner/repo:1", "--slots", "1", "--mint", str(mint)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=5,
    )

    assert result.returncode == 75, (
        "a preparation breach must stop the supervisor rather than enter its retry loop; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert not minted.exists(), "preflight failure must cause zero GitHub JIT mint requests"
    assert log.read_text(encoding="utf-8").splitlines() == [
        "start runner-slot-preflight@owner-repo-1.service"
    ]
