"""The versioning lockstep of `SPECIFICATION/contracts.md`, read off the checkout.

The section makes two claims, and each fails in a way nothing else here would
catch.

**Three version records stay in lockstep.** The `pyproject.toml` `version`
field, the `.release-please-manifest.json` entry, and the git tag. The first two
are always readable and are asserted as equal outright: they are the pair a
consumer's `tag = "vX.Y.Z"` pin and the packaging metadata are resolved from, and
they drift the moment anything but the release tool touches either. The tag is
asserted CONDITIONALLY — `v<version>` must be among the tags when the checkout
carries any at all. That is not a softening: a clone made without tags has not
told us the tag is absent, and a can't-read is not a violation
(`livespec-dev-tooling-6ge`), so a bare `git tag` list of length zero is treated
as the absence of evidence it is.

One further absence is evidence of nothing either: THE RELEASE IS IN FLIGHT.
`release-please` lands the release commit on `master` first and creates the tag
afterwards, so between the two there is a window in which `master` legitimately
declares a version no tag names. A clone taken inside it failed this test on
2026-10-12 — `declared='1.95.7' tags=[... 'v1.95.6']`, 23 seconds before the tag
existed — and parked a correctly merged work-item. So a missing `v<declared>` is
admitted on exactly two co-held conditions: NO tag is newer than the declared
version, and the last commit to write that version is one `release-please` itself
authored. Both halves are load-bearing. A declared version that LAGS its tags is
convicted by the first, since a newer tag proves the tag record runs past the
point the declared version should have been written into it; a version written by
any other hand is convicted by the second, which is the whole of the guard
against a second writer that bumps and never tags. The window is read off the
LOCAL checkout: this suite does no network I/O, so an absent tag is never
re-fetched — the checkout that failed in 2026-10-12's window still failed five
minutes later, after the tag existed, because nothing had fetched it.

**`release-please` is the only tool that writes to these.** A second writer is
what makes lockstep unmaintainable, and it announces itself long before it
misfires: to write the manifest a tool must first NAME it. Asserted as the
absence of that name from every shipped module and from the `justfile` — the two
places a second writer would live — with the release-please workflow the single
sanctioned namer. This is a necessary-condition test and says so: it convicts a
would-be writer at the point it acquires the path, which is the only point at
which the convicting is cheap.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import cast

from livespec_dev_tooling.cross_repo._bump_version_order import version_gt
from livespec_dev_tooling.cross_repo.master_health_commit_shape import is_release_commit

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _REPO_ROOT / ".release-please-manifest.json"
_JUSTFILE = _REPO_ROOT / "justfile"
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

_VERSION_LINE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)

# The manifest's root-package key — this repository releases one package.
_ROOT_PACKAGE = "."

# The manifest path a second writer would have to name before writing it, and
# the one workflow sanctioned to.
_MANIFEST_NAME = ".release-please-manifest.json"
_SANCTIONED_NAMER = _REPO_ROOT / ".github" / "workflows" / "release-please.yml"

# A committer for the throwaway checkouts below, supplied per-invocation because
# the fixture must not depend on — or write — any host or repository git config.
_FIXTURE_IDENTITY = (
    "-c",
    "user.email=tests@livespec.invalid",
    "-c",
    "user.name=livespec tests",
)


def _git_env() -> dict[str, str]:
    """The environment every `git` child here runs in — each `GIT_*` variable dropped.

    A commit hook exports `GIT_DIR` and `GIT_INDEX_FILE` into the pytest run it
    launches, and both would point these children at the SURROUNDING repository:
    a read would answer about the wrong checkout, and a fixture's `git add` would
    write the real index.
    """
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git(*, repo_root: Path, args: list[str], check: bool = True) -> str:
    """Run `git` in `repo_root` and return its stdout.

    `check=False` for the two READS below: a checkout git cannot answer about
    yields an empty string, which each reader already treats as the absence of
    evidence it is.
    """
    # S603/S607: a literal `git` plus a fixed argument list, never a shell string.
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=check,
        env=_git_env(),
    )
    return completed.stdout


def _declared_version(*, repo_root: Path) -> str:
    """The version `pyproject.toml` declares."""
    pyproject = repo_root / "pyproject.toml"
    matched = _VERSION_LINE.search(pyproject.read_text(encoding="utf-8"))
    assert matched is not None, 'pyproject.toml must declare a `version = "..."` line'
    return matched.group("version")


def _manifest_version() -> str:
    """The version the release manifest records for the root package."""
    parsed = cast("dict[str, str]", json.loads(_MANIFEST.read_text(encoding="utf-8")))
    assert _ROOT_PACKAGE in parsed, (
        f"the release manifest must carry a `{_ROOT_PACKAGE}` entry for the root package; "
        f"keys={sorted(parsed)}"
    )
    return parsed[_ROOT_PACKAGE]


def _release_tags(*, repo_root: Path) -> list[str]:
    """Every `v*` tag this checkout carries — possibly none, on a tagless clone."""
    stdout = _git(repo_root=repo_root, args=["tag", "--list", "v*"], check=False)
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _version_change_subject(*, repo_root: Path, declared: str) -> str:
    """The subject of the last commit to write `declared` as the packaging version.

    The pickaxe names the declared version itself, so the answer is the commit
    that wrote THIS value rather than whichever commit touched `pyproject.toml`
    last. An empty string where no commit carries it, or where there is no
    readable history at all.
    """
    pickaxe = f'-Sversion = "{declared}"'
    args = ["log", "-1", "--format=%s", pickaxe, "--", "pyproject.toml"]
    return _git(repo_root=repo_root, args=args, check=False).strip()


def _tag_lockstep_holds(*, repo_root: Path) -> bool:
    """Whether this checkout's tag record is in lockstep with its declared version.

    True for the two absences the module docstring records as evidence of
    nothing — a tagless clone, and the in-flight release window.
    """
    declared = _declared_version(repo_root=repo_root)
    tags = _release_tags(repo_root=repo_root)
    if not tags or f"v{declared}" in tags:
        return True
    if any(version_gt(left=tag, right=f"v{declared}") for tag in tags):
        return False
    subject = _version_change_subject(repo_root=repo_root, declared=declared)
    return is_release_commit(subject=subject)


def _make_checkout(*, root: Path, declared: str, subject: str, tags: tuple[str, ...]) -> Path:
    """A throwaway checkout declaring `declared`, written by a commit with `subject`.

    Two commits, because the pickaxe read above answers about the commit that
    WROTE the declared version: the baseline declares a different one, so the
    second commit is unambiguously the writer of this one.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(repo_root=root, args=["init", "-q", "-b", "master"])
    pyproject = root / "pyproject.toml"
    for version, message in (("0.0.0", "chore: baseline"), (declared, subject)):
        pyproject.write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
        _git(repo_root=root, args=["add", "pyproject.toml"])
        _git(repo_root=root, args=[*_FIXTURE_IDENTITY, "commit", "-q", "-m", message])
    for tag in tags:
        _git(repo_root=root, args=["tag", tag])
    return root


