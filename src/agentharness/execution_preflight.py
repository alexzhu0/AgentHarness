"""Side-effect-free execution preflight decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .approval_record import approval_subject_digest, validate_approval_record
from .validate import ValidationReport


NOT_EXECUTED = "not_executed"
PREFLIGHT_DECISIONS = {
    "ready_without_approval",
    "ready_with_approval",
    "blocked_missing_approval",
    "blocked_rejected_approval",
    "blocked_by_policy",
    "invalid_subject",
}


def approval_record_digest(approval_record: Mapping[str, Any]) -> str:
    """Return a stable digest for an approval record artifact."""

    payload = json.dumps(
        approval_record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_execution_preflight_decision(
    tool_gate_entry: Mapping[str, Any],
    approval_record: Mapping[str, Any] | None = None,
    expected_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a side-effect-free execution eligibility decision."""

    request_id = _string(tool_gate_entry.get("request_id"), "unknown")
    tool_decision = _mapping_or_empty(tool_gate_entry.get("decision"))
    gate_decision = tool_decision.get("decision")
    approval_decision = _approval_decision(approval_record)
    subject = {
        "tool_gate_decision": gate_decision,
        "tool_gate_digest": approval_subject_digest(tool_gate_entry),
        "approval_decision": approval_decision,
        "approval_digest": approval_record_digest(approval_record)
        if isinstance(approval_record, Mapping)
        else None,
    }
    scope = _scope_from_tool_decision(tool_decision)

    if gate_decision == "deny":
        return _decision(
            request_id,
            "blocked_by_policy",
            False,
            "Tool gate policy denied this request.",
            subject,
            scope,
        )
    if gate_decision == "allow":
        if approval_record is not None:
            return _decision(
                request_id,
                "invalid_subject",
                False,
                "Allow decisions must not be broadened with approval records.",
                subject,
                scope,
            )
        return _decision(
            request_id,
            "ready_without_approval",
            True,
            "Tool gate policy allows this request without approval.",
            subject,
            scope,
        )
    if gate_decision != "approval_required":
        return _decision(
            request_id,
            "invalid_subject",
            False,
            "Tool gate entry does not contain a recognized policy decision.",
            subject,
            scope,
        )
    if approval_record is None:
        return _decision(
            request_id,
            "blocked_missing_approval",
            False,
            "Approval-required request has no approval record.",
            subject,
            scope,
        )
    if not _has_complete_expected_context(expected_context):
        return _decision(
            request_id,
            "invalid_subject",
            False,
            "Approval record requires complete expected context.",
            subject,
            scope,
        )

    approval_validation = validate_approval_record(
        approval_record,
        {"decisions": [tool_gate_entry]},
        expected_context,
    )
    if not approval_validation.ok:
        return _decision(
            request_id,
            "invalid_subject",
            False,
            "Approval record is not valid for this tool gate entry.",
            subject,
            scope,
        )
    if approval_record.get("decision") == "approved":
        return _decision(
            request_id,
            "ready_with_approval",
            True,
            "Valid user approval record is bound to this approval-required request.",
            subject,
            scope,
        )
    if approval_record.get("decision") == "rejected":
        return _decision(
            request_id,
            "blocked_rejected_approval",
            False,
            "User approval record rejected this approval-required request.",
            subject,
            scope,
        )
    return _decision(
        request_id,
        "invalid_subject",
        False,
        "Approval record decision is not recognized.",
        subject,
        scope,
    )


