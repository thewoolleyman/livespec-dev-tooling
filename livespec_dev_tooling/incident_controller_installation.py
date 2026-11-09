"""Protected host installation identity for the independent incident controller.

The manifest is provisioned by the host with its approved released artifact. A
candidate request cannot choose code, dependency paths, reader or principal argv.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.incident_ci_identity_policy import (
    CiIdentityPolicy,
    load_identity_policy,
)
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["ControllerInstallation"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_PRIVATE_DIRECTORY_MODE = 0o700
_SECRET_BYTES = 32
_PORT_LIMIT = 65536


@dataclass(frozen=True, kw_only=True)
class ControllerInstallation:
    """Settings authenticated from a protected independently provisioned manifest."""

    repository: str
    repo: Path
    state: Path
    reader: tuple[str, ...]
    reader_release: str
    principal: tuple[str, ...]
    release: str
    revision: str
    jobs: tuple[str, ...]
    webhook_secret: bytes
    control_secret: bytes
    query_secret: bytes
    port: int
    config: Path
    ci_identity_policy: CiIdentityPolicy | None = None

    @classmethod
    def load(cls, *, config: Path) -> ControllerInstallation | None:
        """Validate identity, complete installed package and executable chain before listen."""
        try:
            data = _record(path=config)
            if (
                data is None
                or set(data)
                != {
                    "manifest",
                    "candidate_uid",
                    "repository",
                    "repo",
                    "state",
                    "webhook_secret",
                    "control_secret",
                    "query_secret",
                    "port",
                }
                or type(data["candidate_uid"]) is not int
                or data["candidate_uid"] == os.geteuid()
            ):
                return None
            manifest = _record(path=Path(data["manifest"]))
            if manifest is None or set(manifest) - {"ci_identity_policy"} != {
                "release",
                "revision",
                "package_sha256",
                "reader",
                "reader_release",
                "principal",
                "files",
                "required_jobs",
            }:
                return None
            if not (
                _valid_build(manifest=manifest)
                and _valid_files(manifest=manifest)
                and _valid_paths(data=data)
                and _valid_jobs(jobs=manifest["required_jobs"])
            ):
                return None
            repo, state = Path(data["repo"]), Path(data["state"])
            jobs = manifest["required_jobs"]
            webhook = _secret(path=Path(data["webhook_secret"]))
            control = _secret(path=Path(data["control_secret"]))
            query = _secret(path=Path(data["query_secret"]))
            if (
                webhook is None
                or control is None
                or query is None
                or webhook == control
                or query in {webhook, control}
                or type(data["port"]) is not int
                or not 0 < data["port"] < _PORT_LIMIT
            ):
                return None
            return cls(
                repository=data["repository"],
                repo=repo,
                state=state,
                reader=tuple(manifest["reader"]),
                reader_release=manifest["reader_release"],
                principal=tuple(manifest["principal"]),
                release=manifest["release"],
                revision=manifest["revision"],
                jobs=tuple(jobs),
                webhook_secret=webhook,
                control_secret=control,
                query_secret=query,
                port=data["port"],
                config=config,
                ci_identity_policy=load_identity_policy(
                    descriptor=manifest.get("ci_identity_policy"), repository=data["repository"]
                ),
            )
        except (
            OSError,
            ValueError,
            IncidentJsonRefusalError,
            TypeError,
            KeyError,
            importlib.metadata.PackageNotFoundError,
        ):
            return None


def _valid_build(*, manifest: dict[str, Any]) -> bool:
    revision = manifest["revision"]
    return (
        manifest["release"] == "v" + importlib.metadata.version("livespec-dev-tooling")
        and isinstance(revision, str)
        and re.fullmatch(r"[0-9a-f]{40}", revision) is not None
        and isinstance(manifest["reader_release"], str)
        and bool(manifest["reader_release"])
        and _package_digest(root=Path(__file__).resolve().parent) == manifest["package_sha256"]
    )


def _valid_files(*, manifest: dict[str, Any]) -> bool:
    raw_files = manifest["files"]
    files = cast("dict[str, Any]", raw_files)
    return (
        isinstance(raw_files, dict)
        and _command_files(manifest=manifest, files=files)
        and all(
            _protected(path=Path(name))
            and hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
            for name, digest in files.items()
        )
    )


def _valid_paths(*, data: dict[str, Any]) -> bool:
    repo, state = Path(data["repo"]), Path(data["state"])
    return (
        isinstance(data["repository"], str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", data["repository"])
        is not None
        and repo.is_dir()
        and _protected(path=repo)
        and state.is_dir()
        and _protected(path=state)
        and stat.S_IMODE(state.stat().st_mode) == _PRIVATE_DIRECTORY_MODE
        and not state.resolve().is_relative_to(repo.resolve())
        and not Path(__file__).resolve().parent.is_relative_to(repo.resolve())
    )


def _valid_jobs(*, jobs: Any) -> bool:
    values = cast("list[Any]", jobs)
    return (
        isinstance(jobs, list)
        and bool(values)
        and all(isinstance(job, str) and bool(job) for job in values)
        and len(set(values)) == len(values)
    )


def _record(*, path: Path) -> dict[str, Any] | None:
    if not _protected(path=path) or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        return None
    data: object = strict_json(text=path.read_bytes(), limit=None)
    return cast("dict[str, Any]", data) if isinstance(data, dict) else None


def _secret(*, path: Path) -> bytes | None:
    if not _protected(path=path) or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        return None
    value = path.read_bytes()
    return value if len(value) >= _SECRET_BYTES else None


def _command_files(*, manifest: dict[str, Any], files: dict[str, Any]) -> bool:
    for key in ("reader", "principal"):
        raw_command = manifest[key]
        command = cast("list[Any]", raw_command)
        if (
            not isinstance(raw_command, list)
            or not command
            or not all(isinstance(v, str) for v in command)
        ):
            return False
        if any(Path(value).name == "with-livespec-env.sh" for value in command):
            return False
        if not os.access(command[0], os.X_OK):
            return False
        for value in command:
            if value in {"-I", "--"}:
                continue
            if not Path(value).is_absolute() or value not in files:
                return False
    # The actual interpreter and every imported dependency are also protected;
    # -I in the service unit prevents PYTHONPATH and user-site injection.
    return _protected(path=Path(sys.executable)) and str(Path(sys.executable).resolve()) in files


def _package_digest(*, root: Path) -> str | None:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if not _protected(path=path):
            return None
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(path.read_bytes())
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name and Path(name).is_absolute() and not _protected(path=Path(name)):
            return None
    return digest.hexdigest()


def _protected(*, path: Path) -> bool:
    if not path.is_absolute() or not path.exists():
        return False
    resolved = path.resolve(strict=True)
    for entry in (path, *path.parents, resolved, *resolved.parents):
        link = entry.lstat()
        if link.st_uid not in {0, os.geteuid()}:
            return False
        info = entry.stat()
        sticky_root = entry.is_dir() and info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if info.st_uid not in {0, os.geteuid()} or (info.st_mode & 0o022 and not sticky_root):
            return False
    return True
