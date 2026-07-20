"""Tool gate report building and validation."""

from __future__ import annotations

from typing import Any, Mapping

from .tool_router import DECISIONS, route_tool_request
from .validate import ValidationReport


REQUIRED_AUDIT_FIELDS = {
    "event_id",
    "timestamp",
    "actor",
    "user_request_id",
    "tool_name",
    "category",
    "intent",
    "target_scope",
    "risk_level",
    "policy_decision",
    "approval_required",
    "result_status",
}


def build_tool_gate_report(
    policy: Mapping[str, Any],
    governance: Mapping[str, Any],
    task_context: Mapping[str, Any],
    requests: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a side-effect-free report of routed tool decisions."""

    decisions = []
    counts = {"allow": 0, "approval_required": 0, "deny": 0}
    for index, request in enumerate(requests, start=1):
        request_id = _string(request.get("request_id"), f"TR-{index:03}")
        routed_request = dict(request)
        routed_request.pop("request_id", None)
        routed_request.setdefault("actor", task_context.get("actor", "unknown"))
        decision = route_tool_request(policy, governance, routed_request).as_dict()
        decision_name = decision["decision"]
        counts[decision_name] += 1
        decisions.append(
            {
                "request_id": request_id,
                "request": routed_request,
                "decision": decision,
                "gate": _gate_for_decision(decision_name),
            }
        )

    return {
        "version": "0.1.0",
        "kind": "tool_gate_report",
        "task_id": task_context.get("task_id"),
        "objective_ref": task_context.get("objective_ref"),
        "attempt": task_context.get("attempt"),
        "actor": task_context.get("actor", "executor"),
        "source": "route_tool_request",
        "summary": {
            "total": len(decisions),
            "allow": counts["allow"],
            "approval_required": counts["approval_required"],
            "deny": counts["deny"],
            "result_status": "not_executed",
        },
        "decisions": decisions,
    }


def validate_tool_gate_report(
    report: Mapping[str, Any],
    expected_context: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    governance: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Validate a tool gate report without executing any tools."""

    validation = ValidationReport()
    if not isinstance(report, Mapping):
        validation.error("$", "tool gate report must be a mapping")
        return validation
    if not isinstance(policy, Mapping) or not isinstance(governance, Mapping):
        validation.error(
            "policy",
            "policy and governance are required for tool gate decision recomputation",
        )

    if report.get("kind") != "tool_gate_report":
        validation.error("kind", "must be tool_gate_report")
    if report.get("source") != "route_tool_request":
        validation.error("source", "must be route_tool_request")

    _validate_context(report, expected_context or {}, validation)

    summary = _mapping(report.get("summary"), "summary", validation)
    decisions = report.get("decisions")
    if not isinstance(decisions, list):
        validation.error("decisions", "must be a list")
        decisions = []

    counts = {"allow": 0, "approval_required": 0, "deny": 0}
    for index, entry in enumerate(decisions):
        _validate_decision_entry(
            entry,
            f"decisions[{index}]",
            counts,
            validation,
            policy,
            governance,
        )

    if summary:
        if summary.get("result_status") != "not_executed":
            validation.error("summary.result_status", "must be not_executed")
        expected_total = len(decisions)
        if summary.get("total") != expected_total:
            validation.error("summary.total", f"must equal {expected_total}")
        for decision_name, count in counts.items():
            if summary.get(decision_name) != count:
                validation.error(
                    f"summary.{decision_name}", f"must equal {count}"
                )

    return validation


def _validate_context(
    report: Mapping[str, Any],
    expected_context: Mapping[str, Any],
    validation: ValidationReport,
) -> None:
    for field_name in ("task_id", "objective_ref", "attempt"):
        value = report.get(field_name)
        if field_name == "attempt":
            if not isinstance(value, int) or value < 1:
                validation.error(field_name, "must be a positive integer")
        elif not isinstance(value, str) or not value:
            validation.error(field_name, "must be a non-empty string")

        if field_name in expected_context and value != expected_context[field_name]:
            validation.error(field_name, "must match ledger event")


def _validate_decision_entry(
    entry: Any,
    path: str,
    counts: dict[str, int],
    validation: ValidationReport,
    policy: Mapping[str, Any] | None,
    governance: Mapping[str, Any] | None,
) -> None:
    if not isinstance(entry, Mapping):
        validation.error(path, "must be a mapping")
        return
    request_id = entry.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        validation.error(f"{path}.request_id", "must be a non-empty string")
    request = _mapping(entry.get("request"), f"{path}.request", validation)
    decision = _mapping(entry.get("decision"), f"{path}.decision", validation)
    gate = _mapping(entry.get("gate"), f"{path}.gate", validation)
    if not request or not decision or not gate:
        return

    decision_name = decision.get("decision")
    if decision_name not in DECISIONS:
        validation.error(f"{path}.decision.decision", "must be allow, approval_required, or deny")
        return
    counts[decision_name] += 1

    policy_source = _mapping(
        decision.get("policy_source"), f"{path}.decision.policy_source", validation
    )

    audit_fields = _mapping(
        decision.get("audit_fields"), f"{path}.decision.audit_fields", validation
    )
    if audit_fields:
        missing = sorted(REQUIRED_AUDIT_FIELDS - set(audit_fields))
        for field_name in missing:
            validation.error(
                f"{path}.decision.audit_fields.{field_name}",
                "missing required audit field",
            )
        if audit_fields.get("result_status") != "not_executed":
            validation.error(
                f"{path}.decision.audit_fields.result_status",
                "must be not_executed",
            )
        if audit_fields.get("policy_decision") != decision_name:
            validation.error(
                f"{path}.decision.audit_fields.policy_decision",
                "must match decision.decision",
            )

    expected_gate = _gate_for_decision(decision_name)
    for field_name, expected_value in expected_gate.items():
        if gate.get(field_name) != expected_value:
            validation.error(f"{path}.gate.{field_name}", f"must be {expected_value}")
    if gate.get("result_status") != "not_executed":
        validation.error(f"{path}.gate.result_status", "must be not_executed")

    if isinstance(policy, Mapping) and isinstance(governance, Mapping):
        recomputed = route_tool_request(policy, governance, request).as_dict()
        _validate_recomputed_decision(
            path,
            decision,
            gate,
            recomputed,
            validation,
        )


def _validate_recomputed_decision(
    path: str,
    decision: Mapping[str, Any],
    gate: Mapping[str, Any],
    recomputed: Mapping[str, Any],
    validation: ValidationReport,
) -> None:
    for field_name in (
        "tool_name",
        "category",
        "intent",
        "target_scope",
        "risk_level",
        "decision",
        "approval_required",
        "audit_required",
        "reason",
        "policy_source",
        "audit_fields",
    ):
        if decision.get(field_name) != recomputed.get(field_name):
            validation.error(
                f"{path}.decision.{field_name}",
                "must match recomputed route_tool_request ToolDecision",
            )

    recomputed_decision = recomputed.get("decision")
    expected_gate = _gate_for_decision(str(recomputed_decision))
    for field_name, expected_value in expected_gate.items():
        if gate.get(field_name) != expected_value:
            validation.error(
                f"{path}.gate.{field_name}",
                "must match recomputed route_tool_request gate",
            )


def _gate_for_decision(decision: str) -> dict[str, Any]:
    return {
        "execution_allowed_by_policy": decision == "allow",
        "requires_approval": decision == "approval_required",
        "blocked_by_policy": decision == "deny",
        "result_status": "not_executed",
    }


def _mapping(
    value: Any, path: str, validation: ValidationReport
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        validation.error(path, "must be a mapping")
        return None
    return value


def _string(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default
