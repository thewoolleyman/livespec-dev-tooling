"""The live recovery principal merges exactly one complete incident inverse per action.

The forge is a faithful fake: a bare Git repository answering the REST calls the
principal makes as the recovery App. Its blobs, trees, commits and the non-forced
ref update are real Git objects and a real fast-forward test, so a tree the fake
reports is the tree GitHub would report for the same bytes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_runtime_budget.github_budget import GithubBudgetResponse
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import incident_inverse_service as client_service
from livespec_dev_tooling import incident_recovery_principal_service as service
from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePublishRequest,
)
from livespec_dev_tooling._incident_observer_store import (
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverArm,
    ObserverRegistration,
    RecoveryIntent,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_inverse import plan_incident_inverse, recover_incident_inverse
from livespec_dev_tooling.incident_inverse_service import ProcessInverseForge
from livespec_dev_tooling.incident_recovery_app import (
    AppRefusal,
    RecoveryAppCredential,
    RecoveryForge,
)
from livespec_dev_tooling.incident_recovery_principal import RecoveryPrincipal

REPOSITORY = "owner/repo"
_PEM = "-----BEGIN RSA PRIVATE KEY-----\nZmFrZQ==\n-----END RSA PRIVATE KEY-----\n"
_OK, _CREATED, _NOT_FOUND, _UNPROCESSABLE = 200, 201, 404, 422


def git(repo, *args, data=None, env=None):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE_", "COVERAGE_"))
    }
    environment.update(
        GIT_AUTHOR_NAME="Principal fixture",
        GIT_AUTHOR_EMAIL="principal@example.invalid",
        GIT_COMMITTER_NAME="Principal fixture",
        GIT_COMMITTER_EMAIL="principal@example.invalid",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        **(env or {}),
    )
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args],
            input=data,
            capture_output=True,
            check=True,
            env=environment,
        )
        .stdout.decode()
        .strip()
    )


def commit(repo, message):
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class Forge:
    """A bare repository speaking the recovery App's REST subset."""

    def __init__(self, *, bare, pull):
        self.bare, self.pull, self.calls = bare, pull, []
        self.hooks = {}
        self.lost_patch_reply = self.ref_missing = self.wrong_tree = False
        self.broken = self.compare = None

    def master(self):
        return git(self.bare, "rev-parse", "refs/heads/master")

    def __call__(self, *, request):
        method, resource, value = request.method, request.resource, request.value
        self.calls.append((method, resource))
        hook = self.hooks.pop((method, resource.split("/")[-1]), None)
        if hook is not None:
            hook()
        status, body = self._answer(method=method, resource=resource, value=value)
        return GithubBudgetResponse(
            status_code=status, headers={}, value=body, primary_budget_spent=1
        )

    def count(self, method, suffix):
        return sum(1 for call in self.calls if call[0] == method and call[1].endswith(suffix))

    def _answer(self, *, method, resource, value):
        route = resource.removeprefix(f"repos/{REPOSITORY}/")
        number = self.pull["number"]
        fixed = {
            f"repos/{REPOSITORY}/installation": lambda: (_OK, {"id": 7}),
            "app/installations/7/access_tokens": lambda: (
                _CREATED,
                {"token": "ghs_fixture", "permissions": {"contents": "write"}},
            ),
            "git/ref/heads/master": self._ref,
            f"pulls/{number}": lambda: (_OK, self.pull["record"]),
            f"pulls/{number}/commits?per_page=100": lambda: (
                _OK,
                [{"commit": {"message": text}} for text in self.pull["messages"]]
                if isinstance(self.pull["messages"], list)
                else self.pull["messages"],
            ),
        }
        if resource in fixed or route in fixed:
            return fixed.get(resource, fixed.get(route))()
        if route.startswith("compare/"):
            return self._compare(commit=route.removeprefix("compare/").split("...")[0])
        if route.startswith("git/commits/") and method == "GET":
            return self._parent(sha=route.removeprefix("git/commits/"))
        return self._write(method=method, route=route, value=value)

    def _ref(self):
        return (_NOT_FOUND, None) if self.ref_missing else (_OK, {"object": {"sha": self.master()}})

    def _parent(self, *, sha):
        if self.broken == "base":
            return _NOT_FOUND, None
        return _OK, {"tree": {"sha": git(self.bare, "rev-parse", sha + "^{tree}")}}

    def _compare(self, *, commit):
        if self.compare is not None:
            return (_NOT_FOUND, None) if self.compare == "missing" else (500, None)
        head = self.master()
        if head == commit:
            return _OK, {"status": "identical"}
        if _ancestor(self.bare, commit, head):
            return _OK, {"status": "ahead"}
        if _ancestor(self.bare, head, commit):
            return _OK, {"status": "behind"}
        return _OK, {"status": "diverged"}

    def _write(self, *, method, route, value):
        if route == "git/blobs":
            data = base64.b64decode(value["content"]) + (b"!" if self.broken == "blob" else b"")
            return _CREATED, {"sha": git(self.bare, "hash-object", "-w", "--stdin", data=data)}
        if route == "git/trees":
            tree = self._tree(base=value["base_tree"], entries=value["tree"])
            return _CREATED, {"sha": "0" * 40 if self.wrong_tree else tree}
        if route == "git/commits":
            parents = [part for sha in value["parents"] for part in ("-p", sha)]
            sha = git(
                self.bare, "commit-tree", value["tree"], *parents, data=value["message"].encode()
            )
            return _CREATED, {"sha": sha}
        assert (method, route, value["force"]) == ("PATCH", "git/refs/heads/master", False)
        if not _ancestor(self.bare, self.master(), value["sha"]):
            return _UNPROCESSABLE, {"message": "Update is not a fast forward"}
        git(self.bare, "update-ref", "refs/heads/master", value["sha"])
        return (0, None) if self.lost_patch_reply else (_OK, {"object": {"sha": value["sha"]}})

    def _tree(self, *, base, entries):
        index = {"GIT_INDEX_FILE": str(Path(self.bare) / "fixture-index")}
        git(self.bare, "read-tree", base, env=index)
        lines = []
        for entry in entries:
            sha = entry.get("sha")
            if "content" in entry:
                data = entry["content"].encode()
                sha = git(self.bare, "hash-object", "-w", "--stdin", data=data)
            if sha is None:
                lines.append(f"0 {'0' * 40}\t{entry['path']}")
            else:
                lines.append(f"{entry['mode']} {sha}\t{entry['path']}")
        git(self.bare, "update-index", "--index-info", data="\n".join(lines).encode(), env=index)
        return git(self.bare, "write-tree", env=index)


