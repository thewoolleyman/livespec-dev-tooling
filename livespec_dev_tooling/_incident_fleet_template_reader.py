"""The templates' serving build: the workflow templates a consumer's default-branch CI runs.

Read over the git transport from the consumer's default branch (a fresh read, never the
local clone's possibly-stale checkout, and nothing is written to the clone). The serving
build is the commit the consumer's `ci.yml` pins its dev-tooling reusable workflows to:
a tag is resolved to the commit it points at, so a moved or deleted tag never reads as
the release it names. A consumer that runs its own local workflows serves its own
default-branch commit. Mixed pins, a branch ref, an unreadable file or an unresolvable
ref leave the consumer unverified.
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

from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed  # noqa: E402
from livespec_dev_tooling.fleet._local_context import CommandRunner, command_answer  # noqa: E402
from livespec_dev_tooling.fleet._manifest_git import git_file_text  # noqa: E402
from livespec_dev_tooling.incident_fleet_host import FLEET_OWNER, HostProbe  # noqa: E402

__all__: list[str] = ["read_templates"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_TEMPLATE_REPOSITORY = "livespec-dev-tooling"
_WORKFLOW = "ci.yml"
_COMMIT = re.compile(r"[0-9a-f]{40}")
_LS_REMOTE_FIELDS = 2
_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*[\"']?(?P<target>[^\s\"'#]+)", re.MULTILINE)


def _remote_commit(*, run: CommandRunner, repo: str, ref: str) -> str | None:
    """The commit `ref` names on the remote; an annotated tag is read through to its commit."""
    url = f"https://github.com/{FLEET_OWNER}/{repo}.git"
    answer = command_answer(outcome=run(args=["git", "ls-remote", url, ref, f"{ref}^{{}}"]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    rows = {
        fields[1]: fields[0]
        for line in answer.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }
    commit = rows.get(f"{ref}^{{}}") or rows.get(ref)
    return commit if commit and _COMMIT.fullmatch(commit) else None


def read_templates(*, probe: HostProbe, repository: str) -> str | None:
    """`<repo>@<commit>` of the templates the consumer's CI is pinned to, else None."""
    name = repository.rsplit("/", 1)[-1]
    read = git_file_text(
        run=probe.run, owner=FLEET_OWNER, repo=name, path=f".github/workflows/{_WORKFLOW}"
    )
    if isinstance(read, IOFailure):
        return None
    prefix = f"{FLEET_OWNER}/{_TEMPLATE_REPOSITORY}/.github/workflows/"
    targets = [m["target"] for m in _USES.finditer(unsafe_perform_io(read.unwrap()))]
    refs = {t.rsplit("@", 1)[1] for t in targets if t.startswith(prefix) and "@" in t}
    if len(refs) > 1:
        return None
    if refs:
        ref = next(iter(refs))
        commit = (
            ref
            if _COMMIT.fullmatch(ref)
            else _remote_commit(
                run=probe.run,
                repo=_TEMPLATE_REPOSITORY,
                ref=f"refs/tags/{ref}",
            )
        )
        return None if commit is None else f"{_TEMPLATE_REPOSITORY}@{commit}"
    if any(t.startswith("./.github/") for t in targets):
        commit = _remote_commit(run=probe.run, repo=name, ref="HEAD")
        return None if commit is None else f"{name}@{commit}"
    return None
