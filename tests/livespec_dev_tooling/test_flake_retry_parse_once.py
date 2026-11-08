"""The flake-retry plugin parses each source module once per pytest process."""

from __future__ import annotations

import importlib
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.mark.integration
def test_collection_parses_each_closure_module_once_however_many_items_import_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Many items over two test files sharing one import parse every module exactly once."""
    _ = (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    test_a = tests / "test_a.py"
    test_b = tests / "test_b.py"
    _ = test_a.write_text("import app\nassert app.VALUE == 1\n", encoding="utf-8")
    _ = test_b.write_text("import app\nassert app.VALUE == 1\n", encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    changed = {Path("livespec_dev_tooling/gate_runner_delegate.py")}
    monkeypatch.setattr(plugin, "change_paths", Mock(return_value=changed))
    counting_parse = Mock(side_effect=plugin.ast.parse)
    monkeypatch.setattr(plugin.ast, "parse", counting_parse)
    items = [Mock(path=test_a) for _ in range(5)] + [Mock(path=test_b) for _ in range(2)]

    withheld = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)

    parsed = Counter(call.kwargs["filename"] for call in counting_parse.call_args_list)
    assert withheld is None
    assert parsed == Counter({str(tmp_path / "app.py"): 1, str(test_a): 1, str(test_b): 1})
    assert [item.add_marker.call_count for item in items] == [1] * 7
    assert {
        (marker.name, tuple(sorted(marker.kwargs.items())))
        for item in items
        for marker in (item.add_marker.call_args.args[0],)
    } == {("flaky", (("reruns", 3), ("reruns_delay", 60)))}
