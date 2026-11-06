"""The input model and namespace constants for one delegated gate run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["GATE_NAMESPACE", "GateRunRequest"]

# The namespace R4.S2 builds and the gate Job template already declares. Named
# here rather than passed by every caller, and still overridable per request.
GATE_NAMESPACE = "gates"


@dataclass(frozen=True, kw_only=True)
class GateRunRequest:
    """Everything one delegated gate run needs to know about the world.

    Bundled rather than spread across `run_gate`'s parameters so the seams
    (the runner and the sleeper) stay the only other arguments — what the run
    NEEDS and how it REACHES the world are different kinds of thing.

    `manifest` arrives already rendered, by `render-gate-job.sh` from the gated
    repository's own workflow. There is NO job name here: the manifest asks for
    a `metadata.generateName`, so the name is assigned by the API server at
    submit and read back off that submit's own answer.

    `gate_ref` is the mirror ref THIS RUN owns, and it is passed in rather than
    derived here for one reason: the pod fetches whatever the manifest was
    rendered with, so the ref this client pushes to and the ref the Job looks
    for have to be ONE value decided in ONE place. The caller mints it per run
    (`gate_remote_delegate`) because this client deletes the refs it created on
    its way out, and a name shared with a concurrent gate of the same tree is a
    name one run can delete while the other still needs it.

    `private_sibling_token` and `private_sibling_secret` are the ONE credential
    this request may carry, and they are deliberately separate values: the
    SECRET NAME is already inside `manifest` and is safe to print, while the
    TOKEN appears nowhere in it. Both default to empty, which is the request of
    every push whose repository names no private sibling — the overwhelming
    majority — so the token-bearing path is entered only when a mint actually
    happened rather than on every run.
    """

    repo_root: Path
    mirror_url: str
    manifest: str
    gate_ref: str
    # A commit-time replay may gate the index before it is committed.  Its
    # temporary commit is the object pushed to the mirror, while this is the
    # tree identity the manifest and verdict must retain.
    source_ref: str = "HEAD"
    # A commit-time replay owes the caller evidence of the Job's output, so it
    # reads the log instead of streaming it past this process.
    capture_output: bool = False
    tree_hash: str = ""
    private_sibling_token: str = ""
    private_sibling_secret: str = ""
    namespace: str = GATE_NAMESPACE
    poll_interval_seconds: float = 10.0
    poll_timeout_seconds: float = 3600.0
