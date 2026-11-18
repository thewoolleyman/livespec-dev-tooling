"""A regenerated PR test merge commit keeps the run's own pinned merge commit verifiable."""

from __future__ import annotations

from tests.livespec_dev_tooling import test_incident_ci_job_identity as identity_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated

_RUN_MERGE = "repos/owner/repo/git/commits/" + "d" * 40


def test_pr_whose_current_merge_commit_was_regenerated_still_verifies(correlated):
    verifier, records, _ = correlated
    records["repos/owner/repo/pulls/55"]["merge_commit_sha"] = "1" * 40
    records["repos/owner/repo/git/commits/" + "1" * 40] = {
        "sha": "1" * 40,
        "parents": [{"sha": "e" * 40}, {"sha": "c" * 40}],
    }
    identity = verifier.verify()
    assert identity is not None and identity.job_id == 1011 and identity.check_suite_id == 77


def test_run_merge_commit_with_wrong_parents_still_refuses_after_regeneration(correlated):
    verifier, records, _ = correlated
    records["repos/owner/repo/pulls/55"]["merge_commit_sha"] = "1" * 40
    records[_RUN_MERGE]["parents"] = [{"sha": "e" * 40}, {"sha": "f" * 40}]
    assert verifier.verify() is None


def test_run_merge_commit_that_is_unreadable_still_refuses_after_regeneration(correlated):
    verifier, records, _ = correlated
    records["repos/owner/repo/pulls/55"]["merge_commit_sha"] = "1" * 40
    del records[_RUN_MERGE]
    assert verifier.verify() is None
