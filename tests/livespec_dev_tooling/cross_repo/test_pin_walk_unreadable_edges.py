"""Every walker's can't-READ short-circuit reaches the caller as a value.

The `failed_read` arm in each walker is one line and is exactly the line
that used to be an uncaught raise. `livespec-dev-tooling-9sl0` recorded
what that cost: in the central fleet sweep the raise propagated out of a
function whose contract is tolerance and killed the whole nine-member run
partway through one member's walk.

WHY THESE CALL THE WALKERS DIRECTLY rather than driving `discover`.
`discover` runs the walkers in a fixed order and STOPS at the first
failure, and two of them read the SAME files: `walk_github_workflow_uses`
and `walk_github_workflow_container_image` both scan
`.github/workflows/*.yml`. An unreadable workflow file therefore always
fails at `walk_github_workflow_uses` first, which makes the container-image
walker's short-circuit UNREACHABLE through `discover`. Testing it through
the composed entry point would leave that line uncovered while looking
thorough — so each walker is exercised at its own seam.

WHY INVALID UTF-8 rather than `chmod 000`. A permission fixture is a lie
when the suite runs as root (every read succeeds, the assertion never
fires, and the test passes while proving nothing — the green-that-means-
nothing this epic exists to remove). Undecodable bytes fail identically
for every user, and they also exercise the flavor that motivated
`read_pin_text`: `UnicodeDecodeError` carries the offending bytes and NO
filename, so without the shared reader the diagnostic could only ever
name the walk root.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import _pin_directory_scan_formats as scan
from livespec_dev_tooling.cross_repo import _pin_single_file_formats as single
from livespec_dev_tooling.cross_repo.pin_autodiscovery import PinFileUnreadable

__all__: list[str] = []


# Bytes that are not valid UTF-8 in any locale: a lone continuation byte
# followed by a truncated two-byte sequence.
_UNDECODABLE = b"\xff\xfe\x00\xc3"

_LOG: structlog.stdlib.BoundLogger = structlog.get_logger("test_pin_walk_unreadable_edges")


def _assert_unreadable(*, walked: object, expected_walk: str) -> None:
    assert isinstance(walked, IOFailure), (
        f"{expected_walk} returned a SUCCESS for an undecodable file; the read "
        "failure must reach the caller as a value, not degrade to an empty "
        "record list that reads as 'this repo carries no pins'"
    )
    failure = unsafe_perform_io(walked.failure())
    assert isinstance(failure, PinFileUnreadable)
    # The walker's own name, not the composing caller's: one repo can carry
    # files of several formats, so an operator reading the diagnostic needs
    # to know WHICH walk hit the bad file.
    assert failure.pin_walk == expected_walk
    assert failure.detail


def test_livespec_jsonc_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=single.walk_livespec_jsonc(root=tmp_path, source_repo_filter=None, log=_LOG),
        expected_walk="walk_livespec_jsonc",
    )


def test_pyproject_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=single.walk_pyproject_toml(root=tmp_path, source_repo_filter=None, log=_LOG),
        expected_walk="walk_pyproject_toml",
    )


def test_vendor_jsonc_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    _ = (tmp_path / ".vendor.jsonc").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=single.walk_vendor_jsonc(root=tmp_path, source_repo_filter=None, log=_LOG),
        expected_walk="walk_vendor_jsonc",
    )


def test_workflow_uses_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=scan.walk_github_workflow_uses(root=tmp_path, source_repo_filter=None, log=_LOG),
        expected_walk="walk_github_workflow_uses",
    )


def test_container_image_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    """Unreachable through `discover` — see this module's docstring."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=scan.walk_github_workflow_container_image(
            root=tmp_path, source_repo_filter=None, log=_LOG
        ),
        expected_walk="walk_github_workflow_container_image",
    )


def test_fabro_workflow_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".fabro" / "workflows" / "implement"
    workflow_dir.mkdir(parents=True)
    _ = (workflow_dir / "workflow.toml").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=scan.walk_fabro_workflow_docker(root=tmp_path, source_repo_filter=None, log=_LOG),
        expected_walk="walk_fabro_workflow_docker",
    )


def test_codex_acp_walk_surfaces_an_undecodable_file(tmp_path: Path) -> None:
    dockerfile_dir = tmp_path / "docker" / "fabro-sandbox" / "agent"
    dockerfile_dir.mkdir(parents=True)
    _ = (dockerfile_dir / "Dockerfile").write_bytes(_UNDECODABLE)
    _assert_unreadable(
        walked=scan.walk_codex_acp_docker_arg(root=tmp_path, source_repo_filter=None, log=_LOG),
        expected_walk="walk_codex_acp_docker_arg",
    )