def _ancestor(repo, older, newer):
    try:
        git(repo, "merge-base", "--is-ancestor", older, newer)
    except subprocess.CalledProcessError:
        return False
    return True


def _intent(*, before, merge, original_head):
    arm = ObserverArm(
        repository=REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=3,
        owner="controller-owner",
        phase="repair",
        pr_number=71,
        base_sha=before,
        head_sha=original_head,
        required_jobs=("ci-green",),
        controller_release="v1.186.0",
        controller_revision="c" * 40,
        authority_receipt=b"retained-canonical-authority",
    )
    registration = ObserverRegistration(
        repository=REPOSITORY,
        incident_item_id=arm.incident_item_id,
        attempt_id=arm.attempt_id,
        operation_id=arm.operation_id,
        generation=arm.generation,
        owner=arm.owner,
        phase=arm.phase,
        head_sha=merge,
        run_id=81,
        required_jobs=arm.required_jobs,
        controller_release=arm.controller_release,
        controller_revision=arm.controller_revision,
        candidate_revision=arm.head_sha,
        authority_receipt=arm.authority_receipt,
    )
    completion = LeafCompletion(
        delivery_id="delivery-1",
        repository=REPOSITORY,
        head_sha=merge,
        branch="master",
        run_id=81,
        job_id=82,
        job_name="ci-green",
        conclusion="failure",
    )
    identity = f"{REPOSITORY}:{arm.operation_id}:{arm.generation}:recover"
    return RecoveryIntent(
        action_id=hashlib.sha256(identity.encode()).hexdigest(),
        registration=registration,
        completion=completion,
        observer_arm=arm,
    )


