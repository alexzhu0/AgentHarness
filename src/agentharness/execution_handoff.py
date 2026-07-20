"""Side-effect-free execution handoff decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .approval_record import approval_subject_digest, validate_approval_record
from .execution_preflight import (
    approval_record_digest,
    validate_execution_preflight_report,
)
from .tool_gate import validate_tool_gate_report
from .validate import ValidationReport


NOT_EXECUTED = "not_executed"
READY_PREFLIGHT_DECISIONS = {"ready_without_approval", "ready_with_approval"}
SUPPORT_FIELD_MAP = {
    "tool_name": "tool_names",
    "category": "categories",
    "intent": "intents",
    "target_scope": "target_scopes",
}


def preflight_decision_digest(preflight_decision: Mapping[str, Any]) -> str:
    """Return a stable digest for the full preflight decision mapping."""

    return _canonical_digest(preflight_decision)


def execution_handoff_digest(handoff: Mapping[str, Any]) -> str:
    """Return a stable digest for a complete execution handoff mapping."""

    return _canonical_digest(handoff)


def build_execution_handoff(
    tool_gate_entry: Mapping[str, Any],
    preflight_decision: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    task_context: Mapping[str, Any] | None = None,
    approval_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one side-effect-free handoff artifact for a tool request."""

    context = task_context or {}
    request_id = _string(tool_gate_entry.get("request_id"), "unknown")
    decision_scope = _request_scope(tool_gate_entry, preflight_decision)
    gate = _gate_for_handoff(tool_gate_entry, preflight_decision, adapter_spec, context)
    approval_path = _string_or_none(context.get("approval_record_path"))
    return {
        "version": "0.1.0",
        "kind": "execution_handoff",
        "handoff_id": _string(context.get("handoff_id"), f"HOFF-{request_id}"),
        "task_id": context.get("task_id"),
        "objective_ref": context.get("objective_ref"),
        "attempt": context.get("attempt"),
        "request_id": request_id,
        "result_status": NOT_EXECUTED,
        "source": "build_execution_handoff",
        "subject": {
            "tool_gate_report_path": context.get("tool_gate_report_path"),
            "preflight_report_path": context.get("preflight_report_path"),
            "approval_record_path": approval_path,
            "tool_gate_digest": approval_subject_digest(tool_gate_entry),
            "preflight_digest": preflight_decision_digest(preflight_decision),
            "approval_digest": approval_record_digest(approval_record)
            if isinstance(approval_record, Mapping)
            else None,
            "expected_preflight_decision": preflight_decision.get("decision"),
        },
        "adapter": _adapter_projection(adapter_spec),
        "control_plane": {
            "policy_path": context.get("policy_path"),
            "governance_path": context.get("governance_path"),
            "runtime_boundary": "handoff_only",
        },
        "request": decision_scope,
        "gate": gate,
    }


