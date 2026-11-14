"""The flake-retry plugin solves each test path's closure once per pytest process.

Collection asks two questions of every item: whether its own closure withholds
the retry, and whether the change set touches it. Both read the same closure,
so a test file with many items, or with many parametrized cases, solves it
once for the whole session.
"""

from __future__ import annotations

import importlib
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.mark.integration
def test_collection_solves_each_test_path_closure_once_however_many_items_it_holds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Many items over two test files solve two closures, one per test path."""
    _ = (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    test_a = tests / "test_a.py"
    test_b = tests / "test_b.py"
    _ = test_a.write_text("import app\nassert app.VALUE == 1\n", encoding="utf-8")
    _ = test_b.write_text("import app\nassert app.VALUE == 1\n", encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    decisions = importlib.import_module("livespec_dev_tooling.flake_retry_decisions")
    changed = {Path("livespec_dev_tooling/gate_runner_delegate.py")}
    monkeypatch.setattr(plugin, "change_paths", Mock(return_value=changed))
    counting_closure = Mock(side_effect=vars(decisions)["_closure"])
    monkeypatch.setattr(decisions, "_closure", counting_closure)
    items = [Mock(path=test_a) for _ in range(5)] + [Mock(path=test_b) for _ in range(2)]

    withheld = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)

    solved = Counter(call.kwargs["test_path"] for call in counting_closure.call_args_list)
    assert withheld is None
    assert solved == Counter({test_a: 1, test_b: 1})
    assert [item.add_marker.call_count for item in items] == [1] * 7
