"""The single protected-path ownership check and the callers that must share it."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_protected_path as protected
from livespec_dev_tooling import incident_recovery_app as app

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xhb7pj

_DUPLICATES = (
    ("incident_controller_installation", "_protected"),
    ("incident_ci_identity_policy", "protected_identity_path"),
    ("incident_repository_fence", "_protected_directory"),
    ("_incident_recovery_journal_io", "_protected"),
    ("incident_recovery_app", "_protected_file"),
    ("_incident_recovery_publication", "_private"),
)


def _tree(tmp_path: Path) -> Path:
    outer = tmp_path / "outer"
    outer.mkdir(mode=0o700)
    inner = outer / "inner"
    inner.mkdir(mode=0o700)
    target = inner / "item"
    target.write_text("{}")
    target.chmod(0o600)
    return target


def test_a_private_chain_is_protected_and_relative_or_missing_paths_are_not(tmp_path):
    target = _tree(tmp_path)
    assert protected.protected_path(path=target)
    assert not protected.protected_path(path=Path("relative"))
    assert not protected.protected_path(path=tmp_path / "missing")


@pytest.mark.parametrize("mode", [0o770, 0o707, 0o777])
def test_any_ancestor_writable_by_another_user_refuses_the_path(tmp_path, mode):
    target = _tree(tmp_path)
    target.parent.parent.chmod(mode)
    try:
        assert not protected.protected_path(path=target)
    finally:
        target.parent.parent.chmod(0o700)


def test_a_symlink_cycle_is_refused_not_raised(tmp_path):
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    assert not protected.protected_path(path=loop)


def test_a_foreign_owned_entry_refuses_the_path(tmp_path, monkeypatch):
    target = _tree(tmp_path)
    original = Path.lstat

    def foreign(path, *args, **kwargs):
        values = list(original(path, *args, **kwargs))
        values[4] = os.geteuid() + 100 if path == target else values[4]
        return os.stat_result(values)

    monkeypatch.setattr(Path, "lstat", foreign)
    assert not protected.protected_path(path=target)


def test_the_app_key_is_refused_when_any_ancestor_is_writable_by_another_user(tmp_path):
    target = _tree(tmp_path)
    unprotected = "recovery-app-credential-unprotected"
    before = app.RecoveryAppCredential.load(path=target)
    assert isinstance(before, app.AppRefusal)
    assert before.code != unprotected
    target.parent.parent.chmod(0o770)
    try:
        after = app.RecoveryAppCredential.load(path=target)
    finally:
        target.parent.parent.chmod(0o700)
    assert isinstance(after, app.AppRefusal)
    assert after.code == unprotected


def test_no_incident_path_keeps_its_own_ancestor_walk():
    root = Path(protected.__file__).parent
    walkers = [
        f"{module}.{name}"
        for module, name in _DUPLICATES
        if re.search(r"\.parents\b", (root / f"{module}.py").read_text())
    ]
    assert walkers == [], f"re-implemented ancestor walks remain: {walkers}"
