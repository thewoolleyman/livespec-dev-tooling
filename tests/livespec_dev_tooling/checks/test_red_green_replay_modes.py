"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_modes.py`.

The private sibling module carries the Red-leg, Green-leg, and
suite-green-leg handlers plus their git-trailer subprocess helpers
for `red_green_replay.py`. The leg handlers' behavioral coverage
lives in `test_red_green_replay.py` (they are exercised outside-in
through the parent supervisor's argv contract); THIS file carries
the module-surface and helper-unit tests, giving the helper module
the mirror-paired test file the incremental coverage gate resolves
(`_red_green_replay_modes.py` → `test_red_green_replay_modes.py`,
leading underscore stripped).
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []


_HELPERS_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_modes.py"
)


def test_red_green_replay_modes_helpers_importable() -> None:
    """The sibling helper module exposes the expected leg handlers.

    The cycle 4c extraction moved `_handle_red_mode`,
    `_handle_green_mode`, plus their git-trailer subprocess helpers
    into the sibling `_red_green_replay_modes.py` so
    `red_green_replay.py` stays under the 200-LLOC ceiling; the
    green-verified leg added `_handle_suite_green_mode` alongside.
    This test pins the public surface of the helper module.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_red_green_replay_modes_for_import_test",
        str(_HELPERS_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module._handle_red_mode)  # noqa: SLF001
    assert callable(module._handle_green_mode)  # noqa: SLF001
    assert callable(module._handle_suite_green_mode)  # noqa: SLF001
    assert callable(module._head_has_red_trailers)  # noqa: SLF001
    assert callable(module._head_trailer_value)  # noqa: SLF001
    assert callable(module._current_head_sha)  # noqa: SLF001
    assert callable(module._write_trailers)  # noqa: SLF001


def test_write_trailers_replaces_existing_keys_does_not_append(*, tmp_path: Path) -> None:
    """`_write_trailers` REPLACES existing trailers with the same key, not append.

    Bug surfaced 2026-05-04 during v039 D3 authoring: re-amending
    a Red commit caused the commit-msg hook to call `_write_trailers`
    a second time, which appended a NEW set of TDD-Red-* trailers
    instead of replacing the existing set. After three Red
    re-amends the commit message had three duplicate
    `TDD-Red-Test:` trailer lines, three duplicate
    `TDD-Red-Test-File-Checksum:` lines, etc. The Green-mode
    handler's `_head_trailer_value(key="TDD-Red-Test")` returned
    a newline-joined string of three identical paths, which
    `Path.cwd() / recorded_test` then turned into a non-existent
    nested-path → FileNotFoundError. Workflow-blocking for any
    Red→Green pair where the Red commit needed re-authoring.

    Fix contract: `_write_trailers` MUST use git's
    `--if-exists=replace` mode so that calling it twice with the
    same trailer key removes the prior occurrence and writes a
    fresh single instance. This test pins that behavior by
    constructing a commit-message file with pre-existing
    `TDD-Red-Test-File-Checksum:` trailers (simulating a prior
    write), invoking `_write_trailers` with a NEW value for the
    same key, and asserting the resulting file has EXACTLY ONE
    occurrence of that key with the new value.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_red_green_replay_modes_for_replace_test",
        str(_HELPERS_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

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

    module._write_trailers(  # noqa: SLF001
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
        f"_write_trailers should REPLACE existing TDD-Red-Test-File-Checksum, "
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
