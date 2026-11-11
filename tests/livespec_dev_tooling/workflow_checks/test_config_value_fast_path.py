"""Mirror coverage for the config-value commit-hook workflow check."""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest
import tomli

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "workflow_checks"
    / "config_value_fast_path.py"
)


def _subject() -> object:
    """Import the new workflow check only after proving its source exists."""
    assert _MODULE_PATH.is_file(), "the config-value fast-path workflow check must ship"
    return importlib.import_module("livespec_dev_tooling.workflow_checks.config_value_fast_path")


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run one fixture repository command."""
    _ = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write(*, root: Path, path: str, text: str) -> None:
    """Write a fixture path, creating its parent directories."""
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _repository(*, tmp_path: Path) -> Path:
    """Create a committed fixture repository with each qualifying file shape."""
    root = tmp_path / "repo"
    root.mkdir()
    _write(
        root=root,
        path=".livespec.jsonc",
        text='{"dispatcher": {\n  "wip_cap": 4\n},\n"stall_timeout_seconds": 60\n}\n',
    )
    _write(root=root, path="ansible/inventory/host_vars/node.yml", text="max_concurrent_runs: 2\n")
    _write(
        root=root,
        path="ci-runner/k3s/phase0-bare-metal/profiles/test.env",
        text="ADMISSION_CAPACITY_C=2\n",
    )
    _write(
        root=root,
        path="ci-runner/k3s/phase0-bare-metal/profile.sh",
        text='profile_load() { test -n "$(grep "^ADMISSION_CAPACITY_C=[1-9]" "$1")"; }\n',
    )
    _git(cwd=root, args=["init", "--quiet", "-b", "master"])
    _git(cwd=root, args=["add", "."])
    _git(cwd=root, args=["commit", "--quiet", "-m", "base"])
    return root


def test_the_workflow_check_declares_the_required_capacity_keys() -> None:
    """The shared list remains the one declaration used by the hook classifier."""
    subject = _subject()
    assert {rule.key_path for rule in subject.CONFIG_VALUE_FAST_PATH_RULES} >= {
        "ADMISSION_CAPACITY_C",
        "dispatcher.wip_cap",
        "max_concurrent_runs",
        "stall_timeout_seconds",
    }


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (".livespec.jsonc", '"wip_cap": 4', '"wip_cap": 6'),
        (
            "ansible/inventory/host_vars/node.yml",
            "max_concurrent_runs: 2",
            "max_concurrent_runs: 3",
        ),
        (
            "ci-runner/k3s/phase0-bare-metal/profiles/test.env",
            "ADMISSION_CAPACITY_C=2",
            "ADMISSION_CAPACITY_C=3",
        ),
    ],
)
def test_declared_value_replacements_qualify_in_every_supported_format(
    *, tmp_path: Path, path: str, before: str, after: str
) -> None:
    """A complete declared value-line replacement is the only qualifying diff."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    target = root / path
    _ = target.write_text(
        target.read_text(encoding="utf-8").replace(before, after), encoding="utf-8"
    )
    _git(cwd=root, args=["add", path])
    assert subject.is_config_value_fast_path(cwd=root) is True
    assert subject.validate_config_value_fast_path(cwd=root) == ()


