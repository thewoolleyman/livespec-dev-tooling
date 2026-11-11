"""The templates' serving build: the dev-tooling templates a consumer's default-branch CI runs.

Read over the git transport from the consumer's default branch (a fresh read, never the
local clone's possibly-stale checkout, and nothing is written to the clone). Every
workflow file under `.github/workflows/` is read, because the fleet's pins are spread
across them: `ci.yml` pins this library's composite actions, and the release-dispatch,
pin-freshness and bump-pin workflows pin its reusable workflows. The serving build is
the one commit those pins (`.github/workflows/...@ref` and `.github/actions/...@ref`)
name: a tag is resolved to the commit it points at, so a moved or deleted tag never
reads as the release it names. A consumer that runs its own local workflows serves its
own default-branch commit, keyed to a release because a committed claim can never name
the commit that contains it: the newest release tag that is an ancestor of that commit,
read in the consumer's clone on this host, and served to each row only while every file
of that row's surface is byte-identical to the release's (`_incident_fleet_release_keyed`).
Pins that disagree, a branch ref, an unreadable file or an unresolvable ref leave the
consumer unverified.

This library is the exception to pins-first. Its own `ci.yml` runs its templates
locally (`./.github/...`) at the audited revision, and those serve its CI surfaces; its
release-lane workflows pin older releases of itself. So when this library runs local
workflows, its serving templates are its own default-branch commit, release-keyed as
above, whatever its self-pins say.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_fleet_clones import consumer_clone  # noqa: E402
from livespec_dev_tooling._incident_fleet_release_keyed import (  # noqa: E402
    ServingReading,
    release_keyed_reading,
    remote_commit,
)
from livespec_dev_tooling.fleet._manifest_git import git_directory_texts  # noqa: E402
from livespec_dev_tooling.incident_fleet_host import FLEET_OWNER, HostProbe  # noqa: E402

__all__: list[str] = ["read_templates"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_TEMPLATE_REPOSITORY = "livespec-dev-tooling"
_WORKFLOWS = ".github/workflows"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")
_TEMPLATE_PREFIX = f"{FLEET_OWNER}/{_TEMPLATE_REPOSITORY}/.github/"
_COMMIT = re.compile(r"[0-9a-f]{40}")
_CAPABILITY = "templates"
_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*[\"']?(?P<target>[^\s\"'#]+)", re.MULTILINE)


def _own_head(*, probe: HostProbe, repository: str) -> ServingReading | None:
    """The consumer's own default branch, release-keyed: it runs its local templates."""
    name = repository.rsplit("/", 1)[-1]
    commit = remote_commit(run=probe.run, repo=name, ref="HEAD")
    if commit is None:
        return None
    clone = consumer_clone(probe=probe, repository=repository)
    if clone is None:
        return ServingReading(build="", detail=f"no clone of {name} on this host", head=commit)
    return release_keyed_reading(
        run=probe.run, clone=clone, repo=name, head=commit, capability=_CAPABILITY
    )


def read_templates(*, probe: HostProbe, repository: str) -> str | ServingReading | None:
    """`<repo>@<commit>` of the templates the consumer's workflows are pinned to, else None.

    A consumer running its own local workflows is read as a release-keyed `ServingReading`.
    """
    name = repository.rsplit("/", 1)[-1]
    read = git_directory_texts(
        run=probe.run,
        owner=FLEET_OWNER,
        repo=name,
        directory=_WORKFLOWS,
        suffixes=_WORKFLOW_SUFFIXES,
    )
    if isinstance(read, IOFailure):
        return None
    targets = [
        m["target"] for text in unsafe_perform_io(read.unwrap()) for m in _USES.finditer(text)
    ]
    local = any(t.startswith("./.github/") for t in targets)
    if name == _TEMPLATE_REPOSITORY and local:
        return _own_head(probe=probe, repository=repository)
    refs = {t.rsplit("@", 1)[1] for t in targets if t.startswith(_TEMPLATE_PREFIX) and "@" in t}
    if len(refs) > 1:
        return None
    if refs:
        ref = next(iter(refs))
        commit = (
            ref
            if _COMMIT.fullmatch(ref)
            else remote_commit(
                run=probe.run,
                repo=_TEMPLATE_REPOSITORY,
                ref=f"refs/tags/{ref}",
            )
        )
        return None if commit is None else f"{_TEMPLATE_REPOSITORY}@{commit}"
    return _own_head(probe=probe, repository=repository) if local else None
