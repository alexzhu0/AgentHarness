"""Read-only export package for registry-backed handoff reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .adapter_registry import validate_adapter_registry_binding
from .execution_handoff import execution_handoff_digest
from .loop_bus import parse_ledger, validate_bus
from .validate import ValidationReport
from .yamlio import YamlLoadError, load_yaml


NOT_EXECUTED = "not_executed"


def build_handoff_export_package(
    bus_root: str | Path,
) -> tuple[dict[str, Any] | None, ValidationReport]:
    """Build a deterministic ready-only export package from a validated bus."""

    root = Path(bus_root).resolve()
    report = validate_bus(root)
    if not report.ok:
        return None, report

    events, ledger_report = parse_ledger(root / "ledger.jsonl")
    _merge(report, ledger_report)
    if not report.ok:
        return None, report

    references = _handoff_report_references(events)
    if not references:
        report.error(
            "ledger.execution_handoff_report_path",
            "no execution handoff report referenced by designer_review event",
        )
        return None, report

    exports: list[dict[str, Any]] = []
    summary = {
        "reports": 0,
        "total_handoffs": 0,
        "exported": 0,
        "blocked": 0,
        "unsupported": 0,
        "result_status": NOT_EXECUTED,
    }

    for index, reference in enumerate(references):
        field_path = f"ledger.handoff_reports[{index}]"
        handoff_report_path, handoff_report = _load_mapping_reference(
            root,
            reference,
            field_path,
            "execution handoff report",
            report,
        )
        if handoff_report_path is None or handoff_report is None:
            continue

        summary["reports"] += 1
        adapter_spec_path, adapter_spec = _load_mapping_reference(
            root,
            handoff_report.get("adapter_spec_path"),
            f"{field_path}.adapter_spec_path",
            "adapter spec",
            report,
        )
        if adapter_spec_path is None or adapter_spec is None:
            continue

        if "adapter_registry_path" not in handoff_report:
            report.error(
                f"{field_path}.adapter_registry_path",
                "registry-backed handoff report is required for export",
            )
            continue
        if "adapter_ref" not in handoff_report:
            report.error(
                f"{field_path}.adapter_ref",
                "registry-backed handoff report is required for export",
            )
            continue

        binding = validate_adapter_registry_binding(handoff_report, adapter_spec, root)
        _merge_prefixed(report, binding, field_path)
        if not binding.ok:
            continue

        registry_path, registry = _load_mapping_reference(
            root,
            handoff_report.get("adapter_registry_path"),
            f"{field_path}.adapter_registry_path",
            "adapter registry",
            report,
        )
        if registry_path is None or registry is None:
            continue

        selected_entry = _selected_registry_entry(registry, handoff_report.get("adapter_ref"))
        if selected_entry is None:
            report.error(f"{field_path}.adapter_ref", "must select a registered adapter")
            continue

        handoffs = handoff_report.get("handoffs")
        if not isinstance(handoffs, list):
            report.error(f"{field_path}.handoffs", "must be a list")
            continue

        for handoff in handoffs:
            if not isinstance(handoff, Mapping):
                continue
            summary["total_handoffs"] += 1
            status = _handoff_status(handoff)
            if status == "unsupported":
                summary["unsupported"] += 1
                continue
            if status != "handoff_ready":
                summary["blocked"] += 1
                continue

            exports.append(
                _export_item(
                    root,
                    handoff_report_path,
                    registry_path,
                    adapter_spec_path,
                    selected_entry,
                    handoff,
                )
            )

    if report.ok and not exports:
        report.error("exports", "no handoff_ready registry-backed handoffs to export")
    if not report.ok:
        return None, report

    summary["exported"] = len(exports)
    package = {
        "version": "0.1.0",
        "kind": "handoff_export_package",
        "source": "build_handoff_export_package",
        "result_status": NOT_EXECUTED,
        "summary": summary,
        "exports": exports,
    }
    return package, report


def _export_item(
    root: Path,
    handoff_report_path: Path,
    registry_path: Path,
    adapter_spec_path: Path,
    selected_entry: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    gate = _mapping_or_empty(handoff.get("gate"))
    request = _mapping_or_empty(handoff.get("request"))
    return {
        "version": "0.1.0",
        "kind": "handoff_export_item",
        "result_status": NOT_EXECUTED,
        "handoff_report_path": _relative_to(root, handoff_report_path),
        "adapter_registry_path": _relative_to(root, registry_path),
        "adapter_spec_path": _relative_to(root, adapter_spec_path),
        "adapter_ref": {
            "adapter_id": selected_entry.get("adapter_id"),
            "adapter_version": selected_entry.get("adapter_version"),
            "adapter_spec_digest": selected_entry.get("adapter_spec_digest"),
        },
        "handoff_id": handoff.get("handoff_id"),
        "task_id": handoff.get("task_id"),
        "objective_ref": handoff.get("objective_ref"),
        "attempt": handoff.get("attempt"),
        "request_id": handoff.get("request_id"),
        "handoff_digest": execution_handoff_digest(handoff),
        "request": {
            "tool_name": request.get("tool_name"),
            "category": request.get("category"),
            "intent": request.get("intent"),
            "target_scope": request.get("target_scope"),
        },
        "gate": {
            "handoff_ready": gate.get("handoff_ready") is True,
            "execution_allowed_by_preflight": gate.get("execution_allowed_by_preflight"),
            "result_status": gate.get("result_status"),
        },
    }


def _handoff_report_references(events: list[dict[str, Any]]) -> list[str]:
    references: list[str] = []
    for event in events:
        if event.get("event_type") != "designer_review":
            continue
        reference = event.get("execution_handoff_report_path")
        if isinstance(reference, str) and reference:
            references.append(reference)
    return references


def _load_mapping_reference(
    root: Path,
    reference: Any,
    path: str,
    label: str,
    report: ValidationReport,
) -> tuple[Path | None, Mapping[str, Any] | None]:
    resolved, error = _resolve_bus_reference(root, reference)
    if error:
        report.error(path, error)
        return None, None
    if resolved is None or not resolved.is_file():
        report.error(path, "referenced file does not exist")
        return None, None
    try:
        value = load_yaml(resolved)
    except YamlLoadError as exc:
        report.error(path, f"could not parse {label}: {exc}")
        return None, None
    if not isinstance(value, Mapping):
        report.error(path, f"{label} must be a mapping")
        return None, None
    return resolved, value


def _selected_registry_entry(
    registry: Mapping[str, Any],
    adapter_ref: Any,
) -> Mapping[str, Any] | None:
    if not isinstance(adapter_ref, Mapping):
        return None
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


def _handoff_status(handoff: Mapping[str, Any]) -> str:
    gate = _mapping_or_empty(handoff.get("gate"))
    if gate.get("handoff_ready") is True:
        return "handoff_ready"
    if gate.get("unsupported_reason") is not None:
        return "unsupported"
    return "blocked"


def _resolve_bus_reference(root: Path, reference: Any) -> tuple[Path | None, str | None]:
    if not isinstance(reference, str) or not reference:
        return None, "must be a non-empty string"
    path = Path(reference)
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        return resolved, "referenced path must stay within bus_root"
    return resolved, None


def _relative_to(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _merge(target: ValidationReport, source: ValidationReport) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)


def _merge_prefixed(
    target: ValidationReport, source: ValidationReport, prefix: str
) -> None:
    target.errors.extend(f"{prefix}.{error}" for error in source.errors)
    target.warnings.extend(f"{prefix}.{warning}" for warning in source.warnings)