def _observer_record(intent):
    arm = asdict(intent.observer_arm)
    arm["authority_receipt"] = intent.observer_arm.authority_receipt.hex()
    action = {
        "status": "pending",
        "registration": registration_record(registration=intent.registration),
        "completion": asdict(intent.completion),
        "receipt": None,
        "observer_arm": arm,
        "observer_arm_id": hashlib.sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest(),
    }
    return {**action, "actions": {intent.action_id: action}}


class World(SimpleNamespace):
    """One incident: the forge, the author's clone, the reference clone and the state."""

    def principal(self, *, connect=None):
        return RecoveryPrincipal(installation=self.installation, connect=connect or self.connect)

    def service(self, *, connect=None):
        return service.PrincipalService(principal=self.principal(connect=connect))

    def connect(self):
        return RecoveryForge.connect(
            repository=REPOSITORY,
            credential=RecoveryAppCredential(app_id="1", private_key=_PEM),
            transport=self.forge,
            signer=lambda **_: b"fixture-signature",
        )

    def client(self, monkeypatch, *, connect=None):
        """The observer's real process adapter, answered in process by this principal."""
        application = self.service(connect=connect)

        def run(argv, *, input, **_):
            del argv
            reply = application.execute(raw=input)
            return subprocess.CompletedProcess([], 0, stdout=json.dumps(reply).encode())

        scoped = SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired)
        monkeypatch.setattr(client_service, "subprocess", scoped)
        return ProcessInverseForge(command=("/fixed/principal",))

    def push_later(self, *, path, text, message="later unrelated work"):
        git(self.author, "pull", "--quiet", "--ff-only", "origin", "master")
        (self.author / path).write_text(text)
        sha = commit(self.author, message)
        git(self.author, "push", "--quiet", "origin", "HEAD:master")
        return sha

    def recover(self, monkeypatch, *, connect=None):
        forge = self.client(monkeypatch, connect=connect)
        with repository_lock(
            directory=self.installation.state, repository=REPOSITORY, existing_only=True
        ):
            return recover_incident_inverse(
                repo_root=self.installation.repo, intent=self.intent, forge=forge
            )

    def recovered(self, monkeypatch):
        """The recovery outcome, asserting the observer's recovery call succeeded."""
        result = self.recover(monkeypatch)
        assert is_successful(result), result
        return unsafe_perform_io(result.unwrap())

    def packet(self, operation, payload):
        body = json.loads(
            json.dumps(payload, sort_keys=True, default=lambda v: base64.b64encode(v).decode())
        )
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return {"schema": 1, "operation": operation, "binding": {"request_sha256": digest}, **body}

    def call(self, operation, payload, *, connect=None, fenced=True):
        raw = json.dumps(self.packet(operation, payload)).encode()
        application = self.service(connect=connect)
        if not fenced:
            return application.execute(raw=raw)
        with repository_lock(
            directory=self.installation.state, repository=REPOSITORY, existing_only=True
        ):
            return application.execute(raw=raw)

    def reverts(self):
        log = git(self.bare, "log", "--format=%H %s", "refs/heads/master")
        return [line for line in log.splitlines() if "Revert complete incident" in line]


