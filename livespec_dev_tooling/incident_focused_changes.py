"""The head's changed product files, as the observer's own reference clone answers them.

A focused-evidence record names the paths its collector measured, but a record is
the operator's artifact: a hand-built or stale one can name none. `/arm` therefore
never takes the changed set from the record or from the request. It reads it here,
in the observer's independent reference clone: the merge base of the configured
target branch and the head, then every path that differs between that base and
the head (SPECIFICATION `contracts.md`, the expedited incident execution contract:
focused tests and touched-file coverage are recorded before merge).

A product file is a changed path under the source prefixes of the COMMITTED
configuration, the union of the target branch's and the head's. The clone's
checked-out copy is never read (nothing moves it after provisioning), and the
union means a head can widen its own scope, by declaring a new source tree, but
never narrow it. Each changed path is listed with `--no-renames`, so a moved file
is both its old path and its new one, as the collector lists it. Each one present
at the head is classified by the collector's own `classify`, over the head's exact
blob and mode, so the observer and the collector name the same files `executable`.

Anything the clone cannot establish is a reason, never an empty set: a missing
head, an unresolvable merge base, an unreadable committed configuration at either
ref or a source-prefix set that is empty would otherwise admit a record that
covers nothing.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling._incident_focused_scope import classify
from livespec_dev_tooling.config import ConfigParseError, derive_source_prefixes, load_config
from livespec_dev_tooling.incident_git import IncidentGitError, git_text, run_git

__all__: list[str] = ["ChangedProductFiles", "changed_product_files"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-6ou5m2
_EXECUTABLE_MODE = "100755"


@dataclass(frozen=True, kw_only=True)
class ChangedProductFiles:
    """Every changed product file of a head, and those the collector would measure."""

    product: tuple[str, ...]
    executable: tuple[str, ...]


def _names(*, raw: bytes) -> list[str]:
    return [name for name in raw.decode().split("\0") if name]


def _blobs(*, repo: Path, head: str, names: list[str]) -> dict[str, tuple[str, bytes]]:
    """Each named path present at `head`, as its tree mode and exact blob bytes."""
    listing = run_git(repo=repo, args=("ls-tree", "-r", "-z", head)).stdout
    wanted = set(names)
    entries = [
        (meta.split()[0], meta.split()[2], name)
        for meta, _, name in (entry.partition("\t") for entry in _names(raw=listing))
        if name in wanted
    ]
    batch = run_git(
        repo=repo,
        args=("cat-file", "--batch"),
        data="".join(f"{sha}\n" for _, sha, _ in entries).encode(),
    ).stdout
    blobs: dict[str, tuple[str, bytes]] = {}
    for mode, _, name in entries:
        header, _, rest = batch.partition(b"\n")
        size = int(header.split()[2])
        blobs[name] = (mode, rest[:size])
        batch = rest[size + 1 :]
    return blobs


def _committed_prefixes(*, repo: Path, refs: tuple[str, ...]) -> tuple[str, ...]:
    """The union of the source prefixes each ref's committed configuration declares."""
    prefixes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="incident-focused-config-") as scratch:
        root = Path(scratch)
        for ref in refs:
            text = run_git(repo=repo, args=("show", f"{ref}:pyproject.toml")).stdout
            _ = (root / "pyproject.toml").write_bytes(text)
            prefixes.extend(derive_source_prefixes(config=load_config(repo_root=root)))
    return tuple(dict.fromkeys(prefixes))


def _changed(
    *, repo: Path, target_ref: str, head: str, prefixes: tuple[str, ...]
) -> ChangedProductFiles:
    base = git_text(repo=repo, args=("merge-base", target_ref, head))
    raw = run_git(
        repo=repo, args=("diff-tree", "-r", "-z", "--no-renames", "--name-only", base, head)
    )
    product = sorted(name for name in _names(raw=raw.stdout) if name.startswith(prefixes))
    blobs = _blobs(repo=repo, head=head, names=product)
    with tempfile.TemporaryDirectory(prefix="incident-focused-changes-") as scratch:
        root = Path(scratch)
        for name, (mode, data) in blobs.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_bytes(data)
            target.chmod(0o755 if mode == _EXECUTABLE_MODE else 0o644)
        executable = [
            name
            for name in product
            if classify(path=root / name, name=name, source_prefixes=prefixes) == "executable"
        ]
    return ChangedProductFiles(product=tuple(product), executable=tuple(executable))


def changed_product_files(
    *, repo: Path, target_branch: str, head: str
) -> ChangedProductFiles | str:
    """The changed product files of `head` in the reference clone, or why they are unknown."""
    target_ref = f"refs/remotes/origin/{target_branch}"
    try:
        present = run_git(repo=repo, args=("cat-file", "-e", f"{head}^{{commit}}"), check=False)
        if present.returncode:
            return (
                f"the reference clone does not hold head {head}; its reference fetch has not"
                " brought the head in yet"
            )
        prefixes = _committed_prefixes(repo=repo, refs=(target_ref, head))
        if not prefixes:
            return (
                "the committed configuration declares no source prefixes, so no product file"
                " is knowable"
            )
        return _changed(repo=repo, target_ref=target_ref, head=head, prefixes=prefixes)
    except ConfigParseError as unreadable:
        return (
            f"the committed configuration at {target_branch} or head {head} is unreadable:"
            f" {unreadable}"
        )
    except (
        IncidentGitError,
        IndexError,
        OSError,
        SyntaxError,
        UnicodeDecodeError,
        ValueError,
    ) as failure:
        return (
            f"the reference clone cannot establish head {head}'s changed files against its merge"
            f" base with {target_branch}: {failure}"
        )
