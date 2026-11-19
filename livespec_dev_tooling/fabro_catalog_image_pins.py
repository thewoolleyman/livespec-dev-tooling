"""Validate Fabro catalog image tags against the committed workflow-pin mirror."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

import yaml

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CATALOG_HOST_VARS_DIR = Path("ansible") / "inventory" / "host_vars"
_WORKFLOW_PIN_MIRROR_PATH = Path("livespec_dev_tooling") / "data" / "fabro_workflow_image_pins.json"
_SANDBOX_IMAGE_WORKFLOW_PATH = Path(".github") / "workflows" / "fabro-sandbox-image.yml"
_CATALOG_HOLD_KEY = "image_pin_hold"
_SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_ARCHITECTURE_SUFFIX = re.compile(
    r"^[ \t]*suffix=-(?P<architecture>[a-z0-9][a-z0-9-]*)[ \t]*$", re.MULTILINE
)
_IMAGE_TAG = re.compile(
    r"^(?P<layer>[a-z0-9]+(?:-[a-z0-9]+)*)-v(?P<version>[0-9]+(?:\.[0-9]+)+)(?:-(?P<architecture>[a-z0-9][a-z0-9-]*))?$"
)
_WORK_ITEM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")


def _catalog_architectures(*, workflow_source: str) -> set[str]:
    return set(_ARCHITECTURE_SUFFIX.findall(workflow_source))


def _architecture_workflow_source(*, cwd: Path) -> str:
    path = cwd / _SANDBOX_IMAGE_WORKFLOW_PATH
    if not path.is_file():
        path = _SOURCE_REPOSITORY_ROOT / _SANDBOX_IMAGE_WORKFLOW_PATH
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _workflow_pin_mirror(*, source: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    try:
        raw: object = cast(object, json.loads(source))
    except json.JSONDecodeError as error:
        return {}, [f"{_WORKFLOW_PIN_MIRROR_PATH}: invalid JSON: {error.msg}"]
    if not isinstance(raw, dict):
        return {}, [f"{_WORKFLOW_PIN_MIRROR_PATH}: expected an object keyed by workflow_pin_member"]
    pins: dict[str, dict[str, str]] = {}
    issues: list[str] = []
    for member, layers in cast(dict[object, object], raw).items():
        if not isinstance(member, str) or not isinstance(layers, dict):
            issues.append(f"{_WORKFLOW_PIN_MIRROR_PATH}: every member must map to layer pins")
            continue
        member_pins: dict[str, str] = {}
        for layer, tag in cast(dict[object, object], layers).items():
            if not isinstance(layer, str) or not isinstance(tag, str):
                issues.append(f"{_WORKFLOW_PIN_MIRROR_PATH}: {member!r} has a non-string layer pin")
                continue
            member_pins[layer] = tag
        pins[member] = member_pins
    return pins, issues


def _catalog_image_identity(*, image: str, architectures: set[str]) -> tuple[str, str] | None:
    _, separator, tag = image.rpartition(":")
    if not separator:
        return None
    match = _IMAGE_TAG.fullmatch(tag)
    if match is None:
        return None
    architecture = match.group("architecture")
    if architecture is not None and architecture not in architectures:
        return None
    return match.group("layer"), match.group("version")


def _catalog_entries(*, instance: dict[str, Any]) -> list[tuple[str, str, object]]:
    entries: list[tuple[str, str, object]] = []
    environments = instance.get("environments", [])
    if isinstance(environments, list):
        for environment in cast(list[object], environments):
            if not isinstance(environment, dict):
                continue
            environment_mapping = cast(dict[str, Any], environment)
            image = environment_mapping.get("image")
            if isinstance(image, str):
                entries.append(
                    (
                        f"environments.{environment_mapping.get('id', '<unnamed>')}",
                        image,
                        environment_mapping.get(_CATALOG_HOLD_KEY),
                    )
                )
    providers = instance.get("sandbox_providers", {})
    if isinstance(providers, dict):
        for provider_name, provider in cast(dict[object, object], providers).items():
            if not isinstance(provider, dict):
                continue
            provider_mapping = cast(dict[str, Any], provider)
            process_spec = provider_mapping.get("process_spec", {})
            if not isinstance(process_spec, dict):
                continue
            process_spec_mapping = cast(dict[str, Any], process_spec)
            image = process_spec_mapping.get("image")
            if isinstance(image, str):
                entries.append(
                    (
                        f"sandbox_providers.{provider_name}.process_spec",
                        image,
                        process_spec_mapping.get(_CATALOG_HOLD_KEY),
                    )
                )
    return entries


def _catalog_entry_issue(
    *,
    context: str,
    member: str,
    member_pins: dict[str, str],
    catalog_entry: tuple[str, str, object],
    architectures: set[str],
) -> str | None:
    entry_name, image, hold = catalog_entry
    identity = _catalog_image_identity(image=image, architectures=architectures)
    if identity is None:
        return f"{context} {entry_name}: catalog image {image!r} has an unsupported tag"
    layer, version = identity
    workflow_tag = member_pins.get(layer)
    if workflow_tag is None:
        return (
            f"{context} {entry_name}: no workflow image pin for layer {layer!r} "
            f"in member {member!r}"
        )
    workflow_identity = _catalog_image_identity(
        image=f"image:{workflow_tag}", architectures=architectures
    )
    if workflow_identity is None or workflow_identity[0] != layer:
        return (
            f"{_WORKFLOW_PIN_MIRROR_PATH}: {member!r} pin {workflow_tag!r} "
            f"is not a {layer!r} image tag"
        )
    if version == workflow_identity[1]:
        return None
    divergence = (
        f"{context} {entry_name}: catalog image {image!r} differs from "
        f"workflow image pin {workflow_tag!r}"
    )
    if not isinstance(hold, str) or not _WORK_ITEM_ID.fullmatch(hold):
        return f"{divergence}; declared {_CATALOG_HOLD_KEY} must name a work-item id"
    structlog.get_logger("fabro_image_pin_lockstep").info(
        "declared Fabro catalog image divergence",
        catalog_entry=entry_name,
        catalog_image=image,
        workflow_image_pin=workflow_tag,
        work_item_id=hold,
    )
    return None


def _instance_catalog_issues(
    *,
    context: str,
    instance: dict[str, Any],
    pin_mirror: dict[str, dict[str, str]],
    architectures: set[str],
) -> list[str]:
    entries = _catalog_entries(instance=instance)
    if not entries:
        return []
    member = instance.get("workflow_pin_member")
    if not isinstance(member, str) or not member:
        return [f"{context}: catalog images require workflow_pin_member"]
    member_pins = pin_mirror.get(member)
    if member_pins is None:
        return [
            f"{context}: workflow_pin_member {member!r} is absent from "
            f"{_WORKFLOW_PIN_MIRROR_PATH}"
        ]
    return [
        issue
        for entry in entries
        if (
            issue := _catalog_entry_issue(
                context=context,
                member=member,
                member_pins=member_pins,
                catalog_entry=entry,
                architectures=architectures,
            )
        )
        is not None
    ]


def _host_vars_catalog_issues(
    *,
    host_vars_path: Path,
    cwd: Path,
    pin_mirror: dict[str, dict[str, str]],
    architectures: set[str],
) -> list[str]:
    relative_path = host_vars_path.relative_to(cwd)
    try:
        document: object = cast(object, yaml.safe_load(host_vars_path.read_text(encoding="utf-8")))
    except yaml.YAMLError as error:
        return [f"{relative_path}: invalid YAML: {error}"]
    document_mapping = cast(dict[str, Any], document) if isinstance(document, dict) else {}
    instances = document_mapping.get("fabro_server_instances", [])
    if not isinstance(instances, list):
        return []
    return [
        issue
        for instance in cast(list[object], instances)
        if isinstance(instance, dict)
        for issue in _instance_catalog_issues(
            context=(
                f"{relative_path} "
                f"{cast(dict[str, Any], instance).get('unit_name', '<unnamed>')}"
            ),
            instance=cast(dict[str, Any], instance),
            pin_mirror=pin_mirror,
            architectures=architectures,
        )
    ]


def catalog_pin_issues(
    *,
    cwd: Path,
    pin_mirror: dict[str, dict[str, str]] | None = None,
    architectures: set[str] | None = None,
) -> list[str]:
    """Compare every Fabro catalog image to its named member's workflow image pin."""
    issues: list[str] = []
    if pin_mirror is None:
        mirror_path = cwd / _WORKFLOW_PIN_MIRROR_PATH
        pin_mirror, mirror_issues = _workflow_pin_mirror(
            source=mirror_path.read_text(encoding="utf-8") if mirror_path.is_file() else "{}"
        )
        issues.extend(mirror_issues)
    if architectures is None:
        architectures = _catalog_architectures(
            workflow_source=_architecture_workflow_source(cwd=cwd)
        )
    for host_vars_path in sorted((cwd / _CATALOG_HOST_VARS_DIR).glob("*.yml")):
        issues.extend(
            _host_vars_catalog_issues(
                host_vars_path=host_vars_path,
                cwd=cwd,
                pin_mirror=pin_mirror,
                architectures=architectures,
            )
        )
    return issues
