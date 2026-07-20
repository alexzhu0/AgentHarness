"""Deterministic single-use methodology evidence-decision contract.

This module evaluates one pre-execution Pi request.  It never invokes Pi,
reads the pinned Pi artifact, or executes a tool.  A ``permit_once`` response
is a finite current-call-bound evidence artifact, not runtime authority.  The
external Pi runtime independently owns authorization, validation, and any
consumption of that evidence.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from .pi_evidence_contract_v1 import (
    CANONICALIZATION_ID,
    ContractValidationError,
    NOT_EXECUTED,
    arguments_digest_v1,
    validate_observation_batch_v1,
)


PERMIT_VERSION = "1.0.0"
PERMIT_REQUEST_KIND = "pi_methodology_permit_request"
PERMIT_RESPONSE_KIND = "agentharness_pi_methodology_permit_response"
PERMIT_REQUEST_SOURCE = "pi_methodology_permit_pilot_v1"
PERMIT_RESPONSE_SOURCE = "agentharness_pi_methodology_permit_evaluator_v1"
PERMIT_POLICY_VERSION = "AH-PI-METHODOLOGY-PERMIT-1"
PERMIT_TOOL_NAME = "win9_methodology_lookup"
PERMIT_QUESTION = "SPIN顾问式销售对应Win9哪一步？"
PINNED_PI_COMMIT = "d4c7682e8cec45f8b76c6f192172da8892e2723d"
PINNED_ARTIFACT_PATH = ".pi/win9-workspaces/win9-main/METHODOLOGY.md"
PINNED_ARTIFACT_DIGEST = (
    "sha256:8d9422391531951b8b8e2d2748cb80e17b11efb2385613350cb324f7fe852a14"
)
MAX_PERMIT_DOCUMENT_BYTES = 64 * 1024

_REQUEST_KEYS = {
    "version",
    "kind",
    "source",
    "result_status",
    "policy_version",
    "artifact_binding",
    "observation_batch",
    "arguments",
}
_ARTIFACT_KEYS = {"pi_commit", "logical_path", "sha256", "result_status"}
_RESPONSE_KEYS = {
    "version",
    "kind",
    "source",
    "result_status",
    "decision",
    "reason_code",
    "call_binding",
    "policy_binding",
    "artifact_binding",
    "constraints",
    "decision_digest",
    "errors",
}


class MethodologyPermitValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def build_methodology_permit_request_v1(
    observation_batch: Mapping[str, Any], arguments: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the exact finite-pilot request envelope without execution."""

    request = {
        "version": PERMIT_VERSION,
        "kind": PERMIT_REQUEST_KIND,
        "source": PERMIT_REQUEST_SOURCE,
        "result_status": NOT_EXECUTED,
        "policy_version": PERMIT_POLICY_VERSION,
        "artifact_binding": _artifact_binding(),
        "observation_batch": dict(observation_batch),
        "arguments": dict(arguments),
    }
    _validate_request_shape(request)
    return request


def parse_methodology_permit_request_json_v1(raw: str | bytes) -> Mapping[str, Any]:
    """Parse one bounded UTF-8 JSON document and reject duplicate keys."""

    if isinstance(raw, bytes):
        encoded = raw
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise MethodologyPermitValidationError("deny.request_invalid_utf8") from None
    elif isinstance(raw, str):
        text = raw
        encoded = raw.encode("utf-8")
    else:
        raise MethodologyPermitValidationError("deny.request_invalid")
    if not encoded:
        raise MethodologyPermitValidationError("deny.request_empty")
    if len(encoded) > MAX_PERMIT_DOCUMENT_BYTES:
        raise MethodologyPermitValidationError("deny.request_too_large")
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, RecursionError):
        raise MethodologyPermitValidationError("deny.request_invalid_json") from None
    if not isinstance(value, dict):
        raise MethodologyPermitValidationError("deny.request_invalid")
    return value


def evaluate_methodology_permit_request_v1(request: Any) -> dict[str, Any]:
    """Return deterministic ``permit_once`` evidence or a denial."""

    code, call_binding = _decision_code_and_binding(request)
    decision = "permit_once" if code == "permit.exact_methodology_lookup" else "deny"
    return _response(decision, code, call_binding)


def denied_methodology_permit_response_v1(code: str) -> dict[str, Any]:
    """Return a bounded deterministic denial for transport/parser failures."""

    safe_code = code if code.startswith("deny.") else "deny.request_invalid"
    return _response("deny", safe_code, None)


def verify_methodology_permit_response_v1(response: Any, request: Any) -> dict[str, Any]:
    """Verify exact deterministic response/request correlation in memory."""

    expected = evaluate_methodology_permit_request_v1(request)
    valid = isinstance(response, dict) and response == expected
    return {
        "result_status": NOT_EXECUTED,
        "valid": valid,
        "errors": [] if valid else ["response.invalid_or_mismatched"],
    }


