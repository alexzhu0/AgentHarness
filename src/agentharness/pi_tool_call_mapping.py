"""Pure mock validator for static Pi-like tool-call mapping fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .audit_contract import (
    NOT_EXECUTED,
    SHA256_DIGEST_PATTERN,
    VERSION,
    sanitize_audit_message,
)
from .handoff_exporter import build_handoff_export_package
from .handoff_manifest import build_handoff_export_manifest


REPORT_KIND = "pi_tool_call_mapping_validation_report"
REPORT_SOURCE = "build_pi_tool_call_mapping_report"
OBSERVATION_KIND = "pi_tool_call_observation_batch"
EXPECTATION_KIND = "agentharness_pi_mapping_expectations"
DECISION_VOCABULARY = ("allow_candidate", "block", "unsupported", "error")


def build_pi_tool_call_mapping_report(
    observations_path: str | Path,
    expectations_path: str | Path,
    bus_root: str | Path,
) -> dict[str, Any]:
    """Validate static Pi-like observations against expected mock decisions.

    This function is intentionally AgentHarness-local, deterministic, and side-effect
    free aside from reading fixture/evidence files. It never imports, calls, or
    normalizes toward Pi runtime behavior, and it never turns ``allow_candidate``
    into runtime allow.
    """

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    observations_payload = _load_json_mapping(observations_path, "observations", checks)
    expectations_payload = _load_json_mapping(expectations_path, "expectations", checks)

    if observations_payload is not None:
        _validate_top_level(
            observations_payload,
            "observations",
            OBSERVATION_KIND,
            errors,
            checks,
        )
    if expectations_payload is not None:
        _validate_top_level(
            expectations_payload,
            "expectations",
            EXPECTATION_KIND,
            errors,
            checks,
        )

    package, package_errors = _build_package(bus_root, checks)
    errors.extend(package_errors)
    manifest, manifest_errors = _build_manifest(bus_root, checks)
    errors.extend(manifest_errors)

    observations = _mapping_list(
        observations_payload, "observations", "observations.observations", errors
    )
    expectations = _mapping_list(
        expectations_payload,
        "mapping_expectations",
        "expectations.mapping_expectations",
        errors,
    )

    _check_unique_ids(observations, "observation_id", "observations", errors)
    _check_unique_ids(expectations, "observation_id", "expectations", errors)
    _check_order(observations, expectations, errors, checks)
    _check_decision_vocabulary(expectations_payload, expectations, errors, checks)

    evidence = _Evidence(package, manifest)
    decisions: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        expectation = expectations[index] if index < len(expectations) else None
        decisions.append(_decision_report(index, observation, expectation, evidence, errors))

    summary = _summary(observations, expectations, decisions)
    _add_check(
        checks,
        "decision_derivation",
        bool(decisions)
        and len(decisions) == len(observations) == len(expectations)
        and all(decision.get("decision_matches_expectation") is True for decision in decisions),
        "derived one mock decision per observation and matched expectations",
    )

    failed_check_ids = _failed_check_ids(checks)
    final_errors = list(errors)
    if failed_check_ids:
        final_errors.append(
            "checks: failed check(s): " + ", ".join(failed_check_ids)
        )

    report = {
        "version": VERSION,
        "kind": REPORT_KIND,
        "source": REPORT_SOURCE,
        "result_status": NOT_EXECUTED,
        "ok": not final_errors and not failed_check_ids,
        "summary": summary,
        "decisions": decisions,
        "checks": checks,
        "errors": final_errors,
        "warnings": warnings,
    }
    return _sanitize_report(report)


class _Evidence:
    def __init__(
        self,
        package: Mapping[str, Any] | None,
        manifest: Mapping[str, Any] | None,
    ) -> None:
        self.package = package
        self.manifest = manifest
        self.exports_by_request = _items_by_request(package, "exports")
        self.manifest_by_request = _items_by_request(manifest, "items")

    def bind_allow_candidate(
        self,
        request_id: Any,
        observation_request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        binding = {
            "request_id": request_id if isinstance(request_id, str) else None,
            "observation_request": dict(observation_request),
            "export_request": None,
            "export": None,
            "manifest": None,
            "gate": None,
        }
        errors: list[str] = []
        if not isinstance(request_id, str) or not request_id:
            errors.append("allow_candidate.evidence.request_id: must be a non-empty string")
            return binding, errors
        if self.package is None:
            errors.append("allow_candidate.evidence.export_package: unavailable")
            return binding, errors
        if self.manifest is None:
            errors.append("allow_candidate.evidence.manifest: unavailable")
            return binding, errors
        if self.package.get("result_status") != NOT_EXECUTED:
            errors.append("allow_candidate.evidence.export_package.result_status: must be not_executed")
        if self.manifest.get("result_status") != NOT_EXECUTED:
            errors.append("allow_candidate.evidence.manifest.result_status: must be not_executed")

        export_item = self.exports_by_request.get(request_id)
        manifest_item = self.manifest_by_request.get(request_id)
        if export_item is None:
            errors.append(f"allow_candidate.evidence.export: missing request_id {request_id!r}")
        if manifest_item is None:
            errors.append(f"allow_candidate.evidence.manifest: missing request_id {request_id!r}")
        if export_item is None or manifest_item is None:
            return binding, errors

        export_gate = _mapping_or_empty(export_item.get("gate"))
        export_request = _mapping_or_empty(export_item.get("request"))
        binding["export_request"] = {
            "tool_name": export_request.get("tool_name"),
            "category": export_request.get("category"),
            "intent": export_request.get("intent"),
            "target_scope": export_request.get("target_scope"),
        }
        semantic_errors = _request_semantic_errors(observation_request, export_request)
        errors.extend(semantic_errors)
        if export_item.get("result_status") != NOT_EXECUTED:
            errors.append("allow_candidate.evidence.export.result_status: must be not_executed")
        if manifest_item.get("result_status") != NOT_EXECUTED:
            errors.append("allow_candidate.evidence.manifest_item.result_status: must be not_executed")
        if export_gate.get("result_status") != NOT_EXECUTED:
            errors.append("allow_candidate.evidence.gate.result_status: must be not_executed")
        if export_gate.get("handoff_ready") is not True:
            errors.append("allow_candidate.evidence.gate.handoff_ready: must be true")

        binding["export"] = {
            "request_id": export_item.get("request_id"),
            "handoff_id": export_item.get("handoff_id"),
            "handoff_digest": export_item.get("handoff_digest"),
            "result_status": export_item.get("result_status"),
        }
        binding["manifest"] = {
            "request_id": manifest_item.get("request_id"),
            "handoff_id": manifest_item.get("handoff_id"),
            "handoff_digest": manifest_item.get("handoff_digest"),
            "export_item_digest": manifest_item.get("export_item_digest"),
            "result_status": manifest_item.get("result_status"),
        }
        binding["gate"] = {
            "handoff_ready": export_gate.get("handoff_ready") is True,
            "result_status": export_gate.get("result_status"),
        }
        return binding, errors


def _decision_report(
    index: int,
    observation: Mapping[str, Any],
    expectation: Mapping[str, Any] | None,
    evidence: _Evidence,
    report_errors: list[str],
) -> dict[str, Any]:
    observation_id = observation.get("observation_id")
    expected_decision = (
        expectation.get("expected_decision") if isinstance(expectation, Mapping) else None
    )
    expected_observation_id = (
        expectation.get("observation_id") if isinstance(expectation, Mapping) else None
    )

    decision, reason, binding, decision_errors = _derive_decision(observation, evidence)
    if expected_decision != decision:
        report_errors.append(
            f"decisions[{index}].decision: expected {expected_decision!r}, got {decision!r}"
        )
        report_errors.extend(
            f"decisions[{index}].{error}" for error in decision_errors
        )
    if expected_observation_id != observation_id:
        report_errors.append(
            f"decisions[{index}].observation_id: expected {expected_observation_id!r}, got {observation_id!r}"
        )

    return {
        "kind": "pi_tool_call_mapping_decision",
        "result_status": NOT_EXECUTED,
        "observation_id": observation_id if isinstance(observation_id, str) else None,
        "order_index": observation.get("order_index"),
        "tool_call_id": observation.get("tool_call_id")
        if isinstance(observation.get("tool_call_id"), str)
        else None,
        "decision": decision,
        "expected_decision": expected_decision
        if isinstance(expected_decision, str)
        else None,
        "decision_matches_expectation": expected_decision == decision,
        "reason": reason,
        "evidence_binding": binding,
        "errors": _sanitize_list(decision_errors),
        "warnings": [],
    }


def _derive_decision(
    observation: Mapping[str, Any],
    evidence: _Evidence,
) -> tuple[str, str, dict[str, Any] | None, list[str]]:
    missing = _missing_observation_fields(observation)
    if missing:
        return (
            "error",
            f"malformed observation missing required field(s): {', '.join(missing)}",
            None,
            [f"observation: malformed missing {', '.join(missing)}"],
        )

    arguments_digest = observation.get("arguments_digest")
    if not isinstance(arguments_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
        arguments_digest
    ):
        return (
            "error",
            "malformed observation has invalid arguments_digest",
            None,
            ["observation.arguments_digest: must match sha256:<64 lowercase hex characters>"],
        )

    tool_name = _string_value(observation.get("tool_name"))
    category = _string_value(observation.get("category_candidate"))
    intent = _string_value(observation.get("intent_candidate"))
    target_scope = _string_value(observation.get("target_scope_candidate"))

    if category == "shell" or tool_name in {"bash", "shell", "sh"}:
        return ("block", "shell-like observation fails closed by policy", None, [])
    if category in {"file_write", "file_edit", "file_delete"} or tool_name in {
        "edit_file",
        "write_file",
        "delete_file",
    }:
        return ("unsupported", "write/edit-like observation is unsupported in T036", None, [])
    if category == "file_read":
        if intent == "inspect_workspace" and target_scope == "repository":
            request_id = _mapping_or_empty(
                observation.get("agentharness_refs_if_available")
            ).get("request_id_candidate")
            observation_request = {
                "tool_name": tool_name,
                "category": category,
                "intent": intent,
                "target_scope": target_scope,
            }
            binding, binding_errors = evidence.bind_allow_candidate(
                request_id,
                observation_request,
            )
            if binding_errors:
                return (
                    "error",
                    "read-like allow_candidate could not be bound to export and manifest evidence",
                    binding,
                    binding_errors,
                )
            return (
                "allow_candidate",
                "read-like repository inspection binds to existing ready AgentHarness evidence",
                binding,
                [],
            )
        return (
            "unsupported",
            "read-like observation has unsupported intent or target scope",
            None,
            [],
        )

    # Unknown categories fail closed without becoming allow_candidate.
    return ("unsupported", "unknown observation category fails closed as unsupported", None, [])


def _missing_observation_fields(observation: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    required_strings = (
        "observation_id",
        "tool_name",
        "arguments_digest",
        "category_candidate",
        "intent_candidate",
        "target_scope_candidate",
    )
    for field_name in required_strings:
        if not _string_value(observation.get(field_name)):
            missing.append(field_name)
    if not isinstance(observation.get("order_index"), int):
        missing.append("order_index")
    return missing


def _load_json_mapping(
    path: str | Path,
    label: str,
    checks: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        _add_check(
            checks,
            f"load_{label}",
            False,
            f"{label}: malformed UTF-8 at byte {exc.start}",
        )
        return None
    except OSError:
        _add_check(checks, f"load_{label}", False, f"{label}: could not read JSON")
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        _add_check(
            checks,
            f"load_{label}",
            False,
            f"{label}: malformed JSON at line {exc.lineno} column {exc.colno}",
        )
        return None
    if not isinstance(value, Mapping):
        _add_check(checks, f"load_{label}", False, f"{label}: must be a JSON object")
        return None
    _add_check(checks, f"load_{label}", True, f"{label}: JSON object loaded")
    return value


def _validate_top_level(
    payload: Mapping[str, Any],
    label: str,
    expected_kind: str,
    errors: list[str],
    checks: list[dict[str, Any]],
) -> None:
    check_errors: list[str] = []
    if payload.get("kind") != expected_kind:
        check_errors.append(f"{label}.kind: must be {expected_kind}")
    if payload.get("schema_version") != VERSION:
        check_errors.append(f"{label}.schema_version: must be {VERSION}")
    if payload.get("result_status") != NOT_EXECUTED:
        check_errors.append(f"{label}.result_status: must be not_executed")
    errors.extend(check_errors)
    _add_check(
        checks,
        f"validate_{label}_top_level",
        not check_errors,
        f"{label}: kind, schema_version, and result_status are valid",
        check_errors,
    )


def _build_package(
    bus_root: str | Path,
    checks: list[dict[str, Any]],
) -> tuple[Mapping[str, Any] | None, list[str]]:
    package, report = build_handoff_export_package(bus_root)
    errors = [f"export_package.{error}" for error in report.errors]
    _add_check(
        checks,
        "build_export_package",
        package is not None and report.ok,
        "handoff export package evidence built",
        errors,
    )
    return package, _sanitize_list(errors)


def _build_manifest(
    bus_root: str | Path,
    checks: list[dict[str, Any]],
) -> tuple[Mapping[str, Any] | None, list[str]]:
    manifest, report = build_handoff_export_manifest(bus_root)
    errors = [f"manifest.{error}" for error in report.errors]
    _add_check(
        checks,
        "build_manifest",
        manifest is not None and report.ok,
        "handoff export manifest evidence built",
        errors,
    )
    return manifest, _sanitize_list(errors)


def _mapping_list(
    payload: Mapping[str, Any] | None,
    field_name: str,
    path: str,
    errors: list[str],
) -> list[Mapping[str, Any]]:
    if payload is None:
        errors.append(f"{path}: unavailable")
        return []
    value = payload.get(field_name)
    if not isinstance(value, list):
        errors.append(f"{path}: must be a list")
        return []
    mappings: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            errors.append(f"{path}[{index}]: must be an object")
            continue
        mappings.append(item)
    return mappings


def _check_unique_ids(
    items: list[Mapping[str, Any]],
    field_name: str,
    label: str,
    errors: list[str],
) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        value = item.get(field_name)
        if not isinstance(value, str) or not value:
            errors.append(f"{label}[{index}].{field_name}: must be a non-empty string")
            continue
        if value in seen:
            errors.append(f"{label}.{field_name}: duplicate value {value!r}")
        seen.add(value)


def _check_order(
    observations: list[Mapping[str, Any]],
    expectations: list[Mapping[str, Any]],
    errors: list[str],
    checks: list[dict[str, Any]],
) -> None:
    observation_ids = [item.get("observation_id") for item in observations]
    expectation_ids = [item.get("observation_id") for item in expectations]
    order_ok = observation_ids == expectation_ids
    check_errors = [] if order_ok else ["order: observation IDs must match expectation IDs"]
    errors.extend(check_errors)
    _add_check(
        checks,
        "check_observation_expectation_order",
        order_ok,
        "observation and expectation order matches",
        check_errors,
    )


def _request_semantic_errors(
    observation_request: Mapping[str, Any],
    export_request: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    pairs = (
        ("tool_name", "tool_name"),
        ("category", "category"),
        ("intent", "intent"),
        ("target_scope", "target_scope"),
    )
    for observation_field, export_field in pairs:
        observation_value = observation_request.get(observation_field)
        export_value = export_request.get(export_field)
        if observation_value != export_value:
            errors.append(
                "allow_candidate.evidence.request_semantic_mismatch: "
                f"observation.{observation_field}={observation_value!r} "
                f"does not match export.request.{export_field}={export_value!r}"
            )
    return errors


def _check_decision_vocabulary(
    expectations_payload: Mapping[str, Any] | None,
    expectations: list[Mapping[str, Any]],
    errors: list[str],
    checks: list[dict[str, Any]],
) -> None:
    check_errors: list[str] = []
    top_level_vocabulary = (
        expectations_payload.get("decision_vocabulary")
        if isinstance(expectations_payload, Mapping)
        else None
    )
    if top_level_vocabulary != list(DECISION_VOCABULARY):
        check_errors.append(
            "expectations.decision_vocabulary: must exactly equal "
            f"{list(DECISION_VOCABULARY)!r}"
        )
    for index, expectation in enumerate(expectations):
        decision = expectation.get("expected_decision")
        if decision not in DECISION_VOCABULARY:
            check_errors.append(
                f"expectations[{index}].expected_decision: must be one of {list(DECISION_VOCABULARY)!r}"
            )
    errors.extend(check_errors)
    _add_check(
        checks,
        "check_decision_vocabulary",
        not check_errors,
        "expectation decisions use the fixed mock vocabulary",
        check_errors,
    )


def _summary(
    observations: list[Mapping[str, Any]],
    expectations: list[Mapping[str, Any]],
    decisions: list[Mapping[str, Any]],
) -> dict[str, Any]:
    counts = {decision: 0 for decision in DECISION_VOCABULARY}
    for decision in decisions:
        value = decision.get("decision")
        if value in counts:
            counts[value] += 1
    return {
        "observations": len(observations),
        "expectations": len(expectations),
        "decisions": len(decisions),
        "allow_candidate": counts["allow_candidate"],
        "block": counts["block"],
        "unsupported": counts["unsupported"],
        "error": counts["error"],
        "decision_vocabulary": list(DECISION_VOCABULARY),
        "result_status": NOT_EXECUTED,
    }


def _items_by_request(
    payload: Mapping[str, Any] | None,
    field_name: str,
) -> dict[str, Mapping[str, Any]]:
    if payload is None:
        return {}
    value = payload.get(field_name)
    if not isinstance(value, list):
        return {}
    by_request: dict[str, Mapping[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            continue
        request_id = item.get("request_id")
        if isinstance(request_id, str) and request_id:
            by_request[request_id] = item
    return by_request


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    ok: bool,
    description: str,
    errors: list[str] | None = None,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "pass" if ok else "fail",
            "result_status": NOT_EXECUTED,
            "description": description,
            "errors": _sanitize_list(errors or []),
            "warnings": [],
        }
    )


def _failed_check_ids(checks: list[dict[str, Any]]) -> list[str]:
    failed: list[str] = []
    for check in checks:
        if check.get("status") != "pass":
            check_id = check.get("id")
            failed.append(check_id if isinstance(check_id, str) else "<unknown>")
    return failed


def _sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_payload(report)
    if isinstance(sanitized, dict):
        return sanitized
    return report


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_audit_message(value)
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()}
    return value


def _sanitize_list(values: list[str]) -> list[str]:
    return [sanitize_audit_message(value) for value in values]


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