def test_classifier_rejects_empty_binary_added_removed_and_comment_diffs(*, tmp_path: Path) -> None:
    """Everything other than paired declared value lines retains ordinary pre-commit."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    assert subject.is_config_value_fast_path(cwd=root) is False
    target = root / ".livespec.jsonc"
    _ = target.write_text(
        target.read_text(encoding="utf-8").replace('"wip_cap": 4', '"wip_cap": 6\n"new": 1'),
        encoding="utf-8",
    )
    _git(cwd=root, args=["add", ".livespec.jsonc"])
    assert subject.is_config_value_fast_path(cwd=root) is False
    _git(cwd=root, args=["reset", "--hard", "HEAD"])
    _write(root=root, path="blob.bin", text="\x00changed")
    _git(cwd=root, args=["add", "blob.bin"])
    assert subject.is_config_value_fast_path(cwd=root) is False


def test_jsonc_classifier_requires_the_declared_dotted_key_path(*, tmp_path: Path) -> None:
    """A similarly named value outside `dispatcher` retains normal pre-commit."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    config = root / ".livespec.jsonc"
    _ = config.write_text(
        config.read_text(encoding="utf-8").replace(
            '"stall_timeout_seconds": 60',
            '"stall_timeout_seconds": 60,\n"decoy": {"wip_cap": 4}',
        ),
        encoding="utf-8",
    )
    _git(cwd=root, args=["add", ".livespec.jsonc"])
    _git(cwd=root, args=["commit", "--quiet", "-m", "decoy"])
    _ = config.write_text(
        config.read_text(encoding="utf-8").replace('"wip_cap": 4}', '"wip_cap": 6}'),
        encoding="utf-8",
    )
    _git(cwd=root, args=["add", ".livespec.jsonc"])
    assert subject.is_config_value_fast_path(cwd=root) is False


