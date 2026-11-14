"""Mirror tests for sandbox affected-tests evidence qualification."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.affected_tests_record import AffectedTestsEvidence
from livespec_dev_tooling.checks import _red_green_replay_affected_tests as affected

__all__: list[str] = []


def test_qualifying_evidence_requires_every_sandbox_condition(
    *,
    tmp_path: Path,
) -> None:
    """Failed, empty, mismatched, and host records cannot narrow the suite."""
    for sandbox, outcome, paths, recorded_tree, index_tree, expected in (
        (True, "passed", ("tests/test_alpha.py",), "tree", "tree", True),
        (False, "passed", ("tests/test_alpha.py",), "tree", "tree", False),
        (True, "failed", ("tests/test_alpha.py",), "tree", "tree", False),
        (True, "passed", (), "tree", "tree", False),
        (True, "passed", ("tests/test_alpha.py",), "other", "tree", False),
        (True, "passed", ("tests/test_alpha.py",), "tree", None, False),
    ):
        evidence = AffectedTestsEvidence(
            tree_hash=recorded_tree,
            outcome=outcome,
            test_paths=paths,
            run_id="affected-tests:run-1",
        )
        actual = affected.qualifying_affected_tests_evidence(
            cwd=tmp_path,
            index_tree=index_tree,
            sandbox=lambda sandbox=sandbox, **_kwargs: sandbox,
            read_evidence=lambda evidence=evidence, **_kwargs: evidence,
        )
        assert (actual is not None) is expected
