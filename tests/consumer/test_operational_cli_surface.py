"""Consumer-tier: the `SPECIFICATION/contracts.md` §"CLI surface" operational modules.

The section's first paragraph — zero positional argv, `--help` exiting `0`, no
network I/O — is covered where a consumer meets it, at
`tests.consumer.test_cli_shape` and `tests.consumer.test_no_network_io`. What
is NOT covered anywhere else is the section's SECOND paragraph, which extends
the same semver-stable invocation contract BEYOND the check modules to three
operational CLI modules:

- `python -m livespec_dev_tooling.install_commit_refuse_hooks`,
- `python -m livespec_dev_tooling.install_worktree_pack`,
- `python -m livespec_dev_tooling.install_no_shadow_ledger`.

Two properties are asserted, and they fail independently.

**The invocation form resolves.** Each module ships inside the packaged
`livespec_dev_tooling/` directory (the section's "wheel-carried because only
the `livespec_dev_tooling/` package is packaged" clause), exposes a `main` a
bare `python -m` can call with no arguments, and carries the `__main__` guard
without which `python -m` imports the module and runs nothing. A consumer wires
these behind `just install-*` recipes that name the module and nothing else, so
any of the three breaking leaves the recipe silently doing nothing.

**Each module is the SINGLE source of its canonical body.** The section says so
of all three — "there is no second on-disk copy to drift" — and each expresses
it as a module-level string constant on its public surface. Asserted as a
non-empty exported constant per module, and then EXERCISED on the one whose
body a consumer receives by running the installer against its own declared
path: `install_no_shadow_ledger` writes bytes byte-identical to
`CANONICAL_NO_SHADOW_LEDGER_BODY`, is idempotent on a second run, and — per the
same paragraph's "the installer is a provisioning surface, not a gating check"
clause — no-ops with exit `0` rather than hard-erroring when the role key
carries a declared-absent variant.

The installer is invoked IN-PROCESS (`main()` under `monkeypatch.chdir`) rather
than by spawning a Python child, per the `tests_no_subprocess_spawn` discipline.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"
_PACKAGE = "livespec_dev_tooling"

# The `python -m` guard: without it the module imports and exits silently.
_MAIN_GUARD = '__name__ == "__main__"'

# Each operational CLI module the section enumerates, mapped to the canonical
# body constants it declares itself the single source of.
_OPERATIONAL_MODULES: dict[str, tuple[str, ...]] = {
    "install_commit_refuse_hooks": ("CANONICAL_HOOK_BODY",),
    "install_worktree_pack": (
        "CANONICAL_WORKTREE_LIB_BODY",
        "CANONICAL_BRANCH_PROTECTION_BODY",
        "CANONICAL_WORKTREE_JUST_BODY",
        "CANONICAL_BRANCH_PROTECTION_JUST_BODY",
    ),
    "install_no_shadow_ledger": ("CANONICAL_NO_SHADOW_LEDGER_BODY",),
}

# The consumer fixture's `[tool.livespec_dev_tooling]` block, with the one role
# key the exercised installer reads left for the caller to spell.
_FIXTURE_BLOCK = """\
[tool.livespec_dev_tooling]
source_trees = []
io_trees = []
commands_trees = []
covered_trees = []
supervisor_entry_files = []
dataclasses_tree = {{ not_applicable = "fixture" }}
pure_trees = {{ not_applicable = "fixture" }}
source_tree_prefixes = {{ not_applicable = "fixture" }}
target_dirs = {{ not_applicable = "fixture" }}
neutral_hook_body_path = {spelling}
"""

_DECLARED_PATH = "hooks/no_shadow_ledger.py"
_DECLARED_ABSENT = '{ not_applicable = "this consumer ships no neutral shared body" }'


def _write_consumer(*, root: Path, spelling: str) -> Path:
    """A consumer tree declaring `neutral_hook_body_path` as `spelling`."""
    root.mkdir(parents=True, exist_ok=True)
    _ = root.joinpath("pyproject.toml").write_text(
        _FIXTURE_BLOCK.format(spelling=spelling), encoding="utf-8"
    )
    return root


def _required_parameters(*, module_name: str) -> list[str]:
    """Parameter names the module's `main` would demand from a bare call."""
    entrypoint = importlib.import_module(f"{_PACKAGE}.{module_name}").main
    return [
        name
        for name, parameter in inspect.signature(entrypoint).parameters.items()
        if parameter.default is inspect.Parameter.empty
    ]


