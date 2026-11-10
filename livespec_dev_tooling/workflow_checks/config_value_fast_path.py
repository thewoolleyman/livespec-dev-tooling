"""Classify and validate the narrow config-value pre-commit fast path.

The classifier reads the staged index. A qualifying diff replaces each
declared key's whole value line; added keys, removed keys, comments, and every
other edit fall through to the ordinary pre-commit aggregate.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:
    import tomli as _toml

__all__: list[str] = ["CONFIG_VALUE_FAST_PATH_RULES", "ConfigValueFastPathRule", "main"]

_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "config_value_fast_path.toml"
_NORMAL_PRE_COMMIT = 75
_VALID_JSON_VALUE = r'(?:-?(?:0|[1-9][0-9]*)|true|false|null|"(?:[^"\\\\]|\\\\.)*")'


@dataclass(frozen=True, kw_only=True)
class ConfigValueFastPathRule:
    """One value line eligible for the config-only pre-commit lane."""

    pattern: str
    key_path: str
    format: str


@dataclass(frozen=True, kw_only=True)
class ValidationFailure:
    """A schema or parse failure attributed to the qualified config key."""

    path: str
    key_path: str
    detail: str


def _load_rules() -> tuple[ConfigValueFastPathRule, ...]:
    """Read the one packaged fast-path declaration."""
    document = cast(dict[str, list[dict[str, str]]], _toml.loads(_RULES_PATH.read_text()))
    return tuple(
        ConfigValueFastPathRule(
            pattern=rule["pattern"],
            key_path=rule["key_path"],
            format=rule["format"],
        )
        for rule in document["rules"]
    )


CONFIG_VALUE_FAST_PATH_RULES = _load_rules()


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one read-only staged-index query."""
    return subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)


def _staged_paths(*, cwd: Path) -> list[str]:
    """Return every changed index path, including deletions that disqualify the lane."""
    result = _git(cwd=cwd, args=["diff", "--cached", "--name-only"])
    return result.stdout.splitlines() if result.returncode == 0 else []


def _rules_for_path(*, path: str) -> tuple[ConfigValueFastPathRule, ...]:
    """Return declarations whose file glob accepts this staged path."""
    return tuple(
        rule for rule in CONFIG_VALUE_FAST_PATH_RULES if fnmatch.fnmatch(path, rule.pattern)
    )


def _line_rule(*, path: str, line: str) -> ConfigValueFastPathRule | None:
    """Return the declared key whose complete value line is `line`, if any."""
    for rule in _rules_for_path(path=path):
        key = re.escape(rule.key_path.rsplit(".", maxsplit=1)[-1])
        if rule.format == "jsonc":
            pattern = rf'^\s*"{key}"\s*:\s*{_VALID_JSON_VALUE}\s*,?\s*$'
        elif rule.format == "yaml":
            pattern = rf"^\s*{key}:\s*[^#\n]+?\s*$"
        else:
            pattern = rf"^{key}=[^#\n]*$"
        if re.fullmatch(pattern, line) is not None:
            return rule
    return None


def _changed_line_pairs(*, cwd: Path, path: str) -> tuple[tuple[str, str], ...] | None:
    """Return replacement pairs, refusing additions, deletions and non-text diffs."""
    result = _git(cwd=cwd, args=["diff", "--cached", "--unified=0", "--", path])
    if result.returncode != 0 or "Binary files" in result.stdout:
        return None
    removed: list[str] = []
    added: list[str] = []
    pairs: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            if len(removed) != len(added):
                return None
            pairs.extend(zip(removed, added, strict=True))
            removed, added = [], []
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    if len(removed) != len(added):
        return None
    pairs.extend(zip(removed, added, strict=True))
    return tuple(pairs) if pairs else None


def is_config_value_fast_path(*, cwd: Path) -> bool:
    """Whether the staged diff contains only declared value-line replacements."""
    paths = _staged_paths(cwd=cwd)
    if not paths:
        return False
    for path in paths:
        pairs = _changed_line_pairs(cwd=cwd, path=path)
        if pairs is None:
            return False
        for before, after in pairs:
            before_rule = _line_rule(path=path, line=before)
            after_rule = _line_rule(path=path, line=after)
            if before_rule is None or before_rule != after_rule:
                return False
    return True


