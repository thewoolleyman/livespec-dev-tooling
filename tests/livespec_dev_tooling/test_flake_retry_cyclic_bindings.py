"""The closure solve terminates when bindings go through one another in a cycle.

livespec-dev-tooling-4ai5ao: a name bound to another name that is bound back to
it (`HERE = OTHER`, `OTHER = HERE`) makes the closure's key graph cyclic. The
solve must still finish, and decide as it would without the cycle: a change
under the directory the names resolve to touches the test. The decision runs
on a daemon thread joined with a time limit, so a solve that never finishes
fails the test instead of hanging the session.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_decisions import retry_marker_for

_CYCLIC = (
    "from pathlib import Path\n\n"
    "HERE = Path(__file__).parent\nOTHER = HERE\nHERE = OTHER\n\n"
    "def test_read():\n    name = str(len(__name__))\n    assert HERE / 'data' / name\n"
)


@pytest.mark.integration
def test_a_cycle_of_bindings_is_solved_and_still_touches_the_test(*, tmp_path: Path) -> None:
    """A change under the cyclically bound directory touches the test, and the solve ends."""
    tests = tmp_path / "tests"
    tests.mkdir()
    test_path = tests / "test_x.py"
    _ = test_path.write_text(_CYCLIC, encoding="utf-8")
    decided: list[dict[str, int] | None] = []

    solver = threading.Thread(
        target=lambda: decided.append(
            retry_marker_for(
                repo_root=tmp_path, test_path=test_path, change_paths={Path("tests/data/x.json")}
            )
        ),
        daemon=True,
    )
    solver.start()
    solver.join(timeout=60)

    assert decided == [None]