def build_execution_handoff_report(
    tool_gate_report: Mapping[str, Any],
    preflight_report: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    task_context: Mapping[str, Any],
    approval_records: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
    approval_record_paths: Mapping[str, str] | None = None,
    request_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a report containing side-effect-free handoffs."""

    approvals = _approval_records_by_request(approval_records)
    paths = approval_record_paths or {}
    gate_entries = _entries_by_request(tool_gate_report)
    preflight_decisions = _preflight_decisions_by_request(preflight_report)
    selected_request_ids = request_ids or [
        decision.get("request_id")
        for decision in _decision_entries(preflight_report)
        if isinstance(decision.get("request_id"), str)
    ]

    handoffs = []
    for request_id in selected_request_ids:
        if not isinstance(request_id, str):
            continue
        entry = gate_entries.get(request_id, {"request_id": request_id})
        preflight = preflight_decisions.get(request_id, {"request_id": request_id})
        context = dict(task_context)
        context.setdefault("handoff_id", f"HOFF-{request_id}")
        context["approval_record_path"] = paths.get(request_id)
        handoffs.append(
            build_execution_handoff(
                entry,
                preflight,
                adapter_spec,
                context,
                approvals.get(request_id),
            )
        )

    return {
        "version": "0.1.0",
        "kind": "execution_handoff_report",
        "task_id": task_context.get("task_id"),
        "objective_ref": task_context.get("objective_ref"),
        "attempt": task_context.get("attempt"),
        "result_status": NOT_EXECUTED,
        "source": "build_execution_handoff",
        "tool_gate_report_path": task_context.get("tool_gate_report_path"),
        "preflight_report_path": task_context.get("preflight_report_path"),
        "adapter_spec_path": task_context.get("adapter_spec_path"),
        "policy_path": task_context.get("policy_path"),
        "governance_path": task_context.get("governance_path"),
        "summary": _summary_for_handoffs(handoffs),
        "handoffs": handoffs,
    }


def validate_runtime_adapter_spec(adapter_spec: Mapping[str, Any]) -> ValidationReport:
    """Validate a side-effect-free runtime adapter capability spec."""

    report = ValidationReport()
    if not isinstance(adapter_spec, Mapping):
        report.error("$", "adapter spec must be a mapping")
        return report

    if adapter_spec.get("kind") != "runtime_adapter_spec":
        report.error("kind", "must be runtime_adapter_spec")
    for field_name in ("adapter_id", "adapter_kind", "adapter_version", "execution_plane"):
        if not isinstance(adapter_spec.get(field_name), str) or not adapter_spec.get(
            field_name
        ):
            report.error(field_name, "must be a non-empty string")

    contract = _mapping(adapter_spec.get("contract"), "contract", report)
    if contract:
        if contract.get("input") != "execution_handoff":
            report.error("contract.input", "must be execution_handoff")
        if not isinstance(contract.get("hook"), str) or not contract.get("hook"):
            report.error("contract.hook", "must be a non-empty string")
        if contract.get("agentharness_role") != "control_plane":
            report.error("contract.agentharness_role", "must be control_plane")

    supports = _mapping(adapter_spec.get("supports"), "supports", report)
    if supports:
        for support_field in SUPPORT_FIELD_MAP.values():
            values = supports.get(support_field)
            if not isinstance(values, list) or not values:
                report.error(f"supports.{support_field}", "must be a non-empty list")
                continue
            for index, value in enumerate(values):
                if not isinstance(value, str) or not value:
                    report.error(
                        f"supports.{support_field}[{index}]",
                        "must be a non-empty string",
                    )
                elif value == "*":
                    report.error(
                        f"supports.{support_field}[{index}]",
                        "wildcards are not supported in version 0.1.0",
                    )

    requirements = _mapping(adapter_spec.get("requirements"), "requirements", report)
    if requirements:
        for field_name in (
            "require_handoff_ready",
            "require_not_executed",
            "require_digest_validation",
            "reject_unsupported",
        ):
            if requirements.get(field_name) is not True:
                report.error(f"requirements.{field_name}", "must be true")

    return report


def validate_execution_handoff(
    handoff: Mapping[str, Any],
    tool_gate_entry: Mapping[str, Any],
    preflight_decision: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    task_context: Mapping[str, Any] | None = None,
    approval_record: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Validate one handoff by recomputing it from trusted inputs."""

    report = ValidationReport()
    if not isinstance(handoff, Mapping):
        report.error("$", "execution handoff must be a mapping")
        return report

    if handoff.get("kind") != "execution_handoff":
        report.error("kind", "must be execution_handoff")
    if handoff.get("source") != "build_execution_handoff":
        report.error("source", "must be build_execution_handoff")
    if handoff.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")
    if not isinstance(handoff.get("handoff_id"), str) or not handoff.get("handoff_id"):
        report.error("handoff_id", "must be a non-empty string")

    expected_context = dict(task_context or {})
    expected_context.setdefault("handoff_id", handoff.get("handoff_id"))
    expected = build_execution_handoff(
        tool_gate_entry,
        preflight_decision,
        adapter_spec,
        expected_context,
        approval_record,
    )
    for field_name in (
        "version",
        "kind",
        "task_id",
        "objective_ref",
        "attempt",
        "request_id",
        "result_status",
        "source",
        "subject",
        "adapter",
        "control_plane",
        "request",
        "gate",
    ):
        if handoff.get(field_name) != expected.get(field_name):
            report.error(field_name, "must match computed execution handoff")

    if preflight_decision.get("request_id") != tool_gate_entry.get("request_id"):
        report.error("request_id", "preflight decision must match tool gate request_id")

    _merge_prefixed(report, validate_runtime_adapter_spec(adapter_spec), "adapter_spec")
    _validate_complete_context(expected_context, report, "task_context")
    return report


def validate_execution_handoff_report(
    handoff_report: Mapping[str, Any],
    tool_gate_report: Mapping[str, Any],
    preflight_report: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
    governance: Mapping[str, Any] | None = None,
    approval_records: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
    approval_record_paths: Mapping[str, str] | None = None,
    task_context: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Validate a handoff report from full source artifacts."""

    report = ValidationReport()
    if not isinstance(handoff_report, Mapping):
        report.error("$", "execution handoff report must be a mapping")
        return report
    if not isinstance(tool_gate_report, Mapping):
        report.error("tool_gate_report", "must be a mapping")
        return report
    if not isinstance(preflight_report, Mapping):
        report.error("preflight_report", "must be a mapping")
        return report

    if handoff_report.get("kind") != "execution_handoff_report":
        report.error("kind", "must be execution_handoff_report")
    if handoff_report.get("source") != "build_execution_handoff":
        report.error("source", "must be build_execution_handoff")
    if handoff_report.get("result_status") != NOT_EXECUTED:
        report.error("result_status", "must be not_executed")

    context = _report_context(handoff_report, task_context)
    _validate_report_context(handoff_report, context, report)
    _merge_prefixed(
        report,
        validate_tool_gate_report(
            tool_gate_report,
            {
                "task_id": context.get("task_id"),
                "objective_ref": context.get("objective_ref"),
                "attempt": context.get("attempt"),
            },
            policy=policy,
            governance=governance,
        ),
        "tool_gate_report",
    )
    approvals = _approval_records_by_request(approval_records)
    paths = approval_record_paths or {}
    _merge_prefixed(
        report,
        validate_execution_preflight_report(
            preflight_report,
            tool_gate_report,
            approvals,
            {
                "task_id": context.get("task_id"),
                "objective_ref": context.get("objective_ref"),
                "attempt": context.get("attempt"),
                "tool_gate_report_path": context.get("tool_gate_report_path"),
            },
        ),
        "preflight_report",
    )
    _merge_prefixed(report, validate_runtime_adapter_spec(adapter_spec), "adapter_spec")

    for request_id, approval_record in approvals.items():
        approval_context = {
            "task_id": context.get("task_id"),
            "objective_ref": context.get("objective_ref"),
            "attempt": context.get("attempt"),
            "tool_gate_report_path": context.get("tool_gate_report_path"),
        }
        _merge_prefixed(
            report,
            validate_approval_record(approval_record, tool_gate_report, approval_context),
            f"approval_records.{request_id}",
        )

    handoffs = handoff_report.get("handoffs")
    if not isinstance(handoffs, list):
        report.error("handoffs", "must be a list")
        handoffs = []

    gate_entries = _entries_by_request(tool_gate_report)
    preflight_decisions = _preflight_decisions_by_request(preflight_report)
    seen_request_ids: set[str] = set()
    valid_handoffs: list[Mapping[str, Any]] = []
    for index, handoff in enumerate(handoffs):
        item_path = f"handoffs[{index}]"
        if not isinstance(handoff, Mapping):
            report.error(item_path, "must be a mapping")
            continue
        request_id = handoff.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            report.error(f"{item_path}.request_id", "must be a non-empty string")
            continue
        if request_id in seen_request_ids:
            report.error(f"{item_path}.request_id", "must be unique")
        seen_request_ids.add(request_id)
        if request_id not in gate_entries:
            report.error(f"{item_path}.request_id", "must reference tool gate report")
            continue
        if request_id not in preflight_decisions:
            report.error(f"{item_path}.request_id", "must reference preflight report")
            continue

        handoff_context = dict(context)
        handoff_context["handoff_id"] = handoff.get("handoff_id")
        handoff_context["approval_record_path"] = paths.get(request_id)
        handoff_validation = validate_execution_handoff(
            handoff,
            gate_entries[request_id],
            preflight_decisions[request_id],
            adapter_spec,
            handoff_context,
            approvals.get(request_id),
        )
        _merge_prefixed(report, handoff_validation, item_path)
        valid_handoffs.append(handoff)

    summary = _mapping(handoff_report.get("summary"), "summary", report)
    if summary:
        expected_summary = _summary_for_handoffs(valid_handoffs)
        for field_name, expected_value in expected_summary.items():
            if summary.get(field_name) != expected_value:
                report.error(f"summary.{field_name}", "must match included handoffs")

    return report


def _gate_for_handoff(
    tool_gate_entry: Mapping[str, Any],
    preflight_decision: Mapping[str, Any],
    adapter_spec: Mapping[str, Any],
    task_context: Mapping[str, Any],
) -> dict[str, Any]:
    preflight_allowed = preflight_decision.get("execution_allowed") is True
    preflight_name = preflight_decision.get("decision")
    if not _has_complete_context(task_context):
        return _gate(False, "invalid_context", None, preflight_allowed)
    if preflight_decision.get("request_id") != tool_gate_entry.get("request_id"):
        return _gate(False, "invalid_subject", None, preflight_allowed)
    if preflight_decision.get("result_status") != NOT_EXECUTED:
        return _gate(False, "invalid_subject", None, preflight_allowed)
    if not preflight_allowed or preflight_name not in READY_PREFLIGHT_DECISIONS:
        blocked_reason = _string(preflight_name, "invalid_subject")
        return _gate(False, blocked_reason, None, preflight_allowed)

    request = _request_scope(tool_gate_entry, preflight_decision)
    if not _adapter_supports_request(adapter_spec, request):
        return _gate(False, None, "unsupported_by_adapter", preflight_allowed)
    return _gate(True, None, None, preflight_allowed)


def _gate(
    handoff_ready: bool,
    blocked_reason: str | None,
    unsupported_reason: str | None,
    execution_allowed_by_preflight: bool,
) -> dict[str, Any]:
    return {
        "handoff_ready": handoff_ready,
        "blocked_reason": blocked_reason,
        "unsupported_reason": unsupported_reason,
        "execution_allowed_by_preflight": execution_allowed_by_preflight,
        "result_status": NOT_EXECUTED,
    }


def _adapter_supports_request(
    adapter_spec: Mapping[str, Any], request: Mapping[str, Any]
) -> bool:
    supports = adapter_spec.get("supports")
    if not isinstance(supports, Mapping):
        return False
    for request_field, support_field in SUPPORT_FIELD_MAP.items():
        value = request.get(request_field)
        supported_values = supports.get(support_field)
        if not isinstance(value, str) or not isinstance(supported_values, list):
            return False
        if value not in supported_values:
            return False
    return True


def _adapter_projection(adapter_spec: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping_or_empty(adapter_spec.get("contract"))
    supports = _mapping_or_empty(adapter_spec.get("supports"))
    return {
        "adapter_id": adapter_spec.get("adapter_id"),
        "adapter_kind": adapter_spec.get("adapter_kind"),
        "adapter_version": adapter_spec.get("adapter_version"),
        "hook": contract.get("hook"),
        "supports": {
            "tool_names": list(supports.get("tool_names", []))
            if isinstance(supports.get("tool_names"), list)
            else supports.get("tool_names"),
            "categories": list(supports.get("categories", []))
            if isinstance(supports.get("categories"), list)
            else supports.get("categories"),
            "intents": list(supports.get("intents", []))
            if isinstance(supports.get("intents"), list)
            else supports.get("intents"),
            "target_scopes": list(supports.get("target_scopes", []))
            if isinstance(supports.get("target_scopes"), list)
            else supports.get("target_scopes"),
        },
    }


def _request_scope(
    tool_gate_entry: Mapping[str, Any], preflight_decision: Mapping[str, Any]
) -> dict[str, Any]:
    tool_decision = _mapping_or_empty(tool_gate_entry.get("decision"))
    preflight_scope = _mapping_or_empty(preflight_decision.get("scope"))
    return {
        "tool_name": tool_decision.get("tool_name", preflight_scope.get("tool_name")),
        "category": tool_decision.get("category", preflight_scope.get("category")),
        "intent": tool_decision.get("intent", preflight_scope.get("intent")),
        "target_scope": tool_decision.get(
            "target_scope", preflight_scope.get("target_scope")
        ),
    }


def _summary_for_handoffs(handoffs: list[Mapping[str, Any]]) -> dict[str, Any]:
    ready = 0
    unsupported = 0
    for handoff in handoffs:
        gate = _mapping_or_empty(handoff.get("gate"))
        if gate.get("handoff_ready") is True:
            ready += 1
        elif gate.get("unsupported_reason") is not None:
            unsupported += 1
    total = len(handoffs)
    return {
        "total": total,
        "handoff_ready": ready,
        "blocked": total - ready - unsupported,
        "unsupported": unsupported,
        "result_status": NOT_EXECUTED,
    }


def _entries_by_request(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        entry["request_id"]: entry
        for entry in _decision_entries(report)
        if isinstance(entry.get("request_id"), str)
    }


def _preflight_decisions_by_request(
    report: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    return {
        decision["request_id"]: decision
        for decision in _decision_entries(report)
        if isinstance(decision.get("request_id"), str)
    }


def _decision_entries(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    decisions = report.get("decisions")
    if not isinstance(decisions, list):
        return []
    return [decision for decision in decisions if isinstance(decision, Mapping)]


def _approval_records_by_request(
    approval_records: Mapping[str, Any] | list[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    if approval_records is None:
        return {}
    if isinstance(approval_records, Mapping):
        normalized = {}
        for request_id, value in approval_records.items():
            if isinstance(request_id, str) and isinstance(value, Mapping):
                normalized[request_id] = value
        return normalized
    normalized = {}
    for record in approval_records:
        if not isinstance(record, Mapping):
            continue
        subject = record.get("subject")
        request_id = subject.get("request_id") if isinstance(subject, Mapping) else None
        if isinstance(request_id, str):
            normalized[request_id] = record
    return normalized


def _report_context(
    handoff_report: Mapping[str, Any], task_context: Mapping[str, Any] | None
) -> dict[str, Any]:
    context = dict(task_context or {})
    for field_name in (
        "task_id",
        "objective_ref",
        "attempt",
        "tool_gate_report_path",
        "preflight_report_path",
        "adapter_spec_path",
        "policy_path",
        "governance_path",
    ):
        if field_name not in context:
            context[field_name] = handoff_report.get(field_name)
    return context


def _validate_report_context(
    handoff_report: Mapping[str, Any],
    context: Mapping[str, Any],
    report: ValidationReport,
) -> None:
    for field_name in ("task_id", "objective_ref", "attempt"):
        if handoff_report.get(field_name) != context.get(field_name):
            report.error(field_name, "must match expected context")
    for field_name in (
        "tool_gate_report_path",
        "preflight_report_path",
        "adapter_spec_path",
    ):
        if handoff_report.get(field_name) != context.get(field_name):
            report.error(field_name, "must match expected context")
    _validate_complete_context(context, report, "context")


def _validate_complete_context(
    context: Mapping[str, Any], report: ValidationReport, path: str
) -> None:
    if not isinstance(context.get("task_id"), str) or not context.get("task_id"):
        report.error(f"{path}.task_id", "must be a non-empty string")
    if not isinstance(context.get("objective_ref"), str) or not context.get(
        "objective_ref"
    ):
        report.error(f"{path}.objective_ref", "must be a non-empty string")
    if not isinstance(context.get("attempt"), int) or context.get("attempt") < 1:
        report.error(f"{path}.attempt", "must be a positive integer")
    for field_name in ("tool_gate_report_path", "preflight_report_path"):
        if not isinstance(context.get(field_name), str) or not context.get(field_name):
            report.error(f"{path}.{field_name}", "must be a non-empty string")


def _has_complete_context(context: Mapping[str, Any]) -> bool:
    return (
        isinstance(context.get("task_id"), str)
        and bool(context.get("task_id"))
        and isinstance(context.get("objective_ref"), str)
        and bool(context.get("objective_ref"))
        and isinstance(context.get("attempt"), int)
        and context.get("attempt") >= 1
        and isinstance(context.get("tool_gate_report_path"), str)
        and bool(context.get("tool_gate_report_path"))
        and isinstance(context.get("preflight_report_path"), str)
        and bool(context.get("preflight_report_path"))
    )


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
