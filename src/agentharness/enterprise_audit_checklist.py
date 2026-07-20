"""Read-only enterprise audit checklist report for pre-execution evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .audit_contract import (
    NOT_EXECUTED,
    VERSION,
    contains_raw_audit_path,
    sanitize_audit_message,
)
from .enterprise_audit_report import build_enterprise_audit_report
from .handoff_exporter import build_handoff_export_package
from .handoff_inspector import inspect_handoff_bus
from .handoff_manifest import build_handoff_export_manifest
from .loop_bus import validate_bus
from .validate import ValidationReport
from .yamlio import YamlLoadError


_CHECK_FILE_BUS = "file_bus_validation"
_CHECK_HANDOFF_INSPECTION = "handoff_inspection"
_CHECK_REGISTRY_EXPORT = "registry_backed_export"
_CHECK_DIGEST_MANIFEST = "digest_manifest"
_CHECK_AUDIT_REPORT = "enterprise_audit_report"
_CHECK_SAVED_MANIFEST = "saved_manifest_readback"
_CHECK_SAVED_AUDIT_REPORT = "saved_audit_report_readback"
_PASS = "pass"
_FAIL = "fail"
_BLOCKED = "blocked"
_MANUAL = "manual"
_ALLOWED_CHECK_STATUSES = {_PASS, _FAIL, _BLOCKED, _MANUAL}
_CHECK_IDS = [
    _CHECK_FILE_BUS,
    _CHECK_HANDOFF_INSPECTION,
    _CHECK_REGISTRY_EXPORT,
    _CHECK_DIGEST_MANIFEST,
    _CHECK_AUDIT_REPORT,
    _CHECK_SAVED_MANIFEST,
    _CHECK_SAVED_AUDIT_REPORT,
]
_TOP_LEVEL_FIELDS = [
    "version",
    "kind",
    "source",
    "result_status",
    "ok",
    "goal",
    "summary",
    "checks",
    "errors",
    "warnings",
]
_GOAL_FIELDS = ["id", "status", "description"]
_SUMMARY_FIELDS = [
    "checks",
    "passed",
    "failed",
    "blocked",
    "manual",
    "reports",
    "total_handoffs",
    "handoff_ready",
    "exported",
    "blocked_handoffs",
    "unsupported",
]
_REQUIRED_SUMMARY_COUNT_FIELDS = ["checks", "passed", "failed", "blocked", "manual"]
_NULLABLE_SUMMARY_COUNT_FIELDS = [
    "reports",
    "total_handoffs",
    "handoff_ready",
    "exported",
    "blocked_handoffs",
    "unsupported",
]
_CHECK_BASE_FIELDS = ["id", "title", "status", "result_status", "errors", "warnings"]
_NON_MANUAL_CHECK_FIELDS = [*_CHECK_BASE_FIELDS, "evidence"]
_MANUAL_CHECK_FIELDS = [*_CHECK_BASE_FIELDS, "command"]
_MANUAL_COMMANDS = {
    _CHECK_SAVED_MANIFEST: "agentharness handoff verify-manifest <bus_root> <manifest_path>",
    _CHECK_SAVED_AUDIT_REPORT: "agentharness audit verify-report <bus_root> <audit_report_path>",
}


Builder = Callable[[str | Path], tuple[Mapping[str, Any] | None, ValidationReport]]


def build_enterprise_audit_checklist(bus_root: str | Path) -> dict[str, Any]:
    """Build a deterministic goal/check report over current evidence builders."""

    checks: list[dict[str, Any]] = []
    inspection: Mapping[str, Any] | None = None
    package: Mapping[str, Any] | None = None
    manifest: Mapping[str, Any] | None = None
    audit_report: Mapping[str, Any] | None = None

    bus_report = _call_validation_builder(validate_bus, bus_root)
    checks.append(
        _check(
            _CHECK_FILE_BUS,
            "file-bus validates",
            _PASS if bus_report.ok else _FAIL,
            evidence={"validated": bus_report.ok},
            errors=bus_report.errors,
            warnings=bus_report.warnings,
        )
    )

    if bus_report.ok:
        inspection, inspection_report = _call_payload_builder(
            inspect_handoff_bus, bus_root
        )
        checks.append(
            _check(
                _CHECK_HANDOFF_INSPECTION,
                "handoff report can be inspected",
                _PASS if inspection_report.ok and inspection is not None else _FAIL,
                evidence=_inspection_evidence(inspection),
                errors=inspection_report.errors,
                warnings=inspection_report.warnings,
            )
        )
    else:
        checks.append(_blocked_check(_CHECK_HANDOFF_INSPECTION, "handoff report can be inspected", _CHECK_FILE_BUS))

    if _check_passed(checks, _CHECK_HANDOFF_INSPECTION):
        package, export_report = _call_payload_builder(
            build_handoff_export_package, bus_root
        )
        checks.append(
            _check(
                _CHECK_REGISTRY_EXPORT,
                "ready requests export through registry-backed handoff evidence",
                _PASS if export_report.ok and package is not None else _FAIL,
                evidence=_export_evidence(package),
                errors=export_report.errors,
                warnings=export_report.warnings,
            )
        )
    else:
        checks.append(
            _blocked_check(
                _CHECK_REGISTRY_EXPORT,
                "ready requests export through registry-backed handoff evidence",
                _CHECK_HANDOFF_INSPECTION,
            )
        )

    if _check_passed(checks, _CHECK_REGISTRY_EXPORT):
        manifest, manifest_report = _call_payload_builder(
            build_handoff_export_manifest, bus_root
        )
        checks.append(
            _check(
                _CHECK_DIGEST_MANIFEST,
                "exported evidence has deterministic digest manifest",
                _PASS if manifest_report.ok and manifest is not None else _FAIL,
                evidence=_manifest_evidence(manifest),
                errors=manifest_report.errors,
                warnings=manifest_report.warnings,
            )
        )
    else:
        checks.append(
            _blocked_check(
                _CHECK_DIGEST_MANIFEST,
                "exported evidence has deterministic digest manifest",
                _CHECK_REGISTRY_EXPORT,
            )
        )

    if _check_passed(checks, _CHECK_DIGEST_MANIFEST):
        audit_report, audit_report_status = _call_payload_builder(
            build_enterprise_audit_report, bus_root
        )
        checks.append(
            _check(
                _CHECK_AUDIT_REPORT,
                "enterprise audit report builds and self-validates",
                _PASS if audit_report_status.ok and audit_report is not None else _FAIL,
                evidence=_audit_report_evidence(audit_report),
                errors=audit_report_status.errors,
                warnings=audit_report_status.warnings,
            )
        )
    else:
        checks.append(
            _blocked_check(
                _CHECK_AUDIT_REPORT,
                "enterprise audit report builds and self-validates",
                _CHECK_DIGEST_MANIFEST,
            )
        )

    checks.append(
        _manual_check(
            _CHECK_SAVED_MANIFEST,
            "saved manifest can be verified when reviewer provides a manifest path",
            "agentharness handoff verify-manifest <bus_root> <manifest_path>",
        )
    )
    checks.append(
        _manual_check(
            _CHECK_SAVED_AUDIT_REPORT,
            "saved audit report can be verified when reviewer provides an audit report path",
            "agentharness audit verify-report <bus_root> <audit_report_path>",
        )
    )

    errors = _top_level_errors(checks)
    warnings = _top_level_warnings(checks)
    ok = not errors and _status_count(checks, _FAIL) == 0 and _status_count(checks, _BLOCKED) == 0

    payload = {
        "version": VERSION,
        "kind": "enterprise_audit_checklist_report",
        "source": "build_enterprise_audit_checklist",
        "result_status": NOT_EXECUTED,
        "ok": ok,
        "goal": {
            "id": "pre_execution_evidence_review",
            "status": _PASS if ok else _FAIL,
            "description": "deterministic pre-execution evidence is ready for reviewer inspection",
        },
        "summary": _summary(checks, inspection, package, audit_report),
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
    self_check = validate_enterprise_audit_checklist_payload(payload)
    if not self_check.ok:
        return _self_check_failure_payload(payload, self_check)
    return payload


def validate_enterprise_audit_checklist_payload(payload: Any) -> ValidationReport:
    """Validate an enterprise audit checklist payload in memory only."""

    report = ValidationReport()
    if not isinstance(payload, Mapping):
        report.error("$", "payload must be a mapping")
        return report

    _validate_required_fields(payload, _TOP_LEVEL_FIELDS, report)
    _validate_no_unknown_fields(payload, _TOP_LEVEL_FIELDS, "$", report)
    if payload.get("version") != VERSION:
        report.error("version", f"must be {VERSION}")
    if payload.get("kind") != "enterprise_audit_checklist_report":
        report.error("kind", "must be enterprise_audit_checklist_report")
    if payload.get("source") != "build_enterprise_audit_checklist":
        report.error("source", "must be build_enterprise_audit_checklist")
    if payload.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")
    if not isinstance(payload.get("ok"), bool):
        report.error("ok", "must be a boolean")

    goal = _require_mapping(payload.get("goal"), "goal", report)
    if goal is not None:
        _validate_goal(goal, report)

    checks = _validate_checks(payload.get("checks"), report)
    summary = _require_mapping(payload.get("summary"), "summary", report)
    if summary is not None:
        _validate_summary(summary, checks, report)

    _validate_string_messages(payload.get("errors"), "errors", report)
    _validate_string_messages(payload.get("warnings"), "warnings", report)
    _validate_status_consistency(payload, checks, report)
    _validate_not_executed(payload, report)
    return report


def _validate_goal(goal: Mapping[str, Any], report: ValidationReport) -> None:
    _validate_required_fields(goal, _GOAL_FIELDS, report, "goal")
    _validate_no_unknown_fields(goal, _GOAL_FIELDS, "goal", report)
    if goal.get("id") != "pre_execution_evidence_review":
        report.error("goal.id", "must be pre_execution_evidence_review")
    if goal.get("status") not in {_PASS, _FAIL}:
        report.error("goal.status", "must be pass or fail")
    if not isinstance(goal.get("description"), str) or not goal.get("description"):
        report.error("goal.description", "must be a non-empty string")


def _validate_checks(value: Any, report: ValidationReport) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        report.error("checks", "must be a list")
        return []

    checks: list[Mapping[str, Any]] = []
    actual_ids: list[Any] = []
    for index, item in enumerate(value):
        path = f"checks[{index}]"
        if not isinstance(item, Mapping):
            report.error(path, "must be a mapping")
            continue
        checks.append(item)
        actual_ids.append(item.get("id"))
        _validate_check(item, path, report)

    if actual_ids != _CHECK_IDS:
        report.error("checks", "must contain required check IDs in deterministic order")
    if len(actual_ids) != len(set(actual_ids)):
        report.error("checks", "must not contain duplicate check IDs")
    return checks


def _validate_check(check: Mapping[str, Any], path: str, report: ValidationReport) -> None:
    status = check.get("status")
    fields = _MANUAL_CHECK_FIELDS if status == _MANUAL else _NON_MANUAL_CHECK_FIELDS
    _validate_required_fields(check, fields, report, path)
    _validate_no_unknown_fields(check, fields, path, report)

    check_id = check.get("id")
    if check_id not in _CHECK_IDS:
        report.error(f"{path}.id", "must be a known checklist check ID")
    if not isinstance(check.get("title"), str) or not check.get("title"):
        report.error(f"{path}.title", "must be a non-empty string")
    if status not in _ALLOWED_CHECK_STATUSES:
        report.error(f"{path}.status", "must be pass, fail, blocked, or manual")
    if check.get("result_status") != NOT_EXECUTED:
        report.error(f"{path}.result_status", "must be not_executed")

    _validate_string_messages(check.get("errors"), f"{path}.errors", report)
    _validate_string_messages(check.get("warnings"), f"{path}.warnings", report)

    if status == _MANUAL:
        command = check.get("command")
        if not isinstance(command, str) or not command:
            report.error(f"{path}.command", "manual checks require a non-empty command")
        elif isinstance(check_id, str) and _MANUAL_COMMANDS.get(check_id) != command:
            report.error(f"{path}.command", "must match the documented manual readback command")
        if "evidence" in check:
            report.error(f"{path}.evidence", "manual checks must not include evidence")
    else:
        if not isinstance(check.get("evidence"), Mapping):
            report.error(f"{path}.evidence", "non-manual checks require an evidence mapping")
        if "command" in check:
            report.error(f"{path}.command", "non-manual checks must not include command")


def _validate_summary(
    summary: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    report: ValidationReport,
) -> None:
    _validate_required_fields(summary, _SUMMARY_FIELDS, report, "summary")
    _validate_no_unknown_fields(summary, _SUMMARY_FIELDS, "summary", report)
    for field_name in _REQUIRED_SUMMARY_COUNT_FIELDS:
        _validate_non_negative_int(summary.get(field_name), f"summary.{field_name}", report)
    for field_name in _NULLABLE_SUMMARY_COUNT_FIELDS:
        value = summary.get(field_name)
        if value is not None:
            _validate_non_negative_int(value, f"summary.{field_name}", report)

    expected_counts = {
        "checks": len(checks),
        "passed": _status_count(checks, _PASS),
        "failed": _status_count(checks, _FAIL),
        "blocked": _status_count(checks, _BLOCKED),
        "manual": _status_count(checks, _MANUAL),
    }
    for field_name, expected_value in expected_counts.items():
        if summary.get(field_name) != expected_value:
            report.error(f"summary.{field_name}", f"must be {expected_value}")


def _validate_status_consistency(
    payload: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    report: ValidationReport,
) -> None:
    failed = _status_count(checks, _FAIL)
    blocked = _status_count(checks, _BLOCKED)
    top_level_errors = payload.get("errors")
    top_level_errors_present = not isinstance(top_level_errors, list) or len(top_level_errors) > 0
    expected_ok = not top_level_errors_present and failed == 0 and blocked == 0
    if isinstance(payload.get("ok"), bool) and payload.get("ok") is not expected_ok:
        report.error("ok", f"must be {expected_ok}")
    goal = payload.get("goal")
    if isinstance(goal, Mapping):
        expected_goal_status = _PASS if expected_ok else _FAIL
        if goal.get("status") != expected_goal_status:
            report.error("goal.status", f"must be {expected_goal_status} when ok is {expected_ok}")


def _validate_not_executed(value: Any, report: ValidationReport, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path != "$" else str(key)
            if key == "result_status" and item != NOT_EXECUTED:
                report.error(child_path, "must be not_executed")
            _validate_not_executed(item, report, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_not_executed(item, report, f"{path}[{index}]")


def _validate_string_messages(value: Any, path: str, report: ValidationReport) -> None:
    if not isinstance(value, list):
        report.error(path, "must be a list")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str):
            report.error(item_path, "must be a string")
            continue
        if contains_raw_audit_path(item):
            report.error(item_path, "must not contain raw host paths")


def _validate_required_fields(
    value: Mapping[str, Any],
    fields: Sequence[str],
    report: ValidationReport,
    path: str = "$",
) -> None:
    for field_name in fields:
        if field_name not in value:
            field_path = field_name if path == "$" else f"{path}.{field_name}"
            report.error(field_path, "missing required field")


def _validate_no_unknown_fields(
    value: Mapping[str, Any],
    allowed_fields: Sequence[str],
    path: str,
    report: ValidationReport,
) -> None:
    allowed = set(allowed_fields)
    for field_name in value:
        if field_name not in allowed:
            field_path = field_name if path == "$" else f"{path}.{field_name}"
            report.error(field_path, "unknown field")


def _require_mapping(value: Any, path: str, report: ValidationReport) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        report.error(path, "must be a mapping")
        return None
    return value


def _validate_non_negative_int(value: Any, path: str, report: ValidationReport) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        report.error(path, "must be an integer")
    elif value < 0:
        report.error(path, "must be non-negative")


def _self_check_failure_payload(
    payload: Mapping[str, Any], report: ValidationReport
) -> dict[str, Any]:
    failure = dict(payload)
    failure["ok"] = False
    goal = dict(_mapping_or_empty(failure.get("goal")))
    goal["status"] = _FAIL
    failure["goal"] = goal
    errors = list(_list_or_empty(failure.get("errors")))
    errors.extend(f"checklist_schema.self_check: {error}" for error in report.errors)
    failure["errors"] = _sanitize_check_messages(
        [error for error in errors if isinstance(error, str)]
    )
    failure["warnings"] = _sanitize_check_messages(
        [warning for warning in _list_or_empty(failure.get("warnings")) if isinstance(warning, str)]
    )
    return failure


def _call_validation_builder(
    builder: Callable[[str | Path], ValidationReport], bus_root: str | Path
) -> ValidationReport:
    try:
        return builder(bus_root)
    except (YamlLoadError, ValueError, OSError) as exc:
        report = ValidationReport()
        report.error("file_bus_validation", str(exc))
        return report


def _call_payload_builder(
    builder: Builder,
    bus_root: str | Path,
) -> tuple[Mapping[str, Any] | None, ValidationReport]:
    try:
        payload, report = builder(bus_root)
    except (YamlLoadError, ValueError, OSError) as exc:
        report = ValidationReport()
        report.error("builder", str(exc))
        return None, report
    return payload, report


def _check(
    check_id: str,
    title: str,
    status: str,
    *,
    evidence: Mapping[str, Any] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "result_status": NOT_EXECUTED,
        "evidence": dict(evidence or {}),
        "errors": _sanitize_check_messages(errors or []),
        "warnings": _sanitize_check_messages(warnings or []),
    }


def _blocked_check(check_id: str, title: str, prerequisite: str) -> dict[str, Any]:
    return _check(
        check_id,
        title,
        _BLOCKED,
        errors=[f"prerequisite {prerequisite} did not pass"],
    )


def _manual_check(check_id: str, title: str, command: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "status": _MANUAL,
        "result_status": NOT_EXECUTED,
        "command": command,
        "errors": [],
        "warnings": [],
    }


def _inspection_evidence(inspection: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = _mapping_or_empty(_mapping_get(inspection, "summary"))
    return {
        "reports": _int_or_none(summary.get("reports")),
        "total_handoffs": _int_or_none(summary.get("total")),
        "handoff_ready": _int_or_none(summary.get("handoff_ready")),
        "blocked_handoffs": _int_or_none(summary.get("blocked")),
        "unsupported": _int_or_none(summary.get("unsupported")),
        "result_status": summary.get("result_status"),
    }


def _export_evidence(package: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = _mapping_or_empty(_mapping_get(package, "summary"))
    exports = _list_or_empty(_mapping_get(package, "exports"))
    return {
        "package_kind": _mapping_get(package, "kind"),
        "source": _mapping_get(package, "source"),
        "reports": _int_or_none(summary.get("reports")),
        "total_handoffs": _int_or_none(summary.get("total_handoffs")),
        "exported": _int_or_none(summary.get("exported")),
        "blocked_handoffs": _int_or_none(summary.get("blocked")),
        "unsupported": _int_or_none(summary.get("unsupported")),
        "result_status": _mapping_get(package, "result_status"),
        "exported_request_ids": _request_ids(exports),
    }


def _manifest_evidence(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    items = _list_or_empty(_mapping_get(manifest, "items"))
    return {
        "manifest_kind": _mapping_get(manifest, "kind"),
        "source": _mapping_get(manifest, "source"),
        "package_kind": _mapping_get(manifest, "package_kind"),
        "package_digest": _mapping_get(manifest, "package_digest"),
        "result_status": _mapping_get(manifest, "result_status"),
        "item_request_ids": _request_ids(items),
    }


def _audit_report_evidence(audit_report: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = _mapping_or_empty(_mapping_get(audit_report, "summary"))
    manifest_verification = _mapping_or_empty(
        _mapping_get(audit_report, "manifest_verification")
    )
    return {
        "report_kind": _mapping_get(audit_report, "kind"),
        "source": _mapping_get(audit_report, "source"),
        "result_status": _mapping_get(audit_report, "result_status"),
        "summary": dict(summary),
        "manifest_verification": dict(manifest_verification),
    }


def _summary(
    checks: Sequence[Mapping[str, Any]],
    inspection: Mapping[str, Any] | None,
    package: Mapping[str, Any] | None,
    audit_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    counts = _best_counts(inspection, package, audit_report)
    return {
        "checks": len(checks),
        "passed": _status_count(checks, _PASS),
        "failed": _status_count(checks, _FAIL),
        "blocked": _status_count(checks, _BLOCKED),
        "manual": _status_count(checks, _MANUAL),
        "reports": counts.get("reports"),
        "total_handoffs": counts.get("total_handoffs"),
        "handoff_ready": counts.get("handoff_ready"),
        "exported": counts.get("exported"),
        "blocked_handoffs": counts.get("blocked_handoffs"),
        "unsupported": counts.get("unsupported"),
    }


def _best_counts(
    inspection: Mapping[str, Any] | None,
    package: Mapping[str, Any] | None,
    audit_report: Mapping[str, Any] | None,
) -> dict[str, int | None]:
    audit_summary = _mapping_or_empty(_mapping_get(audit_report, "summary"))
    if audit_summary:
        return {
            "reports": _int_or_none(audit_summary.get("reports")),
            "total_handoffs": _int_or_none(audit_summary.get("total_handoffs")),
            "handoff_ready": _int_or_none(audit_summary.get("handoff_ready")),
            "exported": _int_or_none(audit_summary.get("exported")),
            "blocked_handoffs": _int_or_none(audit_summary.get("blocked")),
            "unsupported": _int_or_none(audit_summary.get("unsupported")),
        }

    package_summary = _mapping_or_empty(_mapping_get(package, "summary"))
    if package_summary:
        return {
            "reports": _int_or_none(package_summary.get("reports")),
            "total_handoffs": _int_or_none(package_summary.get("total_handoffs")),
            "handoff_ready": _int_or_none(package_summary.get("exported")),
            "exported": _int_or_none(package_summary.get("exported")),
            "blocked_handoffs": _int_or_none(package_summary.get("blocked")),
            "unsupported": _int_or_none(package_summary.get("unsupported")),
        }

    inspection_summary = _mapping_or_empty(_mapping_get(inspection, "summary"))
    if inspection_summary:
        return {
            "reports": _int_or_none(inspection_summary.get("reports")),
            "total_handoffs": _int_or_none(inspection_summary.get("total")),
            "handoff_ready": _int_or_none(inspection_summary.get("handoff_ready")),
            "exported": None,
            "blocked_handoffs": _int_or_none(inspection_summary.get("blocked")),
            "unsupported": _int_or_none(inspection_summary.get("unsupported")),
        }

    return {
        "reports": None,
        "total_handoffs": None,
        "handoff_ready": None,
        "exported": None,
        "blocked_handoffs": None,
        "unsupported": None,
    }


def _check_passed(checks: Sequence[Mapping[str, Any]], check_id: str) -> bool:
    for check in checks:
        if check.get("id") == check_id:
            return check.get("status") == _PASS
    return False


def _status_count(checks: Sequence[Mapping[str, Any]], status: str) -> int:
    return sum(1 for check in checks if check.get("status") == status)


def _top_level_errors(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    for check in checks:
        if check.get("status") in {_FAIL, _BLOCKED}:
            for error in _list_or_empty(check.get("errors")):
                if isinstance(error, str):
                    errors.append(f"{check.get('id')}: {error}")
    return errors


def _top_level_warnings(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for check in checks:
        for warning in _list_or_empty(check.get("warnings")):
            if isinstance(warning, str):
                warnings.append(f"{check.get('id')}: {warning}")
    return warnings


def _sanitize_check_messages(values: list[str]) -> list[str]:
    return [sanitize_audit_message(value) for value in values]


def _mapping_get(value: Mapping[str, Any] | None, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _list_or_empty(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _request_ids(items: list[Any]) -> list[str]:
    request_ids: list[str] = []
    for item in items:
        if isinstance(item, Mapping) and isinstance(item.get("request_id"), str):
            request_ids.append(item["request_id"])
    return request_ids


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None
