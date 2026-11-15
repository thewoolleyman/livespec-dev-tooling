"""The controller admits only a recent default-branch advance beyond an armed base."""

from __future__ import annotations

import os
import subprocess

import pytest

from livespec_dev_tooling import incident_expedited_base as module


def _commit(*, root, message: str, timestamp: int) -> str:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_AUTHOR_DATE": f"{timestamp} +0000",
        "GIT_COMMITTER_DATE": f"{timestamp} +0000",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    _ = subprocess.run(
        ["git", "-C", str(root), "commit", "--quiet", "--allow-empty", "-m", message],
        check=True,
        env=environment,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    ).stdout.strip()


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "reference"
    _ = subprocess.run(["git", "init", "--quiet", "--initial-branch=master", str(root)], check=True)
    initial = _commit(root=root, message="initial", timestamp=1_700_000_000)
    genesis = _commit(root=root, message="genesis", timestamp=1_700_000_060)
    event = _commit(root=root, message="event", timestamp=1_700_000_180)
    return root, initial, genesis, event


def test_recent_ancestor_is_admitted(history):
    root, _, genesis, event = history
    assert (
        module.base_freshness_refusal(
            root=root,
            genesis_base=genesis,
            event_base=event,
            max_commits=1,
            max_minutes=2,
        )
        is None
    )


@pytest.mark.parametrize(
    ("genesis", "event", "commits", "minutes", "named"),
    [
        ("x" * 40, "a" * 40, 1, 1, "controller freshness configuration is invalid"),
        ("event", "initial", 2, 3, "genesis base is not an ancestor"),
        ("genesis", "event", 0, 0, "commits 1>0, minutes 2>0"),
    ],
)
def test_invalid_nonancestor_and_stale_bases_name_the_held_event_and_bound(
    history, genesis, event, commits, minutes, named
):
    root, initial, actual_genesis, actual_event = history
    values = {"initial": initial, "genesis": actual_genesis, "event": actual_event}
    held = values.get(genesis, genesis)
    current = values.get(event, event)
    refusal = module.base_freshness_refusal(
        root=root,
        genesis_base=held,
        event_base=current,
        max_commits=commits,
        max_minutes=minutes,
    )
    assert refusal is not None
    assert "genesis base " + held in refusal
    assert "event base " + current in refusal
    assert "bound exceeded: " + named in refusal


def test_unreadable_object_view_refuses_with_a_named_freshness_failure(history, monkeypatch):
    root, _, genesis, event = history

    def unavailable(**_kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(module.IsolatedGit, "view", unavailable)
    assert module.base_freshness_refusal(
        root=root,
        genesis_base=genesis,
        event_base=event,
        max_commits=1,
        max_minutes=2,
    ).endswith("bound exceeded: ancestry or freshness could not be determined")