def _history(*, tmp_path, bare):
    author = tmp_path / "author"
    git(tmp_path, "init", "--quiet", "--bare", "-b", "master", str(bare))
    git(tmp_path, "clone", "--quiet", str(bare), str(author))
    git(author, "checkout", "--quiet", "-b", "master")
    lines = "".join(f"line {number}\n" for number in range(40))
    (author / "shared.txt").write_text(lines)
    (author / "keep.txt").write_text("kept\n")
    (author / "removed.txt").write_text("restore me\n")
    (author / "old.bin").write_bytes(b"\x00before\xff")
    before = commit(author, "base")
    (author / "shared.txt").write_text(lines.replace("line 3\n", "incident first\n"))
    (author / "removed.txt").unlink()
    (author / "old.bin").write_bytes(b"\x00incident\xff")
    commit(author, "incident: first")
    (author / "introduced.txt").write_text("incident added\n")
    (author / "script.sh").write_text("#!/bin/sh\nexit 1\n")
    (author / "script.sh").chmod(0o755)
    merge = commit(author, "incident: second\n\nIncident-Item: incident-1")
    git(author, "push", "--quiet", "origin", "HEAD:master")
    return author, before, merge


@pytest.fixture
def world(tmp_path):
    bare = tmp_path / "forge.git"
    author, before, merge = _history(tmp_path=tmp_path, bare=bare)
    reference = tmp_path / "reference"
    git(tmp_path, "clone", "--quiet", str(bare), str(reference))
    reference.chmod(0o700)
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    for name in ("recovery-journal", "recovery-journal-contexts"):
        (state / name).mkdir(mode=0o700)
    original_head = "b" * 40
    intent = _intent(before=before, merge=merge, original_head=original_head)
    record = state / (hashlib.sha256(REPOSITORY.encode()).hexdigest() + ".json")
    save_record(path=record, record=_observer_record(intent))
    pull = {
        "number": 71,
        "messages": ["incident: first", "incident: second\n\nIncident-Item: incident-1"],
        "record": {
            "merged": True,
            "merge_commit_sha": merge,
            "base": {"ref": "master", "sha": before},
            "head": {"sha": original_head},
            "commits": 2,
        },
    }
    installation = ControllerInstallation(
        repository=REPOSITORY,
        repo=reference,
        state=state,
        reader=(sys.executable,),
        reader_release="v0.298.0",
        principal=(sys.executable,),
        release=intent.registration.controller_release,
        revision=intent.registration.controller_revision,
        jobs=intent.registration.required_jobs,
        webhook_secret=b"unused-webhook-fixture",
        control_secret=b"unused-control-fixture",
        query_secret=b"unused-query-fixture",
        port=8765,
        config=state.parent / "controller.json",
    )
    return World(
        bare=bare,
        author=author,
        before=before,
        merge=merge,
        intent=intent,
        installation=installation,
        record=record,
        forge=Forge(bare=bare, pull=pull),
        ledger=state / "recovery-journal" / f"{intent.action_id}.publication.json",
    )


def no_app():
    return AppRefusal(code="recovery-app-credential-absent", detail="no projected credential")


# Definition of Done 1: the exact inverse of the complete landed patch, merged as the App.


def test_authorized_action_merges_the_exact_complete_inverse_as_the_recovery_app(
    world, monkeypatch
):
    incident_head = world.forge.master()
    outcome = world.recovered(monkeypatch)
    assert outcome.status == "reverted", outcome
    head = world.forge.master()
    assert git(world.bare, "rev-parse", head + "^") == incident_head
    assert git(world.bare, "rev-parse", head + "^{tree}") == git(
        world.bare, "rev-parse", world.before + "^{tree}"
    )
    assert outcome.receipt == f"recovery-inverse:{world.intent.action_id}:commit:{head}"
    message = git(world.bare, "show", "-s", "--format=%B", head)
    assert f"Incident-Action: {world.intent.action_id}" in message
    # Installation token, never a check wait: one ref update, non-forced, and no
    # status, check-run or workflow resource is ever read on the way to master.
    assert world.forge.count("PATCH", "git/refs/heads/master") == 1
    assert not any("check" in call[1] or "actions" in call[1] for call in world.forge.calls)
    assert world.reverts() == [f"{head} Revert complete incident PR #71"]


