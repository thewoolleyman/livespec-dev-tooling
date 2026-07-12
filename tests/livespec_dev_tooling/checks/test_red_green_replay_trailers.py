"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_trailers.py`.

The private sibling module carries the git commit-message trailer I/O
extracted from `_red_green_replay_modes.py` at the fleet-check-coverage
LLOC-reduction split: the HEAD-state resolver plus the HEAD readers and
the trailer writer. The functions' end-to-end coverage lives in
`test_red_green_replay.py` (they are exercised outside-in through the
parent supervisor's argv contract); THIS file pins the module surface
and unit-tests the trailer writer's replace-not-append contract
directly at the module boundary.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks._red_green_replay_trailers import (
    current_head_sha,
    head_red_awaiting_green,
    head_trailer_value,
    write_trailers,
)

__all__: list[str] = []


def test_trailer_helpers_are_callable() -> None:
    """The sibling module exposes the HEAD-state resolver, readers, and writer."""
    assert callable(head_red_awaiting_green)
    assert callable(head_trailer_value)
    assert callable(current_head_sha)
    assert callable(write_trailers)


def test_write_trailers_replaces_existing_keys_does_not_append(*, tmp_path: Path) -> None:
    """`write_trailers` REPLACES existing trailers with the same key, not append.

    Bug surfaced 2026-05-04 during v039 D3 authoring: re-amending
    a Red commit caused the commit-msg hook to call `write_trailers`
    a second time, which appended a NEW set of TDD-Red-* trailers
    instead of replacing the existing set. After three Red
    re-amends the commit message had three duplicate
    `TDD-Red-Test:` trailer lines, three duplicate
    `TDD-Red-Test-File-Checksum:` lines, etc. The Green-mode
    handler's `head_trailer_value(key="TDD-Red-Test")` returned
    a newline-joined string of three identical paths, which
    `Path.cwd() / recorded_test` then turned into a non-existent
    nested-path → FileNotFoundError. Workflow-blocking for any
    Red→Green pair where the Red commit needed re-authoring.

    Fix contract: `write_trailers` MUST use git's
    `--if-exists=replace` mode so that calling it twice with the
    same trailer key removes the prior occurrence and writes a
    fresh single instance. This test pins that behavior by
    constructing a commit-message file with pre-existing
    `TDD-Red-Test-File-Checksum:` trailers (simulating a prior
    write), invoking `write_trailers` with a NEW value for the
    same key, and asserting the resulting file has EXACTLY ONE
    occurrence of that key with the new value.
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text(
        "feat: red — sample\n"
        "\n"
        "Body explaining the change.\n"
        "\n"
        "TDD-Red-Test: tests/dev-tooling/checks/test_sample.py\n"
        "TDD-Red-Test-File-Checksum: sha256:aaaa\n"
        "TDD-Red-Captured-At: 2026-05-04T01:00:00Z\n",
        encoding="utf-8",
    )

    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Red-Test", "tests/dev-tooling/checks/test_sample.py"),
            ("TDD-Red-Test-File-Checksum", "sha256:bbbb"),
            ("TDD-Red-Captured-At", "2026-05-04T02:00:00Z"),
        ),
    )

    final_message = msg_path.read_text(encoding="utf-8")
    test_file_lines = [
        line
        for line in final_message.splitlines()
        if line.startswith("TDD-Red-Test-File-Checksum:")
    ]
    assert len(test_file_lines) == 1, (
        f"write_trailers should REPLACE existing TDD-Red-Test-File-Checksum, "
        f"not append: expected exactly 1 occurrence, got {len(test_file_lines)}: "
        f"{test_file_lines!r}; full message:\n{final_message}"
    )
    assert "sha256:bbbb" in test_file_lines[0], (
        f"the surviving TDD-Red-Test-File-Checksum line should carry the NEW value "
        f"(sha256:bbbb), got: {test_file_lines[0]!r}"
    )
    assert "sha256:aaaa" not in final_message, (
        f"the OLD value (sha256:aaaa) should be GONE after replace, "
        f"but it persists in:\n{final_message}"
    )
