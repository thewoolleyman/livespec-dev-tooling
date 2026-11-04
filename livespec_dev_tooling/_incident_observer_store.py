"""Durable controller receipts outside the tenant and credential wrapper."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverRegistration

__all__: list[str] = [
    "load_record",
    "read_observer_arm",
    "read_registration",
    "registration_record",
    "repository_lock",
    "save_record",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_INVALID_RECORD = "invalid incident controller record"
_INVALID_REGISTRATION = "invalid stored observer registration"
_INVALID_RECEIPT = "invalid stored observer receipt"
_INVALID_ARM = "invalid stored pre-merge observer arm"


@contextmanager
def repository_lock(*, directory: Path, repository: str) -> Iterator[Path]:
    """Serialize ALL controller and ordinary-reconciler mutations per repo.

    Production must provision this directory on the independent controller,
    inaccessible to candidate trees. A filesystem error propagates as refusal;
    there is no unlocked, tenant-backed, or wrapper-backed fallback.
    """
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(repository.encode()).hexdigest()
    path = directory / (key + ".json")
    with (directory / (key + ".lock")).open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def load_record(*, path: Path) -> dict[str, object]:
    """Read controller-owned state; corrupt state fails rather than going empty."""
    if not path.exists():
        return {}
    value: object = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(_INVALID_RECORD)
    return cast("dict[str, object]", value)


def save_record(*, path: Path, record: dict[str, object]) -> None:
    """Persist intent before effects with atomic replacement and directory fsync."""
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            _ = stream.write(json.dumps(record, sort_keys=True).encode())
            stream.flush()
            os.fsync(stream.fileno())
        _ = Path(temporary).replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def registration_record(*, registration: ObserverRegistration) -> dict[str, object]:
    """Encode only a registration already authorized at admission."""
    record: dict[str, object] = asdict(registration)
    record["authority_receipt"] = registration.authority_receipt.hex()
    return record


def read_registration(*, record: dict[str, object]) -> ObserverRegistration | None:
    """Read this controller's receipt, never an environment-supplied payload."""
    value = record.get("registration")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(_INVALID_REGISTRATION)
    data = cast("dict[str, object]", value).copy()
    jobs = data.get("required_jobs")
    receipt = data.get("authority_receipt")
    texts = (
        "repository",
        "incident_item_id",
        "attempt_id",
        "operation_id",
        "owner",
        "phase",
        "head_sha",
        "controller_release",
        "controller_revision",
        "candidate_revision",
        "branch",
    )
    if (
        not isinstance(jobs, list)
        or not all(isinstance(job, str) for job in cast("list[object]", jobs))
        or not isinstance(receipt, str)
        or not all(isinstance(data.get(key), str) for key in texts)
        or type(data.get("generation")) is not int
        or type(data.get("run_id")) is not int
        or set(data) != {*texts, "generation", "run_id", "required_jobs", "authority_receipt"}
    ):
        raise TypeError(_INVALID_RECEIPT)
    return ObserverRegistration(
        repository=cast("str", data["repository"]),
        incident_item_id=cast("str", data["incident_item_id"]),
        attempt_id=cast("str", data["attempt_id"]),
        operation_id=cast("str", data["operation_id"]),
        generation=cast("int", data["generation"]),
        owner=cast("str", data["owner"]),
        phase=cast("str", data["phase"]),
        head_sha=cast("str", data["head_sha"]),
        run_id=cast("int", data["run_id"]),
        required_jobs=tuple(cast("list[str]", jobs)),
        controller_release=cast("str", data["controller_release"]),
        controller_revision=cast("str", data["controller_revision"]),
        candidate_revision=cast("str", data["candidate_revision"]),
        authority_receipt=bytes.fromhex(receipt),
        branch=cast("str", data["branch"]),
    )


def read_observer_arm(*, record: dict[str, object]) -> ObserverArm | None:
    """Decode the protected cached grant, verifying its immutable arm digest."""
    value = record.get("observer_arm")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(_INVALID_ARM)
    data = cast("dict[str, object]", value)
    if hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest() != record.get(
        "observer_arm_id"
    ):
        raise ValueError(_INVALID_ARM)
    texts = (
        "repository",
        "incident_item_id",
        "attempt_id",
        "operation_id",
        "owner",
        "phase",
        "base_sha",
        "head_sha",
        "controller_release",
        "controller_revision",
        "authority_receipt",
    )
    jobs = data.get("required_jobs")
    if (
        not all(isinstance(data.get(key), str) for key in texts)
        or type(data.get("generation")) is not int
        or type(data.get("pr_number")) is not int
        or not isinstance(jobs, list)
        or not all(isinstance(job, str) for job in cast("list[object]", jobs))
        or set(data) != {*texts, "generation", "pr_number", "required_jobs"}
    ):
        raise TypeError(_INVALID_ARM)
    return ObserverArm(
        repository=cast("str", data["repository"]),
        incident_item_id=cast("str", data["incident_item_id"]),
        attempt_id=cast("str", data["attempt_id"]),
        operation_id=cast("str", data["operation_id"]),
        generation=cast("int", data["generation"]),
        owner=cast("str", data["owner"]),
        phase=cast("str", data["phase"]),
        pr_number=cast("int", data["pr_number"]),
        base_sha=cast("str", data["base_sha"]),
        head_sha=cast("str", data["head_sha"]),
        required_jobs=tuple(cast("list[str]", jobs)),
        controller_release=cast("str", data["controller_release"]),
        controller_revision=cast("str", data["controller_revision"]),
        authority_receipt=bytes.fromhex(cast("str", data["authority_receipt"])),
    )
