"""Bounded, evidence-only Pi observation contract v1.

The contract correlates observation envelopes with frozen legacy evidence.  It
does not establish authenticity, hostile-tamper resistance, or argument-specific
legacy evidence: byte-identical replay remains indistinguishable here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import errno
import hashlib
import json
import math
from pathlib import Path
import os
import re
import stat
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from urllib.parse import unquote

import yaml

from .execution_handoff import execution_handoff_digest
from .execution_handoff import (
    validate_execution_handoff_report,
    validate_runtime_adapter_spec,
)
from .execution_preflight import validate_execution_preflight_report
from .tool_gate import validate_tool_gate_report


REQUEST_SCHEMA_ID = "urn:agentharness:schema:pi-tool-call-observation-batch:1"
RESPONSE_SCHEMA_ID = "urn:agentharness:schema:pi-tool-call-evidence-response-batch:1"
CONTRACT_ID = "AH-PI-EVIDENCE-BINDING-1"
CANONICALIZATION_ID = "AH-ARGS-C14N-1"
ORDER_CONTRACT_ID = "AH-PI-BATCH-ORDER-1"
BATCH_ID_CONTRACT_ID = "AH-PI-BATCH-ID-1"
SNAPSHOT_CONTRACT_ID = "AH-EVIDENCE-SNAPSHOT-1"
NOT_EXECUTED = "not_executed"
REQUEST_KIND = "pi_tool_call_observation_batch"
RESPONSE_KIND = "agentharness_pi_evidence_response_batch"
REQUEST_SOURCE = "pi_pure_observation_builder_v1"
RESPONSE_SOURCE = "agentharness_pi_evidence_evaluator_v1"
DECISION_VOCABULARY = ("allow_candidate", "block", "unsupported", "error")

# Public aliases use the architect's normative contract terminology.
ARGS_CANONICALIZATION = CANONICALIZATION_ID
BATCH_ORDER = ORDER_CONTRACT_ID
BATCH_ID = BATCH_ID_CONTRACT_ID
SNAPSHOT_ID = SNAPSHOT_CONTRACT_ID

MAX_OBSERVATIONS = 32
MAX_JSON_DOCUMENT_BYTES = 256 * 1024
MAX_SNAPSHOT_FILES = 256
MAX_SNAPSHOT_FILE_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_SNAPSHOT_ENTRIES = 1024
MAX_EXTERNAL_DEPENDENCIES = 8
MAX_STRUCTURE_DEPTH = 64
MAX_PERCENT_DECODING_PASSES = 8

_SHELL_METACHAR_RE = re.compile(r"(?:[|&;$`<>]|\$\()")
_GLOB_RE = re.compile(r"[*?[\]{}]")
_ASCII_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_REJECTED_CODES = frozenset(
    {
        "request.invalid",
        "request.depth_exceeded",
        "request.cycle_detected",
        "snapshot.invalid",
        "snapshot.bus_unreadable",
        "snapshot.resource_limit",
        "snapshot.file_unreadable",
        "snapshot.file_changed",
        "snapshot.symlink_not_allowed",
        "snapshot.structured_file_malformed",
        "snapshot.evidence_chain_invalid",
        "evaluation.depth_exceeded",
        "evaluation.internal_error",
    }
)

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SEMVER_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_BATCH_RE = re.compile(r"pi-batch:([0-9a-f]{64})\Z")
_OBSERVATION_RE = re.compile(r"pi-observation:([0-9a-f]{64}):([0-9]{6})\Z")
_OPAQUE_IDENTIFIER_RE = re.compile(
    r"(?!.*(?:^|[._:@+-])(?:sk(?:-proj)?[-_]|gh[porus]_|github_pat_|AKIA|ASIA|eyJ))"
    r"[A-Za-z0-9][A-Za-z0-9._:@+-]{0,191}\Z"
)
_MAPPING_CATEGORIES = frozenset({"file_read", "file_write", "file_delete", "shell", "unknown"})
_MAPPING_INTENTS = frozenset(
    {"inspect_workspace", "inspect_config", "edit_file", "delete_file", "run_tests", "unknown"}
)
_MAPPING_SCOPES = frozenset({"repository", "outside_repository", "unknown"})
_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "adapter_id", "adapter_kind", "adapter_version", "execution_plane",
        "status", "adapter_spec_path", "adapter_spec_digest",
    }
)
_REGISTRY_STATUSES = frozenset({"active", "deprecated", "disabled"})
_RANGE_OR_WILDCARD_TOKENS = ("*", "<", ">", "=", "^", "~", "|", ",")
_FORBIDDEN = frozenset(
    {
        "request_id_candidate",
        "expectations",
        "expected_decision",
        "decision_matches_expectation",
        "fixture_bus",
        "fixture_path",
        "fixture_identity",
        "allow",
        "authorized",
        "safe_to_execute",
        "execution_allowed",
        "runtime_allow",
    }
)


class ContractValidationError(ValueError):
    def __init__(self, codes: Sequence[str]):
        self.codes = tuple(dict.fromkeys(codes)) or ("contract.invalid",)
        super().__init__(self.codes[0])


class SnapshotValidationError(ValueError):
    def __init__(self, codes: Sequence[str]):
        self.codes = tuple(dict.fromkeys(codes)) or ("snapshot.invalid",)
        super().__init__(self.codes[0])


@dataclass(frozen=True)
class EvidenceRecord:
    semantic_key: tuple[str, str, str, str, str, str]
    status: str
    request_id: str
    handoff_id: str
    handoff_digest: str
    adapter_spec_digest: str
    export_item_digest: str | None


@dataclass(frozen=True)
class EvidenceSnapshot:
    snapshot_digest: str
    file_digests: tuple[tuple[str, str], ...]
    records: tuple[EvidenceRecord, ...]
    export_package_digest: str


def canonicalize_pi_arguments_v1(value: Any) -> bytes:
    """Return AH-ARGS-C14N-1 UTF-8 bytes for compatibility with digest callers."""

    return canonicalize_arguments_v1(value).encode("utf-8")


def build_pi_observation_batch_v1(
    observations: Sequence[Mapping[str, Any]],
    *,
    adapter_id: str = "pi-tool-call-v0",
    adapter_version: str = "0.1.0",
) -> dict[str, Any]:
    """Build a deterministic envelope from ordered raw Pi observations.

    Raw items contain only ``tool_call_id``, exact runtime ``tool_name``, and
    validated ``arguments``. Semantic mapping, identities, and digests are
    always internally derived.
    """

    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise ValueError("observations: must be an ordered sequence")
    if not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise ValueError("observations: must contain 1..32 items")
    adapter_id = _opaque_identifier(adapter_id, "adapter_id")
    adapter_version = _opaque_identifier(adapter_version, "adapter_version")
    raw_keys = {"tool_call_id", "tool_name", "arguments"}
    built: list[dict[str, Any]] = []
    seen_calls: set[str] = set()
    for index, item in enumerate(observations):
        if not isinstance(item, Mapping):
            raise ValueError(f"observations[{index}]: must be an object")
        if set(item) != raw_keys:
            raise ValueError(f"observations[{index}]: caller-provided/unknown fields are forbidden")
        call_id = item.get("tool_call_id")
        tool_name = item.get("tool_name")
        if not _is_opaque_identifier(call_id) or call_id in seen_calls:
            raise ValueError(f"observations[{index}].tool_call_id: invalid or duplicate")
        if not _is_opaque_identifier(tool_name):
            raise ValueError(f"observations[{index}].tool_name: invalid")
        arguments = item.get("arguments")
        canonicalize_arguments_v1(arguments)
        claim = derive_mapping_claim_v1(tool_name, arguments)
        seen_calls.add(call_id)
        built.append(
            {
                "observation_id": "pending",
                "order_index": index,
                "result_status": NOT_EXECUTED,
                "call_binding": {
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                    "arguments_canonicalization_id": CANONICALIZATION_ID,
                    "arguments_digest": arguments_digest_v1(arguments),
                    "result_status": NOT_EXECUTED,
                },
                "mapping_claim": {**claim, "result_status": NOT_EXECUTED},
            }
        )
    request: dict[str, Any] = {
        "schema_id": REQUEST_SCHEMA_ID,
        "contract_id": CONTRACT_ID,
        "kind": REQUEST_KIND,
        "source": REQUEST_SOURCE,
        "result_status": NOT_EXECUTED,
        "adapter_contract": {
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "result_status": NOT_EXECUTED,
        },
        "batch": {
            "batch_id": "pending",
            "batch_id_contract_id": BATCH_ID_CONTRACT_ID,
            "order_contract_id": ORDER_CONTRACT_ID,
            "result_status": NOT_EXECUTED,
            "observations": built,
        },
    }
    batch_id = derive_batch_id_v1(request)
    digest = batch_id.removeprefix("pi-batch:")
    request["batch"]["batch_id"] = batch_id
    for index, observation in enumerate(built):
        observation["observation_id"] = f"pi-observation:{digest}:{index:06d}"
    validate_observation_batch_v1(request)
    return request


def verify_pi_observation_batch_v1(value: Any) -> dict[str, Any]:
    """Return a side-effect-free independent request verification report."""

    try:
        validated = validate_observation_batch_v1(value)
    except (RecursionError, OverflowError):
        return _request_verification_report(False, "request.depth_exceeded")
    except ContractValidationError as exc:
        return _request_verification_report(False, _request_verification_code(exc.codes))
    except Exception:
        return _request_verification_report(False, "request.invalid")
    return {
        "result_status": NOT_EXECUTED,
        "valid": True,
        "recomputed_batch_id": derive_batch_id_v1(validated),
        "errors": [],
    }


def parse_pi_observation_batch_json_v1(raw: str | bytes) -> Mapping[str, Any]:
    """Parse one bounded JSON request while rejecting duplicate object keys."""

    if isinstance(raw, str):
        encoded = raw.encode("utf-8")
        text = raw
    elif isinstance(raw, bytes):
        encoded = raw
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ContractValidationError(("request.invalid_utf8",)) from None
    else:
        raise ContractValidationError(("request.document_type",))
    if not encoded:
        raise ContractValidationError(("request.empty",))
    if len(encoded) > MAX_JSON_DOCUMENT_BYTES:
        raise ContractValidationError(("request.too_large",))
    try:
        value = _json_loads_unique(text)
    except (RecursionError, OverflowError):
        raise ContractValidationError(("request.depth_exceeded",)) from None
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError):
        raise ContractValidationError(("request.malformed_or_duplicate_json",)) from None
    return validate_observation_batch_v1(value)


def build_pi_evidence_response_v1(
    observation_batch: Any, bus_root: str | Path
) -> dict[str, Any]:
    """Pure compatibility entry point for a later caller surface."""

    return evaluate_pi_evidence_request_v1(observation_batch, bus_root)


def verify_pi_evidence_response_v1(
    response: Any, observation_batch: Any
) -> dict[str, Any]:
    """Verify response structure and exact binding to the current request.

    This recomputes envelope relationships and echo rules only.  It does not
    authenticate the response or detect byte-identical replay.
    """

    try:
        request = validate_observation_batch_v1(observation_batch)
    except (RecursionError, OverflowError):
        return _verification_report(False, ["request.depth_exceeded"])
    except ContractValidationError as exc:
        return _verification_report(False, [_request_verification_code(exc.codes)])
    except Exception:
        return _verification_report(False, ["request.invalid"])
    try:
        errors = _response_verification_errors(response, request)
    except (KeyError, TypeError, ValueError):
        errors = ["response.invalid"]
    except (OverflowError, RecursionError):
        errors = ["response.depth_exceeded"]
    except Exception:
        errors = ["response.invalid"]
    return _verification_report(not errors, errors)


def canonicalize_arguments_v1(value: Any) -> str:
    """Return AH-ARGS-C14N-1 text for a plain JSON object."""

    if type(value) is not dict:
        raise ContractValidationError(("arguments.root_not_object",))
    return _canonical_value(value, set(), 0)


def derive_mapping_claim_v1(tool_name: str, arguments: Any) -> dict[str, str]:
    """Pure AH-PI-MAPPING-1 mapping from exact tool name and validated args."""

    if not _is_opaque_identifier(tool_name):
        raise ContractValidationError(("request.invalid",))
    canonicalize_arguments_v1(arguments)
    normalized = tool_name.strip().lower()
    path = arguments.get("path") if isinstance(arguments, dict) else None
    path = path if isinstance(path, str) and path else None
    scope = _mapping_scope(path)
    if normalized in {"read", "read_file", "read_workspace", "win9_read_shared"}:
        intent = "inspect_config" if "config" in normalized or _config_path(path) else "inspect_workspace"
        return {
            "tool_name_candidate": "read_file",
            "category_candidate": "file_read",
            "intent_candidate": intent,
            "target_scope_candidate": scope,
        }
    if normalized in {"bash", "shell", "sh", "run_command", "win9_run"}:
        return {
            "tool_name_candidate": "mystery_shell",
            "category_candidate": "shell",
            "intent_candidate": "run_tests",
            "target_scope_candidate": "outside_repository" if scope == "outside_repository" else "repository",
        }
    if normalized in {"delete_file", "runtime_delete"}:
        return {
            "tool_name_candidate": "delete_file",
            "category_candidate": "file_delete",
            "intent_candidate": "delete_file",
            "target_scope_candidate": scope,
        }
    if normalized in {"edit", "edit_file", "write", "write_file", "patch_file", "win9_write_agent_result"}:
        return {
            "tool_name_candidate": normalized,
            "category_candidate": "file_write",
            "intent_candidate": "edit_file",
            "target_scope_candidate": scope,
        }
    return {
        "tool_name_candidate": normalized or "unknown",
        "category_candidate": "unknown",
        "intent_candidate": "unknown",
        "target_scope_candidate": "unknown",
    }


def _mapping_scope(path: str | None) -> str:
    if path is None:
        return "unknown"
    return "repository" if _is_safe_repository_relative_path(path) else "outside_repository"


def _is_safe_repository_relative_path(value: str) -> bool:
    decoded = value
    for _ in range(MAX_PERCENT_DECODING_PASSES):
        if "%" not in decoded:
            break
        try:
            next_value = unquote(decoded, encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError):
            return False
        if next_value == decoded:
            break
        decoded = next_value
    if "%" in decoded:
        return False
    normalized = decoded.replace("\\", "/")
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return False
    if normalized.startswith("~") or _ASCII_CONTROL_RE.search(normalized):
        return False
    if _SHELL_METACHAR_RE.search(normalized) or _GLOB_RE.search(normalized):
        return False
    return not any(part in {"", ".."} for part in normalized.split("/"))


def _config_path(path: str | None) -> bool:
    if path is None:
        return False
    lowered = path.lower()
    return "config" in lowered or lowered.endswith((".yaml", ".yml", ".toml"))


def arguments_digest_v1(value: Any) -> str:
    return _sha256(canonicalize_arguments_v1(value).encode("utf-8"))


def derive_batch_id_v1(request: Mapping[str, Any]) -> str:
    adapter = _as_mapping(request.get("adapter_contract"))
    batch = _as_mapping(request.get("batch"))
    observations = batch.get("observations")
    if not isinstance(observations, list):
        raise ContractValidationError(("request.batch.observations.invalid",))
    seed_items = []
    for item in observations:
        observation = _as_mapping(item)
        binding = _as_mapping(observation.get("call_binding"))
        claim = _as_mapping(observation.get("mapping_claim"))
        seed_items.append(
            {
                "order_index": observation.get("order_index"),
                "tool_call_id": binding.get("tool_call_id"),
                "tool_name": binding.get("tool_name"),
                "arguments_canonicalization_id": binding.get(
                    "arguments_canonicalization_id"
                ),
                "arguments_digest": binding.get("arguments_digest"),
                "tool_name_candidate": claim.get("tool_name_candidate"),
                "category_candidate": claim.get("category_candidate"),
                "intent_candidate": claim.get("intent_candidate"),
                "target_scope_candidate": claim.get("target_scope_candidate"),
            }
        )
    seed = {
        "contract_id": CONTRACT_ID,
        "adapter_id": adapter.get("adapter_id"),
        "adapter_version": adapter.get("adapter_version"),
        "order_contract_id": ORDER_CONTRACT_ID,
        "observations": seed_items,
    }
    return "pi-batch:" + arguments_digest_v1(seed).removeprefix("sha256:")


def validate_observation_batch_v1(value: Any) -> Mapping[str, Any]:
    errors: list[str] = []
    if not isinstance(value, dict):
        raise ContractValidationError(("request.not_object",))
    _find_forbidden(value, errors)
    _keys(
        value,
        {
            "schema_id",
            "contract_id",
            "kind",
            "source",
            "result_status",
            "adapter_contract",
            "batch",
        },
        "request",
        errors,
    )
    for key, expected in (
        ("schema_id", REQUEST_SCHEMA_ID),
        ("contract_id", CONTRACT_ID),
        ("kind", REQUEST_KIND),
        ("source", REQUEST_SOURCE),
        ("result_status", NOT_EXECUTED),
    ):
        _const(value, key, expected, "request", errors)

    adapter = value.get("adapter_contract")
    if not isinstance(adapter, dict):
        errors.append("request.adapter_contract.not_object")
        adapter = {}
    _keys(
        adapter,
        {"adapter_id", "adapter_version", "result_status"},
        "request.adapter_contract",
        errors,
    )
    _opaque_string(adapter, "adapter_id", "request.adapter_contract", errors)
    _opaque_string(adapter, "adapter_version", "request.adapter_contract", errors)
    _const(adapter, "result_status", NOT_EXECUTED, "request.adapter_contract", errors)

    batch = value.get("batch")
    if not isinstance(batch, dict):
        errors.append("request.batch.not_object")
        batch = {}
    _keys(
        batch,
        {
            "batch_id",
            "batch_id_contract_id",
            "order_contract_id",
            "result_status",
            "observations",
        },
        "request.batch",
        errors,
    )
    batch_id = batch.get("batch_id")
    batch_match = _BATCH_RE.fullmatch(batch_id) if isinstance(batch_id, str) else None
    if batch_match is None:
        errors.append("request.batch.batch_id.invalid")
    _const(batch, "batch_id_contract_id", BATCH_ID_CONTRACT_ID, "request.batch", errors)
    _const(batch, "order_contract_id", ORDER_CONTRACT_ID, "request.batch", errors)
    _const(batch, "result_status", NOT_EXECUTED, "request.batch", errors)
    observations = batch.get("observations")
    if not isinstance(observations, list):
        errors.append("request.batch.observations.not_array")
        observations = []
    elif not 1 <= len(observations) <= MAX_OBSERVATIONS:
        errors.append("request.batch.observations.count")

    observation_ids: set[str] = set()
    tool_call_ids: set[str] = set()
    order_ids: set[int] = set()
    for position, item in enumerate(observations):
        path = f"request.batch.observations[{position}]"
        if not isinstance(item, dict):
            errors.append(f"{path}.not_object")
            continue
        _keys(
            item,
            {
                "observation_id",
                "order_index",
                "result_status",
                "call_binding",
                "mapping_claim",
            },
            path,
            errors,
        )
        _const(item, "result_status", NOT_EXECUTED, path, errors)
        order_index = item.get("order_index")
        if type(order_index) is not int or order_index != position:
            errors.append(f"{path}.order_index.invalid")
        elif order_index in order_ids:
            errors.append(f"{path}.order_index.duplicate")
        else:
            order_ids.add(order_index)

        observation_id = item.get("observation_id")
        match = (
            _OBSERVATION_RE.fullmatch(observation_id)
            if isinstance(observation_id, str)
            else None
        )
        if match is None:
            errors.append(f"{path}.observation_id.invalid")
        else:
            if observation_id in observation_ids:
                errors.append(f"{path}.observation_id.duplicate")
            observation_ids.add(observation_id)
            if (
                batch_match is None
                or match.group(1) != batch_match.group(1)
                or int(match.group(2)) != position
            ):
                errors.append(f"{path}.observation_id.binding")

        binding = item.get("call_binding")
        if not isinstance(binding, dict):
            errors.append(f"{path}.call_binding.not_object")
            binding = {}
        _keys(
            binding,
            {
                "tool_call_id",
                "tool_name",
                "arguments_canonicalization_id",
                "arguments_digest",
                "result_status",
            },
            f"{path}.call_binding",
            errors,
        )
        tool_call_id = binding.get("tool_call_id")
        if not _is_opaque_identifier(tool_call_id):
            errors.append(f"{path}.call_binding.tool_call_id.invalid")
        elif tool_call_id in tool_call_ids:
            errors.append(f"{path}.call_binding.tool_call_id.duplicate")
        else:
            tool_call_ids.add(tool_call_id)
        _opaque_string(binding, "tool_name", f"{path}.call_binding", errors)
        _const(
            binding,
            "arguments_canonicalization_id",
            CANONICALIZATION_ID,
            f"{path}.call_binding",
            errors,
        )
        digest = binding.get("arguments_digest")
        if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
            errors.append(f"{path}.call_binding.arguments_digest.invalid")
        _const(binding, "result_status", NOT_EXECUTED, f"{path}.call_binding", errors)

        claim = item.get("mapping_claim")
        if not isinstance(claim, dict):
            errors.append(f"{path}.mapping_claim.not_object")
            claim = {}
        _keys(
            claim,
            {
                "tool_name_candidate",
                "category_candidate",
                "intent_candidate",
                "target_scope_candidate",
                "result_status",
            },
            f"{path}.mapping_claim",
            errors,
        )
        _opaque_string(claim, "tool_name_candidate", f"{path}.mapping_claim", errors)
        for key in ("category_candidate", "intent_candidate", "target_scope_candidate"):
            _string(claim, key, f"{path}.mapping_claim", errors)
        _enum(
            claim, "category_candidate", _MAPPING_CATEGORIES,
            f"{path}.mapping_claim", errors,
        )
        _enum(
            claim, "intent_candidate", _MAPPING_INTENTS,
            f"{path}.mapping_claim", errors,
        )
        _enum(
            claim, "target_scope_candidate", _MAPPING_SCOPES,
            f"{path}.mapping_claim", errors,
        )
        _const(claim, "result_status", NOT_EXECUTED, f"{path}.mapping_claim", errors)
    if not errors and batch_id != derive_batch_id_v1(value):
        errors.append("request.batch.batch_id.derivation")
    if errors:
        raise ContractValidationError(errors)
    return value


def build_evidence_snapshot_v1(bus_root: str | Path) -> EvidenceSnapshot:
    """Read every bus file once and derive all evidence from captured bytes."""

    requested_root = Path(bus_root)
    errors: list[str] = []
    try:
        if requested_root.is_symlink():
            raise SnapshotValidationError(("snapshot.root_symlink_not_allowed",))
        root = requested_root.resolve(strict=True)
        if not root.is_dir():
            raise SnapshotValidationError(("snapshot.bus_unreadable",))
        candidates = _enumerate_snapshot_files(root)
    except SnapshotValidationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise SnapshotValidationError(("snapshot.bus_unreadable",)) from None

    declared_total = 0
    for _path, _relative, declared_metadata in candidates:
        declared_size = declared_metadata[3]
        if declared_size > MAX_SNAPSHOT_FILE_BYTES:
            errors.append("snapshot.resource_limit")
        declared_total += declared_size
        if declared_total > MAX_SNAPSHOT_BYTES:
            errors.append("snapshot.resource_limit")
            break
    if errors:
        raise SnapshotValidationError(errors)

    files: dict[str, bytes] = {}
    total = 0
    for path, relative, declared_metadata in candidates:
        declared_size = declared_metadata[3]
        try:
            raw = _bounded_read(path, MAX_SNAPSHOT_FILE_BYTES, declared_metadata)
        except SnapshotValidationError as exc:
            errors.extend(exc.codes)
            continue
        except (OSError, RuntimeError, ValueError):
            errors.append("snapshot.file_unreadable")
            continue
        if len(raw) != declared_size:
            errors.append("snapshot.file_changed")
        if len(raw) > MAX_SNAPSHOT_FILE_BYTES:
            errors.append("snapshot.resource_limit")
            continue
        total += len(raw)
        if total > MAX_SNAPSHOT_BYTES:
            errors.append("snapshot.resource_limit")
            break
        files[relative] = raw
    if not errors and "ledger.jsonl" not in files:
        errors.append("snapshot.ledger_missing")
    if errors:
        raise SnapshotValidationError(errors)

    _capture_external_dependencies(root, files, errors)
    if errors:
        raise SnapshotValidationError(errors)
    captured: Mapping[str, bytes] = MappingProxyType(dict(files))
    _validate_structured_snapshot(captured)
    file_digests = tuple((path, _sha256(raw)) for path, raw in sorted(captured.items()))
    snapshot_digest = _object_digest(
        {
            "snapshot_contract_id": SNAPSHOT_CONTRACT_ID,
            "files": [
                {"path": path, "raw_bytes_digest": digest}
                for path, digest in file_digests
            ],
        }
    )
    try:
        records, package_digest = _snapshot_records(captured)
    except SnapshotValidationError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise SnapshotValidationError(("snapshot.derived_evidence_invalid",)) from None
    return EvidenceSnapshot(snapshot_digest, file_digests, tuple(records), package_digest)


def _enumerate_snapshot_files(
    root: Path,
) -> list[tuple[Path, str, tuple[int, int, int, int, int]]]:
    candidates: list[tuple[Path, str, tuple[int, int, int, int, int]]] = []
    pending = [root]
    entries_seen = 0
    try:
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    entries_seen += 1
                    if entries_seen > MAX_SNAPSHOT_ENTRIES:
                        raise SnapshotValidationError(("snapshot.resource_limit",))
                    path = Path(entry.path)
                    if entry.is_symlink():
                        raise SnapshotValidationError(("snapshot.symlink_not_allowed",))
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        raise SnapshotValidationError(("snapshot.file_unreadable",))
                    metadata = entry.stat(follow_symlinks=False)
                    candidates.append(
                        (path, path.relative_to(root).as_posix(), _file_identity(metadata))
                    )
                    if len(candidates) > MAX_SNAPSHOT_FILES:
                        raise SnapshotValidationError(("snapshot.resource_limit",))
    except SnapshotValidationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise SnapshotValidationError(("snapshot.bus_unreadable",)) from None
    return sorted(candidates, key=lambda item: item[1])


def _bounded_read(
    path: Path,
    limit: int,
    expected: tuple[int, int, int, int, int] | None = None,
) -> bytes:
    """Read a stable regular file without following any path-component symlink."""

    absolute = Path(os.path.abspath(path))
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    directory = os.open(absolute.anchor, directory_flags)
    descriptor: int | None = None
    try:
        for component in absolute.parts[1:-1]:
            metadata = os.stat(component, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise SnapshotValidationError(("snapshot.symlink_not_allowed",))
            child = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        metadata = os.stat(absolute.name, dir_fd=directory, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise SnapshotValidationError(("snapshot.symlink_not_allowed",))
        descriptor = os.open(absolute.name, os.O_RDONLY | nofollow, dir_fd=directory)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SnapshotValidationError(("snapshot.symlink_not_allowed",)) from None
        raise
    finally:
        os.close(directory)

    try:
        before = os.fstat(descriptor)
        before_identity = _file_identity(before)
        if not stat.S_ISREG(before.st_mode):
            raise SnapshotValidationError(("snapshot.file_changed",))
        if expected is not None and before_identity != expected:
            raise SnapshotValidationError(("snapshot.file_changed",))
        if before.st_size > limit:
            raise SnapshotValidationError(("snapshot.resource_limit",))
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(descriptor)
        if len(raw) > limit:
            raise SnapshotValidationError(("snapshot.resource_limit",))
        if before_identity != _file_identity(after) or len(raw) != before.st_size:
            raise SnapshotValidationError(("snapshot.file_changed",))
        return raw
    finally:
        os.close(descriptor)


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _capture_external_dependencies(
    root: Path, files: dict[str, bytes], errors: list[str]
) -> None:
    """Capture the bounded policy/governance inputs named by frozen handoffs."""

    local_errors: list[str] = []
    events = _ledger(files.get("ledger.jsonl", b""), local_errors)
    references = {
        event.get("execution_handoff_report_path")
        for event in events
        if event.get("event_type") == "designer_review"
        and isinstance(event.get("execution_handoff_report_path"), str)
    }
    dependencies: set[str] = set()
    for reference in references:
        report = _yaml(files, _reference(reference, local_errors), "handoff_report", local_errors)
        if report is None:
            continue
        for field in ("policy_path", "governance_path"):
            value = report.get(field)
            if isinstance(value, str) and value:
                dependencies.add(value)
            else:
                local_errors.append("snapshot.evidence_chain_invalid")
    if len(dependencies) > MAX_EXTERNAL_DEPENDENCIES:
        local_errors.append("snapshot.resource_limit")
    total = sum(len(raw) for raw in files.values())
    for reference in sorted(dependencies)[:MAX_EXTERNAL_DEPENDENCIES]:
        try:
            if reference not in {
                "../../examples/agent_policy.example.yaml",
                "../../policies/tool_governance.yaml",
            }:
                raise OSError
            raw = _read_external_dependency(root / reference)
            total += len(raw)
            if total > MAX_SNAPSHOT_BYTES:
                raise SnapshotValidationError(("snapshot.resource_limit",))
            files[reference] = raw
        except SnapshotValidationError:
            raise
        except (OSError, RuntimeError, ValueError):
            local_errors.append("snapshot.file_unreadable")
    errors.extend(local_errors)


def _read_external_dependency(path: Path) -> bytes:
    """Read one regular file without following any path-component symlink."""

    absolute = Path(os.path.abspath(path))
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    directory = os.open(absolute.anchor, directory_flags)
    try:
        for component in absolute.parts[1:-1]:
            metadata = os.stat(component, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise SnapshotValidationError(("snapshot.symlink_not_allowed",))
            child = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        metadata = os.stat(absolute.name, dir_fd=directory, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise SnapshotValidationError(("snapshot.symlink_not_allowed",))
        descriptor = os.open(absolute.name, os.O_RDONLY | nofollow, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError
        if before.st_size > MAX_SNAPSHOT_FILE_BYTES:
            raise SnapshotValidationError(("snapshot.resource_limit",))
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            raw = stream.read(MAX_SNAPSHOT_FILE_BYTES + 1)
        after = os.fstat(descriptor)
        if len(raw) > MAX_SNAPSHOT_FILE_BYTES:
            raise SnapshotValidationError(("snapshot.resource_limit",))
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        ) or len(raw) != before.st_size:
            raise SnapshotValidationError(("snapshot.file_changed",))
        return raw
    finally:
        os.close(descriptor)


def evaluate_pi_evidence_request_v1(
    request: Any, bus_root: str | Path
) -> dict[str, Any]:
    try:
        validated = validate_observation_batch_v1(request)
    except (RecursionError, OverflowError):
        return rejected_response_v1(("request.depth_exceeded",))
    except ContractValidationError as exc:
        return rejected_response_v1(exc.codes)
    try:
        snapshot = build_evidence_snapshot_v1(bus_root)
    except (RecursionError, OverflowError):
        return rejected_response_v1(("evaluation.depth_exceeded",))
    except SnapshotValidationError as exc:
        return rejected_response_v1(exc.codes)

    adapter = _as_mapping(validated["adapter_contract"])
    batch = _as_mapping(validated["batch"])
    results: list[dict[str, Any]] = []
    counts = {decision: 0 for decision in DECISION_VOCABULARY}
    for item in batch["observations"]:
        observation = _as_mapping(item)
        binding = _as_mapping(observation["call_binding"])
        claim = _as_mapping(observation["mapping_claim"])
        derived_mapping = _independently_derived_mapping(binding, claim)
        if derived_mapping is None:
            decision = "error"
            reason = "mapping_claim_not_independently_derivable"
            evidence = None
        else:
            key = (
                adapter["adapter_id"],
                adapter["adapter_version"],
                *derived_mapping,
            )
            matches = [record for record in snapshot.records if record.semantic_key == key]
            decision, reason, evidence = _match_result(matches, snapshot)
        counts[decision] += 1
        results.append(
            {
                "observation_id": observation["observation_id"],
                "order_index": observation["order_index"],
                "result_status": NOT_EXECUTED,
                "binding_echo": {
                    "tool_call_id": binding["tool_call_id"],
                    "tool_name": binding["tool_name"],
                    "arguments_canonicalization_id": binding[
                        "arguments_canonicalization_id"
                    ],
                    "arguments_digest": binding["arguments_digest"],
                    "result_status": NOT_EXECUTED,
                },
                "mapping_claim_echo": {
                    "tool_name_candidate": claim["tool_name_candidate"],
                    "category_candidate": claim["category_candidate"],
                    "intent_candidate": claim["intent_candidate"],
                    "target_scope_candidate": claim["target_scope_candidate"],
                    "result_status": NOT_EXECUTED,
                },
                "decision": decision,
                "reason_code": reason,
                "evidence_binding": evidence,
                "errors": [reason] if decision == "error" else [],
                "warnings": [],
            }
        )
    return _response(
        snapshot_digest=snapshot.snapshot_digest,
        batch_id=batch["batch_id"],
        status="complete",
        results=results,
        counts=counts,
        errors=[],
    )


def rejected_response_v1(error_codes: Sequence[str]) -> dict[str, Any]:
    sanitized = {_sanitize_rejected_code(code) for code in error_codes}
    diagnostic = min(sanitized) if sanitized else "snapshot.invalid"
    return _response(
        snapshot_digest=None,
        batch_id=None,
        status="rejected",
        results=[],
        counts={decision: 0 for decision in DECISION_VOCABULARY},
        errors=[diagnostic],
    )


def _response(
    *,
    snapshot_digest: str | None,
    batch_id: str | None,
    status: str,
    results: list[dict[str, Any]],
    counts: Mapping[str, int],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "schema_id": RESPONSE_SCHEMA_ID,
        "request_schema_id": REQUEST_SCHEMA_ID,
        "contract_id": CONTRACT_ID,
        "kind": RESPONSE_KIND,
        "source": RESPONSE_SOURCE,
        "result_status": NOT_EXECUTED,
        "evidence_snapshot": None if status == "rejected" else {
            "snapshot_contract_id": SNAPSHOT_CONTRACT_ID,
            "snapshot_digest": snapshot_digest,
            "result_status": NOT_EXECUTED,
        },
        "batch": {
            "batch_id": batch_id,
            "batch_id_contract_id": BATCH_ID_CONTRACT_ID,
            "order_contract_id": ORDER_CONTRACT_ID,
            "evaluation_status": status,
            "result_status": NOT_EXECUTED,
            "results": results,
        },
        "summary": {
            "total": len(results),
            **counts,
            "result_status": NOT_EXECUTED,
        },
        "errors": errors,
        "warnings": [],
    }


def _verification_report(valid: bool, errors: Sequence[str]) -> dict[str, Any]:
    code = _response_verification_code(errors)
    return {
        "kind": "pi_evidence_response_verification",
        "result_status": NOT_EXECUTED,
        "valid": valid,
        "errors": [] if valid else [code],
    }


def _request_verification_report(valid: bool, code: str) -> dict[str, Any]:
    return {
        "result_status": NOT_EXECUTED,
        "valid": valid,
        "errors": [] if valid else [code],
    }


def _request_verification_code(codes: Sequence[str]) -> str:
    if any("depth" in code for code in codes):
        return "request.depth_exceeded"
    if any("cycle" in code or "recursive" in code or "repeated_reference" in code for code in codes):
        return "request.cycle_detected"
    return "request.invalid"


def _response_verification_code(codes: Sequence[str]) -> str:
    if any(code.startswith("request.") for code in codes):
        return _request_verification_code(codes)
    if any("depth" in code for code in codes):
        return "response.depth_exceeded"
    if any("cycle" in code or "recursive" in code for code in codes):
        return "response.cycle_detected"
    return "response.invalid"


def _response_verification_errors(
    response: Any, request: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    if type(response) is not dict:
        return ["response.not_object"]
    _exact_keys(
        response,
        {
            "schema_id", "request_schema_id", "contract_id", "kind", "source",
            "result_status", "evidence_snapshot", "batch", "summary", "errors",
            "warnings",
        },
        "response",
        errors,
    )
    constants = {
        "schema_id": RESPONSE_SCHEMA_ID,
        "request_schema_id": REQUEST_SCHEMA_ID,
        "contract_id": CONTRACT_ID,
        "kind": RESPONSE_KIND,
        "source": RESPONSE_SOURCE,
        "result_status": NOT_EXECUTED,
    }
    for key, expected in constants.items():
        if response.get(key) != expected:
            errors.append(f"response.{key}.invalid")
    _message_list(response.get("errors"), "response.errors", errors)
    _message_list(response.get("warnings"), "response.warnings", errors)
    response_batch = response.get("batch")
    summary = response.get("summary")
    if type(response_batch) is not dict:
        errors.append("response.batch.not_object")
        response_batch = {}
    if type(summary) is not dict:
        errors.append("response.summary.not_object")
        summary = {}
    _exact_keys(
        response_batch,
        {
            "batch_id", "batch_id_contract_id", "order_contract_id",
            "evaluation_status", "result_status", "results",
        },
        "response.batch",
        errors,
    )
    _exact_keys(
        summary,
        {"total", *DECISION_VOCABULARY, "result_status"},
        "response.summary",
        errors,
    )
    if response_batch.get("batch_id_contract_id") != BATCH_ID_CONTRACT_ID:
        errors.append("response.batch.batch_id_contract_id.invalid")
    if response_batch.get("order_contract_id") != ORDER_CONTRACT_ID:
        errors.append("response.batch.order_contract_id.invalid")
    if response_batch.get("result_status") != NOT_EXECUTED:
        errors.append("response.batch.result_status.invalid")
    if summary.get("result_status") != NOT_EXECUTED:
        errors.append("response.summary.result_status.invalid")

    status = response_batch.get("evaluation_status")
    results = response_batch.get("results")
    if type(results) is not list:
        errors.append("response.batch.results.not_array")
        results = []
    if status == "rejected":
        if response.get("evidence_snapshot") is not None:
            errors.append("response.rejected.evidence_snapshot_must_be_null")
        if response_batch.get("batch_id") is not None:
            errors.append("response.rejected.batch_id_must_be_null")
        if results:
            errors.append("response.rejected.results_must_be_empty")
        rejected_errors = response.get("errors")
        if type(rejected_errors) is not list or len(rejected_errors) != 1:
            errors.append("response.rejected.errors_required")
        elif any(type(code) is not str or code not in _REJECTED_CODES for code in rejected_errors):
            errors.append("response.rejected.errors_invalid")
        elif len(set(rejected_errors)) != len(rejected_errors):
            errors.append("response.rejected.errors_not_unique")
        if response.get("warnings") != []:
            errors.append("response.rejected.warnings_must_be_empty")
        _verify_summary(summary, [], errors)
        return errors
    if status != "complete":
        errors.append("response.batch.evaluation_status.invalid")
        return errors

    if response.get("errors") != [] or response.get("warnings") != []:
        errors.append("response.complete.top_level_messages_must_be_empty")
    snapshot = response.get("evidence_snapshot")
    if type(snapshot) is not dict:
        errors.append("response.evidence_snapshot.not_object")
    else:
        _exact_keys(
            snapshot,
            {"snapshot_contract_id", "snapshot_digest", "result_status"},
            "response.evidence_snapshot",
            errors,
        )
        if snapshot.get("snapshot_contract_id") != SNAPSHOT_CONTRACT_ID:
            errors.append("response.evidence_snapshot.contract.invalid")
        if not _is_digest(snapshot.get("snapshot_digest")):
            errors.append("response.evidence_snapshot.digest.invalid")
        if snapshot.get("result_status") != NOT_EXECUTED:
            errors.append("response.evidence_snapshot.result_status.invalid")

    request_batch = _as_mapping(request["batch"])
    observations = request_batch["observations"]
    if response_batch.get("batch_id") != request_batch.get("batch_id"):
        errors.append("response.batch.batch_id.echo_mismatch")
    if len(results) != len(observations):
        errors.append("response.batch.results.cardinality_mismatch")
    for index, result in enumerate(results):
        observation = observations[index] if index < len(observations) else None
        _verify_result(result, observation, index, errors)
    _verify_summary(summary, results, errors)
    return errors


def _verify_result(
    result: Any,
    observation: Any,
    index: int,
    errors: list[str],
) -> None:
    path = f"response.batch.results[{index}]"
    if type(result) is not dict:
        errors.append(f"{path}.not_object")
        return
    _exact_keys(
        result,
        {
            "observation_id", "order_index", "result_status", "binding_echo",
            "mapping_claim_echo", "decision", "reason_code", "evidence_binding",
            "errors", "warnings",
        },
        path,
        errors,
    )
    _message_list(result.get("errors"), f"{path}.errors", errors)
    _message_list(result.get("warnings"), f"{path}.warnings", errors)
    if result.get("warnings") != []:
        errors.append(f"{path}.warnings_must_be_empty")
    if type(observation) is not dict:
        errors.append(f"{path}.unexpected_result")
        return
    if result.get("observation_id") != observation.get("observation_id"):
        errors.append(f"{path}.observation_id.echo_mismatch")
    if (
        type(result.get("order_index")) is not int
        or result.get("order_index") != index
        or result.get("order_index") != observation.get("order_index")
    ):
        errors.append(f"{path}.order_index.echo_mismatch")
    if result.get("binding_echo") != observation.get("call_binding"):
        errors.append(f"{path}.binding_echo.mismatch")
    if result.get("mapping_claim_echo") != observation.get("mapping_claim"):
        errors.append(f"{path}.mapping_claim_echo.mismatch")
    if result.get("result_status") != NOT_EXECUTED:
        errors.append(f"{path}.result_status.invalid")

    decision = result.get("decision")
    reason = result.get("reason_code")
    evidence = result.get("evidence_binding")
    decision_errors = result.get("errors")
    if decision == "allow_candidate":
        if not _mapping_claim_is_independently_derived(
            _as_mapping(observation.get("call_binding")),
            _as_mapping(observation.get("mapping_claim")),
        ):
            errors.append(f"{path}.allow_candidate.mapping_provenance_invalid")
        if reason != "unique_ready_evidence_match":
            errors.append(f"{path}.allow_candidate.reason.invalid")
        _verify_evidence_binding(evidence, path, require_export=True, errors=errors)
        if decision_errors != []:
            errors.append(f"{path}.allow_candidate.errors_must_be_empty")
    elif decision == "block":
        if reason != "unique_blocked_evidence_match":
            errors.append(f"{path}.block.reason.invalid")
        _verify_evidence_binding(evidence, path, require_export=False, errors=errors)
        if decision_errors != []:
            errors.append(f"{path}.block.errors_must_be_empty")
    elif decision == "unsupported":
        if reason == "unique_unsupported_evidence_match":
            _verify_evidence_binding(evidence, path, require_export=False, errors=errors)
        elif reason == "no_semantic_evidence_match":
            if evidence is not None:
                errors.append(f"{path}.unsupported.evidence_must_be_null")
        else:
            errors.append(f"{path}.unsupported.reason.invalid")
        if decision_errors != []:
            errors.append(f"{path}.unsupported.errors_must_be_empty")
    elif decision == "error":
        if reason not in {
            "ambiguous_evidence_match",
            "mapping_claim_not_independently_derivable",
        }:
            errors.append(f"{path}.error.reason.invalid")
        if evidence is not None:
            errors.append(f"{path}.error.evidence_must_be_null")
        if decision_errors != [reason]:
            errors.append(f"{path}.error.errors_mismatch")
    else:
        errors.append(f"{path}.decision.invalid")
def _verify_evidence_binding(
    evidence: Any, path: str, *, require_export: bool, errors: list[str]
) -> None:
    if type(evidence) is not dict:
        errors.append(f"{path}.evidence_binding.required")
        return
    _exact_keys(
        evidence,
        {
            "request_id", "handoff_id", "handoff_digest", "export_item_digest",
            "export_package_digest", "adapter_spec_digest", "result_status",
        },
        f"{path}.evidence_binding",
        errors,
    )
    for key in ("request_id", "handoff_id"):
        if not _is_opaque_identifier(evidence.get(key)):
            errors.append(f"{path}.evidence_binding.{key}.invalid")
    for key in ("handoff_digest", "export_package_digest", "adapter_spec_digest"):
        if not _is_digest(evidence.get(key)):
            errors.append(f"{path}.evidence_binding.{key}.invalid")
    export_digest = evidence.get("export_item_digest")
    if require_export and not _is_digest(export_digest):
        errors.append(f"{path}.evidence_binding.export_item_digest.required")
    if not require_export and export_digest is not None:
        errors.append(f"{path}.evidence_binding.export_item_digest.must_be_null")
    if evidence.get("result_status") != NOT_EXECUTED:
        errors.append(f"{path}.evidence_binding.result_status.invalid")


def _verify_summary(
    summary: Mapping[str, Any], results: Sequence[Mapping[str, Any]], errors: list[str]
) -> None:
    for key in ("total", *DECISION_VOCABULARY):
        value = summary.get(key)
        if type(value) is not int or not 0 <= value <= MAX_OBSERVATIONS:
            errors.append(f"response.summary.{key}.invalid")
    counts = {decision: 0 for decision in DECISION_VOCABULARY}
    for result in results:
        if isinstance(result, Mapping) and result.get("decision") in counts:
            counts[result["decision"]] += 1
    expected = {"total": len(results), **counts, "result_status": NOT_EXECUTED}
    if dict(summary) != expected:
        errors.append("response.summary.mismatch")


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], path: str, errors: list[str]
) -> None:
    actual = set(value)
    if actual != expected:
        errors.append(f"{path}.shape.invalid")


def _message_list(value: Any, path: str, errors: list[str]) -> None:
    if type(value) is not list or not all(isinstance(item, str) for item in value):
        errors.append(f"{path}.invalid")


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def _validate_structured_snapshot(files: Mapping[str, bytes]) -> None:
    errors: list[str] = []
    for path, raw in files.items():
        suffix = Path(path).suffix.lower()
        try:
            text = raw.decode("utf-8")
            if path == "ledger.jsonl":
                for line in text.splitlines():
                    if line.strip():
                        _json_loads_unique(line)
            elif suffix == ".json":
                _json_loads_unique(text)
            elif suffix in {".yaml", ".yml"}:
                yaml.load(text, Loader=_UniqueLoader)
        except (UnicodeError, json.JSONDecodeError, yaml.YAMLError, TypeError, ValueError):
            errors.append("snapshot.structured_file.malformed")
    if errors:
        raise SnapshotValidationError(errors)


def _snapshot_records(
    files: Mapping[str, bytes],
) -> tuple[list[EvidenceRecord], str]:
    errors: list[str] = []
    events = _ledger(files["ledger.jsonl"], errors)
    references = [
        event.get("execution_handoff_report_path")
        for event in events
        if event.get("event_type") == "designer_review"
    ]
    references = [reference for reference in references if isinstance(reference, str)]
    if not references:
        errors.append("snapshot.handoff_report_missing")

    request_ids: set[str] = set()
    handoff_ids: set[str] = set()
    registry_entries: dict[tuple[str, str], str] = {}
    records_pending: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    exports: list[dict[str, Any]] = []
    reports = total = blocked = unsupported = 0

    for reference in references:
        report_path = _reference(reference, errors)
        report = _yaml(files, report_path, "handoff_report", errors)
        if report is None:
            continue
        reports += 1
        if (
            report.get("kind") != "execution_handoff_report"
            or report.get("result_status") != NOT_EXECUTED
        ):
            errors.append("snapshot.handoff_report.invalid")
        spec_path = _reference(report.get("adapter_spec_path"), errors)
        registry_path = _reference(report.get("adapter_registry_path"), errors)
        gate_path = _reference(report.get("tool_gate_report_path"), errors)
        preflight_path = _reference(report.get("preflight_report_path"), errors)
        spec = _yaml(files, spec_path, "adapter_spec", errors)
        registry = _yaml(files, registry_path, "adapter_registry", errors)
        tool_gate = _yaml(files, gate_path, "tool_gate_report", errors)
        preflight = _yaml(files, preflight_path, "preflight_report", errors)
        policy = _yaml(files, report.get("policy_path"), "policy", errors)
        governance = _yaml(files, report.get("governance_path"), "governance", errors)
        adapter_ref = _as_mapping(report.get("adapter_ref"))
        if None in (spec, registry, tool_gate, preflight, policy, governance):
            continue
        spec_digest = _object_digest(spec)
        adapter_id = adapter_ref.get("adapter_id")
        adapter_version = adapter_ref.get("adapter_version")
        approvals: dict[str, Mapping[str, Any]] = {}
        approval_paths: dict[str, str] = {}
        handoff_items = report.get("handoffs")
        if isinstance(handoff_items, list):
            for handoff_item in handoff_items:
                if not isinstance(handoff_item, Mapping):
                    continue
                subject = _as_mapping(handoff_item.get("subject"))
                approval_path = subject.get("approval_record_path")
                request_id = handoff_item.get("request_id")
                if isinstance(approval_path, str) and isinstance(request_id, str):
                    approval = _yaml(files, _reference(approval_path, errors), "approval_record", errors)
                    if approval is not None:
                        approvals[request_id] = approval
                        approval_paths[request_id] = approval_path

        context = {
            "task_id": report.get("task_id"),
            "objective_ref": report.get("objective_ref"),
            "attempt": report.get("attempt"),
            "tool_gate_report_path": gate_path,
            "preflight_report_path": preflight_path,
            "adapter_spec_path": spec_path,
            "policy_path": report.get("policy_path"),
            "governance_path": report.get("governance_path"),
        }
        if (
            validate_tool_gate_report(tool_gate, context, policy=policy, governance=governance).errors
            or validate_execution_preflight_report(preflight, tool_gate, approvals, context).errors
            or validate_execution_handoff_report(
                report,
                tool_gate,
                preflight,
                spec,
                policy=policy,
                governance=governance,
                approval_records=approvals,
                approval_record_paths=approval_paths,
                task_context=context,
            ).errors
            or validate_runtime_adapter_spec(spec).errors
        ):
            errors.append("snapshot.evidence_chain_invalid")
        if (
            spec.get("kind") != "runtime_adapter_spec"
            or spec.get("adapter_id") != adapter_id
            or spec.get("adapter_version") != adapter_version
            or adapter_ref.get("adapter_spec_digest") != spec_digest
        ):
            errors.append("snapshot.adapter_ref.invalid")

        selected = _validate_frozen_adapter_registry(
            registry,
            files,
            registry_entries,
            adapter_id,
            adapter_version,
            spec_path,
            spec,
            spec_digest,
            errors,
        )
        if selected is None:
            continue

        handoffs = report.get("handoffs")
        if not isinstance(handoffs, list):
            errors.append("snapshot.handoffs.invalid")
            continue
        for handoff in handoffs:
            if not isinstance(handoff, Mapping):
                errors.append("snapshot.handoff.invalid")
                continue
            total += 1
            request_id = handoff.get("request_id")
            handoff_id = handoff.get("handoff_id")
            if not _is_opaque_identifier(request_id):
                errors.append("snapshot.request_id.invalid")
                continue
            if request_id in request_ids:
                errors.append("snapshot.request_id.duplicate")
            request_ids.add(request_id)
            if not _is_opaque_identifier(handoff_id):
                errors.append("snapshot.handoff_id.invalid")
                continue
            if handoff_id in handoff_ids:
                errors.append("snapshot.handoff_id.duplicate")
            handoff_ids.add(handoff_id)
            adapter = _as_mapping(handoff.get("adapter"))
            request = _as_mapping(handoff.get("request"))
            gate = _as_mapping(handoff.get("gate"))
            subject = _as_mapping(handoff.get("subject"))
            if (
                handoff.get("result_status") != NOT_EXECUTED
                or gate.get("result_status") != NOT_EXECUTED
            ):
                errors.append("snapshot.handoff.result_status")
            for digest_field in ("tool_gate_digest", "preflight_digest"):
                digest_value = subject.get(digest_field)
                if not isinstance(digest_value, str) or _DIGEST_RE.fullmatch(digest_value) is None:
                    errors.append(f"snapshot.handoff.{digest_field}_invalid")
            if subject.get("approval_record_path") is not None:
                approval_digest = subject.get("approval_digest")
                if not isinstance(approval_digest, str) or _DIGEST_RE.fullmatch(approval_digest) is None:
                    errors.append("snapshot.handoff.approval_digest_invalid")
            if (
                adapter.get("adapter_id") != adapter_id
                or adapter.get("adapter_version") != adapter_version
            ):
                errors.append("snapshot.handoff.adapter_mismatch")
            semantic = tuple(
                request.get(field)
                for field in ("tool_name", "category", "intent", "target_scope")
            )
            if not all(isinstance(part, str) and part for part in semantic):
                errors.append("snapshot.handoff.request_invalid")
                continue
            status = _status(gate, errors)
            blocked += status == "blocked"
            unsupported += status == "unsupported"
            handoff_digest = execution_handoff_digest(handoff)
            data = {
                "semantic_key": (adapter_id, adapter_version, *semantic),
                "status": status,
                "request_id": request_id,
                "handoff_id": handoff_id,
                "handoff_digest": handoff_digest,
                "adapter_spec_digest": spec_digest,
            }
            export = None
            if status == "ready":
                export = _export(
                    report_path,
                    registry_path,
                    spec_path,
                    selected,
                    handoff,
                    handoff_digest,
                )
                exports.append(export)
            records_pending.append((data, export))
    if errors:
        raise SnapshotValidationError(errors)
    package = {
        "version": "0.1.0",
        "kind": "handoff_export_package",
        "source": "build_handoff_export_package",
        "result_status": NOT_EXECUTED,
        "summary": {
            "reports": reports,
            "total_handoffs": total,
            "exported": len(exports),
            "blocked": blocked,
            "unsupported": unsupported,
            "result_status": NOT_EXECUTED,
        },
        "exports": exports,
    }
    records = [
        EvidenceRecord(
            **data,
            export_item_digest=execution_handoff_digest(export) if export else None,
        )
        for data, export in records_pending
    ]
    return records, execution_handoff_digest(package)


def _match_result(
    matches: Sequence[EvidenceRecord], snapshot: EvidenceSnapshot
) -> tuple[str, str, dict[str, Any] | None]:
    if not matches:
        return "unsupported", "no_semantic_evidence_match", None
    if len(matches) != 1:
        return "error", "ambiguous_evidence_match", None
    record = matches[0]
    decision = {"ready": "allow_candidate", "blocked": "block", "unsupported": "unsupported"}[
        record.status
    ]
    reason = {
        "ready": "unique_ready_evidence_match",
        "blocked": "unique_blocked_evidence_match",
        "unsupported": "unique_unsupported_evidence_match",
    }[record.status]
    return (
        decision,
        reason,
        {
            "request_id": record.request_id,
            "handoff_id": record.handoff_id,
            "handoff_digest": record.handoff_digest,
            "export_item_digest": record.export_item_digest,
            "export_package_digest": snapshot.export_package_digest,
            "adapter_spec_digest": record.adapter_spec_digest,
            "result_status": NOT_EXECUTED,
        },
    )


def _independently_derived_mapping(
    binding: Mapping[str, Any], claim: Mapping[str, Any]
) -> tuple[str, str, str, str] | None:
    """Prove a serialized claim using only wire-safe exact tool identity.

    Arguments are intentionally absent from the wire, so target scope and any
    path-sensitive intent cannot be proven from an arguments digest.  A claim
    that asserts either is therefore never eligible to select ready evidence.
    """

    tool_name = binding.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    normalized = tool_name.strip().lower()
    if normalized in {"read", "read_file", "read_workspace", "win9_read_shared"}:
        derived = ("read_file", "file_read", "inspect_workspace", "unknown")
    elif normalized in {"bash", "shell", "sh", "run_command", "win9_run"}:
        derived = ("mystery_shell", "shell", "run_tests", "unknown")
    elif normalized in {"delete_file", "runtime_delete"}:
        derived = ("delete_file", "file_delete", "delete_file", "unknown")
    elif normalized in {
        "edit", "edit_file", "write", "write_file", "patch_file",
        "win9_write_agent_result",
    }:
        derived = (normalized, "file_write", "edit_file", "unknown")
    else:
        derived = (normalized or "unknown", "unknown", "unknown", "unknown")
    serialized = tuple(
        claim.get(field)
        for field in (
            "tool_name_candidate", "category_candidate", "intent_candidate",
            "target_scope_candidate",
        )
    )
    return derived if serialized == derived else None


def _mapping_claim_is_independently_derived(
    binding: Mapping[str, Any], claim: Mapping[str, Any]
) -> bool:
    return _independently_derived_mapping(binding, claim) is not None


def _validate_frozen_adapter_registry(
    registry: Mapping[str, Any],
    files: Mapping[str, bytes],
    registry_entries: dict[tuple[str, str], str],
    adapter_id: Any,
    adapter_version: Any,
    selected_spec_path: str | None,
    selected_spec: Mapping[str, Any],
    selected_spec_digest: str,
    errors: list[str],
) -> Mapping[str, Any] | None:
    """Validate one registry and every pinned spec from frozen snapshot bytes."""

    if registry.get("kind") != "runtime_adapter_registry" or registry.get("version") != "0.1.0":
        errors.append("snapshot.adapter_registry.invalid")
    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("snapshot.adapter_registry.invalid")
        return None

    selected = None
    local_ids: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            errors.append("snapshot.adapter_registry.entry_invalid")
            continue
        for field in _REGISTRY_ENTRY_FIELDS:
            if not isinstance(entry.get(field), str) or not entry.get(field):
                errors.append("snapshot.adapter_registry.entry_invalid")
        entry_id = entry.get("adapter_id")
        entry_version = entry.get("adapter_version")
        if isinstance(entry_id, str) and any(
            token in entry_id for token in _RANGE_OR_WILDCARD_TOKENS
        ):
            errors.append("snapshot.adapter_registry.entry_invalid")
        if not isinstance(entry_version, str) or _SEMVER_RE.fullmatch(entry_version) is None:
            errors.append("snapshot.adapter_registry.entry_invalid")
        if entry.get("status") not in _REGISTRY_STATUSES:
            errors.append("snapshot.adapter_registry.entry_invalid")
        if not _is_digest(entry.get("adapter_spec_digest")):
            errors.append("snapshot.adapter_registry.entry_invalid")

        key = (entry_id, entry_version)
        if all(isinstance(part, str) and part for part in key):
            if key in local_ids:
                errors.append("snapshot.adapter_registry.duplicate_entry")
            local_ids.add(key)
            entry_value = _json(entry)
            if key in registry_entries and registry_entries[key] != entry_value:
                errors.append("snapshot.adapter_registry.conflicting_entry")
            registry_entries.setdefault(key, entry_value)
            if key == (adapter_id, adapter_version):
                selected = entry

        pinned_path = _reference(entry.get("adapter_spec_path"), errors)
        pinned_spec = _yaml(files, pinned_path, "adapter_registry_spec", errors)
        if pinned_spec is None:
            continue
        if validate_runtime_adapter_spec(pinned_spec).errors:
            errors.append("snapshot.adapter_registry.spec_invalid")
        if any(
            entry.get(field) != pinned_spec.get(field)
            for field in ("adapter_id", "adapter_kind", "adapter_version", "execution_plane")
        ):
            errors.append("snapshot.adapter_registry.spec_binding_invalid")
        if entry.get("adapter_spec_digest") != _object_digest(pinned_spec):
            errors.append("snapshot.adapter_registry.spec_binding_invalid")

    if (
        selected is None
        or selected.get("status") != "active"
        or selected.get("adapter_spec_path") != selected_spec_path
        or selected.get("adapter_spec_digest") != selected_spec_digest
        or any(
            selected.get(field) != selected_spec.get(field)
            for field in ("adapter_id", "adapter_kind", "adapter_version", "execution_plane")
        )
    ):
        errors.append("snapshot.adapter_registry.binding_invalid")
        return None
    return selected


def _export(
    report_path: str,
    registry_path: str,
    spec_path: str,
    selected: Mapping[str, Any],
    handoff: Mapping[str, Any],
    handoff_digest: str,
) -> dict[str, Any]:
    request = _as_mapping(handoff.get("request"))
    gate = _as_mapping(handoff.get("gate"))
    return {
        "version": "0.1.0",
        "kind": "handoff_export_item",
        "result_status": NOT_EXECUTED,
        "handoff_report_path": report_path,
        "adapter_registry_path": registry_path,
        "adapter_spec_path": spec_path,
        "adapter_ref": {
            "adapter_id": selected.get("adapter_id"),
            "adapter_version": selected.get("adapter_version"),
            "adapter_spec_digest": selected.get("adapter_spec_digest"),
        },
        "handoff_id": handoff.get("handoff_id"),
        "task_id": handoff.get("task_id"),
        "objective_ref": handoff.get("objective_ref"),
        "attempt": handoff.get("attempt"),
        "request_id": handoff.get("request_id"),
        "handoff_digest": handoff_digest,
        "request": {key: request.get(key) for key in ("tool_name", "category", "intent", "target_scope")},
        "gate": {
            "handoff_ready": gate.get("handoff_ready") is True,
            "execution_allowed_by_preflight": gate.get("execution_allowed_by_preflight"),
            "result_status": gate.get("result_status"),
        },
    }


def _status(gate: Mapping[str, Any], errors: list[str]) -> str:
    ready = gate.get("handoff_ready") is True
    blocked = gate.get("blocked_reason")
    unsupported = gate.get("unsupported_reason")
    if ready:
        if blocked is not None or unsupported is not None or gate.get(
            "execution_allowed_by_preflight"
        ) is not True:
            errors.append("snapshot.handoff.gate_inconsistent")
        return "ready"
    if blocked is not None and unsupported is not None:
        errors.append("snapshot.handoff.gate_inconsistent")
    if unsupported is not None:
        return "unsupported"
    if blocked is None:
        errors.append("snapshot.handoff.gate_inconsistent")
    return "blocked"


def _ledger(raw: bytes, errors: list[str]) -> list[Mapping[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("snapshot.ledger.invalid_utf8")
        return []
    events = []
    event_ids: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = _json_loads_unique(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            errors.append("snapshot.ledger.malformed_json")
            continue
        if not isinstance(event, Mapping):
            errors.append("snapshot.ledger.event_invalid")
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            errors.append("snapshot.ledger.event_id_invalid")
        elif event_id in event_ids:
            errors.append("snapshot.ledger.event_id_duplicate")
        event_ids.add(event_id)
        events.append(event)
    return events


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.YAMLError("duplicate mapping key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _json_loads_unique(source: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(source, object_pairs_hook=unique_object)


def _yaml(
    files: Mapping[str, bytes], path: str | None, label: str, errors: list[str]
) -> Mapping[str, Any] | None:
    if path is None or path not in files:
        errors.append(f"snapshot.{label}.missing")
        return None
    try:
        value = yaml.load(files[path].decode("utf-8"), Loader=_UniqueLoader)
    except (UnicodeError, yaml.YAMLError, TypeError, ValueError):
        errors.append(f"snapshot.{label}.malformed")
        return None
    if not isinstance(value, Mapping):
        errors.append(f"snapshot.{label}.not_object")
        return None
    return value


def _reference(value: Any, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value:
        errors.append("snapshot.reference.invalid")
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        errors.append("snapshot.reference.outside_bus")
        return None
    return value


def _canonical_value(value: Any, seen: set[int], depth: int) -> str:
    if depth > MAX_STRUCTURE_DEPTH:
        raise ContractValidationError(("arguments.depth_exceeded",))
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _canonical_string(value)
    if type(value) is int:
        if abs(value) > 9007199254740991:
            raise ContractValidationError(("arguments.unsafe_integer",))
        return str(value)
    if type(value) is float:
        return _canonical_float(value)
    if type(value) is list:
        identity = id(value)
        if identity in seen:
            raise ContractValidationError(("arguments.repeated_reference",))
        seen.add(identity)
        return "[" + ",".join(_canonical_value(item, seen, depth + 1) for item in value) + "]"
    if type(value) is dict:
        identity = id(value)
        if identity in seen:
            raise ContractValidationError(("arguments.repeated_reference",))
        seen.add(identity)
        if any(not isinstance(key, str) for key in value):
            raise ContractValidationError(("arguments.non_string_key",))
        keys = sorted(value, key=lambda key: tuple(ord(char) for char in key))
        return "{" + ",".join(
            _canonical_string(key) + ":" + _canonical_value(value[key], seen, depth + 1) for key in keys
        ) + "}"
    raise ContractValidationError(("arguments.unsupported_type",))


def _canonical_string(value: str) -> str:
    pieces = ['"']
    escapes = {
        0x08: "\\b",
        0x09: "\\t",
        0x0A: "\\n",
        0x0C: "\\f",
        0x0D: "\\r",
        0x22: '\\"',
        0x5C: "\\\\",
    }
    for char in value:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            raise ContractValidationError(("arguments.invalid_unicode_scalar",))
        if code in escapes:
            pieces.append(escapes[code])
        elif 0x20 <= code <= 0x7E:
            pieces.append(char)
        elif code <= 0xFFFF:
            pieces.append(f"\\u{code:04x}")
        else:
            scalar = code - 0x10000
            pieces.append(f"\\u{0xD800 + (scalar >> 10):04x}")
            pieces.append(f"\\u{0xDC00 + (scalar & 0x3FF):04x}")
    return "".join(pieces) + '"'


def _canonical_float(value: float) -> str:
    if not math.isfinite(value):
        raise ContractValidationError(("arguments.non_finite_number",))
    if value == 0.0:
        if math.copysign(1.0, value) < 0:
            raise ContractValidationError(("arguments.negative_zero",))
        return "0"
    if value.is_integer() and abs(value) > 9007199254740991:
        raise ContractValidationError(("arguments.unsafe_integer",))
    text = repr(value).lower()
    if 1e-6 <= abs(value) < 1e21:
        return (format(Decimal(text), "f") if "e" in text else text).removesuffix(".0")
    if "e" not in text:
        text = format(value, ".15e")
    coefficient, exponent = text.split("e")
    coefficient = coefficient.rstrip("0").rstrip(".")
    return f"{coefficient}e{int(exponent):+d}".replace("e+0", "e+").replace(
        "e-0", "e-"
    )


def _object_digest(value: Any) -> str:
    return _sha256(_json(value).encode("utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _keys(value: Mapping[str, Any], expected: set[str], path: str, errors: list[str]) -> None:
    actual = set(value)
    errors.extend(f"{path}.{key}.missing" for key in sorted(expected - actual))
    errors.extend(f"{path}.{key}.extra" for key in sorted(actual - expected))


def _const(
    value: Mapping[str, Any], key: str, expected: Any, path: str, errors: list[str]
) -> None:
    if value.get(key) != expected:
        errors.append(f"{path}.{key}.invalid")


def _string(value: Mapping[str, Any], key: str, path: str, errors: list[str]) -> None:
    if not isinstance(value.get(key), str) or not value.get(key):
        errors.append(f"{path}.{key}.invalid")


def _is_opaque_identifier(value: Any) -> bool:
    return isinstance(value, str) and _OPAQUE_IDENTIFIER_RE.fullmatch(value) is not None


def _opaque_identifier(value: Any, path: str) -> str:
    if not _is_opaque_identifier(value):
        raise ValueError(f"{path}: invalid opaque identifier")
    return value


def _opaque_string(value: Mapping[str, Any], key: str, path: str, errors: list[str]) -> None:
    if not _is_opaque_identifier(value.get(key)):
        errors.append(f"{path}.{key}.invalid")


def _enum(
    value: Mapping[str, Any], key: str, allowed: frozenset[str], path: str,
    errors: list[str],
) -> None:
    if value.get(key) not in allowed:
        errors.append(f"{path}.{key}.invalid")


def _find_forbidden(value: Any, errors: list[str], seen: set[int] | None = None, depth: int = 0) -> None:
    if depth > MAX_STRUCTURE_DEPTH:
        errors.append("request.depth_exceeded")
        return
    seen = seen if seen is not None else set()
    if isinstance(value, (Mapping, list)):
        identity = id(value)
        if identity in seen:
            errors.append("request.cycle_detected")
            return
        seen.add(identity)
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _FORBIDDEN or key.startswith("runtime_allow"):
                errors.append("request.forbidden_field")
            _find_forbidden(child, errors, seen, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _find_forbidden(child, errors, seen, depth + 1)


def _sanitize_rejected_code(code: str) -> str:
    if code in _REJECTED_CODES:
        return code
    if "depth" in code:
        return "request.depth_exceeded"
    if "recursive" in code or "repeated_reference" in code or "cycle" in code:
        return "request.cycle_detected"
    if code.startswith(("request", "arguments")):
        return "request.invalid"
    if "resource" in code or "too_" in code or "large" in code:
        return "snapshot.resource_limit"
    if "symlink" in code:
        return "snapshot.symlink_not_allowed"
    if "changed" in code:
        return "snapshot.file_changed"
    if "malformed" in code or "structured" in code:
        return "snapshot.structured_file_malformed"
    if code.startswith(("snapshot.file", "snapshot.bus")):
        return "snapshot.file_unreadable"
    if code.startswith("snapshot"):
        return "snapshot.evidence_chain_invalid"
    return "snapshot.invalid"
