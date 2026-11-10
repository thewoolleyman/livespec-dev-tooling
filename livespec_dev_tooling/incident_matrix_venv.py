"""Prepare the reusable-check-matrix incident decision's throwaway environment.

The decision's two dependencies (`incident_matrix_requirements.txt`: PyYAML for
the call-site parse, typing_extensions for the sanctioned `gh_read` client) are
not on a runner's system interpreter, and a workflow `run:` block may reach no
dev tool directly, so the decision step prepares them through this module:

    python3 -m livespec_dev_tooling.incident_matrix_venv "$RUNNER_TEMP/incident-decision"
    "$RUNNER_TEMP/incident-decision/bin/python" -m livespec_dev_tooling.incident_matrix_omission

It creates a virtual environment at the given directory and installs the
requirements into it with `--require-hashes` and `--only-binary=:all:`: every
wheel must match a hash pinned in the released checkout, and nothing is built
from source. A failed creation or install exits non-zero, so the leg fails
before any omission (fail closed).
"""

from __future__ import annotations

import argparse
import subprocess
import venv
from collections.abc import Callable, Sequence
from pathlib import Path

__all__: list[str] = ["REQUIREMENTS", "install_argv", "main", "prepare"]

REQUIREMENTS = Path(__file__).resolve().with_name("incident_matrix_requirements.txt")


def install_argv(*, python: Path) -> list[str]:
    """The one hash-pinned, binary-only install of the decision's requirements."""
    return [
        str(python),
        "-m",
        "pip",
        "install",
        "--quiet",
        "--disable-pip-version-check",
        "--require-hashes",
        "--only-binary=:all:",
        "-r",
        str(REQUIREMENTS),
    ]


def prepare(
    *,
    target: Path,
    create: Callable[..., None],
    run: Callable[..., subprocess.CompletedProcess[bytes]],
) -> int:
    """Create the environment at `target` and install the pinned requirements; 0 on success."""
    try:
        create(str(target), with_pip=True, clear=True)
    except (OSError, subprocess.CalledProcessError):
        return 1
    completed = run(install_argv(python=target / "bin" / "python"), check=False)
    return 0 if completed.returncode == 0 else 1


def main(*, argv: Sequence[str] | None = None) -> int:
    """Prepare the environment at the one positional directory."""
    parser = argparse.ArgumentParser(prog="incident-matrix-venv", description=__doc__)
    _ = parser.add_argument("target")
    args = parser.parse_args(argv)
    return prepare(target=Path(str(args.target)), create=venv.create, run=subprocess.run)


if __name__ == "__main__":
    raise SystemExit(main())
