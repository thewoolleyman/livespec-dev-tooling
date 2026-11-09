"""The observer's release screen refuses fenced incident releases and clears the rest."""

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
from livespec_dev_tooling.incident_release_screen import ReleaseScreen

_REPOSITORY = "owner/repo"


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
def reference(tmp_path):
    """root -> incident -> later on master, and root -> unrelated on a side branch."""
    root = tmp_path / "reference"
    root.mkdir()
    _ = _git(root, "init", "--quiet", "--initial-branch=master")
    commits = {}
    for name in ("root", "incident", "later"):
        _ = _git(root, "commit", "--quiet", "--allow-empty", "-m", name)
        commits[name] = _git(root, "rev-parse", "HEAD")
    _ = _git(root, "checkout", "--quiet", "-b", "side", commits["root"])
    _ = _git(root, "commit", "--quiet", "--allow-empty", "-m", "unrelated")
    commits["unrelated"] = _git(root, "rev-parse", "HEAD")
    return root, commits


@pytest.fixture
def service(tmp_path, reference):
    root, commits = reference
    settings = SimpleNamespace(
        repository=_REPOSITORY,
        repo=root,
        state=tmp_path / "protected",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
    )
    registration = ObserverRegistration(
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
    return (
        ControllerService(installation=settings, recover=lambda _: None),
        registration_record(registration=registration),
        commits,
    )


def _store(*, application, record):
    settings = application.installation
    with repository_lock(directory=settings.state, repository=settings.repository) as path:
        save_record(path=path, record=record)


def _screen(*, application, source, tag="v1.2.3", secret=None, extra=None):
    payload = {"repository": _REPOSITORY, "source_sha": source, "tag": tag, **(extra or {})}
    body = json.dumps(payload).encode()
    secret = application.installation.query_secret if secret is None else secret
    environ = {
        "PATH_INFO": "/release/screen",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
    }
    statuses = []
    result = b"".join(application(environ, lambda status, _headers: statuses.append(status)))
    return statuses[0], json.loads(result)


def _attribution(*, source, tag):
    return {"source_sha": source, "release_tag": tag, "consumer_repository": "owner/consumer"}


def test_a_release_with_no_incident_record_is_clear(service):
    application, _registration, commits = service
    status, result = _screen(application=application, source=commits["later"])
    assert status == "202 Accepted"
    assert result["status"] == "clear"


@pytest.mark.parametrize("field", ["release_attribution", "release_adoption_intents"])
@pytest.mark.parametrize("match", ["source", "tag"])
def test_an_attributed_release_of_a_fenced_registration_is_refused_by_name(service, field, match):
    application, registration, commits = service
    attributed = _attribution(
        source=commits["later"] if match == "source" else "d" * 40,
        tag="v9.9.9" if match == "source" else "v1.2.3",
    )
    _store(
        application=application,
        record={
            "actions": {"action-1": {"status": "completed", "registration": registration}},
            field: {
                "other": {
                    "registration": registration,
                    "attribution": _attribution(source="e" * 40, tag="v0.0.1"),
                },
                "identity": {"registration": registration, "attribution": attributed},
            },
        },
    )
    status, result = _screen(application=application, source=commits["later"])
    assert status == "403 Forbidden"
    assert result["reason"] == "incident-release-recovery-retained"
    assert result["incident_item_id"] == "incident-1"
    assert "incident-1" in result["detail"]


def test_an_attributed_release_of_an_unfenced_registration_is_clear(service):
    application, registration, commits = service
    _store(
        application=application,
        record={
            "release_attribution": {
                "identity": {
                    "registration": registration,
                    "attribution": _attribution(source=commits["later"], tag="v1.2.3"),
                }
            }
        },
    )
    status, result = _screen(application=application, source=commits["later"])
    assert (status, result["status"]) == ("202 Accepted", "clear")


def test_an_unfinished_recovery_refuses_a_source_containing_the_incident_head(service):
    application, registration, commits = service
    _store(
        application=application,
        record={"actions": {"action-1": {"status": "pending", "registration": registration}}},
    )
    status, result = _screen(application=application, source=commits["later"])
    assert status == "403 Forbidden"
    assert result["reason"] == "incident-release-recovery-retained"


def test_an_unfinished_recovery_clears_a_source_without_the_incident_head(service):
    application, registration, commits = service
    _store(
        application=application,
        record={"actions": {"action-1": {"status": "pending", "registration": registration}}},
    )
    status, result = _screen(application=application, source=commits["unrelated"])
    assert (status, result["status"]) == ("202 Accepted", "clear")


def test_a_completed_recovery_alone_does_not_fence_an_unattributed_source(service):
    application, registration, commits = service
    _store(
        application=application,
        record={"actions": {"action-1": {"status": "completed", "registration": registration}}},
    )
    status, result = _screen(application=application, source=commits["later"])
    assert (status, result["status"]) == ("202 Accepted", "clear")


@pytest.mark.parametrize("head", ["unknown", "malformed"])
def test_an_undecidable_ancestry_refuses_as_unverifiable(service, head):
    application, registration, commits = service
    fenced = {**registration, "head_sha": "f" * 40 if head == "unknown" else "not-a-sha"}
    _store(
        application=application,
        record={"actions": {"action-1": {"status": "pending", "registration": fenced}}},
    )
    status, result = _screen(application=application, source=commits["later"])
    assert status == "403 Forbidden"
    assert result["reason"] == "incident-release-source-unverifiable"


@pytest.mark.parametrize(
    "change",
    [
        {"source": "short"},
        {"source": 7},
        {"tag": "-leading-dash"},
        {"tag": 3},
        {"extra": {"unexpected": "field"}},
    ],
)
def test_an_inexact_screen_query_is_refused(service, change):
    application, _registration, commits = service
    arguments = {"application": application, "source": commits["later"], **change}
    status, result = _screen(**arguments)
    assert status == "403 Forbidden"
    assert result["reason"] == "invalid exact release screen query"


def test_the_screen_answers_only_its_own_path_and_repository(service):
    application, _registration, commits = service
    payload = {"repository": _REPOSITORY, "source_sha": commits["later"], "tag": "v1.2.3"}
    screen = ReleaseScreen(installation=application.installation)
    assert screen.execute(path="/current", payload=payload)["status"] == "refused"
    foreign = ReleaseScreen(installation=SimpleNamespace(repository="owner/other"))
    assert foreign.execute(path="/release/screen", payload=payload)["status"] == "refused"


def test_the_control_credential_is_not_a_screen_credential(service):
    application, _registration, commits = service
    status, result = _screen(
        application=application,
        source=commits["later"],
        secret=application.installation.control_secret,
    )
    assert status == "403 Forbidden"
    assert result["status"] == "refused"