def build_execution_preflight_report(
    tool_gate_report: Mapping[str, Any],
    approval_records: Mapping[str, Mapping[str, Any]] | list[Mapping[str, Any]] | None = None,
    tool_gate_report_path: str | None = None,
    expected_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a side-effect-free preflight report for a tool gate report."""

    approvals_by_request = _approval_records_by_request(approval_records)
    decision_context = expected_context or _expected_context_from_tool_gate_report(
        tool_gate_report,
        tool_gate_report_path,
    )
    decisions = []
    counts = {"execution_allowed": 0, "blocked": 0, "invalid": 0}
    for entry in _decision_entries(tool_gate_report):
        request_id = _string(entry.get("request_id"), "unknown")
        preflight = build_execution_preflight_decision(
            entry,
            approvals_by_request.get(request_id),
            decision_context,
        )
        decisions.append(preflight)
        if preflight["execution_allowed"]:
            counts["execution_allowed"] += 1
        else:
            counts["blocked"] += 1
        if preflight["decision"] == "invalid_subject":
            counts["invalid"] += 1

    return {
        "version": "0.1.0",
        "kind": "execution_preflight_report",
        "task_id": tool_gate_report.get("task_id"),
        "objective_ref": tool_gate_report.get("objective_ref"),
        "attempt": tool_gate_report.get("attempt"),
        "source": "build_execution_preflight_decision",
        "tool_gate_report_path": tool_gate_report_path,
        "summary": {
            "total": len(decisions),
            "execution_allowed": counts["execution_allowed"],
            "blocked": counts["blocked"],
            "invalid": counts["invalid"],
            "result_status": NOT_EXECUTED,
        },
        "decisions": decisions,
    }


def validate_execution_preflight_decision(
    preflight_decision: Mapping[str, Any],
    tool_gate_entry: Mapping[str, Any],
    approval_record: Mapping[str, Any] | None = None,
    expected_context: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Validate a preflight decision by recomputing it from trusted inputs."""

    report = ValidationReport()
    if not isinstance(preflight_decision, Mapping):
        report.error("$", "preflight decision must be a mapping")
        return report

    if preflight_decision.get("kind") != "execution_preflight_decision":
        report.error("kind", "must be execution_preflight_decision")
    if preflight_decision.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")
    if preflight_decision.get("decision") not in PREFLIGHT_DECISIONS:
        report.error("decision", "must be a known preflight decision")

    expected = build_execution_preflight_decision(
        tool_gate_entry,
        approval_record,
        expected_context,
    )
    for field_name in (
        "kind",
        "request_id",
        "result_status",
        "decision",
        "execution_allowed",
        "reason",
        "subject",
        "scope",
    ):
        if preflight_decision.get(field_name) != expected.get(field_name):
            report.error(field_name, "must match computed preflight decision")
    return report


def validate_execution_preflight_report(
    preflight_report: Mapping[str, Any],
    tool_gate_report: Mapping[str, Any],
    approval_records: Mapping[str, Mapping[str, Any]] | list[Mapping[str, Any]] | None = None,
    expected_context: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Validate a preflight report by recomputing each decision."""

    report = ValidationReport()
    if not isinstance(preflight_report, Mapping):
        report.error("$", "preflight report must be a mapping")
        return report
    if not isinstance(tool_gate_report, Mapping):
        report.error("tool_gate_report", "must be a mapping")
        return report

    if preflight_report.get("kind") != "execution_preflight_report":
        report.error("kind", "must be execution_preflight_report")
    if preflight_report.get("source") != "build_execution_preflight_decision":
        report.error("source", "must be build_execution_preflight_decision")
    decision_context = expected_context or _expected_context_from_tool_gate_report(
        tool_gate_report,
        _string_or_none(preflight_report.get("tool_gate_report_path")),
    )
    _validate_report_context(preflight_report, decision_context, report)

    summary = _mapping(preflight_report.get("summary"), "summary", report)
    decisions = preflight_report.get("decisions")
    if not isinstance(decisions, list):
        report.error("decisions", "must be a list")
        decisions = []

    approvals_by_request = _approval_records_by_request(approval_records)
    gate_entries = _decision_entries(tool_gate_report)
    gate_entries_by_request = {
        entry.get("request_id"): entry
        for entry in gate_entries
        if isinstance(entry.get("request_id"), str)
    }
    for request_id in approvals_by_request:
        if request_id not in gate_entries_by_request:
            report.error(
                f"approval_records.{request_id}",
                "must reference a tool gate report entry",
            )

    expected_report = build_execution_preflight_report(
        tool_gate_report,
        approvals_by_request,
        tool_gate_report_path=decision_context.get("tool_gate_report_path"),
        expected_context=decision_context,
    )
    expected_counts = expected_report["summary"]
    if summary:
        for field_name in (
            "total",
            "execution_allowed",
            "blocked",
            "invalid",
            "result_status",
        ):
            if summary.get(field_name) != expected_counts.get(field_name):
                report.error(f"summary.{field_name}", "must match computed preflight report")

    seen_request_ids: set[str] = set()
    decisions_by_request: dict[str, Mapping[str, Any]] = {}
    for index, decision in enumerate(decisions):
        if not isinstance(decision, Mapping):
            report.error(f"decisions[{index}]", "must be a mapping")
            continue
        request_id = decision.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            report.error(f"decisions[{index}].request_id", "must be a non-empty string")
            continue
        if request_id in seen_request_ids:
            report.error(f"decisions[{index}].request_id", "must be unique")
        seen_request_ids.add(request_id)
        decisions_by_request[request_id] = decision

    for request_id, entry in gate_entries_by_request.items():
        if request_id not in decisions_by_request:
            report.error(f"decisions.{request_id}", "missing preflight decision")
            continue
        approval_record = approvals_by_request.get(request_id)
        if approval_record is not None:
            approval_report = validate_approval_record(
                approval_record,
                {"decisions": [entry]},
                decision_context,
            )
            _merge_prefixed(report, approval_report, f"approval_records.{request_id}")
        decision_report = validate_execution_preflight_decision(
            decisions_by_request[request_id],
            entry,
            approval_record,
            decision_context,
        )
        _merge_prefixed(report, decision_report, f"decisions.{request_id}")

    for request_id in decisions_by_request:
        if request_id not in gate_entries_by_request:
            report.error(
                f"decisions.{request_id}",
                "must reference a tool gate report entry",
            )

    return report


def _decision(
    request_id: str,
    decision: str,
    execution_allowed: bool,
    reason: str,
    subject: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "version": "0.1.0",
        "kind": "execution_preflight_decision",
        "request_id": request_id,
        "result_status": NOT_EXECUTED,
        "decision": decision,
        "execution_allowed": execution_allowed,
        "reason": reason,
        "subject": dict(subject),
        "scope": dict(scope),
    }


def _expected_context_from_tool_gate_report(
    tool_gate_report: Mapping[str, Any],
    tool_gate_report_path: str | None,
) -> dict[str, Any]:
    return {
        "task_id": tool_gate_report.get("task_id"),
        "objective_ref": tool_gate_report.get("objective_ref"),
        "attempt": tool_gate_report.get("attempt"),
        "tool_gate_report_path": tool_gate_report_path,
    }


def _has_complete_expected_context(
    expected_context: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(expected_context, Mapping):
        return False
    return (
        isinstance(expected_context.get("task_id"), str)
        and bool(expected_context.get("task_id"))
        and isinstance(expected_context.get("objective_ref"), str)
        and bool(expected_context.get("objective_ref"))
        and isinstance(expected_context.get("attempt"), int)
        and expected_context.get("attempt") >= 1
        and isinstance(expected_context.get("tool_gate_report_path"), str)
        and bool(expected_context.get("tool_gate_report_path"))
    )


def _scope_from_tool_decision(tool_decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tool_name": tool_decision.get("tool_name"),
        "category": tool_decision.get("category"),
        "intent": tool_decision.get("intent"),
        "target_scope": tool_decision.get("target_scope"),
    }


def _approval_decision(approval_record: Mapping[str, Any] | None) -> Any:
    if isinstance(approval_record, Mapping):
        return approval_record.get("decision")
    return None


def _approval_records_by_request(
    approval_records: Mapping[str, Mapping[str, Any]] | list[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    if approval_records is None:
        return {}
    if isinstance(approval_records, Mapping):
        return {
            request_id: record
            for request_id, record in approval_records.items()
            if isinstance(request_id, str) and isinstance(record, Mapping)
        }
    by_request: dict[str, Mapping[str, Any]] = {}
    for record in approval_records:
        if not isinstance(record, Mapping):
            continue
        subject = record.get("subject")
        if isinstance(subject, Mapping) and isinstance(subject.get("request_id"), str):
            by_request[subject["request_id"]] = record
    return by_request


def _decision_entries(tool_gate_report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    decisions = tool_gate_report.get("decisions")
    if not isinstance(decisions, list):
        return []
    return [entry for entry in decisions if isinstance(entry, Mapping)]


def _validate_report_context(
    preflight_report: Mapping[str, Any],
    expected_context: Mapping[str, Any],
    report: ValidationReport,
) -> None:
    for field_name in ("task_id", "objective_ref", "attempt"):
        value = preflight_report.get(field_name)
        if field_name == "attempt":
            if not isinstance(value, int) or value < 1:
                report.error(field_name, "must be a positive integer")
        elif not isinstance(value, str) or not value:
            report.error(field_name, "must be a non-empty string")
        if field_name in expected_context and value != expected_context[field_name]:
            report.error(field_name, "must match ledger event")

    if "tool_gate_report_path" in expected_context and (
        preflight_report.get("tool_gate_report_path")
        != expected_context["tool_gate_report_path"]
    ):
        report.error("tool_gate_report_path", "must match ledger tool gate report")


def _mapping(value: Any, path: str, report: ValidationReport) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        report.error(path, "must be a mapping")
        return None
    return value


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string(value: Any, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _merge_prefixed(
    target: ValidationReport, source: ValidationReport, prefix: str
) -> None:
    target.errors.extend(f"{prefix}.{error}" for error in source.errors)
    target.warnings.extend(f"{prefix}.{warning}" for warning in source.warnings)
