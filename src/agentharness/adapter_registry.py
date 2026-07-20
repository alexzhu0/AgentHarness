"""Runtime adapter registry validation for control-plane handoffs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .execution_handoff import execution_handoff_digest, validate_runtime_adapter_spec
from .validate import ValidationReport
from .yamlio import YamlLoadError, load_yaml


REQUIRED_ENTRY_FIELDS = {
    "adapter_id",
    "adapter_kind",
    "adapter_version",
    "execution_plane",
    "status",
    "adapter_spec_path",
    "adapter_spec_digest",
}
ALLOWED_ENTRY_STATUSES = {"active", "deprecated", "disabled"}
SELECTABLE_STATUS = "active"
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
RANGE_OR_WILDCARD_TOKENS = ("*", "<", ">", "=", "^", "~", "|", ",")


def adapter_spec_digest(adapter_spec: Mapping[str, Any]) -> str:
    """Return the canonical digest for a runtime adapter spec mapping."""

    return execution_handoff_digest(adapter_spec)


def validate_runtime_adapter_registry(
    registry: Mapping[str, Any],
    bus_root: str | Path,
) -> ValidationReport:
    """Validate a registry and all adapter specs it pins."""

    report = ValidationReport()
    if not isinstance(registry, Mapping):
        report.error("$", "adapter registry must be a mapping")
        return report

    if registry.get("kind") != "runtime_adapter_registry":
        report.error("kind", "must be runtime_adapter_registry")
    if registry.get("version") != "0.1.0":
        report.error("version", "must be 0.1.0")

    entries = registry.get("entries")
    if not isinstance(entries, list):
        report.error("entries", "must be a non-empty list")
        return report
    if not entries:
        report.error("entries", "must be a non-empty list")
        return report

    root = Path(bus_root).resolve()
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        entry_path = f"entries[{index}]"
        if not isinstance(entry, Mapping):
            report.error(entry_path, "must be a mapping")
            continue
        _validate_registry_entry(entry, entry_path, report)

        adapter_id = entry.get("adapter_id")
        adapter_version = entry.get("adapter_version")
        if isinstance(adapter_id, str) and isinstance(adapter_version, str):
            key = (adapter_id, adapter_version)
            if key in seen:
                report.error(
                    f"{entry_path}.adapter_version",
                    "duplicate adapter_id and adapter_version",
                )
            seen.add(key)

        spec_path = entry.get("adapter_spec_path")
        spec, spec_report = _load_adapter_spec(
            root, spec_path, f"{entry_path}.adapter_spec_path"
        )
        _merge(report, spec_report)
        if spec is None:
            continue

        _merge_prefixed(
            report, validate_runtime_adapter_spec(spec), f"{entry_path}.adapter_spec"
        )
        _validate_entry_matches_spec(entry, spec, entry_path, report)

    return report


def validate_adapter_registry_binding(
    handoff_report: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    bus_root: str | Path,
) -> ValidationReport:
    """Validate optional registry binding fields on an execution handoff report."""

    report = ValidationReport()
    has_registry_path = "adapter_registry_path" in handoff_report
    has_adapter_ref = "adapter_ref" in handoff_report
    if not has_registry_path and not has_adapter_ref:
        return report
    if not has_registry_path:
        report.error(
            "adapter_registry_path",
            "required when adapter_ref is present",
        )
        return report
    if not has_adapter_ref:
        report.error(
            "adapter_ref",
            "required when adapter_registry_path is present",
        )
        return report

    root = Path(bus_root).resolve()
    registry_path = handoff_report.get("adapter_registry_path")
    registry, registry_load_report = _load_registry(
        root, registry_path, "adapter_registry_path"
    )
    _merge(report, registry_load_report)

    adapter_ref = handoff_report.get("adapter_ref")
    ref_report = _validate_adapter_ref(adapter_ref)
    _merge_prefixed(report, ref_report, "adapter_ref")

    if registry is None or not isinstance(adapter_ref, Mapping):
        return report

    registry_report = validate_runtime_adapter_registry(registry, root)
    _merge_prefixed(report, registry_report, "adapter_registry")

    if ref_report.errors:
        return report

    selected = _select_entry(registry, adapter_ref)
    if selected is None:
        report.error("adapter_ref", "must select a registered adapter")
        return report

    if selected.get("status") != SELECTABLE_STATUS:
        report.error("adapter_ref.status", "selected adapter must be active")

    if (
        "adapter_spec_digest" in adapter_ref
        and adapter_ref.get("adapter_spec_digest") != selected.get("adapter_spec_digest")
    ):
        report.error(
            "adapter_ref.adapter_spec_digest",
            "must match selected registry entry",
        )
    if handoff_report.get("adapter_spec_path") != selected.get("adapter_spec_path"):
        report.error(
            "adapter_spec_path",
            "must match selected registry entry adapter_spec_path",
        )

    _validate_selected_spec_matches_ref(adapter_ref, selected, adapter_spec, report)
    return report


def _validate_registry_entry(
    entry: Mapping[str, Any], path: str, report: ValidationReport
) -> None:
    for field_name in sorted(REQUIRED_ENTRY_FIELDS):
        value = entry.get(field_name)
        if not isinstance(value, str) or not value:
            report.error(f"{path}.{field_name}", "must be a non-empty string")

    if entry.get("status") not in ALLOWED_ENTRY_STATUSES:
        report.error(
            f"{path}.status",
            "must be one of: active, deprecated, disabled",
        )
    adapter_id = entry.get("adapter_id")
    if isinstance(adapter_id, str):
        _validate_exact_selector(adapter_id, f"{path}.adapter_id", report)
    adapter_version = entry.get("adapter_version")
    if isinstance(adapter_version, str):
        _validate_semver_selector(adapter_version, f"{path}.adapter_version", report)
    digest = entry.get("adapter_spec_digest")
    if isinstance(digest, str) and not DIGEST_PATTERN.match(digest):
        report.error(f"{path}.adapter_spec_digest", "must be a sha256 digest")


def _validate_entry_matches_spec(
    entry: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    path: str,
    report: ValidationReport,
) -> None:
    for field_name in (
        "adapter_id",
        "adapter_kind",
        "adapter_version",
        "execution_plane",
    ):
        if entry.get(field_name) != adapter_spec.get(field_name):
            report.error(f"{path}.{field_name}", "must match adapter spec")
    expected_digest = adapter_spec_digest(adapter_spec)
    if entry.get("adapter_spec_digest") != expected_digest:
        report.error(
            f"{path}.adapter_spec_digest",
            "must match canonical adapter spec digest",
        )


def _validate_adapter_ref(value: Any) -> ValidationReport:
    report = ValidationReport()
    if not isinstance(value, Mapping):
        report.error("$", "must be a mapping")
        return report

    for field_name in ("adapter_id", "adapter_version"):
        field_value = value.get(field_name)
        if not isinstance(field_value, str) or not field_value:
            report.error(field_name, "must be a non-empty string")
            continue
        if field_name == "adapter_id":
            _validate_exact_selector(field_value, field_name, report)
        else:
            _validate_semver_selector(field_value, field_name, report)

    if "adapter_spec_digest" in value:
        digest = value.get("adapter_spec_digest")
        if not isinstance(digest, str) or not digest:
            report.error("adapter_spec_digest", "must be a non-empty string")
        elif not DIGEST_PATTERN.match(digest):
            report.error("adapter_spec_digest", "must be a sha256 digest")
    return report


def _validate_exact_selector(value: str, path: str, report: ValidationReport) -> None:
    if any(token in value for token in RANGE_OR_WILDCARD_TOKENS):
        report.error(path, "must be an exact value without wildcard or range syntax")


def _validate_semver_selector(value: str, path: str, report: ValidationReport) -> None:
    if any(token in value for token in RANGE_OR_WILDCARD_TOKENS):
        report.error(
            path,
            "must be strict MAJOR.MINOR.PATCH semver without wildcard or range syntax",
        )
        return
    if not SEMVER_PATTERN.match(value):
        report.error(path, "must be strict MAJOR.MINOR.PATCH semver")


def _select_entry(
    registry: Mapping[str, Any], adapter_ref: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    entries = registry.get("entries")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if (
            entry.get("adapter_id") == adapter_ref.get("adapter_id")
            and entry.get("adapter_version") == adapter_ref.get("adapter_version")
        ):
            return entry
    return None


def _validate_selected_spec_matches_ref(
    adapter_ref: Mapping[str, Any],
    selected: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    report: ValidationReport,
) -> None:
    for field_name in ("adapter_id", "adapter_version"):
        if adapter_spec.get(field_name) != adapter_ref.get(field_name):
            report.error(f"adapter_spec.{field_name}", "must match adapter_ref")
    for field_name in (
        "adapter_id",
        "adapter_kind",
        "adapter_version",
        "execution_plane",
    ):
        if adapter_spec.get(field_name) != selected.get(field_name):
            report.error(f"adapter_spec.{field_name}", "must match selected registry entry")
    if adapter_spec_digest(adapter_spec) != selected.get("adapter_spec_digest"):
        report.error(
            "adapter_spec_digest",
            "handoff adapter spec must match selected registry digest",
        )


def _load_registry(
    bus_root: Path, reference: Any, path: str
) -> tuple[Mapping[str, Any] | None, ValidationReport]:
    report = ValidationReport()
    resolved, error = _resolve_reference(bus_root, reference)
    if error:
        report.error(path, error)
        return None, report
    if resolved is None or not resolved.is_file():
        report.error(path, "referenced file does not exist")
        return None, report
    try:
        registry = load_yaml(resolved)
    except YamlLoadError as exc:
        report.error(path, f"could not parse adapter registry: {exc}")
        return None, report
    if not isinstance(registry, Mapping):
        report.error(path, "adapter registry must be a mapping")
        return None, report
    return registry, report


def _load_adapter_spec(
    bus_root: Path, reference: Any, path: str
) -> tuple[Mapping[str, Any] | None, ValidationReport]:
    report = ValidationReport()
    resolved, error = _resolve_reference(bus_root, reference)
    if error:
        report.error(path, error)
        return None, report
    if resolved is None or not resolved.is_file():
        report.error(path, "referenced file does not exist")
        return None, report
    try:
        adapter_spec = load_yaml(resolved)
    except YamlLoadError as exc:
        report.error(path, f"could not parse adapter spec: {exc}")
        return None, report
    if not isinstance(adapter_spec, Mapping):
        report.error(path, "adapter spec must be a mapping")
        return None, report
    return adapter_spec, report


def _resolve_reference(bus_root: Path, reference: Any) -> tuple[Path | None, str | None]:
    if not isinstance(reference, str) or not reference:
        return None, "must be a non-empty string"
    path = Path(reference)
    candidate = path if path.is_absolute() else bus_root / path
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(bus_root):
        return resolved, "referenced path must stay within bus_root"
    return resolved, None


def _merge(target: ValidationReport, source: ValidationReport) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)


def _merge_prefixed(
    target: ValidationReport, source: ValidationReport, prefix: str
) -> None:
    target.errors.extend(f"{prefix}.{error}" for error in source.errors)
    target.warnings.extend(f"{prefix}.{warning}" for warning in source.warnings)
