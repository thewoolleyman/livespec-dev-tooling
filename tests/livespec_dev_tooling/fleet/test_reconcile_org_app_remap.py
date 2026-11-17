"""Pin the org-App remap that `_reconcile.py`'s unsuffixed source names rely on.

`livespec_dev_tooling/fleet/_reconcile.py` reads the UNSUFFIXED
`GITHUB_APP_ID` / `GITHUB_PRIVATE_KEY`, which the bare credential wrapper
projects as the personal fleet App 3668528. For this repository that is not
what a configured-wrapper run uses: `.livespec.jsonc`'s `credential_wrapper`
ends in a `/bin/sh` hop that rebinds the unsuffixed pair from
`GITHUB_APP_ID_ORG` / `GITHUB_PRIVATE_KEY_ORG`, the org App 5761962
(stale-base-merge-options note 009). Work-item livespec-dev-tooling-kn5n3a.

The remap lives in a config file, not in the code that depends on it, so an
edit to either side would silently put the reconcile back on the personal App.
This module runs the committed hop for real (everything after the wrapper's
`--`; the 1Password wrapper itself is not needed for the rebinding) and feeds
what it produced into `reconcile_secret_names`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

import jsoncomment
from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowPass,
)
from livespec_dev_tooling.fleet._reconcile import reconcile_secret_names

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG = _REPO_ROOT / ".livespec.jsonc"
_WRAPPER = "/usr/local/bin/with-livespec-env.sh"

_ORG_ID = "5761962"
_ORG_KEY = "org-app-key"
_PERSONAL_ID = "3668528"
_PERSONAL_KEY = "personal-app-key"


def _committed_hop() -> list[str]:
    """The committed credential_wrapper argv after the 1Password wrapper's `--`."""
    config = cast("dict[str, object]", jsoncomment.JsonComment().loads(_CONFIG.read_text("utf-8")))
    wrapper = cast("list[str]", config["credential_wrapper"])
    assert wrapper[:2] == [_WRAPPER, "--"]
    return wrapper[2:]


def _through_hop() -> tuple[str, str]:
    """The unsuffixed pair a command sees when run through the committed hop."""
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GITHUB_APP_ID": _PERSONAL_ID,
        "GITHUB_PRIVATE_KEY": _PERSONAL_KEY,
        "GITHUB_APP_ID_ORG": _ORG_ID,
        "GITHUB_PRIVATE_KEY_ORG": _ORG_KEY,
    }
    probe = ["/bin/sh", "-c", 'printf "%s\\n%s" "$GITHUB_APP_ID" "$GITHUB_PRIVATE_KEY"']
    completed = subprocess.run(
        [*_committed_hop(), *probe],
        capture_output=True,
        check=True,
        env=environment,
        text=True,
    )
    app_id, private_key = completed.stdout.split("\n")
    return app_id, private_key


def test_the_committed_hop_rebinds_the_unsuffixed_pair_to_the_org_app() -> None:
    assert _through_hop() == (_ORG_ID, _ORG_KEY)


def test_reconcile_pushes_the_org_app_when_run_through_the_committed_hop(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_id, private_key = _through_hop()
    monkeypatch.setenv("GITHUB_APP_ID", app_id)
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", private_key)
    stdins: list[str | None] = []

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        _ = args
        stdins.append(stdin)
        return GhResult(returncode=0, stdout="{}", stderr="")

    runner: GhRunner = run
    ctx = FleetContext(owner="acme", run_gh=lift_gh(runner))
    member = FleetMember(repo="widget", repo_class="impl-plugin")
    outcome = reconcile_secret_names(ctx=ctx, member=member)
    assert isinstance(outcome, RowPass)
    assert stdins == [_ORG_ID, _ORG_KEY]