def _decision_code_and_binding(
    request: Any,
) -> tuple[str, dict[str, Any] | None]:
    try:
        _validate_request_shape(request)
    except MethodologyPermitValidationError as exc:
        return exc.code, None

    assert isinstance(request, dict)
    observation_batch = request["observation_batch"]
    try:
        validated_batch = validate_observation_batch_v1(observation_batch)
    except (ContractValidationError, RecursionError, OverflowError, TypeError, ValueError):
        return "deny.observation_invalid", None

    batch = validated_batch.get("batch")
    observations = batch.get("observations") if isinstance(batch, Mapping) else None
    if not isinstance(observations, list) or len(observations) != 1:
        return "deny.observation_count", None
    observation = observations[0]
    if not isinstance(observation, Mapping):
        return "deny.observation_invalid", None
    binding = observation.get("call_binding")
    if not isinstance(binding, Mapping):
        return "deny.call_binding_invalid", None
    call_binding = {
        "tool_call_id": binding.get("tool_call_id"),
        "tool_name": binding.get("tool_name"),
        "arguments_canonicalization_id": binding.get(
            "arguments_canonicalization_id"
        ),
        "arguments_digest": binding.get("arguments_digest"),
        "result_status": NOT_EXECUTED,
    }

    if request.get("policy_version") != PERMIT_POLICY_VERSION:
        return "deny.policy_mismatch", call_binding
    if request.get("artifact_binding") != _artifact_binding():
        return "deny.artifact_mismatch", call_binding
    if call_binding["tool_name"] != PERMIT_TOOL_NAME:
        return "deny.tool_not_allowed", call_binding
    if call_binding["arguments_canonicalization_id"] != CANONICALIZATION_ID:
        return "deny.canonicalization_mismatch", call_binding

    arguments = request.get("arguments")
    if not isinstance(arguments, dict) or set(arguments) != {"question"}:
        return "deny.arguments_not_allowed", call_binding
    question = arguments.get("question")
    if not isinstance(question, str) or question != PERMIT_QUESTION:
        return "deny.question_not_allowed", call_binding
    try:
        expected_digest = arguments_digest_v1(arguments)
    except (ContractValidationError, RecursionError, OverflowError, TypeError, ValueError):
        return "deny.arguments_invalid", call_binding
    if call_binding["arguments_digest"] != expected_digest:
        return "deny.arguments_digest_mismatch", call_binding
    return "permit.exact_methodology_lookup", call_binding


def _validate_request_shape(request: Any) -> None:
    if not isinstance(request, dict) or set(request) != _REQUEST_KEYS:
        raise MethodologyPermitValidationError("deny.request_shape")
    constants = (
        ("version", PERMIT_VERSION),
        ("kind", PERMIT_REQUEST_KIND),
        ("source", PERMIT_REQUEST_SOURCE),
        ("result_status", NOT_EXECUTED),
    )
    if any(request.get(key) != expected for key, expected in constants):
        raise MethodologyPermitValidationError("deny.request_contract_mismatch")
    artifact = request.get("artifact_binding")
    if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT_KEYS:
        raise MethodologyPermitValidationError("deny.artifact_invalid")
    if not isinstance(request.get("observation_batch"), dict):
        raise MethodologyPermitValidationError("deny.observation_invalid")
    if not isinstance(request.get("arguments"), dict):
        raise MethodologyPermitValidationError("deny.arguments_invalid")


def _response(
    decision: str, reason_code: str, call_binding: dict[str, Any] | None
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "version": PERMIT_VERSION,
        "kind": PERMIT_RESPONSE_KIND,
        "source": PERMIT_RESPONSE_SOURCE,
        "result_status": NOT_EXECUTED,
        "decision": decision,
        "reason_code": reason_code,
        "call_binding": call_binding,
        "policy_binding": {
            "policy_version": PERMIT_POLICY_VERSION,
            "result_status": NOT_EXECUTED,
        },
        "artifact_binding": _artifact_binding(),
        "constraints": {
            "local_read_only": True,
            "network_allowed": False,
            "write_allowed": False,
            "subprocess_allowed": False,
            "follow_up_allowed": False,
            "single_use": True,
            "single_use_scope": "agent_session_current_tool_call",
            "result_status": NOT_EXECUTED,
        },
        "errors": [] if decision == "permit_once" else [reason_code],
    }
    response["decision_digest"] = arguments_digest_v1(response)
    if set(response) != _RESPONSE_KEYS:
        raise AssertionError("permit response contract drift")
    return response


def _artifact_binding() -> dict[str, Any]:
    return {
        "pi_commit": PINNED_PI_COMMIT,
        "logical_path": PINNED_ARTIFACT_PATH,
        "sha256": PINNED_ARTIFACT_DIGEST,
        "result_status": NOT_EXECUTED,
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value
