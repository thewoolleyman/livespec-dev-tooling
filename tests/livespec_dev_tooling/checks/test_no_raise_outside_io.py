"""Outside-in test for `dev-tooling/checks/no_raise_outside_io.py` — domain-error raises confined to io/+errors.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-raise-outside-io` row), raising a
domain error at runtime is restricted to the consumer's declared
`io_trees` and the `errors.py` beside them. Anywhere else,
raising a domain error is banned — pure layers return
`Failure(SomeError(...))` on the ROP railway. Raising bug-class
exceptions (TypeError, NotImplementedError, AssertionError, etc.)
is permitted anywhere.

The domain-error name set is DERIVED FROM THE CONSUMING REPO —
the exception classes its own first-party package defines — not
read from a hardcoded list of livespec-core's four class names.
A consumer whose errors are named `WidgetError` is checked
exactly as one whose errors are named `ValidationError`; a name
the repo does not define is not the repo's domain error and is
not flagged.

Detection lands at a WARN TIER: findings are reported at warning
severity and the check exits 0 unless
`LIVESPEC_FAIL_IF_DOMAIN_ERROR_RAISES_EXIST` is set, which
promotes them to error severity and exit 1. The tests therefore
come in pairs — what is REPORTED by default, and what FAILS
under the promotion lever.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_RAISE_OUTSIDE_IO = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_raise_outside_io.py"
_PROMOTE_ENV_VAR = "LIVESPEC_FAIL_IF_DOMAIN_ERROR_RAISES_EXIST"

_LEGACY_PACKAGE = Path(".claude-plugin") / "scripts" / "livespec"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ)."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it.

    The check derives its universe from the git INDEX, so a fixture that is
    not a git repo has no universe at all, and an untracked file is invisible.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _run(*, cwd: Path, promote: bool = False) -> subprocess.CompletedProcess[str]:
    """`git init` + stage the fixture, then run the check as a consumer would.

    `promote=True` sets the severity lever, so warn-tier findings become
    error-tier failures — the shape CI will use once the fleet is clean.
    """
    _init_repo_with_files(tmp_path=cwd)
    env = {**os.environ, _PROMOTE_ENV_VAR: "true"} if promote else None
    return subprocess.run(
        [sys.executable, str(_NO_RAISE_OUTSIDE_IO)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _write(*, path: Path, body: str) -> None:
    """Write a module body under `path`, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n\n" + body,
        encoding="utf-8",
    )


def _write_errors_module(*, tmp_path: Path, names: tuple[str, ...]) -> None:
    """Define `names` as first-party exception classes in the package's `errors.py`.

    The derivation reads the consumer's OWN class definitions, so a fixture
    that raises a domain error must also define it — exactly as a real
    consumer repo does.
    """
    body = "\n\n".join(f'class {name}(Exception):\n    """A domain error."""' for name in names)
    _write(path=tmp_path / _LEGACY_PACKAGE / "errors.py", body=body + "\n")


