"""A reverted incident's completed original run becomes evidence for its correction."""

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_original_run_canonical import EVIDENCE_MARKER, CanonicalPorts
from livespec_dev_tooling._incident_run_types import (
    EvidenceRefusal,
    ExpectedJob,
    ObservedJob,
    RunEvidence,
    RunSnapshot,
)
from livespec_dev_tooling.incident_original_run_flows import (
    Collection,
    Correction,
    EntryPorts,
    collect,
    propose,
)
from livespec_dev_tooling.incident_run_evidence import evidence_digest

REPOSITORY = "owner/repo"
WORKFLOW = b"name: CI\njobs: {}\n"
GRAPH = (
    ExpectedJob(name="lint"),
    ExpectedJob(name="test"),
    ExpectedJob(name="coverage", needs=("test",)),
    ExpectedJob(name="slow-leg"),
    ExpectedJob(name="late-leg"),
    ExpectedJob(name="other"),
)


def git(repo: Path, *args: str, stdin: bytes = b"") -> bytes:
    """Real Git with the outer hook's GIT_* variables scrubbed."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t")
    env.update(GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL="/dev/null")
    done = subprocess.run(
        ["git", *args], cwd=repo, input=stdin, env=env, capture_output=True, check=True
    )
    return done.stdout


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _ = git(repo, "add", "-A")
    _ = git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD").decode().strip()


@dataclass
class World:
    repo: Path
    state: Path
    shas: dict[str, str]
    comments: list[dict[str, str]] = field(default_factory=list)
    authority: Mock = field(default_factory=Mock)
    read: Mock = field(default_factory=Mock)

    def ledger(self, args: list[str]) -> str:
        if args[:2] == ["comments", "add"]:
            self.comments.append({"text": args[3]})
            return ""
        foreign = {"run_id": 7, "digest": "z"}
        noise = [{"id": "x"}, "junk", {"text": "unrelated"}, {"text": EVIDENCE_MARKER + "\n[]"}]
        noise.append({"text": EVIDENCE_MARKER + "\n" + json.dumps(foreign)})
        return json.dumps([*noise, *self.comments])

    def ports(self) -> EntryPorts:
        return EntryPorts(
            canonical=CanonicalPorts(authority=self.authority, ledger=self.ledger),
            git=lambda args, stdin: git(self.repo, *args, stdin=stdin),
            read=self.read,
        )


def job(name: str, conclusion: str | None, job_id: int, status: str = "completed") -> ObservedJob:
    return ObservedJob(
        name=name,
        job_id=job_id,
        status=status,
        conclusion=conclusion,
        evidence_url=f"https://forge.invalid/job/{job_id}",
    )


def run(world: World, status: str, *jobs: ObservedJob) -> RunSnapshot:
    return RunSnapshot(
        repository=REPOSITORY,
        run_id=42,
        run_attempt=1,
        head_sha=world.shas["merge"],
        status=status,
        jobs=jobs,
        graph_digest=hashlib.sha256(WORKFLOW).hexdigest(),
        complete_listing=True,
    )


FINAL = (
    job("lint", "success", 1),
    job("test", "failure", 2),
    job("coverage", "skipped", 3),
    job("slow-leg", "cancelled", 4),
    job("late-leg", "failure", 5),
)


def attempt(world: World, **changes: object) -> dict[str, Any]:
    record = {
        "repository": REPOSITORY,
        "item_id": "incident-1",
        "attempt_id": "attempt-1",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "incident-owner",
        "pr_number": 12,
        "landed_commits": [world.shas["merge"]],
    }
    return {"attempt": {**record, **changes}}


@pytest.fixture
def world(tmp_path: Path) -> World:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = git(repo, "init", "-q", "-b", "master")
    shas = {
        "base": commit(repo, {".github/workflows/ci.yml": WORKFLOW.decode(), "src": "ok\n"}, "base")
    }
    shas["merge"] = commit(repo, {"src": "broken\n"}, "incident change")
    _ = git(repo, "revert", "--no-edit", shas["merge"])
    shas["revert"] = git(repo, "rev-parse", "HEAD").decode().strip()
    shas["later"] = commit(repo, {"unrelated": "x\n"}, "master moves on")
    _ = git(repo, "checkout", "-qb", "reland")
    _ = git(repo, "cherry-pick", shas["merge"])
    shas["reland"] = git(repo, "rev-parse", "HEAD").decode().strip()
    shas["repair"] = commit(repo, {"src": "broken\nrepaired\n"}, "repair")
    _ = git(repo, "checkout", "-qb", "stale", shas["base"])
    shas["stale"] = commit(repo, {"src": "elsewhere\n"}, "not on the revert")
    _ = git(repo, "checkout", "-q", "master")
    state = tmp_path / "state"
    state.mkdir()
    registration = ObserverRegistration(
        repository=REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=1,
        owner="incident-owner",
        phase="master-observation",
        head_sha=shas["merge"],
        run_id=42,
        required_jobs=("test", "late-leg"),
        controller_release="v1",
        controller_revision="r1",
        candidate_revision="e" * 40,
        authority_receipt=b"{}",
    )
    with repository_lock(directory=state, repository=REPOSITORY) as path:
        record = {"registration": registration_record(registration=registration)}
        save_record(path=path, record={**record, "original_run_evidence": {"earlier": {"k": 1}}})
    created = World(repo=repo, state=state, shas=shas)
    created.authority.side_effect = lambda action, _query, _payload: (
        attempt(created) if action == "read-history" else {"operation_id": "correction-2"}
    )
    created.read.return_value = run(created, "completed", *FINAL)
    return created


def gather(world: World, **changes: Any) -> RunEvidence | EvidenceRefusal:
    request = Collection(
        state_dir=world.state,
        repository=REPOSITORY,
        revert_sha=world.shas["revert"],
        expected=GRAPH,
    )
    return collect(request=replace(request, **changes), ports=world.ports())


def stored(world: World) -> dict[str, object]:
    with repository_lock(directory=world.state, repository=REPOSITORY) as path:
        return cast("dict[str, object]", load_record(path=path)["original_run_evidence"])


def correction(world: World, digest: str, head: str, **changes: Any) -> str | EvidenceRefusal:
    request = Correction(
        state_dir=world.state,
        repository=REPOSITORY,
        evidence_digest=digest,
        next_head_sha=world.shas[head],
        target_ref="refs/heads/incident-1-attempt-2",
        current_generation=3,
        base_ref="master",
    )
    return propose(request=replace(request, **changes), ports=world.ports())


def test_collects_every_expected_job_of_the_completed_run_including_late_legs(
    world: World,
) -> None:
    world.read.return_value = run(
        world, "in_progress", job("test", "failure", 2), job("late-leg", None, 5, "in_progress")
    )
    early = gather(world)
    world.read.return_value = run(world, "completed", *FINAL)
    collected = gather(world)
    assert isinstance(early, EvidenceRefusal)
    assert early.code == "incident-original-run-in-progress"
    assert isinstance(collected, RunEvidence)
    assert collected.terminal
    assert [(row.name, row.state) for row in collected.jobs] == [
        ("lint", "completed"),
        ("test", "failed"),
        ("coverage", "prerequisite-blocked"),
        ("slow-leg", "cancelled"),
        ("late-leg", "failed"),
        ("other", "never-created"),
    ]
    original = collected.original
    assert (original.item_id, original.attempt_id, original.run_id, original.pr_number) == (
        "incident-1",
        "attempt-1",
        42,
        12,
    )
    assert (original.merge_sha, original.revert_sha) == (world.shas["merge"], world.shas["revert"])
    assert (
        original.tree_sha
        == git(world.repo, "rev-parse", world.shas["merge"] + "^{tree}").decode().strip()
    )


def test_controller_retains_and_item_records_one_digest_for_a_repeat_collection(
    world: World,
) -> None:
    first, second = gather(world), gather(world)
    assert isinstance(first, RunEvidence)
    digest = evidence_digest(evidence=first)
    assert isinstance(second, RunEvidence)
    assert evidence_digest(evidence=second) == digest
    assert sorted(stored(world)) == sorted(["earlier", digest])
    assert len(world.comments) == 1
    marker, body = world.comments[0]["text"].split("\n", 1)
    record = json.loads(body)
    assert marker == EVIDENCE_MARKER
    assert (record["item_id"], record["attempt_id"], record["run_id"], record["digest"]) == (
        "incident-1",
        "attempt-1",
        42,
        digest,
    )
    assert [row[:2] for row in record["jobs"]][-2:] == [
        ["late-leg", "failed"],
        ["other", "never-created"],
    ]
    world.comments[0]["text"] = marker + "\n" + json.dumps({**record, "digest": "other"})
    conflicting = gather(world)
    assert isinstance(conflicting, EvidenceRefusal)
    assert len(world.comments) == 1


@pytest.mark.parametrize(
    ("reader", "code"),
    [
        (lambda world: run(world, "queued"), "incident-original-run-in-progress"),
        (lambda _world: OSError("forge unreachable"), "incident-original-run-refused"),
        (
            lambda _world: EvidenceRefusal(code="incident-original-run-unavailable", detail="down"),
            "incident-original-run-unavailable",
        ),
    ],
)
def test_incomplete_run_or_unreachable_forge_refuses_and_keeps_earlier_receipts(
    world: World, reader: Any, code: str
) -> None:
    outcome = reader(world)
    if isinstance(outcome, OSError):
        world.read.side_effect = outcome
    else:
        world.read.return_value = outcome
    refused = gather(world)
    assert isinstance(refused, EvidenceRefusal)
    assert refused.code == code
    assert stored(world) == {"earlier": {"k": 1}}
    assert world.comments == []


def test_unchanged_reland_is_refused_before_any_canonical_attempt(world: World) -> None:
    collected = gather(world)
    assert isinstance(collected, RunEvidence)
    digest = evidence_digest(evidence=collected)
    reland = correction(world, digest, "reland")
    resolved = correction(world, digest, "reland", resolved_jobs=(("test", "rerun-receipt"),))
    assert isinstance(reland, EvidenceRefusal)
    assert reland.code == "incident-original-run-invalid"
    assert isinstance(resolved, EvidenceRefusal)
    actions = [call.args[0] for call in world.authority.call_args_list]
    assert "correct-attempt" not in actions
    assert correction(world, digest, "repair") == "correction-2"
    action, query, payload = world.authority.call_args.args
    correct = json.loads(payload["correction-json"])
    obligations = [row.name for row in collected.jobs if row.state != "completed"]
    measured = correction(
        world, digest, "reland", resolved_jobs=tuple((name, "r-" + name) for name in obligations)
    )
    resolution = json.loads(world.authority.call_args.args[2]["correction-json"])
    assert (action, payload["target-ref"]) == ("correct-attempt", "refs/heads/incident-1-attempt-2")
    assert (query["phase"], query["operation"], query["generation"]) == (
        "collecting-failures",
        "attempt-1#collecting-failures",
        3,
    )
    assert sorted(correct) == ["base", "evidence_id", "head", "kind", "staged_tree"]
    assert (correct["kind"], correct["head"], correct["base"]) == (
        "repair",
        world.shas["repair"],
        world.shas["later"],
    )
    tree = git(world.repo, "rev-parse", world.shas["repair"] + "^{tree}").decode().strip()
    assert correct["staged_tree"] == tree
    assert measured == "correction-2"
    assert (resolution["kind"], resolution["head"]) == ("measured-resolution", world.shas["reland"])
    assert resolution["evidence_id"] not in {correct["evidence_id"], digest}


def test_named_refusals_for_identity_graph_authority_and_revision(world: World) -> None:
    missing_graph = gather(world, expected=GRAPH[:3])
    not_a_revert = gather(world, revert_sha=world.shas["merge"])
    foreign_revert = gather(world, revert_sha=world.shas["stale"])
    world.authority.side_effect = lambda *_args: attempt(world, landed_commits=[])
    unauthorized = gather(world)
    world.authority.side_effect = [attempt(world), {}]
    unreadable = gather(world)
    world.authority.side_effect = lambda *_args: attempt(world, pr_number="12")
    no_pr = gather(world)
    world.authority.side_effect = OSError("authority down")
    down = gather(world)
    unregistered = gather(world, repository="owner/other")
    codes = [
        getattr(value, "code", None)
        for value in (missing_graph, not_a_revert, foreign_revert, unauthorized, unreadable)
    ] + [getattr(value, "code", None) for value in (no_pr, down)]
    assert codes == [
        "incident-original-run-graph-invalid",
        "incident-original-run-local-revision",
        "incident-original-run-local-revision",
        "incident-original-run-refused",
        "incident-original-run-refused",
        "incident-original-run-authority-refused",
        "incident-original-run-authority-refused",
    ]
    assert getattr(unregistered, "code", None) == "incident-original-run-unregistered"
    assert stored(world) == {"earlier": {"k": 1}}


def test_correction_refuses_unretained_unrecorded_or_unrelated_heads(world: World) -> None:
    collected = gather(world)
    assert isinstance(collected, RunEvidence)
    digest = evidence_digest(evidence=collected)
    with repository_lock(directory=world.state, repository=REPOSITORY) as path:
        record = load_record(path=path)
        retained = cast("dict[str, object]", record["original_run_evidence"])
        retained["g" * 64] = retained[digest]
        save_record(path=path, record=record)
    misfiled = correction(world, "g" * 64, "repair")
    unknown = correction(world, "f" * 64, "repair")
    tampered_digest = correction(world, "earlier", "repair")
    stale = correction(world, digest, "stale")
    empty = correction(world, digest, "later")
    unregistered = correction(world, digest, "repair", repository="owner/other")
    world.authority.side_effect = lambda *_args: {"operation_id": None}
    no_receipt = correction(world, digest, "repair")
    world.comments.clear()
    unrecorded = correction(world, digest, "repair")
    codes = [
        getattr(value, "code", None)
        for value in (unknown, tampered_digest, stale, empty, unregistered, no_receipt, unrecorded)
    ]
    assert getattr(misfiled, "code", None) == "incident-original-run-evidence-missing"
    assert codes == [
        "incident-original-run-evidence-missing",
        "incident-original-run-evidence-missing",
        "incident-original-run-local-revision",
        "incident-original-run-invalid",
        "incident-original-run-unregistered",
        "incident-original-run-refused",
        "incident-original-run-unrecorded",
    ]
