"""Machine-readable enterprise audit report for pre-execution evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .audit_contract import (
    EVIDENCE_CHAIN,
    NOT_EXECUTED,
    RUNTIME_RESULT_STATUSES,
    SHA256_DIGEST_PATTERN,
    VERSION,
    contains_raw_audit_path,
    sanitize_audit_message,
)
from .handoff_exporter import build_handoff_export_package
from .handoff_inspector import inspect_handoff_bus
from .handoff_manifest import build_handoff_export_manifest
from .validate import ValidationReport
from .yamlio import YamlLoadError


_SUCCESS_REQUIRED_FIELDS = [
    "version",
    "kind",
    "source",
    "result_status",
    "control_plane_boundary",
    "summary",
    "evidence_chain",
    "reports",
    "handoffs",
    "export",
    "manifest",
    "manifest_verification",
]
_ERROR_REQUIRED_FIELDS = [
    "version",
    "kind",
    "source",
    "ok",
    "result_status",
    "errors",
    "warnings",
]
_SUMMARY_COUNT_FIELDS = [
    "reports",
    "total_handoffs",
    "handoff_ready",
    "exported",
    "blocked",
    "unsupported",
]
_CONTROL_PLANE_BOUNDARY_FIELDS = [
    "execution_occurred",
    "runtime_adapter_invoked",
    "execution_owner",
    "result_status",
]
_EXPORT_FIELDS = [
    "kind",
    "source",
    "result_status",
    "summary",
    "exported_request_ids",
]
_MANIFEST_FIELDS = [
    "kind",
    "source",
    "result_status",
    "package_kind",
    "package_digest",
    "summary",
    "item_request_ids",
]
_MANIFEST_VERIFICATION_FIELDS = [
    "performed",
    "reason",
    "command",
    "result_status",
]
_MANIFEST_VERIFICATION_COMMAND = (
    "agentharness handoff verify-manifest <bus_root> <manifest_path>"
)


def build_enterprise_audit_report(
    bus_root: str | Path,
) -> tuple[dict[str, Any] | None, ValidationReport]:
    """Build a deterministic enterprise audit report from existing evidence builders."""

    report = ValidationReport()

    inspection = _call_builder("inspect", inspect_handoff_bus, bus_root, report)
    if inspection is None or not report.ok:
        return None, report

    package = _call_builder("export", build_handoff_export_package, bus_root, report)
    if package is None or not report.ok:
        return None, report

    manifest = _call_builder("manifest", build_handoff_export_manifest, bus_root, report)
    if manifest is None or not report.ok:
        return None, report

    audit_report = _compose_report(inspection, package, manifest, report)
    if audit_report is None or not report.ok:
        return None, report

    _validate_not_executed(audit_report, report)
    if not report.ok:
        return None, report

    validation_report = validate_enterprise_audit_report_payload(audit_report)
    _merge_prefixed(report, validation_report, "audit_report_schema")
    if not report.ok:
        return None, report

    return audit_report, report


def enterprise_audit_error_payload(report: ValidationReport) -> dict[str, Any]:
    """Return deterministic sanitized failure JSON for audit-report CLI failures."""

    errors = [_sanitize_message(error) for error in report.errors]
    warnings = [_sanitize_message(warning) for warning in report.warnings]
    if not errors:
        errors = ["audit_report: could not build enterprise audit report"]
    return {
        "version": VERSION,
        "kind": "enterprise_audit_report_error",
        "source": "build_enterprise_audit_report",
        "ok": False,
        "result_status": NOT_EXECUTED,
        "errors": errors,
        "warnings": warnings,
    }


def validate_enterprise_audit_report_payload(payload: Any) -> ValidationReport:
    """Validate an enterprise audit report or error payload in memory only."""

    report = ValidationReport()
    if not isinstance(payload, Mapping):
        report.error("$", "payload must be a mapping")
        return report

    kind = payload.get("kind")
    if kind == "enterprise_audit_report":
        _validate_enterprise_audit_success_payload(payload, report)
    elif kind == "enterprise_audit_report_error":
        _validate_enterprise_audit_error_payload(payload, report)
    else:
        report.error(
            "kind",
            "must be enterprise_audit_report or enterprise_audit_report_error",
        )
    return report


def verify_enterprise_audit_report(
    bus_root: str | Path,
    audit_report_path: str | Path,
) -> dict[str, Any]:
    """Verify a saved enterprise audit report against regenerated bus evidence."""

    saved_report, load_errors = _load_audit_report_json(audit_report_path)
    errors = list(load_errors)
    expected_report: Mapping[str, Any] | None = None

    if saved_report is not None:
        validation_report = validate_enterprise_audit_report_payload(saved_report)
        errors.extend(f"saved_report.{error}" for error in validation_report.errors)
        if saved_report.get("kind") != "enterprise_audit_report":
            errors.append("saved_report.kind: must be enterprise_audit_report for readback verification")

        if not errors:
            expected_report, expected_build_report = build_enterprise_audit_report(bus_root)
            errors.extend(
                f"expected_report.{error}" for error in expected_build_report.errors
            )
            if expected_report is None:
                errors.append("expected_report: could not build enterprise audit report")

    if expected_report is not None and saved_report is not None:
        if _canonical_json(expected_report) != _canonical_json(saved_report):
            errors.append("audit_report: canonical object differs from regenerated report")
        errors.extend(_audit_report_field_errors(expected_report, saved_report))

    item_reports, item_summary, item_errors = _audit_report_verification_items(
        expected_report,
        saved_report,
    )
    errors.extend(item_errors)
    errors = [_sanitize_message(error) for error in errors]

    return {
        "version": VERSION,
        "kind": "enterprise_audit_report_verification_report",
        "source": "verify_enterprise_audit_report",
        "result_status": NOT_EXECUTED,
        "ok": not errors,
        "report_kind": saved_report.get("kind") if saved_report is not None else None,
        "expected_report_digest": _canonical_digest(expected_report)
        if expected_report is not None
        else None,
        "saved_report_digest": _canonical_digest(saved_report)
        if saved_report is not None
        else None,
        "summary": item_summary,
        "items": item_reports,
        "errors": errors,
        "warnings": [],
    }


def _validate_enterprise_audit_success_payload(
    payload: Mapping[str, Any], report: ValidationReport
) -> None:
    _validate_required_fields(payload, _SUCCESS_REQUIRED_FIELDS, report)
    _validate_no_unknown_fields(payload, _SUCCESS_REQUIRED_FIELDS, "$", report)
    if payload.get("version") != VERSION:
        report.error("version", f"must be {VERSION}")
    if payload.get("source") != "build_enterprise_audit_report":
        report.error("source", "must be build_enterprise_audit_report")
    if payload.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")
    if "ok" in payload:
        report.error("ok", "must not appear on successful enterprise_audit_report payloads")

    boundary = _require_mapping(payload.get("control_plane_boundary"), "control_plane_boundary", report)
    if boundary is not None:
        _validate_required_fields(
            boundary, _CONTROL_PLANE_BOUNDARY_FIELDS, report, "control_plane_boundary"
        )
        _validate_no_unknown_fields(
            boundary, _CONTROL_PLANE_BOUNDARY_FIELDS, "control_plane_boundary", report
        )
        if boundary.get("execution_occurred") is not False:
            report.error("control_plane_boundary.execution_occurred", "must be false")
        if boundary.get("runtime_adapter_invoked") is not False:
            report.error("control_plane_boundary.runtime_adapter_invoked", "must be false")
        if boundary.get("execution_owner") != "external":
            report.error("control_plane_boundary.execution_owner", "must be external")
        if boundary.get("result_status") != NOT_EXECUTED:
            report.error("control_plane_boundary.result_status", "must be not_executed")

    if payload.get("evidence_chain") != EVIDENCE_CHAIN:
        report.error("evidence_chain", "must match the accepted evidence chain order")

    summary = _require_mapping(payload.get("summary"), "summary", report)
    if summary is not None:
        _validate_summary(summary, "summary", report)

    export = _require_mapping(payload.get("export"), "export", report)
    exported_request_ids: list[str] = []
    if export is not None:
        _validate_required_fields(export, _EXPORT_FIELDS, report, "export")
        _validate_no_unknown_fields(export, _EXPORT_FIELDS, "export", report)
        if export.get("kind") != "handoff_export_package":
            report.error("export.kind", "must be handoff_export_package")
        if export.get("source") != "build_handoff_export_package":
            report.error("export.source", "must be build_handoff_export_package")
        if export.get("result_status") != NOT_EXECUTED:
            report.error("export.result_status", "must be not_executed")
        export_summary = _require_mapping(export.get("summary"), "export.summary", report)
        if export_summary is not None:
            _validate_summary(
                export_summary,
                "export.summary",
                report,
                count_fields=("reports", "total_handoffs", "exported", "blocked", "unsupported"),
            )
        exported_request_ids = _validate_string_list(
            export.get("exported_request_ids"), "export.exported_request_ids", report
        )

    handoffs = _validate_list(payload.get("handoffs"), "handoffs", report)
    exported_handoff_ids: list[str] = []
    for index, handoff_value in enumerate(handoffs):
        path = f"handoffs[{index}]"
        handoff = _require_mapping(handoff_value, path, report)
        if not handoff:
            continue
        request_id = handoff.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            report.error(f"{path}.request_id", "must be a non-empty string")
        handoff_status = handoff.get("handoff_status")
        if not isinstance(handoff_status, str) or not handoff_status:
            report.error(f"{path}.handoff_status", "must be a non-empty string")
        exported = handoff.get("exported")
        if not isinstance(exported, bool):
            report.error(f"{path}.exported", "must be a boolean")
        elif exported:
            if isinstance(request_id, str):
                exported_handoff_ids.append(request_id)
            if handoff_status != "handoff_ready":
                report.error(f"{path}.exported", "only handoff_ready items may be exported")
            if handoff.get("handoff_ready") is not True:
                report.error(f"{path}.handoff_ready", "exported items must be handoff_ready")
        if handoff_status in {"blocked", "unsupported"} and exported is True:
            report.error(f"{path}.exported", "blocked or unsupported handoffs must not be exported")
        if handoff.get("result_status") != NOT_EXECUTED:
            report.error(f"{path}.result_status", "must be not_executed")

    if exported_request_ids != exported_handoff_ids:
        report.error(
            "export.exported_request_ids",
            "must match exported handoff request_id order",
        )

    manifest = _require_mapping(payload.get("manifest"), "manifest", report)
    manifest_request_ids: list[str] = []
    if manifest is not None:
        _validate_required_fields(manifest, _MANIFEST_FIELDS, report, "manifest")
        _validate_no_unknown_fields(manifest, _MANIFEST_FIELDS, "manifest", report)
        if manifest.get("kind") != "handoff_export_manifest":
            report.error("manifest.kind", "must be handoff_export_manifest")
        if manifest.get("source") != "build_handoff_export_manifest":
            report.error("manifest.source", "must be build_handoff_export_manifest")
        if manifest.get("result_status") != NOT_EXECUTED:
            report.error("manifest.result_status", "must be not_executed")
        if manifest.get("package_kind") != "handoff_export_package":
            report.error("manifest.package_kind", "must be handoff_export_package")
        package_digest = manifest.get("package_digest")
        if not isinstance(package_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(package_digest):
            report.error("manifest.package_digest", "must be sha256: followed by 64 lowercase hex characters")
        manifest_summary = _require_mapping(manifest.get("summary"), "manifest.summary", report)
        if manifest_summary is not None:
            _validate_summary(
                manifest_summary,
                "manifest.summary",
                report,
                count_fields=("reports", "total_handoffs", "exported", "blocked", "unsupported"),
            )
        manifest_request_ids = _validate_string_list(
            manifest.get("item_request_ids"), "manifest.item_request_ids", report
        )

    if manifest_request_ids != exported_request_ids:
        report.error(
            "manifest.item_request_ids",
            "must match export.exported_request_ids",
        )

    manifest_verification = _require_mapping(
        payload.get("manifest_verification"), "manifest_verification", report
    )
    if manifest_verification is not None:
        _validate_required_fields(
            manifest_verification,
            _MANIFEST_VERIFICATION_FIELDS,
            report,
            "manifest_verification",
        )
        _validate_no_unknown_fields(
            manifest_verification,
            _MANIFEST_VERIFICATION_FIELDS,
            "manifest_verification",
            report,
        )
        if manifest_verification.get("performed") is not False:
            report.error("manifest_verification.performed", "must be false")
        if manifest_verification.get("reason") != "requires_saved_manifest_path":
            report.error(
                "manifest_verification.reason",
                "must be requires_saved_manifest_path",
            )
        if manifest_verification.get("result_status") != NOT_EXECUTED:
            report.error("manifest_verification.result_status", "must be not_executed")
        if manifest_verification.get("command") != _MANIFEST_VERIFICATION_COMMAND:
            report.error(
                "manifest_verification.command",
                f"must be {_MANIFEST_VERIFICATION_COMMAND}",
            )

    _validate_not_executed(payload, report)


def _validate_enterprise_audit_error_payload(
    payload: Mapping[str, Any], report: ValidationReport
) -> None:
    _validate_required_fields(payload, _ERROR_REQUIRED_FIELDS, report)
    _validate_no_unknown_fields(payload, _ERROR_REQUIRED_FIELDS, "$", report)
    if payload.get("version") != VERSION:
        report.error("version", f"must be {VERSION}")
    if payload.get("source") != "build_enterprise_audit_report":
        report.error("source", "must be build_enterprise_audit_report")
    if payload.get("ok") is not False:
        report.error("ok", "must be false")
    if payload.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")

    errors = _validate_string_list(payload.get("errors"), "errors", report)
    if isinstance(payload.get("errors"), list) and not payload.get("errors"):
        report.error("errors", "must be a non-empty list")
    warnings = _validate_string_list(payload.get("warnings"), "warnings", report)

    for collection_name, values in (("errors", errors), ("warnings", warnings)):
        for index, value in enumerate(values):
            if _contains_raw_path(value):
                report.error(f"{collection_name}[{index}]", "must not contain raw host paths")

    _validate_not_executed(payload, report)


def _validate_required_fields(
    payload: Mapping[str, Any],
    required_fields: list[str],
    report: ValidationReport,
    path_prefix: str | None = None,
) -> None:
    for field_name in required_fields:
        if field_name not in payload:
            path = f"{path_prefix}.{field_name}" if path_prefix else field_name
            report.error(path, "missing required field")


def _validate_no_unknown_fields(
    payload: Mapping[str, Any],
    allowed_fields: list[str],
    path: str,
    report: ValidationReport,
) -> None:
    allowed = set(allowed_fields)
    for field_name in payload:
        if field_name not in allowed:
            field_path = field_name if path == "$" else f"{path}.{field_name}"
            report.error(field_path, "unknown field")


def _require_mapping(value: Any, path: str, report: ValidationReport) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    report.error(path, "must be a mapping")
    return None


def _validate_list(value: Any, path: str, report: ValidationReport) -> list[Any]:
    if isinstance(value, list):
        return value
    report.error(path, "must be a list")
    return []


def _validate_string_list(value: Any, path: str, report: ValidationReport) -> list[str]:
    items = _validate_list(value, path, report)
    strings: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str):
            report.error(f"{path}[{index}]", "must be a string")
            continue
        strings.append(item)
    return strings


def _validate_summary(
    summary: Mapping[str, Any],
    path: str,
    report: ValidationReport,
    count_fields: tuple[str, ...] = tuple(_SUMMARY_COUNT_FIELDS),
) -> None:
    _validate_no_unknown_fields(
        summary,
        [*count_fields, "result_status"],
        path,
        report,
    )
    for field_name in count_fields:
        if field_name not in summary:
            report.error(f"{path}.{field_name}", "missing required count")
            continue
        value = summary.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool):
            report.error(f"{path}.{field_name}", "must be an integer")
        elif value < 0:
            report.error(f"{path}.{field_name}", "must be non-negative")
    if summary.get("result_status") != NOT_EXECUTED:
        report.error(f"{path}.result_status", "must be not_executed")


def _contains_raw_path(message: str) -> bool:
    return contains_raw_audit_path(message)


def _load_audit_report_json(path: str | Path) -> tuple[Mapping[str, Any] | None, list[str]]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return None, [
            f"audit_report: malformed UTF-8 at byte {exc.start}: {exc.reason}"
        ]
    except OSError:
        return None, ["audit_report_path: could not read audit report JSON"]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [
            f"audit_report: malformed JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ]
    if not isinstance(value, Mapping):
        return None, ["audit_report: must be a JSON object"]
    return value, []


def _audit_report_field_errors(
    expected: Mapping[str, Any],
    saved: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "version",
        "kind",
        "source",
        "result_status",
        "control_plane_boundary",
        "summary",
        "evidence_chain",
    ):
        if saved.get(field_name) != expected.get(field_name):
            errors.append(_field_mismatch(field_name, expected.get(field_name), saved.get(field_name)))

    expected_export = _mapping_or_empty(expected.get("export"))
    saved_export = _mapping_or_empty(saved.get("export"))
    if saved_export.get("exported_request_ids") != expected_export.get("exported_request_ids"):
        errors.append(
            _field_mismatch(
                "export.exported_request_ids",
                expected_export.get("exported_request_ids"),
                saved_export.get("exported_request_ids"),
            )
        )

    expected_manifest = _mapping_or_empty(expected.get("manifest"))
    saved_manifest = _mapping_or_empty(saved.get("manifest"))
    for field_name in ("package_digest", "item_request_ids"):
        if saved_manifest.get(field_name) != expected_manifest.get(field_name):
            errors.append(
                _field_mismatch(
                    f"manifest.{field_name}",
                    expected_manifest.get(field_name),
                    saved_manifest.get(field_name),
                )
            )

    expected_verification = _mapping_or_empty(expected.get("manifest_verification"))
    saved_verification = _mapping_or_empty(saved.get("manifest_verification"))
    for field_name in ("performed", "reason", "command", "result_status"):
        if saved_verification.get(field_name) != expected_verification.get(field_name):
            errors.append(
                _field_mismatch(
                    f"manifest_verification.{field_name}",
                    expected_verification.get(field_name),
                    saved_verification.get(field_name),
                )
            )
    return errors


def _audit_report_verification_items(
    expected_report: Mapping[str, Any] | None,
    saved_report: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    expected_handoffs = _handoff_list(expected_report)
    saved_handoffs = _handoff_list(saved_report)
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    matched = 0
    mismatched = 0
    missing = 0
    extra = 0

    max_length = max(len(expected_handoffs), len(saved_handoffs))
    for index in range(max_length):
        expected = expected_handoffs[index] if index < len(expected_handoffs) else None
        saved = saved_handoffs[index] if index < len(saved_handoffs) else None

        if expected is None:
            extra += 1
            mismatched += 1
            errors.append(
                f"handoffs[{index}]: unexpected saved handoff request_id {_display(_mapping_get(saved, 'request_id'))}"
            )
            items.append(_audit_report_verification_item(expected, saved, False))
            continue

        if saved is None:
            missing += 1
            mismatched += 1
            errors.append(
                f"handoffs[{index}]: missing saved handoff request_id {_display(expected.get('request_id'))}"
            )
            items.append(_audit_report_verification_item(expected, saved, False))
            continue

        item_errors = _handoff_item_errors(index, expected, saved)
        item_ok = not item_errors and _canonical_json(expected) == _canonical_json(saved)
        if item_ok:
            matched += 1
        else:
            mismatched += 1
            errors.extend(item_errors)
            if _canonical_json(expected) != _canonical_json(saved):
                errors.append(
                    f"handoffs[{index}]: canonical handoff differs from regenerated report"
                )
        items.append(_audit_report_verification_item(expected, saved, item_ok))

    summary = {
        "reports": _summary_int(expected_report, "reports"),
        "handoffs": len(expected_handoffs),
        "matched_handoffs": matched,
        "mismatched_handoffs": mismatched,
        "missing_handoffs": missing,
        "extra_handoffs": extra,
        "result_status": NOT_EXECUTED,
    }
    return items, summary, errors


def _handoff_item_errors(
    index: int,
    expected: Mapping[str, Any],
    saved: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for field_name in ("request_id", "handoff_status", "exported"):
        if saved.get(field_name) != expected.get(field_name):
            errors.append(
                _field_mismatch(
                    f"handoffs[{index}].{field_name}",
                    expected.get(field_name),
                    saved.get(field_name),
                )
            )
    return errors


def _audit_report_verification_item(
    expected: Mapping[str, Any] | None,
    saved: Mapping[str, Any] | None,
    ok: bool,
) -> dict[str, Any]:
    return {
        "kind": "enterprise_audit_report_verification_item",
        "request_id": _mapping_get(expected, "request_id")
        or _mapping_get(saved, "request_id"),
        "ok": ok,
        "expected_handoff_status": _mapping_get(expected, "handoff_status"),
        "saved_handoff_status": _mapping_get(saved, "handoff_status"),
        "expected_exported": _mapping_get(expected, "exported"),
        "saved_exported": _mapping_get(saved, "exported"),
        "result_status": NOT_EXECUTED,
    }


def _handoff_list(value: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    handoffs = value.get("handoffs")
    if not isinstance(handoffs, list):
        return []
    return [handoff for handoff in handoffs if isinstance(handoff, Mapping)]


def _summary_int(value: Mapping[str, Any] | None, field_name: str) -> int:
    summary = _mapping_or_empty(_mapping_get(value, "summary"))
    item = summary.get(field_name)
    if isinstance(item, int) and not isinstance(item, bool):
        return item
    return 0


def _mapping_get(value: Mapping[str, Any] | None, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _field_mismatch(path: str, expected: Any, saved: Any) -> str:
    return f"{path}: expected {_display(expected)}, got {_display(saved)}"


def _display(value: Any) -> str:
    return repr(value)


def _call_builder(label: str, builder, bus_root: str | Path, report: ValidationReport):
    try:
        payload, builder_report = builder(bus_root)
    except (YamlLoadError, ValueError, OSError) as exc:
        report.error(label, str(exc))
        return None
    _merge_prefixed(report, builder_report, label)
    if not builder_report.ok or payload is None:
        return None
    return payload


def _compose_report(
    inspection: Mapping[str, Any],
    package: Mapping[str, Any],
    manifest: Mapping[str, Any],
    report: ValidationReport,
) -> dict[str, Any] | None:
    inspection_summary = _mapping_or_empty(inspection.get("summary"))
    package_summary = _mapping_or_empty(package.get("summary"))
    manifest_summary = _mapping_or_empty(manifest.get("summary"))

    exported_request_ids = _request_ids(package.get("exports"), "package.exports", report)
    manifest_request_ids = _request_ids(manifest.get("items"), "manifest.items", report)
    if not report.ok:
        return None

    reports = _report_summaries(inspection.get("reports"), report)
    handoffs = _flatten_handoffs(inspection.get("reports"), set(exported_request_ids), report)
    if not report.ok:
        return None

    exported_handoffs = [handoff for handoff in handoffs if handoff.get("exported") is True]
    if [handoff.get("request_id") for handoff in exported_handoffs] != exported_request_ids:
        report.error("export.exported_request_ids", "must match handoff export order")
        return None
    for handoff in exported_handoffs:
        if handoff.get("handoff_status") != "handoff_ready":
            report.error(
                f"handoffs.{handoff.get('request_id')}.exported",
                "only handoff_ready items may be exported",
            )

    summary = {
        "reports": _int_value(package_summary.get("reports")),
        "total_handoffs": _int_value(package_summary.get("total_handoffs")),
        "handoff_ready": _int_value(inspection_summary.get("handoff_ready")),
        "exported": _int_value(package_summary.get("exported")),
        "blocked": _int_value(package_summary.get("blocked")),
        "unsupported": _int_value(package_summary.get("unsupported")),
        "result_status": _string_value(package_summary.get("result_status")),
    }
    if summary["result_status"] != NOT_EXECUTED:
        report.error("summary.result_status", "must be not_executed")

    audit_report = {
        "version": VERSION,
        "kind": "enterprise_audit_report",
        "source": "build_enterprise_audit_report",
        "result_status": NOT_EXECUTED,
        "control_plane_boundary": {
            "execution_occurred": False,
            "runtime_adapter_invoked": False,
            "execution_owner": "external",
            "result_status": NOT_EXECUTED,
        },
        "summary": summary,
        "evidence_chain": list(EVIDENCE_CHAIN),
        "reports": reports,
        "handoffs": handoffs,
        "export": {
            "kind": package.get("kind"),
            "source": package.get("source"),
            "result_status": package.get("result_status"),
            "summary": dict(package_summary),
            "exported_request_ids": exported_request_ids,
        },
        "manifest": {
            "kind": manifest.get("kind"),
            "source": manifest.get("source"),
            "result_status": manifest.get("result_status"),
            "package_kind": manifest.get("package_kind"),
            "package_digest": manifest.get("package_digest"),
            "summary": dict(manifest_summary),
            "item_request_ids": manifest_request_ids,
        },
        "manifest_verification": {
            "performed": False,
            "reason": "requires_saved_manifest_path",
            "command": _MANIFEST_VERIFICATION_COMMAND,
            "result_status": NOT_EXECUTED,
        },
    }
    return audit_report


def _report_summaries(value: Any, report: ValidationReport) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        report.error("inspection.reports", "must be a list")
        return []
    summaries: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            report.error(f"inspection.reports[{index}]", "must be a mapping")
            continue
        summary = _mapping_or_empty(item.get("summary"))
        summaries.append(
            {
                "path": item.get("path"),
                "task_id": item.get("task_id"),
                "objective_ref": item.get("objective_ref"),
                "attempt": item.get("attempt"),
                "result_status": item.get("result_status"),
                "summary": dict(summary),
            }
        )
    return summaries


def _flatten_handoffs(
    value: Any,
    exported_request_ids: set[str],
    report: ValidationReport,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        report.error("inspection.reports", "must be a list")
        return []
    handoffs: list[dict[str, Any]] = []
    for report_index, item in enumerate(value):
        if not isinstance(item, Mapping):
            report.error(f"inspection.reports[{report_index}]", "must be a mapping")
            continue
        report_path = item.get("path")
        report_handoffs = item.get("handoffs")
        if not isinstance(report_handoffs, list):
            report.error(f"inspection.reports[{report_index}].handoffs", "must be a list")
            continue
        for handoff_index, handoff in enumerate(report_handoffs):
            if not isinstance(handoff, Mapping):
                report.error(
                    f"inspection.reports[{report_index}].handoffs[{handoff_index}]",
                    "must be a mapping",
                )
                continue
            request_id = handoff.get("request_id")
            exported = isinstance(request_id, str) and request_id in exported_request_ids
            row = {
                "report_path": report_path,
                "task_id": item.get("task_id"),
                "objective_ref": item.get("objective_ref"),
                "attempt": item.get("attempt"),
                "request_id": request_id,
                "tool_name": handoff.get("tool_name"),
                "category": handoff.get("category"),
                "intent": handoff.get("intent"),
                "target_scope": handoff.get("target_scope"),
                "handoff_status": handoff.get("status"),
                "preflight_status": handoff.get("expected_preflight_decision"),
                "handoff_ready": handoff.get("handoff_ready") is True,
                "execution_allowed_by_preflight": handoff.get("execution_allowed_by_preflight"),
                "exported": exported,
                "result_status": handoff.get("result_status"),
            }
            if handoff.get("blocked_reason") is not None:
                row["blocked_reason"] = handoff.get("blocked_reason")
            if handoff.get("unsupported_reason") is not None:
                row["unsupported_reason"] = handoff.get("unsupported_reason")
            handoffs.append(row)
    return handoffs


def _request_ids(value: Any, path: str, report: ValidationReport) -> list[str]:
    if not isinstance(value, list):
        report.error(path, "must be a list")
        return []
    request_ids: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            report.error(f"{path}[{index}]", "must be a mapping")
            continue
        request_id = item.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            report.error(f"{path}[{index}].request_id", "must be a non-empty string")
            continue
        request_ids.append(request_id)
    return request_ids


def _validate_not_executed(value: Any, report: ValidationReport, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path != "$" else str(key)
            if key == "result_status" and item != NOT_EXECUTED:
                report.error(child_path, "must be not_executed")
            if isinstance(item, str) and key == "result_status" and item in RUNTIME_RESULT_STATUSES:
                report.error(child_path, "must not be a runtime execution status")
            _validate_not_executed(item, report, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_not_executed(item, report, f"{path}[{index}]")



_sanitize_message = sanitize_audit_message


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 0


def _string_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _merge_prefixed(
    target: ValidationReport, source: ValidationReport, prefix: str
) -> None:
    target.errors.extend(f"{prefix}.{error}" for error in source.errors)
    target.warnings.extend(f"{prefix}.{warning}" for warning in source.warnings)
