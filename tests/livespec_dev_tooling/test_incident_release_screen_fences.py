"""Only a published inverse in the release source clears a fenced incident head."""

from __future__ import annotations

import io
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from livespec_dev_tooling._incident_observer_store import (
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.incident_observer_service import ControllerService

_REPOSITORY = "owner/repo"
_RETAINED = "incident-release-recovery-retained"
_UNVERIFIABLE = "incident-release-source-unverifiable"


def _git(root, *args):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True, env=environment
    ).stdout.strip()


@pytest.fixture
def screen(tmp_path):
    """master: root -> incident -> later -> revert -> after; side: root -> unrelated."""
    root = tmp_path / "reference"
    root.mkdir()
    _ = _git(root, "init", "--quiet", "--initial-branch=master")
    commits = {}
    for name in ("root", "incident", "later", "revert", "after"):
        _ = _git(root, "commit", "--quiet", "--allow-empty", "-m", name)
        commits[name] = _git(root, "rev-parse", "HEAD")
    _ = _git(root, "checkout", "--quiet", "-b", "side", commits["root"])
    _ = _git(root, "commit", "--quiet", "--allow-empty", "-m", "unrelated")
    commits["unrelated"] = _git(root, "rev-parse", "HEAD")
    settings = SimpleNamespace(
        repository=_REPOSITORY,
        repo=root,
        state=tmp_path / "protected",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
    )
    registration = registration_record(
        registration=ObserverRegistration(
            repository=_REPOSITORY,
            incident_item_id="incident-1",
            attempt_id="repair-1",
            operation_id="operation-1",
            generation=1,
            owner="owner",
            phase="merged",
            head_sha=commits["incident"],
            run_id=7,
            required_jobs=("ci-green",),
            controller_release="v1.169.0",
            controller_revision="b" * 40,
            candidate_revision="c" * 40,
            authority_receipt=b"receipt",
        )
    )
    return ControllerService(installation=settings, recover=lambda _: None), registration, commits


def _verdict(*, application, record, source, tag="v1.2.3"):
    settings = application.installation
    with repository_lock(directory=settings.state, repository=settings.repository) as path:
        save_record(path=path, record=record)
    body = json.dumps({"repository": _REPOSITORY, "source_sha": source, "tag": tag}).encode()
    environ = {
        "PATH_INFO": "/release/screen",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + settings.query_secret.decode(),
    }
    result = json.loads(b"".join(application(environ, lambda _status, _headers: None)))
    return result.get("reason", result["status"])


def _action(*, registration, receipt, status="completed"):
    return {
        "actions": {
            "action-1": {"status": status, "registration": registration, "receipt": receipt}
        }
    }


def _inverse(*, commit, action="action-1"):
    return f"recovery-inverse:{action}:commit:{commit}"


def test_a_rollback_conflict_keeps_a_source_holding_the_incident_head_refused(screen):
    """The reviewer's probe: a conflict completes the action, but nothing was reverted."""
    application, registration, commits = screen
    conflict = f"rollback-conflict:action-1:owner:owner:head:{commits['later']}"
    record = _action(registration=registration, receipt=conflict)
    assert _verdict(application=application, record=record, source=commits["later"]) == _RETAINED


@pytest.mark.parametrize(
    ("receipt", "source", "expected"),
    [
        ("revert", "after", "clear"),
        ("revert", "later", _RETAINED),
        ("other-action", "after", _RETAINED),
        ("malformed", "after", _RETAINED),
        ("none", "later", _RETAINED),
        ("unknown-commit", "after", _UNVERIFIABLE),
    ],
)
def test_only_a_published_inverse_in_the_source_clears_the_incident_head(
    screen, receipt, source, expected
):
    application, registration, commits = screen
    receipts = {
        "revert": _inverse(commit=commits["revert"]),
        "other-action": _inverse(commit=commits["revert"], action="action-2"),
        "malformed": "recovery-inverse:action-1:commit:not-a-sha",
        "none": None,
        "unknown-commit": _inverse(commit="e" * 40),
    }
    record = _action(registration=registration, receipt=receipts[receipt])
    assert _verdict(application=application, record=record, source=commits[source]) == expected


@pytest.mark.parametrize(
    ("with_inverse", "source", "expected"),
    [
        (False, "later", _RETAINED),
        (False, "after", _RETAINED),
        (False, "unrelated", "clear"),
        (True, "after", "clear"),
        (True, "later", _RETAINED),
    ],
)
def test_a_regression_fences_its_head_until_an_inverse_of_that_registration_is_in_the_source(
    screen, with_inverse, source, expected
):
    application, registration, commits = screen
    record = {
        "release_regressions": {
            "regression-1": {"registration": registration, "regression_id": "r", "receipt": ""}
        },
        **(
            _action(registration=registration, receipt=_inverse(commit=commits["revert"]))
            if with_inverse
            else {}
        ),
    }
    assert _verdict(application=application, record=record, source=commits[source]) == expected


def test_an_attribution_fenced_only_by_a_regression_is_refused_by_name(screen):
    application, registration, commits = screen
    record = {
        "release_regressions": {
            "regression-1": {"registration": registration, "regression_id": "r", "receipt": ""}
        },
        "release_attribution": {
            "elsewhere": {
                "registration": registration,
                "attribution": {"source_sha": "e" * 40, "release_tag": "v0.0.1"},
            },
            "identity": {
                "registration": registration,
                "attribution": {"source_sha": "d" * 40, "release_tag": "v1.2.3"},
            },
        },
    }
    assert (
        _verdict(application=application, record=record, source=commits["unrelated"]) == _RETAINED
    )


def test_a_fenced_head_that_is_not_a_commit_id_refuses_as_unverifiable(screen):
    application, registration, commits = screen
    malformed = {**registration, "head_sha": "not-a-sha"}
    record = {"release_regressions": {"regression-1": {"registration": malformed, "receipt": ""}}}
    assert (
        _verdict(application=application, record=record, source=commits["after"]) == _UNVERIFIABLE
    )


def test_an_inexact_query_is_refused_before_any_fence_is_read(screen):
    application, registration, commits = screen
    record = _action(registration=registration, receipt=None)
    verdict = _verdict(application=application, record=record, source=commits["after"], tag="-bad")
    assert verdict == "invalid exact release screen query"
