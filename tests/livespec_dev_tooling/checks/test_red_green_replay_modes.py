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

    The cycle 4c extraction moved `_handle_red_mode` and
    `_handle_green_mode` into the sibling `_red_green_replay_modes.py`
    so `red_green_replay.py` stays under the 200-LLOC ceiling; the
    green-verified leg added `_handle_suite_green_mode` alongside. The
    fleet-check-coverage split then relocated the git-trailer I/O
    helpers to `_red_green_replay_trailers.py` (covered by its own
    mirror). This test pins the leg-handler surface of the helper
    module.
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
