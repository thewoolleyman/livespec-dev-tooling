"""Git/config/clone/canary half of the standalone host identity probe."""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = []
JsonObject = dict[str, object]


class Runner(Protocol):  # pragma: no cover - follow-up Red cycle
    def __call__(
        self,
        *,
        args: tuple[str, ...],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True, kw_only=True)
class ProbeConfig:  # pragma: no cover - follow-up Red cycle
    host: str
    user: str
    owner: str
    expected_name: str
    expected_email: str
    roots: tuple[str, ...]


def default_runner(  # pragma: no cover - follow-up Red cycle
    *,
    args: tuple[str, ...],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def git_values(  # pragma: no cover - follow-up Red cycle
    *, runner: Runner, args: tuple[str, ...], cwd: Path | None = None
) -> tuple[list[str], str | None]:
    answer = runner(args=("git", *args), cwd=cwd)
    if answer.returncode == 0:
        return answer.stdout.splitlines(), None
    if answer.returncode == 1:
        return [], None
    return [], answer.stderr.strip() or f"git config exited {answer.returncode}"


def discover(  # pragma: no cover - follow-up Red cycle
    *, root: str
) -> tuple[list[Path], JsonObject, list[str]]:
    path = Path(root)
    if not path.exists():
        return [], {"path": root, "state": "absent"}, []
    found: list[Path] = []
    blind: list[str] = []

    def onerror(*errors: OSError) -> None:
        blind.append(f"walk:{errors[0].filename}")

    for current, dirs, files in os.walk(path, onerror=onerror):
        if ".git" in dirs or ".git" in files:
            found.append(Path(current))
            dirs.clear()
        else:
            dirs[:] = [item for item in dirs if item not in {".cache", ".venv", "node_modules"}]
    return found, {"path": root, "state": "present"}, blind


def github_identity(  # pragma: no cover - follow-up Red cycle
    *, origin: str
) -> tuple[str, str] | None:
    matched = re.search(r"github\.com(?::|/)([^/]+)/([^/]+?)(?:\.git)?$", origin)
    return (matched.group(1), matched.group(2)) if matched else None


def worktree_paths(  # pragma: no cover - follow-up Red cycle
    *, runner: Runner, repo: Path
) -> tuple[list[Path], str | None]:
    answer = runner(args=("git", "worktree", "list", "--porcelain"), cwd=repo)
    if answer.returncode != 0:
        return [], f"worktree-list:{repo}"
    return [
        Path(line.removeprefix("worktree "))
        for line in answer.stdout.splitlines()
        if line.startswith("worktree ")
    ], None


def worktree_record(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig, runner: Runner, path: Path
) -> tuple[JsonObject, list[str]]:
    queries = {
        "local_names": ("config", "--local", "--get-all", "user.name"),
        "local_emails": ("config", "--local", "--get-all", "user.email"),
        "extension": ("config", "--local", "--type=bool", "--get", "extensions.worktreeConfig"),
    }
    values: dict[str, list[str]] = {}
    errors: list[str] = []
    for key, args in queries.items():
        values[key], error = git_values(runner=runner, args=args, cwd=path)
        if error is not None:
            errors.append(error)
    values["worktree_names"] = []
    values["worktree_emails"] = []
    if values["extension"] == ["true"]:
        for key, config_key in (("worktree_names", "user.name"), ("worktree_emails", "user.email")):
            values[key], error = git_values(
                runner=runner, args=("config", "--worktree", "--get-all", config_key), cwd=path
            )
            if error is not None:
                errors.append(error)
    author_vars = {"GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE"}
    clean_env = {key: value for key, value in os.environ.items() if key not in author_vars}
    effective = runner(args=("git", "var", "GIT_AUTHOR_IDENT"), cwd=path, env=clean_env)
    identity = _parse_author_ident(value=effective.stdout) if effective.returncode == 0 else None
    if identity is None:
        errors.append(f"git-author-ident:{path}")
    names = (*values["local_names"], *values["worktree_names"])
    emails = (*values["local_emails"], *values["worktree_emails"])
    passed = (
        not errors
        and identity == (config.expected_name, config.expected_email)
        and all(item == config.expected_name for item in names)
        and all(item == config.expected_email for item in emails)
    )
    record: JsonObject = {
        "path": str(path),
        "effective_name": identity[0] if identity is not None else None,
        "effective_email": identity[1] if identity is not None else None,
        "local_names": values["local_names"],
        "local_emails": values["local_emails"],
        "worktree_names": values["worktree_names"],
        "worktree_emails": values["worktree_emails"],
        "passed": passed,
    }
    return record, ([f"git-config:{path}"] if errors else [])


def _parse_author_ident(*, value: str) -> tuple[str, str] | None:
    matched = re.fullmatch(r"(.+) <([^<>]+)> \d+ [+-]\d{4}\n?", value)
    return (matched.group(1), matched.group(2)) if matched else None


def repositories(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig, runner: Runner, candidates: list[Path]
) -> tuple[list[JsonObject], list[JsonObject], list[str]]:
    owned: dict[str, JsonObject] = {}
    excluded: list[JsonObject] = []
    blind: list[str] = []
    for candidate in sorted(set(candidates)):
        common = runner(
            args=("git", "rev-parse", "--path-format=absolute", "--git-common-dir"),
            cwd=candidate,
        )
        origin_answer = runner(args=("git", "remote", "get-url", "origin"), cwd=candidate)
        if common.returncode != 0 or origin_answer.returncode != 0:
            blind.append(f"repository-metadata:{candidate}")
            continue
        origin = origin_answer.stdout.strip()
        identity = github_identity(origin=origin)
        if identity is None or identity[0] != config.owner:
            excluded.append({"path": str(candidate), "origin": origin})
            continue
        common_dir = str(Path(common.stdout.strip()).resolve())
        if common_dir in owned:
            continue
        paths, error = worktree_paths(runner=runner, repo=candidate)
        if error is not None:
            blind.append(error)
        records: list[JsonObject] = []
        for path in paths:
            record, errors = worktree_record(config=config, runner=runner, path=path)
            records.append(record)
            blind.extend(errors)
        owned[common_dir] = {
            "repo": identity[1],
            "common_dir": common_dir,
            "origin": origin,
            "worktrees": sorted(records, key=lambda item: str(item["path"])),
        }
    return (
        [owned[key] for key in sorted(owned)],
        sorted(excluded, key=lambda item: str(item["path"])),
        blind,
    )


def global_config(  # pragma: no cover - follow-up Red cycle
    *, config: ProbeConfig, runner: Runner
) -> tuple[JsonObject, list[str]]:
    names, name_error = git_values(
        runner=runner, args=("config", "--global", "--get-all", "user.name")
    )
    emails, email_error = git_values(
        runner=runner, args=("config", "--global", "--get-all", "user.email")
    )
    use_only, use_error = git_values(
        runner=runner, args=("config", "--global", "--type=bool", "--get", "user.useConfigOnly")
    )
    errors = [item for item in (name_error, email_error, use_error) if item is not None]
    return {
        "name": names[0] if len(names) == 1 else None,
        "email": emails[0] if len(emails) == 1 else None,
        "use_config_only": use_only == ["true"],
        "passed": not errors
        and names == [config.expected_name]
        and emails == [config.expected_email]
        and use_only == ["true"],
    }, [f"global-config:{item}" for item in errors]