def test_no_raise_outside_io_rejects_domain_error_raise_in_pure_layer(*, tmp_path: Path) -> None:
    """A `raise ValidationError(...)` inside `livespec/parse/foo.py` fails the check.

    Fixture: a parse-layer module raises a domain error the package itself
    defines in `errors.py` (banned — pure layers return Failure(...) on the
    railway). The check must walk livespec/, parse the file, detect the
    domain-error raise, and under the promotion lever exit non-zero and
    surface the file path plus line number.
    """
    _write_errors_module(tmp_path=tmp_path, names=("ValidationError",))
    _write(
        path=tmp_path / _LEGACY_PACKAGE / "parse" / "foo.py",
        body='def parse_thing() -> None:\n    raise ValidationError("malformed")\n',
    )

    result = _run(cwd=tmp_path, promote=True)

    assert result.returncode != 0, (
        f"no_raise_outside_io should reject ValidationError raise in parse/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/parse/foo.py"
    assert expected_path in combined, (
        f"no_raise_outside_io diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_domain_error_raise_in_io_layer(*, tmp_path: Path) -> None:
    """A `raise PreconditionError(...)` inside `livespec/io/fs.py` passes (exit 0).

    Pass-case: the io/ layer is the side-effect boundary that
    legitimately raises domain errors (the impure_safe
    decorator lifts them onto the IOResult railway via
    @impure_safe(exceptions=(PreconditionError,)).
    """
    _write_errors_module(tmp_path=tmp_path, names=("PreconditionError",))
    _write(
        path=tmp_path / _LEGACY_PACKAGE / "io" / "fs.py",
        body='def read_text() -> None:\n    raise PreconditionError("missing")\n',
    )

    result = _run(cwd=tmp_path, promote=True)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept domain-error raise in io/ with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_domain_error_raise_in_errors_module(*, tmp_path: Path) -> None:
    """A `raise LivespecError(...)` inside `livespec/errors.py` passes (exit 0).

    Pass-case: errors.py is the hierarchy definition module
    and is exempt by spec.
    """
    _write(
        path=tmp_path / _LEGACY_PACKAGE / "errors.py",
        body=(
            'class LivespecError(Exception):\n    """A domain error."""\n'
            "\n\n"
            'def raise_test() -> None:\n    raise LivespecError("test")\n'
        ),
    )

    result = _run(cwd=tmp_path, promote=True)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept domain-error raise in errors.py with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_bug_class_raise_in_pure_layer(*, tmp_path: Path) -> None:
    """A `raise NotImplementedError(...)` (bug-class) in pure layer passes (exit 0).

    Pass-case: bug-class exceptions (TypeError, ValueError,
    NotImplementedError, AssertionError, etc.) are permitted
    anywhere — they propagate to the supervisor's bug-catcher.
    They are stdlib builtins, not classes the consumer defines,
    so the derived domain-error set never contains them.
    """
    _write(
        path=tmp_path / _LEGACY_PACKAGE / "parse" / "foo.py",
        body=(
            'def parse_thing() -> None:\n    raise NotImplementedError("not yet")\n'
            "\n\n"
            "def reraise() -> None:\n"
            "    try:\n"
            "        parse_thing()\n"
            "    except NotImplementedError:\n"
            "        raise\n"
        ),
    )

    result = _run(cwd=tmp_path, promote=True)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept bug-class raise with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_a_codeless_repo(*, tmp_path: Path) -> None:
    """A genuinely codeless repo (0 tracked first-party `.py`) passes with exit 0.

    Replaces a test that asserted a declared source tree containing no Python
    is a misdeclaration. That was the `source_trees_exit_code` role-key gate,
    which this check no longer consults — the universe comes from the git
    index now, so "declared a tree with nothing in it" is not a state this
    check can observe.

    What replaces it is the distinction that still matters and is easy to get
    wrong: an EMPTY universe must be a PASS, not a configuration error. It is
    the one exemption the railway clause grants — a governed repo with zero
    first-party Python — and `livespec-console-beads-fabro` is the verified
    fleet case. Failing closed here would redden a conforming repo.
    """
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run(cwd=tmp_path, promote=True)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_raise_outside_io_for_import_test",
        str(_NO_RAISE_OUTSIDE_IO),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_no_raise_outside_io_covers_a_tracked_file_with_source_trees_declared_empty(
    *, tmp_path: Path
) -> None:
    """`source_trees = []` must NOT mean "scan nothing" — the scope dodge is closed.

    This is the invariant `livespec-dev-tooling-i532` exists for. Under the
    allowlist universe a repo could disarm the Result-railway checks over its
    whole package by declaring one empty array, and the declaration read as
    conformance: `source_trees_exit_code` treated declared-empty as a
    sanctioned opt-out and returned 0 before inspecting anything.

    A git-derived universe removes the lever entirely. The file below is
    tracked and first-party, so it is covered, and NO declaration names it —
    which is the other half of the acceptance: a newly-tracked first-party
    `.py` is covered the moment it is tracked, with nothing to declare and
    nothing to forget.

    `io_trees` is deliberately still declared here and still empty: it remains
    a genuine architectural role key, and declaring it empty must go on meaning
    "nothing is wholesale exempt", never "inspect nothing".
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" "source_trees = []\n" "io_trees = []\n",
        encoding="utf-8",
    )
    _write(
        path=tmp_path / "pkg" / "undeclared.py",
        body=(
            'class ValidationError(Exception):\n    """A domain error."""\n'
            "\n\n"
            'def parse_thing() -> None:\n    raise ValidationError("malformed")\n'
        ),
    )
    _init_repo_with_files(tmp_path=tmp_path)

    result = _run(cwd=tmp_path, promote=True)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"no_raise_outside_io must inspect a tracked first-party file even with "
        f"`source_trees = []`; got returncode={result.returncode} combined={combined!r}"
    )
    assert (
        "pkg/undeclared.py" in combined
    ), f"the diagnostic must name the undeclared-but-tracked offender; combined={combined!r}"


def test_no_raise_outside_io_flags_a_consumer_defined_error_name(*, tmp_path: Path) -> None:
    """A raise of the CONSUMER's own error class is flagged, at warn tier, exit 0.

    The defect this pins (`livespec-dev-tooling-6vz`): the domain-error name
    set was hardcoded to livespec-core's four class names, so every consumer
    whose errors are named anything else — `livespec-orchestrator-git-jsonl`'s
    `MalformedRecordLineError`, `livespec-runtime`'s `CrossRepoSchemaError`,
    `livespec-orchestrator-beads-fabro`'s nineteen — got a check that
    inspected every file and could never report a single offense. A vacuous
    gate is indistinguishable from a passing one, which is why review, not
    CI, found it.

    `WidgetError` is in NO hardcoded list anywhere. It is flagged because the
    fixture package DEFINES it, which is the whole point: the set follows the
    consumer, not livespec-core.

    Warn tier is the landing severity (see the module docstring), so the
    finding is REPORTED and the exit code stays 0 — the promotion pair is
    `test_..._promotes_consumer_defined_error_findings_under_the_lever`.
    """
    _write(
        path=tmp_path / "pkg" / "errors.py",
        body='class WidgetError(Exception):\n    """A consumer-defined domain error."""\n',
    )
    _write(
        path=tmp_path / "pkg" / "service.py",
        body=(
            "from pkg.errors import WidgetError\n"
            "\n\n"
            'def do_thing() -> None:\n    raise WidgetError("nope")\n'
        ),
    )

    result = _run(cwd=tmp_path)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"warn tier must not fail the run; got returncode={result.returncode} "
        f"combined={combined!r}"
    )
    assert "WidgetError" in combined, (
        f"the check must flag a raise of the CONSUMER's own error class, not only "
        f"livespec-core's hardcoded four; combined={combined!r}"
    )
    assert (
        "pkg/service.py" in combined
    ), f"the diagnostic must name the offending file; combined={combined!r}"
    assert (
        '"level": "warning"' in combined
    ), f"the warn tier must report at warning severity; combined={combined!r}"


def test_no_raise_outside_io_promotes_consumer_defined_error_findings_under_the_lever(
    *, tmp_path: Path
) -> None:
    """`LIVESPEC_FAIL_IF_DOMAIN_ERROR_RAISES_EXIST` turns the same finding into exit 1.

    The severity lever the brief sanctions: land DETECTION behind a
    clearly-labelled warn tier, promote to fail once the fleet is clean. It is
    a lever that makes the check STRICTER, never a per-repo exemption or a
    skip flag — unset it and the finding is still reported, just at warning
    severity.
    """
    _write(
        path=tmp_path / "pkg" / "errors.py",
        body='class WidgetError(Exception):\n    """A consumer-defined domain error."""\n',
    )
    _write(
        path=tmp_path / "pkg" / "service.py",
        body='def do_thing() -> None:\n    raise WidgetError("nope")\n',
    )

    result = _run(cwd=tmp_path, promote=True)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"the promotion lever must fail the run on a consumer-defined domain-error "
        f"raise; got returncode={result.returncode} combined={combined!r}"
    )
    assert (
        '"level": "error"' in combined
    ), f"the promoted tier must report at error severity; combined={combined!r}"


def test_no_raise_outside_io_ignores_an_error_class_the_consumer_does_not_define(
    *, tmp_path: Path
) -> None:
    """A raise of a name the repo never defines is NOT an offense, even under the lever.

    The other half of "derived, not hardcoded". `ValidationError` is one of
    the four names the check used to carry in a frozenset, so under the old
    shape this fixture failed. It must now pass: the fixture package defines
    no such class, so the name is not this consumer's domain error — it is
    some other repo's, or a typo, and either way not a raise this check
    governs.
    """
    _write(
        path=tmp_path / "pkg" / "service.py",
        body='def do_thing() -> None:\n    raise ValidationError("malformed")\n',
    )

    result = _run(cwd=tmp_path, promote=True)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"a name the consumer does not define is not its domain error and must not "
        f"be flagged; got returncode={result.returncode} combined={combined!r}"
    )


def test_no_raise_outside_io_flags_a_subclass_and_a_dotted_raise(*, tmp_path: Path) -> None:
    """Derivation is transitive, and the raise head is matched on its final component.

    Two shapes a name-set-of-one would miss, both routine in real consumers:
    `SchemaViolationError(WidgetError)` inherits domain-error status from a
    first-party base rather than from `Exception` directly, and a module that
    imports the errors module rather than the class raises it dotted, as
    `errors.SchemaViolationError(...)`.
    """
    _write(
        path=tmp_path / "pkg" / "errors.py",
        body=(
            'class WidgetError(Exception):\n    """A consumer-defined domain error."""\n'
            "\n\n"
            'class SchemaViolationError(WidgetError):\n    """A derived domain error."""\n'
        ),
    )
    _write(
        path=tmp_path / "pkg" / "service.py",
        body=(
            "from pkg import errors\n"
            "\n\n"
            'def do_thing() -> None:\n    raise errors.SchemaViolationError("nope")\n'
        ),
    )

    result = _run(cwd=tmp_path, promote=True)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"a dotted raise of a transitively-derived domain error must be flagged; "
        f"got returncode={result.returncode} combined={combined!r}"
    )
    assert (
        "SchemaViolationError" in combined
    ), f"the diagnostic must name the offending error class; combined={combined!r}"


def test_no_raise_outside_io_reports_the_size_of_the_derived_set(*, tmp_path: Path) -> None:
    """Every run reports how many domain-error names it derived.

    A count of zero is what vacuity looks like from the outside, and it reads
    exactly like a clean pass unless the check says so out loud. The
    `files_inspected` line already exists for that reason; the derived-name
    count is the second half of it, because inspecting 219 files against an
    empty name set is still inspecting nothing.
    """
    _write(
        path=tmp_path / "pkg" / "errors.py",
        body='class WidgetError(Exception):\n    """A consumer-defined domain error."""\n',
    )

    result = _run(cwd=tmp_path)

    combined = result.stdout + result.stderr
    assert (
        "domain_error_names" in combined
    ), f"the inspection-complete line must report the derived set size; combined={combined!r}"