def test_principal_refuses_a_request_that_is_not_the_exact_inverse(world, monkeypatch):
    forge = world.client(monkeypatch)
    plan = plan_for(world)
    tampered = replace(plan, inverse_patch=plan.inverse_patch + b"\n")
    reply = world.call("publish", {"request": asdict(publish_request(world, tampered))})
    assert reply["status"] == "refused"
    assert "exact complete inverse" in reply["reason"]
    assert world.forge.master() == world.merge
    assert forge.read_exact_receipt(intent=world.intent) is None


# Definition of Done 2: a moved head is recomputed; a genuine overlap is an owned conflict.


def test_moved_master_is_recomputed_against_the_new_head_preserving_later_work(world, monkeypatch):
    def move():
        world.push_later(path="keep.txt", text="kept and later changed\n")

    world.forge.hooks[("POST", "trees")] = move
    outcome = world.recovered(monkeypatch)
    assert outcome.status == "reverted"
    head = world.forge.master()
    assert git(world.bare, "show", f"{head}:keep.txt") == "kept and later changed"
    assert git(world.bare, "show", f"{head}:removed.txt") == "restore me"
    assert "incident first" not in git(world.bare, "show", f"{head}:shared.txt")
    assert len(world.reverts()) == 1
    record = json.loads(world.ledger.read_text())
    assert [attempt["status"] for attempt in record["attempts"]] == ["head-moved", "prepared"]
    assert world.forge.count("PATCH", "git/refs/heads/master") == 2


def test_genuine_overlap_with_later_work_is_an_owned_rollbackconflict_request(world, monkeypatch):
    world.push_later(
        path="shared.txt",
        text=(world.author / "shared.txt").read_text().replace("incident first", "later edit"),
    )
    head = world.forge.master()
    outcome = world.recovered(monkeypatch)
    assert outcome.status == "rollback-conflict"
    owner = world.intent.registration.owner
    assert (
        outcome.receipt == f"rollback-conflict:{world.intent.action_id}:owner:{owner}:head:{head}"
    )
    assert world.forge.master() == head
    assert world.forge.count("PATCH", "git/refs/heads/master") == 0
    context = world.installation.state / "recovery-journal-contexts"
    assert (context / f"{world.intent.action_id}.json").exists()
    forge = world.client(monkeypatch)
    assert forge.read_exact_receipt(intent=world.intent) == outcome.receipt


def test_conflict_is_refused_when_the_inverse_applies_cleanly(world, monkeypatch):
    world.client(monkeypatch)
    reply = world.call("conflict", {"request": asdict(conflict_request(world, head=world.merge))})
    assert reply["status"] == "refused"
    assert "no genuine overlap" in reply["reason"]
    assert (
        not (world.installation.state / "recovery-journal-contexts")
        .joinpath(f"{world.intent.action_id}.json")
        .exists()
    )


# Definition of Done 3: a repeated publish returns the original receipt, never a second revert.


def test_repeated_publish_after_a_lost_reply_returns_the_original_receipt(world):
    world.forge.lost_patch_reply = True
    request = {"request": asdict(publish_request(world, plan_for(world)))}
    first = world.call("publish", request)
    assert first["status"] == "unknown"
    merged = world.forge.master()
    world.forge.lost_patch_reply = False
    # A restarted principal: a fresh service over the same protected state.
    second = world.call("publish", request)
    assert second["status"] == "committed"
    assert second["merge_sha"] == merged
    again = world.call("publish", request)
    assert again == second
    assert world.forge.count("POST", "git/commits") == 1
    assert world.reverts() == [f"{merged} Revert complete incident PR #71"]


def test_repeated_publish_after_master_moved_on_still_returns_the_original_receipt(world):
    world.forge.lost_patch_reply = True
    request = {"request": asdict(publish_request(world, plan_for(world)))}
    assert world.call("publish", request)["status"] == "unknown"
    merged = world.forge.master()
    world.forge.lost_patch_reply = False
    world.push_later(path="keep.txt", text="work that landed after the revert\n")
    reply = world.call("publish", request)
    assert (reply["status"], reply["merge_sha"]) == ("committed", merged)
    assert world.forge.count("POST", "git/commits") == 1
    assert len(world.reverts()) == 1