def _manifest_namers() -> list[str]:
    """Every shipped module or justfile recipe naming the release manifest."""
    candidates = [_JUSTFILE, *sorted(_PACKAGE_DIR.rglob("*.py"))]
    return sorted(
        str(path.relative_to(_REPO_ROOT))
        for path in candidates
        if "_vendor" not in path.relative_to(_REPO_ROOT).parts
        and _MANIFEST_NAME in path.read_text(encoding="utf-8")
    )


def test_the_version_records_stay_in_lockstep() -> None:
    """The packaging version, the manifest entry, and (where readable) the tag agree."""
    declared = _declared_version(repo_root=_REPO_ROOT)
    recorded = _manifest_version()
    assert declared == recorded, (
        f"the `pyproject.toml` version and the release manifest entry MUST stay in "
        f"lockstep — a consumer's pin tag names one and its resolver reads the other; "
        f"pyproject={declared!r} manifest={recorded!r}"
    )

    assert _tag_lockstep_holds(repo_root=_REPO_ROOT), (
        f"the git tag is the third record of the lockstep, so the declared version must be "
        f"tagged wherever the tags are readable at all and the release is not still in "
        f"flight; declared={declared!r} "
        f"tags={_release_tags(repo_root=_REPO_ROOT)[-5:]} "
        f"version-written-by="
        f"{_version_change_subject(repo_root=_REPO_ROOT, declared=declared)!r}"
    )


