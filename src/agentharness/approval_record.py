"""Approval record building and validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .validate import ValidationReport


APPROVER_ACTORS = {"user"}
APPROVAL_RECORD_DECISIONS = {"approved", "rejected"}
APPROVAL_REQUIRED = "approval_required"
NOT_EXECUTED = "not_executed"


def approval_subject_digest(tool_gate_entry: Mapping[str, Any]) -> str:
    """Return a stable digest for the immutable approval subject."""

    subject = {
        "request_id": tool_gate_entry.get("request_id"),
        "request": tool_gate_entry.get("request"),
        "decision": tool_gate_entry.get("decision"),
        "gate": tool_gate_entry.get("gate"),
    }
    payload = json.dumps(
        subject,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_approval_record(
    task_context: Mapping[str, Any],
    tool_gate_report: Mapping[str, Any],
    request_id: str,
    approver: Mapping[str, Any],
    decision: str = "approved",
    reason: str = "User approved the approval-required tool request.",
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    """Build a side-effect-free approval record for one approval-gated request."""

    entry = _find_tool_gate_entry(tool_gate_report, request_id)
    if entry is None:
        raise ValueError(f"request_id not found in tool gate report: {request_id}")
    tool_decision = _mapping_or_empty(entry.get("decision"))
    return {
        "version": "0.1.0",
        "kind": "approval_record",
        "approval_id": task_context.get("approval_id", f"APR-{request_id}"),
        "task_id": task_context.get("task_id"),
        "objective_ref": task_context.get("objective_ref"),
        "attempt": task_context.get("attempt"),
        "decision": decision,
        "result_status": NOT_EXECUTED,
        "approver": dict(approver),
        "subject": {
            "tool_gate_report_path": task_context.get("tool_gate_report_path"),
            "request_id": request_id,
            "decision_digest": approval_subject_digest(entry),
            "expected_decision": APPROVAL_REQUIRED,
        },
        "scope": {
            "tool_name": tool_decision.get("tool_name"),
            "category": tool_decision.get("category"),
            "intent": tool_decision.get("intent"),
            "target_scope": tool_decision.get("target_scope"),
            "constraints": constraints
            or [
                "approval_does_not_execute_tool",
                "approval_does_not_change_task_lifecycle",
            ],
        },
        "reason": reason,
    }


def validate_approval_record(
    approval_record: Mapping[str, Any],
    tool_gate_report: Mapping[str, Any],
    expected_context: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Validate an approval record against a validated tool gate report."""

    report = ValidationReport()
    if not isinstance(approval_record, Mapping):
        report.error("$", "approval record must be a mapping")
        return report
    if not isinstance(tool_gate_report, Mapping):
        report.error("tool_gate_report", "must be a mapping")
        return report

    if approval_record.get("kind") != "approval_record":
        report.error("kind", "must be approval_record")
    if approval_record.get("decision") not in APPROVAL_RECORD_DECISIONS:
        report.error("decision", "must be approved or rejected")
    if approval_record.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")

    _validate_context(approval_record, expected_context or {}, report)

    approver = _mapping(approval_record.get("approver"), "approver", report)
    if approver:
        if approver.get("actor") not in APPROVER_ACTORS:
            report.error("approver.actor", "must be user")

    subject = _mapping(approval_record.get("subject"), "subject", report)
    scope = _mapping(approval_record.get("scope"), "scope", report)
    if not isinstance(approval_record.get("reason"), str) or not approval_record.get(
        "reason", ""
    ).strip():
        report.error("reason", "must be a non-empty string")

    if not subject:
        return report

    if not isinstance(subject.get("tool_gate_report_path"), str) or not subject.get(
        "tool_gate_report_path"
    ):
        report.error("subject.tool_gate_report_path", "must be a non-empty string")
    if not isinstance(subject.get("decision_digest"), str) or not subject.get(
        "decision_digest"
    ):
        report.error("subject.decision_digest", "must be a non-empty string")

    expected_tool_gate_path = (expected_context or {}).get("tool_gate_report_path")
    if (
        expected_tool_gate_path is not None
        and subject.get("tool_gate_report_path") != expected_tool_gate_path
    ):
        report.error("subject.tool_gate_report_path", "must match ledger tool gate report")

    request_id = subject.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        report.error("subject.request_id", "must be a non-empty string")
        return report

    if subject.get("expected_decision") != APPROVAL_REQUIRED:
        report.error("subject.expected_decision", "must be approval_required")

    entry = _find_tool_gate_entry(tool_gate_report, request_id)
    if entry is None:
        report.error("subject.request_id", "must reference a tool gate report entry")
        return report

    entry_decision = _mapping_or_empty(entry.get("decision"))
    actual_decision = entry_decision.get("decision")
    if actual_decision != APPROVAL_REQUIRED:
        report.error(
            "subject.request_id",
            "approval can only bind approval_required tool gate entries",
        )

    expected_digest = approval_subject_digest(entry)
    if subject.get("decision_digest") != expected_digest:
        report.error("subject.decision_digest", "must match approval subject digest")

    if scope:
        _validate_scope(scope, entry_decision, report)

    return report


def _validate_context(
    approval_record: Mapping[str, Any],
    expected_context: Mapping[str, Any],
    report: ValidationReport,
) -> None:
    for field_name in ("task_id", "objective_ref", "attempt"):
        value = approval_record.get(field_name)
        if field_name == "attempt":
            if not isinstance(value, int) or value < 1:
                report.error(field_name, "must be a positive integer")
        elif not isinstance(value, str) or not value:
            report.error(field_name, "must be a non-empty string")

        if field_name in expected_context and value != expected_context[field_name]:
            report.error(field_name, "must match ledger event")


def _validate_scope(
    scope: Mapping[str, Any],
    entry_decision: Mapping[str, Any],
    report: ValidationReport,
) -> None:
    for field_name in ("tool_name", "category", "intent", "target_scope"):
        if scope.get(field_name) != entry_decision.get(field_name):
            report.error(f"scope.{field_name}", "must match tool gate decision")
    constraints = scope.get("constraints")
    if not isinstance(constraints, list) or not constraints:
        report.error("scope.constraints", "must be a non-empty list")
    elif not all(isinstance(item, str) and item for item in constraints):
        report.error("scope.constraints", "must contain non-empty strings")


def _find_tool_gate_entry(
    tool_gate_report: Mapping[str, Any], request_id: str
) -> Mapping[str, Any] | None:
    decisions = tool_gate_report.get("decisions")
    if not isinstance(decisions, list):
        return None
    for entry in decisions:
        if isinstance(entry, Mapping) and entry.get("request_id") == request_id:
            return entry
    return None


def _mapping(value: Any, path: str, report: ValidationReport) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        report.error(path, "must be a mapping")
        return None
    return value


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}
