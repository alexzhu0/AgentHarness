"""File-bus loop validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapter_registry import validate_adapter_registry_binding
from .approval_record import validate_approval_record
from .execution_handoff import validate_execution_handoff_report
from .execution_preflight import validate_execution_preflight_report
from .tool_gate import validate_tool_gate_report
from .validate import ValidationReport
from .yamlio import YamlLoadError, load_yaml


REQUIRED_TASK_FIELDS = {
    "id",
    "title",
    "owner",
    "status",
    "objective",
    "acceptance_criteria",
    "constraints",
    "verification",
    "retry_policy",
    "failure_classes",
    "audit",
}

REQUIRED_EVENT_FIELDS = {
    "event_id",
    "ts",
    "task_id",
    "actor",
    "event_type",
    "status",
    "attempt",
    "objective_ref",
    "summary",
}

ALLOWED_ACTORS = {"designer", "executor", "user"}
ALLOWED_STATUSES = {
    "assigned",
    "executor_done",
    "reviewing",
    "retry_requested",
    "completed",
    "blocked_escalate",
}
ALLOWED_EVENT_TYPES = {
    "task_assigned",
    "executor_done",
    "designer_review",
    "task_completed",
    "retry_requested",
    "blocked_escalate",
}
EVENT_TYPE_STATUS = {
    "task_assigned": "assigned",
    "executor_done": "executor_done",
    "designer_review": "reviewing",
    "task_completed": "completed",
    "retry_requested": "retry_requested",
    "blocked_escalate": "blocked_escalate",
}
EVENT_TYPE_ALLOWED_ACTORS = {
    "task_assigned": {"designer"},
    "executor_done": {"executor"},
    "designer_review": {"designer"},
    "task_completed": {"designer", "user"},
    "retry_requested": {"designer"},
    "blocked_escalate": {"designer", "user"},
}
TERMINAL_STATUSES = {"completed", "blocked_escalate"}
ALLOWED_TRANSITIONS = {
    "assigned": {"executor_done"},
    "executor_done": {"reviewing"},
    "reviewing": {"completed", "retry_requested", "blocked_escalate"},
    "retry_requested": {"executor_done"},
}
ALLOWED_FAILURE_CLASSES = {
    "verification_failed",
    "baseline_drift",
    "policy_violation",
    "missing_evidence",
    "objective_mismatch",
    "invalid_ledger",
    "repeated_failure_without_new_hypothesis",
}
AUTOMATIC_RETRY_CLASSES = {
    "baseline_drift",
    "verification_failed",
    "missing_evidence",
}
ESCALATION_CLASSES = {
    "policy_violation",
    "objective_mismatch",
    "invalid_ledger",
    "repeated_failure_without_new_hypothesis",
}
REVIEW_VERDICTS = {"accepted", "retry_requested", "blocked_escalate"}
STATUS_REVIEW_VERDICTS = {
    "completed": "accepted",
    "retry_requested": "retry_requested",
    "blocked_escalate": "blocked_escalate",
}


def load_task(path: str | Path) -> dict[str, Any]:
    """Load one file-bus task YAML file."""

    value = load_yaml(path)
    if not isinstance(value, dict):
        raise ValueError(f"task file {path} must contain a mapping")
    return value


def parse_ledger(path: str | Path) -> tuple[list[dict[str, Any]], ValidationReport]:
    """Parse a JSONL ledger into event dictionaries."""

    report = ValidationReport()
    events: list[dict[str, Any]] = []
    ledger_path = Path(path)
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        report.error(str(ledger_path), f"could not read ledger: {exc}")
        return events, report

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            report.error(f"{ledger_path}:{line_number}", f"invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            report.error(f"{ledger_path}:{line_number}", "ledger event must be a mapping")
            continue
        events.append(event)
    return events, report


def validate_bus(bus_root: str | Path) -> ValidationReport:
    """Validate a file-bus fixture directory."""

    root = Path(bus_root).resolve()
    report = ValidationReport()
    tasks_dir = root / "tasks"
    ledger_path = root / "ledger.jsonl"

    if not tasks_dir.is_dir():
        report.error(str(tasks_dir), "tasks directory is missing")
        return report
    if not ledger_path.is_file():
        report.error(str(ledger_path), "ledger.jsonl is missing")
        return report

    tasks: dict[str, dict[str, Any]] = {}
    for task_path in sorted(tasks_dir.glob("*.yaml")):
        task = load_task(task_path)
        task_report = validate_task(task)
        _merge(report, task_report)
        task_id = task.get("id")
        if isinstance(task_id, str):
            tasks[task_id] = task

    events, ledger_report = parse_ledger(ledger_path)
    _merge(report, ledger_report)
    tool_gate_policy, tool_gate_governance = _load_tool_gate_validation_assets(
        root, events, report
    )

    events_by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in tasks}
    for index, event in enumerate(events):
        task_id = event.get("task_id")
        if task_id not in tasks:
            report.error(f"ledger[{index}].task_id", "references unknown task")
            continue
        events_by_task[task_id].append(event)

    for task_id, task in tasks.items():
        chain_report = validate_event_chain(
            task,
            events_by_task.get(task_id, []),
            bus_root=root,
            tool_gate_policy=tool_gate_policy,
            tool_gate_governance=tool_gate_governance,
        )
        _merge(report, chain_report)

    return report


def validate_task(task: dict[str, Any]) -> ValidationReport:
    """Validate one task object against MVP invariants."""

    report = ValidationReport()
    for field_name in sorted(REQUIRED_TASK_FIELDS):
        if field_name not in task:
            report.error(field_name, "missing required field")

    task_id = task.get("id")
    if not isinstance(task_id, str) or not task_id:
        report.error("id", "must be a non-empty string")

    if task.get("owner") not in ALLOWED_ACTORS:
        report.error("owner", "must be one of: designer, executor, user")

    if task.get("status") not in ALLOWED_STATUSES:
        report.error("status", "must be an allowed lifecycle status")

    objective = _mapping(task.get("objective"), "objective", report)
    audit = _mapping(task.get("audit"), "audit", report)
    if objective:
        expected_ref = f"{task_id}#objective"
        if objective.get("ref") != expected_ref:
            report.error("objective.ref", f"must equal {expected_ref}")
    if audit:
        expected_ref = f"{task_id}#objective"
        if audit.get("objective_ref") != expected_ref:
            report.error("audit.objective_ref", f"must equal {expected_ref}")

    for field_name in ("acceptance_criteria", "constraints"):
        if not isinstance(task.get(field_name), list) or not task.get(field_name):
            report.error(field_name, "must be a non-empty list")

    verification = _mapping(task.get("verification"), "verification", report)
    if verification and not isinstance(verification.get("commands"), list):
        report.error("verification.commands", "must be a list")

    retry_policy = _mapping(task.get("retry_policy"), "retry_policy", report)
    if retry_policy:
        max_attempts = retry_policy.get("max_attempts")
        if not isinstance(max_attempts, int) or max_attempts < 1:
            report.error("retry_policy.max_attempts", "must be a positive integer")
        elif max_attempts > 3:
            report.error("retry_policy.max_attempts", "must not exceed 3")
        if retry_policy.get("require_new_failure_hypothesis") is not True:
            report.error(
                "retry_policy.require_new_failure_hypothesis", "must be true"
            )

    failure_classes = _mapping(task.get("failure_classes"), "failure_classes", report)
    if failure_classes:
        _validate_failure_class_list(
            failure_classes.get("allowed"),
            ALLOWED_FAILURE_CLASSES,
            "failure_classes.allowed",
            report,
        )
        _validate_failure_class_list(
            failure_classes.get("automatic_retry"),
            AUTOMATIC_RETRY_CLASSES,
            "failure_classes.automatic_retry",
            report,
        )
        _validate_failure_class_list(
            failure_classes.get("escalate"),
            ESCALATION_CLASSES,
            "failure_classes.escalate",
            report,
        )

    return report


def validate_event_chain(
    task: dict[str, Any],
    events: list[dict[str, Any]],
    bus_root: str | Path | None = None,
    tool_gate_policy: dict[str, Any] | None = None,
    tool_gate_governance: dict[str, Any] | None = None,
) -> ValidationReport:
    """Validate ledger events for one task."""

    report = ValidationReport()
    if not events:
        report.error("ledger", "task has no ledger events")
        return report

    task_id = task.get("id")
    objective_ref = task.get("audit", {}).get("objective_ref")
    allowed_failures = set(task.get("failure_classes", {}).get("allowed", []))
    automatic_retry_failures = set(
        task.get("failure_classes", {}).get("automatic_retry", [])
    )
    max_attempts = task.get("retry_policy", {}).get("max_attempts", 3)
    seen_event_ids: set[str] = set()
    retry_hypotheses: set[str] = set()
    previous_status: str | None = None
    previous_event_type: str | None = None
    previous_attempt: int | None = None
    executor_done_attempts: set[int] = set()
    tool_gate_reports_by_attempt: dict[int, tuple[str, dict[str, Any]]] = {}
    approval_records_by_attempt: dict[int, dict[str, dict[str, Any]]] = {}
    approval_record_paths_by_attempt: dict[int, dict[str, str]] = {}
    preflight_reports_by_attempt: dict[int, tuple[str, dict[str, Any]]] = {}

    for index, event in enumerate(events):
        path = f"ledger[{index}]"
        _validate_event_shape(event, path, report)

        event_id = event.get("event_id")
        if event_id in seen_event_ids:
            report.error(f"{path}.event_id", "must be unique")
        if isinstance(event_id, str):
            seen_event_ids.add(event_id)

        if event.get("task_id") != task_id:
            report.error(f"{path}.task_id", "must match task id")
        if event.get("objective_ref") != objective_ref:
            report.error(f"{path}.objective_ref", "must match task objective ref")

        actor = event.get("actor")
        if actor not in ALLOWED_ACTORS:
            report.error(f"{path}.actor", "must be one of: designer, executor, user")

        event_type = event.get("event_type")
        prior_event_type = previous_event_type
        _validate_event_type(
            event_type,
            event.get("status"),
            actor,
            prior_event_type,
            path,
            report,
        )

        status = event.get("status")
        if status not in ALLOWED_STATUSES:
            report.error(f"{path}.status", "must be an allowed lifecycle status")
        elif previous_status is None:
            if status != "assigned":
                report.error(f"{path}.status", "first event must be assigned")
        else:
            allowed_next = ALLOWED_TRANSITIONS.get(previous_status, set())
            if status not in allowed_next:
                report.error(
                    f"{path}.status",
                    f"invalid transition from {previous_status} to {status}",
                )
        if status in TERMINAL_STATUSES and index != len(events) - 1:
            report.error(f"{path}.status", "terminal state must be the final event")
        if isinstance(status, str):
            previous_status = status

        attempt = event.get("attempt")
        if not isinstance(attempt, int) or attempt < 1:
            report.error(f"{path}.attempt", "must be a positive integer")
        else:
            if previous_attempt is None:
                if attempt != 1:
                    report.error(f"{path}.attempt", "first event attempt must be 1")
            elif prior_event_type == "retry_requested" and event_type == "executor_done":
                expected_attempt = previous_attempt + 1
                if attempt != expected_attempt:
                    report.error(
                        f"{path}.attempt",
                        f"must increment to {expected_attempt} after retry_requested",
                    )
            elif attempt != previous_attempt:
                report.error(
                    f"{path}.attempt",
                    "must stay unchanged until retry_requested advances the attempt",
                )

            if isinstance(max_attempts, int) and attempt > max_attempts:
                report.error(f"{path}.attempt", "exceeds retry_policy.max_attempts")

            if event_type == "executor_done":
                if attempt in executor_done_attempts:
                    report.error(
                        f"{path}.attempt",
                        "executor_done attempts must be unique",
                    )
                executor_done_attempts.add(attempt)
                if (
                    isinstance(max_attempts, int)
                    and len(executor_done_attempts) > max_attempts
                ):
                    report.error(
                        f"{path}.attempt",
                        "retry count exceeds retry_policy.max_attempts",
                    )
            previous_attempt = attempt

        if isinstance(event_type, str):
            previous_event_type = event_type

        _validate_conditional_fields(
            event,
            path,
            allowed_failures,
            automatic_retry_failures,
            max_attempts,
            report,
        )
        _validate_referenced_paths(
            event,
            str(task_id),
            str(objective_ref),
            path,
            bus_root,
            report,
        )
        tool_gate_report = _validate_tool_gate_report_path(
            event,
            str(task_id),
            str(objective_ref),
            path,
            bus_root,
            tool_gate_policy,
            tool_gate_governance,
            report,
        )
        if (
            tool_gate_report is not None
            and event_type == "executor_done"
            and isinstance(attempt, int)
            and isinstance(event.get("tool_gate_report_path"), str)
        ):
            tool_gate_reports_by_attempt[attempt] = (
                event["tool_gate_report_path"],
                tool_gate_report,
            )
        approval_record_result = _validate_approval_record_paths(
            event,
            str(task_id),
            str(objective_ref),
            path,
            bus_root,
            tool_gate_reports_by_attempt,
            report,
        )
        if approval_record_result is not None and isinstance(attempt, int):
            approval_records, approval_record_paths = approval_record_result
            approval_records_by_attempt[attempt] = approval_records
            approval_record_paths_by_attempt[attempt] = approval_record_paths
        preflight_report_result = _validate_preflight_report_path(
            event,
            str(task_id),
            str(objective_ref),
            path,
            bus_root,
            tool_gate_reports_by_attempt,
            approval_records_by_attempt,
            report,
        )
        if preflight_report_result is not None and isinstance(attempt, int):
            preflight_reports_by_attempt[attempt] = preflight_report_result
        _validate_execution_handoff_report_path(
            event,
            str(task_id),
            str(objective_ref),
            path,
            bus_root,
            tool_gate_reports_by_attempt,
            approval_records_by_attempt,
            approval_record_paths_by_attempt,
            preflight_reports_by_attempt,
            tool_gate_policy,
            tool_gate_governance,
            report,
        )

        if status == "retry_requested":
            hypothesis = event.get("failure_hypothesis")
            if not isinstance(hypothesis, str) or not hypothesis.strip():
                report.error(f"{path}.failure_hypothesis", "must be a non-empty string")
            elif hypothesis in retry_hypotheses:
                report.error(
                    f"{path}.failure_hypothesis",
                    "must be new for each retry request",
                )
            else:
                retry_hypotheses.add(hypothesis)

    final_status = events[-1].get("status")
    if final_status != task.get("status"):
        report.error("task.status", "must match final ledger event status")

    return report


def _validate_event_shape(
    event: dict[str, Any], path: str, report: ValidationReport
) -> None:
    for field_name in sorted(REQUIRED_EVENT_FIELDS):
        if field_name not in event:
            report.error(f"{path}.{field_name}", "missing required field")
    if "summary" in event and not isinstance(event["summary"], str):
        report.error(f"{path}.summary", "must be a string")


def _validate_event_type(
    event_type: Any,
    status: Any,
    actor: Any,
    previous_event_type: str | None,
    path: str,
    report: ValidationReport,
) -> None:
    if event_type not in ALLOWED_EVENT_TYPES:
        report.error(f"{path}.event_type", "must be an allowed event type")
        return
    expected_status = EVENT_TYPE_STATUS[event_type]
    if status != expected_status:
        report.error(
            f"{path}.event_type",
            f"{event_type} must produce status {expected_status}",
        )
    allowed_actors = EVENT_TYPE_ALLOWED_ACTORS[event_type]
    if actor not in allowed_actors:
        formatted = ", ".join(sorted(allowed_actors))
        report.error(
            f"{path}.actor",
            f"{actor} is not authorized for {event_type}; allowed: {formatted}",
        )
    if previous_event_type is None:
        if event_type != "task_assigned":
            report.error(f"{path}.event_type", "first event must be task_assigned")
        return
    allowed_next = {
        "task_assigned": {"executor_done"},
        "executor_done": {"designer_review"},
        "designer_review": {"task_completed", "retry_requested", "blocked_escalate"},
        "retry_requested": {"executor_done"},
    }.get(previous_event_type, set())
    if event_type not in allowed_next:
        report.error(
            f"{path}.event_type",
            f"invalid event order from {previous_event_type} to {event_type}",
        )


def _validate_conditional_fields(
    event: dict[str, Any],
    path: str,
    allowed_failures: set[str],
    automatic_retry_failures: set[str],
    max_attempts: Any,
    report: ValidationReport,
) -> None:
    status = event.get("status")
    if status == "executor_done" and not event.get("evidence_path"):
        report.error(f"{path}.evidence_path", "required for executor_done")
    if "tool_gate_report_path" in event and status != "executor_done":
        report.error(
            f"{path}.tool_gate_report_path",
            "only allowed for executor_done events",
        )
    if "approval_record_paths" in event:
        if event.get("event_type") != "designer_review":
            report.error(
                f"{path}.approval_record_paths",
                "only allowed for designer_review events",
            )
        paths = event["approval_record_paths"]
        if not isinstance(paths, list) or not paths:
            report.error(
                f"{path}.approval_record_paths",
                "must be a non-empty list of strings",
            )
        elif not all(isinstance(item, str) and item for item in paths):
            report.error(
                f"{path}.approval_record_paths",
                "must contain non-empty strings",
            )
    if "preflight_report_path" in event:
        if event.get("event_type") != "designer_review":
            report.error(
                f"{path}.preflight_report_path",
                "only allowed for designer_review events",
            )
        if not isinstance(event.get("preflight_report_path"), str) or not event.get(
            "preflight_report_path"
        ):
            report.error(f"{path}.preflight_report_path", "must be a non-empty string")
    if "execution_handoff_report_path" in event:
        if event.get("event_type") != "designer_review":
            report.error(
                f"{path}.execution_handoff_report_path",
                "only allowed for designer_review events",
            )
        if not isinstance(event.get("execution_handoff_report_path"), str) or not event.get(
            "execution_handoff_report_path"
        ):
            report.error(
                f"{path}.execution_handoff_report_path",
                "must be a non-empty string",
            )
    if status in {"completed", "retry_requested"} and not event.get("review_path"):
        report.error(f"{path}.review_path", f"required for {status}")
    if status in {"retry_requested", "blocked_escalate"}:
        failure_class = event.get("failure_class")
        if failure_class not in allowed_failures:
            report.error(f"{path}.failure_class", "must be allowed by task policy")
        if status == "retry_requested" and failure_class not in automatic_retry_failures:
            report.error(f"{path}.failure_class", "must be an automatic retry class")
        if (
            status == "retry_requested"
            and isinstance(max_attempts, int)
            and isinstance(event.get("attempt"), int)
            and event["attempt"] >= max_attempts
        ):
            report.error(f"{path}.attempt", "retry budget is exhausted")
        if (
            status == "blocked_escalate"
            and failure_class in automatic_retry_failures
            and isinstance(max_attempts, int)
            and isinstance(event.get("attempt"), int)
            and event["attempt"] < max_attempts
        ):
            report.error(
                f"{path}.failure_class",
                "automatic retry class cannot escalate before retry budget is exhausted",
            )
        if (
            status == "blocked_escalate"
            and failure_class not in ESCALATION_CLASSES
            and not (
                failure_class in automatic_retry_failures
                and isinstance(max_attempts, int)
                and isinstance(event.get("attempt"), int)
                and event["attempt"] >= max_attempts
            )
        ):
            report.error(f"{path}.failure_class", "must be an escalation class")


def _validate_referenced_paths(
    event: dict[str, Any],
    task_id: str,
    objective_ref: str,
    path: str,
    bus_root: str | Path | None,
    report: ValidationReport,
) -> None:
    if bus_root is None:
        return
    root = Path(bus_root).resolve()
    for field_name in ("evidence_path", "review_path"):
        if field_name not in event:
            continue
        reference, error = _resolve_reference(root, event[field_name])
        if error:
            report.error(f"{path}.{field_name}", error)
            continue
        if reference is None or not reference.is_file():
            report.error(f"{path}.{field_name}", "referenced file does not exist")
            continue
        metadata = _read_frontmatter(reference)
        if metadata.get("task_id") != task_id:
            report.error(f"{path}.{field_name}", "referenced file task_id mismatch")
        if metadata.get("objective_ref") != objective_ref:
            report.error(
                f"{path}.{field_name}", "referenced file objective_ref mismatch"
            )
        if field_name == "review_path":
            verdict = metadata.get("verdict")
            if verdict not in REVIEW_VERDICTS:
                report.error(f"{path}.{field_name}", "review verdict is not allowed")
            expected = STATUS_REVIEW_VERDICTS.get(str(event.get("status")))
            if expected and verdict != expected:
                report.error(
                    f"{path}.{field_name}",
                    f"review verdict must be {expected} for status {event.get('status')}",
                )


def _validate_tool_gate_report_path(
    event: dict[str, Any],
    task_id: str,
    objective_ref: str,
    path: str,
    bus_root: str | Path | None,
    tool_gate_policy: dict[str, Any] | None,
    tool_gate_governance: dict[str, Any] | None,
    report: ValidationReport,
) -> dict[str, Any] | None:
    if "tool_gate_report_path" not in event:
        return None
    if bus_root is None:
        return None
    root = Path(bus_root).resolve()
    reference, error = _resolve_reference(root, event["tool_gate_report_path"])
    field_path = f"{path}.tool_gate_report_path"
    if error:
        report.error(field_path, error)
        return None
    if reference is None or not reference.is_file():
        report.error(field_path, "referenced file does not exist")
        return None
    try:
        value = load_yaml(reference)
    except YamlLoadError as exc:
        report.error(field_path, f"could not parse tool gate report: {exc}")
        return None
    if not isinstance(value, dict):
        report.error(field_path, "tool gate report must be a mapping")
        return None
    expected_context = {
        "task_id": task_id,
        "objective_ref": objective_ref,
        "attempt": event.get("attempt"),
    }
    gate_report = validate_tool_gate_report(
        value,
        expected_context,
        policy=tool_gate_policy,
        governance=tool_gate_governance,
    )
    _merge_prefixed(report, gate_report, field_path)
    return value


def _validate_approval_record_paths(
    event: dict[str, Any],
    task_id: str,
    objective_ref: str,
    path: str,
    bus_root: str | Path | None,
    tool_gate_reports_by_attempt: dict[int, tuple[str, dict[str, Any]]],
    report: ValidationReport,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]] | None:
    if "approval_record_paths" not in event:
        return None
    if bus_root is None:
        return None

    approval_paths = event.get("approval_record_paths")
    if not isinstance(approval_paths, list) or not approval_paths:
        return None
    if not all(isinstance(item, str) and item for item in approval_paths):
        return None

    attempt = event.get("attempt")
    if not isinstance(attempt, int):
        return None
    tool_gate_info = tool_gate_reports_by_attempt.get(attempt)
    if tool_gate_info is None:
        report.error(
            f"{path}.approval_record_paths",
            "same-attempt executor_done tool_gate_report_path is required",
        )
        return None

    tool_gate_report_path, tool_gate_report = tool_gate_info
    root = Path(bus_root).resolve()
    seen_request_ids: set[str] = set()
    approval_records: dict[str, dict[str, Any]] = {}
    approval_record_paths: dict[str, str] = {}
    for index, approval_path in enumerate(approval_paths):
        field_path = f"{path}.approval_record_paths[{index}]"
        reference, error = _resolve_reference(root, approval_path)
        if error:
            report.error(field_path, error)
            continue
        if reference is None or not reference.is_file():
            report.error(field_path, "referenced file does not exist")
            continue
        try:
            approval_record = load_yaml(reference)
        except YamlLoadError as exc:
            report.error(field_path, f"could not parse approval record: {exc}")
            continue
        if not isinstance(approval_record, dict):
            report.error(field_path, "approval record must be a mapping")
            continue

        subject = approval_record.get("subject")
        request_id = subject.get("request_id") if isinstance(subject, dict) else None
        if isinstance(request_id, str):
            if request_id in seen_request_ids:
                report.error(field_path, "duplicate approval for request_id")
            seen_request_ids.add(request_id)
            approval_records[request_id] = approval_record
            approval_record_paths[request_id] = approval_path

        expected_context = {
            "task_id": task_id,
            "objective_ref": objective_ref,
            "attempt": attempt,
            "tool_gate_report_path": tool_gate_report_path,
        }
        approval_report = validate_approval_record(
            approval_record,
            tool_gate_report,
            expected_context,
        )
        _merge_prefixed(report, approval_report, field_path)
    return approval_records, approval_record_paths


def _validate_preflight_report_path(
    event: dict[str, Any],
    task_id: str,
    objective_ref: str,
    path: str,
    bus_root: str | Path | None,
    tool_gate_reports_by_attempt: dict[int, tuple[str, dict[str, Any]]],
    approval_records_by_attempt: dict[int, dict[str, dict[str, Any]]],
    report: ValidationReport,
) -> tuple[str, dict[str, Any]] | None:
    if "preflight_report_path" not in event:
        return None
    if bus_root is None:
        return None

    attempt = event.get("attempt")
    if not isinstance(attempt, int):
        return
    tool_gate_info = tool_gate_reports_by_attempt.get(attempt)
    if tool_gate_info is None:
        report.error(
            f"{path}.preflight_report_path",
            "same-attempt executor_done tool_gate_report_path is required",
        )
        return None

    root = Path(bus_root).resolve()
    reference, error = _resolve_reference(root, event["preflight_report_path"])
    field_path = f"{path}.preflight_report_path"
    if error:
        report.error(field_path, error)
        return None
    if reference is None or not reference.is_file():
        report.error(field_path, "referenced file does not exist")
        return None
    try:
        preflight_report = load_yaml(reference)
    except YamlLoadError as exc:
        report.error(field_path, f"could not parse preflight report: {exc}")
        return None
    if not isinstance(preflight_report, dict):
        report.error(field_path, "preflight report must be a mapping")
        return None

    tool_gate_report_path, tool_gate_report = tool_gate_info
    expected_context = {
        "task_id": task_id,
        "objective_ref": objective_ref,
        "attempt": attempt,
        "tool_gate_report_path": tool_gate_report_path,
    }
    preflight_validation = validate_execution_preflight_report(
        preflight_report,
        tool_gate_report,
        approval_records_by_attempt.get(attempt, {}),
        expected_context,
    )
    _merge_prefixed(report, preflight_validation, field_path)
    return event["preflight_report_path"], preflight_report


def _validate_execution_handoff_report_path(
    event: dict[str, Any],
    task_id: str,
    objective_ref: str,
    path: str,
    bus_root: str | Path | None,
    tool_gate_reports_by_attempt: dict[int, tuple[str, dict[str, Any]]],
    approval_records_by_attempt: dict[int, dict[str, dict[str, Any]]],
    approval_record_paths_by_attempt: dict[int, dict[str, str]],
    preflight_reports_by_attempt: dict[int, tuple[str, dict[str, Any]]],
    tool_gate_policy: dict[str, Any] | None,
    tool_gate_governance: dict[str, Any] | None,
    report: ValidationReport,
) -> None:
    if "execution_handoff_report_path" not in event:
        return
    if bus_root is None:
        return

    attempt = event.get("attempt")
    if not isinstance(attempt, int):
        return
    tool_gate_info = tool_gate_reports_by_attempt.get(attempt)
    if tool_gate_info is None:
        report.error(
            f"{path}.execution_handoff_report_path",
            "same-attempt executor_done tool_gate_report_path is required",
        )
        return
    preflight_info = preflight_reports_by_attempt.get(attempt)
    if preflight_info is None:
        report.error(
            f"{path}.execution_handoff_report_path",
            "same-attempt designer_review preflight_report_path is required",
        )
        return

    root = Path(bus_root).resolve()
    field_path = f"{path}.execution_handoff_report_path"
    reference, error = _resolve_reference(root, event["execution_handoff_report_path"])
    if error:
        report.error(field_path, error)
        return
    if reference is None or not reference.is_file():
        report.error(field_path, "referenced file does not exist")
        return
    try:
        handoff_report = load_yaml(reference)
    except YamlLoadError as exc:
        report.error(field_path, f"could not parse execution handoff report: {exc}")
        return
    if not isinstance(handoff_report, dict):
        report.error(field_path, "execution handoff report must be a mapping")
        return

    adapter_spec_path = handoff_report.get("adapter_spec_path")
    adapter_reference, adapter_error = _resolve_reference(root, adapter_spec_path)
    adapter_field_path = f"{field_path}.adapter_spec_path"
    if adapter_error:
        report.error(adapter_field_path, adapter_error)
        return
    if adapter_reference is None or not adapter_reference.is_file():
        report.error(adapter_field_path, "referenced file does not exist")
        return
    try:
        adapter_spec = load_yaml(adapter_reference)
    except YamlLoadError as exc:
        report.error(adapter_field_path, f"could not parse adapter spec: {exc}")
        return
    if not isinstance(adapter_spec, dict):
        report.error(adapter_field_path, "adapter spec must be a mapping")
        return
    registry_validation = validate_adapter_registry_binding(
        handoff_report,
        adapter_spec,
        root,
    )
    _merge_prefixed(report, registry_validation, field_path)

    tool_gate_report_path, tool_gate_report = tool_gate_info
    preflight_report_path, preflight_report = preflight_info
    expected_context = {
        "task_id": task_id,
        "objective_ref": objective_ref,
        "attempt": attempt,
        "tool_gate_report_path": tool_gate_report_path,
        "preflight_report_path": preflight_report_path,
        "adapter_spec_path": adapter_spec_path,
    }
    handoff_validation = validate_execution_handoff_report(
        handoff_report,
        tool_gate_report,
        preflight_report,
        adapter_spec,
        policy=tool_gate_policy,
        governance=tool_gate_governance,
        approval_records=approval_records_by_attempt.get(attempt, {}),
        approval_record_paths=approval_record_paths_by_attempt.get(attempt, {}),
        task_context=expected_context,
    )
    _merge_prefixed(report, handoff_validation, field_path)


def _load_tool_gate_validation_assets(
    bus_root: Path,
    events: list[dict[str, Any]],
    report: ValidationReport,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not any("tool_gate_report_path" in event for event in events):
        return None, None

    loop_policy_path = bus_root / "loop_policy.yaml"
    if not loop_policy_path.is_file():
        report.error(
            "loop_policy.yaml",
            "required when ledger references tool_gate_report_path",
        )
        return None, None
    try:
        loop_policy = load_yaml(loop_policy_path)
    except YamlLoadError as exc:
        report.error("loop_policy.yaml", f"could not read loop policy: {exc}")
        return None, None
    if not isinstance(loop_policy, dict):
        report.error("loop_policy.yaml", "must contain a mapping")
        return None, None

    config = loop_policy.get("tool_gate_validation")
    if not isinstance(config, dict):
        report.error(
            "loop_policy.yaml.tool_gate_validation",
            "required when ledger references tool_gate_report_path",
        )
        return None, None

    policy = _load_repo_local_yaml_ref(
        bus_root, config.get("policy_path"), "tool_gate_validation.policy_path", report
    )
    governance = _load_repo_local_yaml_ref(
        bus_root,
        config.get("governance_path"),
        "tool_gate_validation.governance_path",
        report,
    )
    return policy, governance


def _load_repo_local_yaml_ref(
    bus_root: Path, reference: Any, path: str, report: ValidationReport
) -> dict[str, Any] | None:
    if not isinstance(reference, str) or not reference:
        report.error(path, "must be a non-empty repo-relative path")
        return None
    ref_path = Path(reference)
    if ref_path.is_absolute():
        report.error(path, "must be repo-relative, not absolute")
        return None

    repo_root = _find_repo_root(bus_root)
    resolved = (repo_root / ref_path).resolve(strict=False)
    if not resolved.is_relative_to(repo_root):
        report.error(path, "must stay within repository root")
        return None
    if not resolved.is_file():
        report.error(path, f"referenced file does not exist: {reference}")
        return None
    try:
        value = load_yaml(resolved)
    except YamlLoadError as exc:
        report.error(path, f"could not read referenced YAML: {exc}")
        return None
    if not isinstance(value, dict):
        report.error(path, "referenced YAML must contain a mapping")
        return None
    return value


def _find_repo_root(start: Path) -> Path:
    search_roots = [
        start.resolve(),
        Path.cwd().resolve(),
        Path(__file__).resolve(),
    ]
    seen: set[Path] = set()
    for search_root in search_roots:
        current = search_root if search_root.is_dir() else search_root.parent
        for candidate in (current, *current.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "pyproject.toml").is_file() and (
                candidate / "agentharness"
            ).is_file():
                return candidate
    return start.resolve()


def _resolve_reference(bus_root: Path, reference: Any) -> tuple[Path | None, str | None]:
    if not isinstance(reference, str) or not reference:
        return None, "must be a non-empty string"
    path = Path(reference)
    candidate = path if path.is_absolute() else bus_root / path
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(bus_root):
        return resolved, "referenced path must stay within bus_root"
    return resolved, None


def _read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return metadata
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    return metadata


def _validate_failure_class_list(
    values: Any, allowed: set[str], path: str, report: ValidationReport
) -> None:
    if not isinstance(values, list) or not values:
        report.error(path, "must be a non-empty list")
        return
    for index, value in enumerate(values):
        if value not in allowed:
            report.error(f"{path}[{index}]", "contains an unknown failure class")


def _mapping(value: Any, path: str, report: ValidationReport) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        report.error(path, "must be a mapping")
        return None
    return value


def _merge(target: ValidationReport, source: ValidationReport) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)


def _merge_prefixed(
    target: ValidationReport, source: ValidationReport, prefix: str
) -> None:
    target.errors.extend(f"{prefix}.{error}" for error in source.errors)
    target.warnings.extend(f"{prefix}.{warning}" for warning in source.warnings)