def test_a_release_commit_awaiting_its_tag_keeps_the_lockstep(tmp_path: Path) -> None:
    """The in-flight window: the release commit has landed, its tag has not yet."""
    checkout = _make_checkout(
        root=tmp_path / "in-flight",
        declared="1.95.7",
        subject="chore(master): release 1.95.7",
        tags=("v1.95.5", "v1.95.6"),
    )

    assert _tag_lockstep_holds(repo_root=checkout), (
        "`release-please` lands the release commit before it creates the tag, so a clone "
        "taken in that window declares a version no tag names yet — and failing it there "
        "parks correctly merged work for the 23 seconds the window lasts"
    )


def test_a_declared_version_behind_a_newer_tag_breaks_the_lockstep(tmp_path: Path) -> None:
    """An untagged version with a NEWER tag present is drift, not an in-flight release."""
    checkout = _make_checkout(
        root=tmp_path / "lagging",
        declared="1.95.7",
        subject="chore(master): release 1.95.7",
        tags=("v1.95.6", "v1.96.0"),
    )

    assert not _tag_lockstep_holds(repo_root=checkout), (
        "a tag NEWER than the declared version proves the tag record already runs past the "
        "point `v1.95.7` should have been written into it, so its absence is the drift this "
        "record exists to catch rather than a release still in flight"
    )


def test_a_version_written_outside_a_release_commit_breaks_the_lockstep(tmp_path: Path) -> None:
    """A second writer's untagged bump is the other half of the guard."""
    checkout = _make_checkout(
        root=tmp_path / "second-writer",
        declared="1.95.7",
        subject="chore: bump the version by hand",
        tags=("v1.95.5", "v1.95.6"),
    )

    assert not _tag_lockstep_holds(repo_root=checkout), (
        "`release-please` is the only tool that writes these records, so an untagged "
        "version some other commit wrote is exactly what the in-flight admission must "
        "not cover — nothing else here would notice it"
    )


def test_a_tagless_checkout_keeps_the_lockstep(tmp_path: Path) -> None:
    """A clone carrying no tags has not told us the tag is absent."""
    checkout = _make_checkout(
        root=tmp_path / "tagless",
        declared="1.95.7",
        subject="chore(master): release 1.95.7",
        tags=(),
    )

    assert _tag_lockstep_holds(repo_root=checkout), (
        "a `git tag` list of length zero is the absence of evidence it is, and a "
        "can't-read is not a violation"
    )


def test_release_please_is_the_only_tool_positioned_to_write_the_manifest() -> None:
    """No shipped module or justfile recipe so much as names the release manifest."""
    assert (
        _SANCTIONED_NAMER.is_file()
    ), "releases are managed by `release-please`, so the workflow that runs it must ship"
    assert _MANIFEST_NAME in _SANCTIONED_NAMER.read_text(encoding="utf-8"), (
        f"the release workflow must name `{_MANIFEST_NAME}` as the manifest it maintains — "
        f"it is the ONE sanctioned writer, and a run pointed at a different file would "
        f"leave the recorded version behind the tag it cut"
    )

    namers = _manifest_namers()
    assert not namers, (
        f"`release-please` is the only tool that writes the version records, and a second "
        f"writer must first NAME the manifest — convicting it here is the cheapest point "
        f"at which lockstep can still be defended; namers={namers}"
    )