def test_publish_interrupted_after_preparing_resends_the_same_commit(world):
    def interrupted():
        message = "process killed before the ref update returned"
        raise OSError(message)

    world.forge.hooks[("PATCH", "master")] = interrupted
    request = {"request": asdict(publish_request(world, plan_for(world)))}
    assert world.call("publish", request)["status"] == "refused"
    prepared = json.loads(world.ledger.read_text())["attempts"][0]
    assert prepared["status"] == "prepared"
    assert world.forge.master() == world.merge
    reply = world.call("publish", request)
    assert reply["status"] == "committed"
    assert reply["merge_sha"] == prepared["commit"] == world.forge.master()
    assert world.forge.count("POST", "git/commits") == 1


# Definition of Done 4: lookup is absent only for authoritative absence.


def test_lookup_answers_absent_only_for_a_pending_action_with_no_attempt(world, monkeypatch):
    forge = world.client(monkeypatch)
    assert forge.read_exact_receipt(intent=world.intent) is None
    world.forge.lost_patch_reply = True
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    world.forge.lost_patch_reply = False
    receipt = forge.read_exact_receipt(intent=world.intent)
    assert receipt == f"recovery-inverse:{world.intent.action_id}:commit:{world.forge.master()}"


def test_reserved_lookup_refuses_before_any_new_publication(world, monkeypatch):
    world.forge.hooks[("PATCH", "master")] = raise_oserror
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    commits = world.forge.count("POST", "git/commits")
    reply = world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    assert reply["status"] == "reserved"
    result = world.recover(monkeypatch)
    assert unsafe_perform_io(result.failure()).code == "inverse-unavailable"
    assert world.forge.count("POST", "git/commits") == commits
    assert world.forge.count("PATCH", "git/refs/heads/master") == 1
    # Without the App the open attempt cannot be resolved, so it stays reserved.
    reply = world.call("lookup", {"intent": asdict(world.intent)}, connect=no_app)
    assert reply["status"] == "reserved"


@pytest.mark.parametrize("damage", ["ledger", "observer"])
def test_malformed_or_unavailable_lookup_refuses(world, monkeypatch, damage):
    if damage == "ledger":
        world.ledger.write_text('{"schema": 1}')
        world.ledger.chmod(0o600)
    else:
        world.record.write_text("{")
    forge = world.client(monkeypatch)
    with pytest.raises(OSError, match="publication refused"):
        forge.read_exact_receipt(intent=world.intent)
    assert unsafe_perform_io(world.recover(monkeypatch).failure()).code == "inverse-unavailable"
    assert world.forge.count("POST", "git/commits") == 0


def raise_oserror():
    message = "unobserved ref update"
    raise OSError(message)


def plan_for(world):
    scope = world.principal().effects().landed(intent=world.intent)
    assert scope is not None, "the principal derives no complete landed scope"
    plan = plan_incident_inverse(
        repo_root=world.installation.repo, scope=scope, expected_head=world.forge.master()
    )
    assert is_successful(plan), plan
    return unsafe_perform_io(plan.unwrap())


def publish_request(world, plan):
    return InversePublishRequest(
        intent=world.intent,
        plan=plan,
        message=(
            "Revert complete incident PR #71\n\n"
            f"Incident-Action: {world.intent.action_id}\n"
            f"Incident-Owner: {world.intent.registration.owner}\n"
        ),
    )


def conflict_request(world, *, head):
    owner = world.intent.registration.owner
    return InverseConflictRequest(
        intent=world.intent,
        scope=world.principal().effects().landed(intent=world.intent),
        expected_head=head,
        reason="caller-asserted overlap",
        receipt=f"rollback-conflict:{world.intent.action_id}:owner:{owner}:head:{head}",
    )