def test_classifier_helpers_refuse_unreadable_or_ambiguous_staged_data(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Defensive index reads fall back to the ordinary pre-commit aggregate."""
    subject = _subject()
    diff = '@@ -1 +1 @@\n-"wip_cap": 4\n+"wip_cap": 6\n'

    def configure(
        *,
        before: str,
        after: str,
        before_returncode: int = 0,
        diff_text: str = diff,
    ) -> None:
        def staged_git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            _ = cwd
            if args[:3] == ["diff", "--cached", "--name-only"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=".livespec.jsonc\n"
                )
            if args[0] == "diff":
                return subprocess.CompletedProcess(args=[], returncode=0, stdout=diff_text)
            is_before = args[1].startswith("HEAD:")
            text = before if is_before else after
            return subprocess.CompletedProcess(
                args=[], returncode=before_returncode if is_before else 0, stdout=text
            )

        monkeypatch.setattr(subject, "_git", staged_git)

    valid = '{"harnesses": {"dispatcher": {"wip_cap": 4}}}'
    configure(before=valid, after="{")
    assert subject.is_config_value_fast_path(cwd=tmp_path) is False
    configure(before=valid, after=valid, before_returncode=1)
    assert subject.is_config_value_fast_path(cwd=tmp_path) is False
    configure(before="[]", after="[]")
    assert subject.is_config_value_fast_path(cwd=tmp_path) is False
    configure(
        before='{"harnesses": {"not_dispatcher": 4}}',
        after='{"harnesses": {"not_dispatcher": 6}}',
    )
    assert subject.is_config_value_fast_path(cwd=tmp_path) is False
    configure(before=valid, after=valid, diff_text="@@ -1 +1 @@\n-old")
    assert subject.is_config_value_fast_path(cwd=tmp_path) is False
    configure(
        before=valid,
        after=valid,
        diff_text="@@ -1 +1 @@\n-old\n@@ -3 +3 @@\n+new\n",
    )
    assert subject.is_config_value_fast_path(cwd=tmp_path) is False


def test_yaml_config_values_inside_lists_remain_schema_valid(*, tmp_path: Path) -> None:
    """Nested values in configuration lists remain available to schema validation."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    path = "ansible/inventory/host_vars/node.yml"
    _write(root=root, path=path, text="- max_concurrent_runs: 3\n")
    _git(cwd=root, args=["add", path])
    assert subject.validate_config_value_fast_path(cwd=root) == ()


def test_profile_validation_reads_the_staged_version_not_an_unstaged_worktree_edit(
    *, tmp_path: Path
) -> None:
    """The validation lane judges the exact profile that the commit would contain."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    path = "ci-runner/k3s/phase0-bare-metal/profiles/test.env"
    _write(root=root, path=path, text="ADMISSION_CAPACITY_C=3\n")
    _git(cwd=root, args=["add", path])
    _write(root=root, path=path, text="ADMISSION_CAPACITY_C=not-staged\n")
    assert subject.validate_config_value_fast_path(cwd=root) == ()


def test_profile_validation_passes_a_real_staged_profile_to_its_authoritative_parser(
    *, tmp_path: Path
) -> None:
    """A valid real profile needs a file path, not a stdin pipe, for parsing."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    source_root = _MODULE_PATH.parents[2]
    parser_path = "ci-runner/k3s/phase0-bare-metal/profile.sh"
    profile_path = "ci-runner/k3s/phase0-bare-metal/profiles/poweredge-xubuntu.env"
    _write(
        root=root,
        path=parser_path,
        text=(source_root / parser_path).read_text(encoding="utf-8"),
    )
    _write(
        root=root,
        path=profile_path,
        text=(source_root / profile_path).read_text(encoding="utf-8"),
    )
    _git(cwd=root, args=["add", "."])
    _git(cwd=root, args=["commit", "--quiet", "-m", "real profile"])
    profile = root / profile_path
    _ = profile.write_text(
        profile.read_text(encoding="utf-8").replace(
            "ADMISSION_CAPACITY_C=17", "ADMISSION_CAPACITY_C=16"
        ),
        encoding="utf-8",
    )
    _git(cwd=root, args=["add", profile_path])
    assert subject.validate_config_value_fast_path(cwd=root) == ()


def test_invalid_jsonc_yaml_and_profile_values_name_the_affected_rule(*, tmp_path: Path) -> None:
    """Validation preserves file/key diagnostics for every authoritative parser."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    _write(root=root, path=".livespec.jsonc", text="{")
    _write(root=root, path="ansible/inventory/host_vars/node.yml", text="[")
    _write(
        root=root,
        path="ci-runner/k3s/phase0-bare-metal/profiles/test.env",
        text="ADMISSION_CAPACITY_C=0\n",
    )
    _git(cwd=root, args=["add", "."])
    failures = subject.validate_config_value_fast_path(cwd=root)
    assert {(failure.path, failure.key_path) for failure in failures} >= {
        (".livespec.jsonc", "dispatcher.wip_cap"),
        ("ansible/inventory/host_vars/node.yml", "max_concurrent_runs"),
        ("ci-runner/k3s/phase0-bare-metal/profiles/test.env", "ADMISSION_CAPACITY_C"),
    }


@pytest.mark.parametrize("value", ["1e2", "1.5", "[1, 2]", '{"n": 1}'])
def test_any_value_only_replacement_on_a_listed_key_is_refused_by_validation_not_skipped(
    *, tmp_path: Path, value: str
) -> None:
    """A float, exponent, or compound value still qualifies, so validation names the file and key."""
    subject = _subject()
    root = _repository(tmp_path=tmp_path)
    target = root / ".livespec.jsonc"
    _ = target.write_text(
        target.read_text(encoding="utf-8").replace('"wip_cap": 4', f'"wip_cap": {value}'),
        encoding="utf-8",
    )
    _git(cwd=root, args=["add", ".livespec.jsonc"])
    assert subject.is_config_value_fast_path(cwd=root) is True
    failures = subject.validate_config_value_fast_path(cwd=root)
    assert {(failure.path, failure.key_path) for failure in failures} == {
        (".livespec.jsonc", "dispatcher.wip_cap")
    }


def test_the_python_311_tomllib_import_path_loads_the_same_public_rules(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newer consumers use the standard-library TOML reader."""
    subject = _subject()
    module_path = Path(subject.__file__)
    spec = importlib.util.spec_from_file_location("config_value_fast_path_tomllib", module_path)
    assert spec is not None
    assert spec.loader is not None
    fake_tomllib = types.ModuleType("tomllib")
    _ = setattr(fake_tomllib, "loads", tomli.loads)
    monkeypatch.setitem(sys.modules, "tomllib", fake_tomllib)
    monkeypatch.setattr(sys, "version_info", (3, 11))
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    try:
        spec.loader.exec_module(loaded)
    finally:
        del sys.modules[spec.name]
    assert {rule.key_path for rule in loaded.CONFIG_VALUE_FAST_PATH_RULES} == {
        rule.key_path for rule in subject.CONFIG_VALUE_FAST_PATH_RULES
    }