def test_each_operational_cli_module_is_invocable_and_carries_its_canonical_body() -> None:
    """The three operational modules resolve as `python -m` and own their bodies."""
    sources = {name: (_PACKAGE_DIR / f"{name}.py") for name in sorted(_OPERATIONAL_MODULES)}
    unpackaged = sorted(name for name, path in sources.items() if not path.is_file())
    assert not unpackaged, (
        f"each operational CLI module must ship inside the packaged "
        f"`livespec_dev_tooling/` directory — the wheel is what carries its canonical "
        f"body to consumers; missing={unpackaged}"
    )

    demanding = {
        name: required
        for name in sources
        for required in [_required_parameters(module_name=name)]
        if required
    }
    assert not demanding, (
        f"`python -m {_PACKAGE}.<module>` passes no arguments, so each operational "
        f"module's `main` may demand none; demanding={demanding}"
    )

    unguarded = sorted(
        name
        for name, path in sources.items()
        if _MAIN_GUARD not in path.read_text(encoding="utf-8")
    )
    assert not unguarded, (
        f"without the `{_MAIN_GUARD}` guard `python -m` imports the module and runs "
        f"nothing, so the documented invocation silently no-ops; unguarded={unguarded}"
    )

    bodies = {
        f"{name}.{constant}": getattr(importlib.import_module(f"{_PACKAGE}.{name}"), constant)
        for name, constants in _OPERATIONAL_MODULES.items()
        for constant in constants
    }
    hollow = sorted(
        key for key, body in bodies.items() if not (isinstance(body, str) and body.strip())
    )
    assert not hollow, (
        f"each installer is the SINGLE source of truth for the body it writes, carried "
        f"as a module-level string so there is no second on-disk copy to drift; "
        f"hollow={hollow}"
    )


def test_the_neutral_hook_installer_writes_its_carried_body_and_no_ops_when_declared_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installer provisions the carried body, idempotently, and never hard-errors."""
    installer = importlib.import_module(f"{_PACKAGE}.install_no_shadow_ledger")

    declared = _write_consumer(root=tmp_path / "declared", spelling=f'"{_DECLARED_PATH}"')
    monkeypatch.chdir(declared)
    first = installer.main()
    installed = declared / _DECLARED_PATH

    assert first == 0, f"the installer must exit 0 on a declared path; got {first}"
    assert installed.read_text(encoding="utf-8") == installer.CANONICAL_NO_SHADOW_LEDGER_BODY, (
        "the consumer's copy must be byte-identical to the wheel-carried constant — "
        "that identity is the whole point of a single source of truth"
    )

    second = installer.main()
    assert (second, installed.read_text(encoding="utf-8")) == (
        0,
        installer.CANONICAL_NO_SHADOW_LEDGER_BODY,
    ), "the installer must be idempotent — a second run neither fails nor rewrites"

    absent = _write_consumer(root=tmp_path / "absent", spelling=_DECLARED_ABSENT)
    monkeypatch.chdir(absent)
    skipped = installer.main()

    assert skipped == 0, (
        f"a declared-absent role key means the consumer ships no neutral shared body; "
        f"the installer is a provisioning surface, not a gating check, so it no-ops "
        f"rather than hard-erroring; got {skipped}"
    )
    assert not (absent / _DECLARED_PATH).exists(), (
        "a no-op must write nothing — provisioning a body the consumer declared it "
        "does not have would manufacture the drift the paired Verifier then reports"
    )
