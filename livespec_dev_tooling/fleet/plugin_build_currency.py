"""Report whether Claude serves the locally expected plugin builds."""

from __future__ import annotations

import sys
from pathlib import Path

from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import (
    CommandRunner,
    command_answer,
    default_command_runner,
)
from livespec_dev_tooling.fleet._plugin_build_currency_core import (
    CURRENCY_CURRENT,
    CURRENCY_STALE,
    CURRENCY_UNDETERMINABLE,
    BuildIdentifier,
    PluginBuildCurrency,
    build_currency,
    resolved_build,
    unresolved_build,
)
from livespec_dev_tooling.fleet._plugin_build_currency_reads import (
    PinnedSource,
    governed_pins,
    served_build_identifier,
)

__all__: list[str] = [
    "CURRENCY_CURRENT",
    "CURRENCY_STALE",
    "CURRENCY_UNDETERMINABLE",
    "currency_exit_code",
    "expected_build_identifier",
    "main",
    "plugin_currencies",
]


def currency_exit_code(*, currencies: tuple[PluginBuildCurrency, ...]) -> int:
    """Pass only a non-vacuous set in which every served build is current."""
    return 0 if currencies and all(item.verdict == CURRENCY_CURRENT for item in currencies) else 4


def expected_build_identifier(
    *, marketplaces_root: Path, pin: PinnedSource, run: CommandRunner
) -> BuildIdentifier:
    """Resolve the pinned remote-tracking ref from its local marketplace clone."""
    if pin.unresolved:
        return unresolved_build(detail=pin.unresolved)
    answer = command_answer(
        outcome=run(
            args=[
                "git",
                "-C",
                str(marketplaces_root / pin.marketplace),
                "rev-parse",
                "--verify",
                f"origin/{pin.ref}",
            ]
        )
    )
    if isinstance(answer, InvocationNotPerformed):
        return unresolved_build(detail=answer.reason)
    if answer.returncode != 0:
        return unresolved_build(
            detail=(
                f"git rev-parse for {pin.repo}@{pin.ref} exited "
                f"{answer.returncode}: {answer.stderr.strip()}"
            )
        )
    return resolved_build(sha=answer.stdout)


def plugin_currencies(
    *,
    settings_text: str,
    project_root: str,
    registry_text: str | None,
    marketplaces_root: Path,
    run: CommandRunner,
) -> tuple[PluginBuildCurrency, ...]:
    """Compare every enabled plugin's project install with its pinned ref."""
    pins = governed_pins(settings_text=settings_text)
    if pins.unreadable:
        return (
            build_currency(
                plugin=".claude/settings.json",
                served=unresolved_build(detail=pins.unreadable),
                expected=unresolved_build(detail=pins.unreadable),
            ),
        )
    return tuple(
        build_currency(
            plugin=pin.plugin,
            served=served_build_identifier(
                registry_text=registry_text,
                plugin=pin.plugin,
                project_root=project_root,
            ),
            expected=expected_build_identifier(
                marketplaces_root=marketplaces_root,
                pin=pin,
                run=run,
            ),
        )
        for pin in pins.sources
    )


def main() -> int:
    """Read local project/plugin state and emit one complete line per plugin."""
    root = Path.cwd()
    settings_text = (root / ".claude" / "settings.json").read_text(encoding="utf-8")
    pins = governed_pins(settings_text=settings_text)
    if pins.unreadable:
        _ = sys.stderr.write(f"plugin_build_currency: {pins.unreadable}\n")
        return 3
    home = Path.home()
    registry_path = home / ".claude" / "plugins" / "installed_plugins.json"
    registry_text = registry_path.read_text(encoding="utf-8") if registry_path.is_file() else None
    currencies = plugin_currencies(
        settings_text=settings_text,
        project_root=str(root),
        registry_text=registry_text,
        marketplaces_root=home / ".claude" / "plugins" / "marketplaces",
        run=default_command_runner,
    )
    for currency in currencies:
        _ = sys.stderr.write(f"plugin_build_currency: {currency.line}\n")
    return currency_exit_code(currencies=currencies)


if __name__ == "__main__":
    raise SystemExit(main())
