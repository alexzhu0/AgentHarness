"""Read-only inspection for execution handoff reports referenced by a file bus."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .audit_contract import sanitize_audit_message
from .loop_bus import parse_ledger, validate_bus
from .validate import ValidationReport
from .yamlio import YamlLoadError, load_yaml


def inspect_handoff_bus(bus_root: str | Path) -> tuple[dict[str, Any] | None, ValidationReport]:
    """Validate a bus and return a deterministic handoff inspection payload."""

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

    reports: list[dict[str, Any]] = []
    for index, reference in enumerate(references):
        field_path = f"ledger.handoff_reports[{index}]"
        resolved, error = _resolve_bus_reference(root, reference)
        if error:
            report.error(field_path, error)
            continue
        if resolved is None or not resolved.is_file():
            report.error(field_path, "referenced file does not exist")
            continue
        try:
            handoff_report = load_yaml(resolved)
        except YamlLoadError as exc:
            report.error(field_path, f"could not parse execution handoff report: {exc}")
            continue
        if not isinstance(handoff_report, Mapping):
            report.error(field_path, "execution handoff report must be a mapping")
            continue
        reports.append(_summarize_report(root, resolved, handoff_report))

    if not report.ok:
        return None, report

    inspection = {
        "ok": True,
        "summary": _aggregate_summary(reports),
        "reports": reports,
        "warnings": sanitize_handoff_inspection_messages(report.warnings),
    }
    return inspection, report


def format_handoff_inspection(inspection: Mapping[str, Any]) -> str:
    """Render a compact text view of an inspection payload."""

    summary = _mapping_or_empty(inspection.get("summary"))
    lines = [
        "PASS handoff inspection",
        (
            "reports={reports} total={total} handoff_ready={ready} "
            "blocked={blocked} unsupported={unsupported} result_status={result_status}"
        ).format(
            reports=summary.get("reports", 0),
            total=summary.get("total", 0),
            ready=summary.get("handoff_ready", 0),
            blocked=summary.get("blocked", 0),
            unsupported=summary.get("unsupported", 0),
            result_status=summary.get("result_status"),
        ),
    ]
    for item in inspection.get("reports", []):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "report {path} task_id={task_id} attempt={attempt}".format(
                path=item.get("path"),
                task_id=item.get("task_id"),
                attempt=item.get("attempt"),
            )
        )
        for handoff in item.get("handoffs", []):
            if not isinstance(handoff, Mapping):
                continue
            lines.append(
                (
                    "- {request_id}: {status} preflight={preflight} "
                    "result_status={result_status} tool={tool_name} "
                    "category={category} intent={intent} target_scope={target_scope}"
                ).format(
                    request_id=handoff.get("request_id"),
                    status=handoff.get("status"),
                    preflight=handoff.get("expected_preflight_decision"),
                    result_status=handoff.get("result_status"),
                    tool_name=handoff.get("tool_name"),
                    category=handoff.get("category"),
                    intent=handoff.get("intent"),
                    target_scope=handoff.get("target_scope"),
                )
            )
    for warning in sanitize_handoff_inspection_messages(inspection.get("warnings", [])):
        lines.append(f"WARN {warning}")
    return "\n".join(lines)


def sanitize_handoff_inspection_messages(values: Any) -> list[str]:
    """Return deterministic public handoff-inspection messages without host paths."""

    if not isinstance(values, list):
        return []
    return [sanitize_handoff_inspection_message(value) for value in values]


def sanitize_handoff_inspection_message(value: Any) -> str:
    """Sanitize one handoff-inspection error or warning for CLI/JSON output."""

    return sanitize_audit_message(value).replace("<path>", "<bus_root>")


def _handoff_report_references(events: list[dict[str, Any]]) -> list[str]:
    references: list[str] = []
    for event in events:
        if event.get("event_type") != "designer_review":
            continue
        reference = event.get("execution_handoff_report_path")
        if isinstance(reference, str) and reference:
            references.append(reference)
    return references


def _summarize_report(
    bus_root: Path,
    report_path: Path,
    handoff_report: Mapping[str, Any],
) -> dict[str, Any]:
    handoff_items = []
    for handoff in handoff_report.get("handoffs", []):
        if not isinstance(handoff, Mapping):
            continue
        handoff_items.append(_summarize_handoff(handoff))
    return {
        "path": _relative_to(bus_root, report_path),
        "task_id": handoff_report.get("task_id"),
        "objective_ref": handoff_report.get("objective_ref"),
        "attempt": handoff_report.get("attempt"),
        "result_status": handoff_report.get("result_status"),
        "summary": _summary_from_handoffs(
            handoff_items, handoff_report.get("result_status")
        ),
        "handoffs": handoff_items,
    }


def _summarize_handoff(handoff: Mapping[str, Any]) -> dict[str, Any]:
    gate = _mapping_or_empty(handoff.get("gate"))
    subject = _mapping_or_empty(handoff.get("subject"))
    request = _mapping_or_empty(handoff.get("request"))
    return {
        "request_id": handoff.get("request_id"),
        "status": _handoff_status(gate),
        "handoff_ready": gate.get("handoff_ready") is True,
        "blocked_reason": gate.get("blocked_reason"),
        "unsupported_reason": gate.get("unsupported_reason"),
        "execution_allowed_by_preflight": gate.get("execution_allowed_by_preflight"),
        "expected_preflight_decision": subject.get("expected_preflight_decision"),
        "result_status": handoff.get("result_status"),
        "tool_name": request.get("tool_name"),
        "category": request.get("category"),
        "intent": request.get("intent"),
        "target_scope": request.get("target_scope"),
    }


def _handoff_status(gate: Mapping[str, Any]) -> str:
    if gate.get("handoff_ready") is True:
        return "handoff_ready"
    if gate.get("unsupported_reason") is not None:
        return "unsupported"
    return "blocked"


def _aggregate_summary(reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    summaries = [_mapping_or_empty(report.get("summary")) for report in reports]
    total = sum(_int_value(summary.get("total")) for summary in summaries)
    ready = sum(_int_value(summary.get("handoff_ready")) for summary in summaries)
    blocked = sum(_int_value(summary.get("blocked")) for summary in summaries)
    unsupported = sum(_int_value(summary.get("unsupported")) for summary in summaries)
    statuses = {
        summary.get("result_status")
        for summary in summaries
        if isinstance(summary.get("result_status"), str)
    }
    result_status = statuses.pop() if len(statuses) == 1 else "mixed"
    return {
        "reports": len(reports),
        "total": total,
        "handoff_ready": ready,
        "blocked": blocked,
        "unsupported": unsupported,
        "result_status": result_status,
    }


def _summary_from_handoffs(
    handoffs: list[Mapping[str, Any]], report_result_status: Any
) -> dict[str, Any]:
    ready = sum(1 for handoff in handoffs if handoff.get("handoff_ready") is True)
    unsupported = sum(1 for handoff in handoffs if handoff.get("status") == "unsupported")
    total = len(handoffs)
    statuses = {
        handoff.get("result_status")
        for handoff in handoffs
        if isinstance(handoff.get("result_status"), str)
    }
    if isinstance(report_result_status, str):
        statuses.add(report_result_status)
    result_status = statuses.pop() if len(statuses) == 1 else "mixed"
    return {
        "total": total,
        "handoff_ready": ready,
        "blocked": total - ready - unsupported,
        "unsupported": unsupported,
        "result_status": result_status,
    }


def _resolve_bus_reference(bus_root: Path, reference: Any) -> tuple[Path | None, str | None]:
    if not isinstance(reference, str) or not reference:
        return None, "must be a non-empty string"
    path = Path(reference)
    candidate = path if path.is_absolute() else bus_root / path
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(bus_root):
        return resolved, "referenced path must stay within bus_root"
    return resolved, None


def _relative_to(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 0


def _merge(target: ValidationReport, source: ValidationReport) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)