def _staged_text(*, cwd: Path, path: str) -> str:
    """Read one changed file exactly as the commit would store it."""
    result = _git(cwd=cwd, args=["show", f":{path}"])
    return result.stdout if result.returncode == 0 else ""


def _values_named(*, document: object, key: str) -> tuple[object, ...]:
    """Return every mapping value with `key` from a structured document."""
    if isinstance(document, dict):
        mapping = cast(dict[str, object], document)
        nested = tuple(
            value for item in mapping.values() for value in _values_named(document=item, key=key)
        )
        own = (mapping[key],) if key in mapping else ()
        return (*own, *nested)
    if isinstance(document, list):
        items = cast(list[object], document)
        return tuple(value for item in items for value in _values_named(document=item, key=key))
    return ()


def _positive_integer_failure(
    *, path: str, rule: ConfigValueFastPathRule, values: tuple[object, ...]
) -> ValidationFailure | None:
    """Return the shared scalar-schema failure, if values are absent or invalid."""
    if values and all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in values
    ):
        return None
    return ValidationFailure(path=path, key_path=rule.key_path, detail="must be a positive integer")


def _validate_jsonc(
    *, path: str, text: str, rule: ConfigValueFastPathRule
) -> ValidationFailure | None:
    """Parse JSONC and apply the scalar schema for one declared dispatcher key."""
    try:
        document: object = jsoncomment.loads(text)
    except ValueError as error:
        return ValidationFailure(path=path, key_path=rule.key_path, detail=str(error))
    key = rule.key_path.rsplit(".", maxsplit=1)[-1]
    return _positive_integer_failure(
        path=path, rule=rule, values=_values_named(document=document, key=key)
    )


def _validate_yaml(
    *, path: str, text: str, rule: ConfigValueFastPathRule
) -> ValidationFailure | None:
    """Parse host variables and require every declared run cap to be positive."""
    try:
        document: object = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return ValidationFailure(path=path, key_path=rule.key_path, detail=str(error))
    return _positive_integer_failure(
        path=path, rule=rule, values=_values_named(document=document, key=rule.key_path)
    )


def _validate_profile(
    *, cwd: Path, path: str, rule: ConfigValueFastPathRule
) -> ValidationFailure | None:
    """Run the profile's authoritative parser instead of duplicating its schema."""
    parser = cwd / "ci-runner/k3s/phase0-bare-metal/profile.sh"
    command = 'die() { printf \'%s\\n\' "$1" >&2; exit 4; }; source "$1"; profile_load "$2"'
    result = subprocess.run(
        ["bash", "-c", command, "config-value-fast-path", str(parser), str(cwd / path)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return None
    return ValidationFailure(
        path=path,
        key_path=rule.key_path,
        detail=(result.stderr or result.stdout).strip() or "profile parser refused the file",
    )


def validate_config_value_fast_path(*, cwd: Path) -> tuple[ValidationFailure, ...]:
    """Validate each changed qualifying file using its parser and value schema."""
    failures: list[ValidationFailure] = []
    for path in _staged_paths(cwd=cwd):
        text = _staged_text(cwd=cwd, path=path)
        for rule in _rules_for_path(path=path):
            if rule.format == "jsonc":
                failure = _validate_jsonc(path=path, text=text, rule=rule)
            elif rule.format == "yaml":
                failure = _validate_yaml(path=path, text=text, rule=rule)
            else:
                failure = _validate_profile(cwd=cwd, path=path, rule=rule)
            if failure is not None:
                failures.append(failure)
    return tuple(failures)


def _logger() -> structlog.stdlib.BoundLogger:
    """Configure the CLI's structured stderr diagnostics."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("config_value_fast_path")


def main() -> int:
    """Classify or validate the staged config-value fast-path candidate."""
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("command", choices=("classify", "validate"))
    options = parser.parse_args()
    cwd = Path.cwd()
    if options.command == "classify":
        return 0 if is_config_value_fast_path(cwd=cwd) else _NORMAL_PRE_COMMIT
    failures = validate_config_value_fast_path(cwd=cwd)
    if not failures:
        return 0
    logger = _logger()
    for failure in failures:
        _ = logger.error(
            "config-value-fast-path-refused",
            file=failure.path,
            key=failure.key_path,
            detail=failure.detail,
        )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
