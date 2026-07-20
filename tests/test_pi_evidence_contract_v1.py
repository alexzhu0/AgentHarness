from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.pi_evidence_contract_v1 import (
    BATCH_ID_CONTRACT_ID,
    CANONICALIZATION_ID,
    CONTRACT_ID,
    ContractValidationError,
    MAX_SNAPSHOT_BYTES,
    MAX_SNAPSHOT_FILE_BYTES,
    MAX_SNAPSHOT_FILES,
    NOT_EXECUTED,
    ORDER_CONTRACT_ID,
    REQUEST_SCHEMA_ID,
    REQUEST_SOURCE,
    SNAPSHOT_CONTRACT_ID,
    SnapshotValidationError,
    arguments_digest_v1,
    build_pi_evidence_response_v1,
    build_pi_observation_batch_v1,
    build_evidence_snapshot_v1,
    canonicalize_arguments_v1,
    derive_batch_id_v1,
    evaluate_pi_evidence_request_v1,
    parse_pi_observation_batch_json_v1,
    validate_observation_batch_v1,
    verify_pi_evidence_response_v1,
    verify_pi_observation_batch_v1,
)
from agentharness.execution_handoff import execution_handoff_digest


BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
VECTORS = ROOT / "schemas" / "ah_args_c14n_1.vectors.json"


class PiEvidenceContractV1Tests(unittest.TestCase):
    def test_golden_canonicalization_vectors(self) -> None:
        vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        self.assertEqual(CANONICALIZATION_ID, vectors["canonicalization_id"])
        for vector in vectors["accepted"]:
            with self.subTest(vector=vector["name"]):
                self.assertEqual(vector["canonical"], canonicalize_arguments_v1(vector["arguments"]))
                self.assertEqual(vector["digest"], arguments_digest_v1(vector["arguments"]))
        for vector in vectors["rejected"]:
            if "json_source" not in vector:
                continue
            with self.subTest(vector=vector["name"]):
                value = json.loads(vector["json_source"])
                with self.assertRaises(ContractValidationError) as raised:
                    canonicalize_arguments_v1(value)
                self.assertIn(vector["error_code"], raised.exception.codes)

    def test_singleton_is_content_addressed_and_evaluates_with_exact_echoes(self) -> None:
        request = _request([_read_observation("call-001")])
        validated = validate_observation_batch_v1(request)
        response = evaluate_pi_evidence_request_v1(validated, BUS_ROOT)

        self.assertEqual("complete", response["batch"]["evaluation_status"])
        self.assertEqual(request["batch"]["batch_id"], response["batch"]["batch_id"])
        self.assertEqual("error", response["batch"]["results"][0]["decision"])
        result = response["batch"]["results"][0]
        self.assertEqual("mapping_claim_not_independently_derivable", result["reason_code"])
        self.assertEqual(request["batch"]["observations"][0]["call_binding"], result["binding_echo"])
        self.assertEqual(request["batch"]["observations"][0]["mapping_claim"], result["mapping_claim_echo"])
        self.assertIsNone(result["evidence_binding"])
        self.assertRegex(response["evidence_snapshot"]["snapshot_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual([], _bad_status_paths(response))
        self.assertNotIn("expected_decision", _canonical(response))
        self.assertNotIn("request_id_candidate", _canonical(response))

    def test_32_is_accepted_and_33_is_rejected(self) -> None:
        request = _request([_read_observation(f"call-{index:03d}") for index in range(32)])
        response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        self.assertEqual("complete", response["batch"]["evaluation_status"])
        self.assertEqual(32, len(response["batch"]["results"]))

        rejected = evaluate_pi_evidence_request_v1(
            _request([_read_observation(f"call-{index:03d}") for index in range(33)]),
            BUS_ROOT,
        )
        self.assertEqual("rejected", rejected["batch"]["evaluation_status"])
        self.assertEqual(["request.invalid"], rejected["errors"])
        self.assertEqual([], rejected["batch"]["results"])

    def test_request_and_snapshot_are_deterministic(self) -> None:
        first = _request([_read_observation("call-001")])
        second = _request([_read_observation("call-001")])
        self.assertEqual(_canonical(first), _canonical(second))
        self.assertEqual(
            _canonical(evaluate_pi_evidence_request_v1(first, BUS_ROOT)),
            _canonical(evaluate_pi_evidence_request_v1(second, BUS_ROOT)),
        )
        self.assertEqual(
            build_evidence_snapshot_v1(BUS_ROOT).snapshot_digest,
            build_evidence_snapshot_v1(BUS_ROOT).snapshot_digest,
        )

    def test_wrong_constants_statuses_digest_and_extra_fields_reject_batch(self) -> None:
        mutations = [
            lambda p: p.__setitem__("schema_id", "wrong"),
            lambda p: p.__setitem__("contract_id", "wrong"),
            lambda p: p.__setitem__("result_status", "executed"),
            lambda p: p["batch"].__setitem__("order_contract_id", "wrong"),
            lambda p: p["batch"]["observations"][0]["call_binding"].__setitem__(
                "arguments_canonicalization_id", "wrong"
            ),
            lambda p: p["batch"]["observations"][0]["call_binding"].__setitem__(
                "arguments_digest", "sha256:" + "A" * 64
            ),
            lambda p: p["batch"]["observations"][0]["mapping_claim"].__setitem__(
                "category_candidate", "read"
            ),
            lambda p: p.__setitem__("extra", True),
        ]
        for mutate in mutations:
            request = _request([_read_observation("call-001")])
            mutate(request)
            with self.subTest(request=request):
                response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertIsNone(response["batch"]["batch_id"])
                self.assertIsNone(response["evidence_snapshot"])

    def test_forbidden_oracle_hint_fixture_and_runtime_fields_reject(self) -> None:
        fields = [
            "request_id_candidate",
            "expectations",
            "expected_decision",
            "decision_matches_expectation",
            "fixture_path",
            "fixture_identity",
            "runtime_allow",
            "authorized",
        ]
        for field in fields:
            request = _request([_read_observation("call-001")])
            request["batch"]["observations"][0]["mapping_claim"][field] = "forbidden"
            with self.subTest(field=field):
                response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertEqual(["request.invalid"], response["errors"])

    def test_disclosure_bearing_call_metadata_rejects_without_echo(self) -> None:
        probes = (
            ("tool_call_id", "https://internal.example/call"),
            ("tool_call_id", "/opt/company/call"),
            ("tool_call_id", "sk-" + "proj-secret12345678"),
            ("tool_call_id", "call-" + "AK" + "IA1234567890EXAMPLE"),
            ("tool_call_id", "call-" + "sk-" + "proj-secret12345678"),
            ("tool_name", "Bearer secret-token"),
            ("tool_name", "token=custom-secret-123456"),
        )
        for field, value in probes:
            observation = _read_observation("safe-call")
            observation["call_binding"][field] = value
            with self.subTest(field=field, value=value):
                response = evaluate_pi_evidence_request_v1(_request([observation]), BUS_ROOT)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertNotIn(value, _canonical(response))

    def test_common_hyphenated_identifiers_are_accepted_by_builder_and_validator(self) -> None:
        request = build_pi_observation_batch_v1([
            {"tool_call_id": "task-1", "tool_name": "mask_tool", "arguments": {}}
        ])

        validated = validate_observation_batch_v1(request)

        self.assertEqual(
            "task-1",
            validated["batch"]["observations"][0]["call_binding"]["tool_call_id"],
        )
        self.assertEqual(
            "mask_tool",
            validated["batch"]["observations"][0]["call_binding"]["tool_name"],
        )

    def test_disclosure_bearing_evidence_ids_reject_snapshot_without_echo(self) -> None:
        for field, value in (
            ("request_id", "https://internal.example/request"),
            ("request_id", "/opt/company/request"),
            ("handoff_id", "github_pat_secret12345678"),
            ("handoff_id", "handoff-github_pat_secret12345678"),
            ("handoff_id", "token=custom-secret-123456"),
        ):
            with self.subTest(field=field, value=value), _copy_bus() as bus:
                report_path = bus / "handoffs" / "T008-handoff-report.yaml"
                report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
                report["handoffs"][0][field] = value
                report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
                response = evaluate_pi_evidence_request_v1(_request([_read_observation("safe-call")]), bus)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertNotIn(value, _canonical(response))

    def test_duplicate_gapped_and_reordered_identities_reject_entire_batch(self) -> None:
        cases = []
        duplicate_call = _request([_read_observation("same"), _read_observation("same")])
        cases.append(duplicate_call)
        duplicate_observation = _request([_read_observation("one"), _read_observation("two")])
        duplicate_observation["batch"]["observations"][1]["observation_id"] = duplicate_observation["batch"]["observations"][0]["observation_id"]
        cases.append(duplicate_observation)
        gapped = _request([_read_observation("one"), _read_observation("two")])
        gapped["batch"]["observations"][1]["order_index"] = 2
        cases.append(gapped)
        reordered = _request([_read_observation("one"), _read_observation("two")])
        reordered["batch"]["observations"].reverse()
        cases.append(reordered)
        for request in cases:
            with self.subTest(request=request):
                response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertEqual([], response["batch"]["results"])

    def test_unprovable_serialized_mapping_claims_fail_closed(self) -> None:
        observations = [
            _read_observation("ready"),
            _observation("unsupported", "read_file", "file_read", "inspect_config", "repository"),
            _observation("blocked", "mystery_shell", "shell", "run_tests", "repository", raw="bash"),
            _observation("ambiguous", "delete_file", "file_delete", "delete_file", "repository", raw="runtime_delete"),
            _observation("missing", "unknown", "unknown", "unknown", "unknown"),
        ]
        response = evaluate_pi_evidence_request_v1(_request(observations), BUS_ROOT)
        self.assertEqual(
            ["error", "error", "error", "error", "unsupported"],
            [result["decision"] for result in response["batch"]["results"]],
        )
        self.assertTrue(
            all(result["decision"] != "allow_candidate" for result in response["batch"]["results"])
        )
        self.assertEqual(
            "mapping_claim_not_independently_derivable",
            response["batch"]["results"][3]["reason_code"],
        )
        self.assertIsNone(response["batch"]["results"][3]["evidence_binding"])

    def test_duplicate_evidence_rejects_snapshot_without_identity_or_path_leak(self) -> None:
        with _copy_bus() as bus:
            report_path = bus / "handoffs" / "T008-handoff-report.yaml"
            report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
            report["handoffs"].append(copy.deepcopy(report["handoffs"][0]))
            report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
            response = evaluate_pi_evidence_request_v1(_request([_read_observation("call")]), bus)

        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertEqual(["snapshot.evidence_chain_invalid"], response["errors"])
        serialized = _canonical(response)
        self.assertNotIn("TR-read", serialized)
        self.assertNotIn(str(bus), serialized)

    def test_snapshot_reads_each_file_once(self) -> None:
        from agentharness import pi_evidence_contract_v1 as contract
        original = contract._bounded_read
        counts: dict[Path, int] = {}

        def counted(path: Path, limit: int, expected=None) -> bytes:
            counts[path] = counts.get(path, 0) + 1
            return original(path, limit, expected)

        with patch.object(contract, "_bounded_read", counted):
            build_evidence_snapshot_v1(BUS_ROOT)
        self.assertTrue(counts)
        self.assertTrue(all(count == 1 for count in counts.values()), counts)

    def test_snapshot_swap_to_symlink_fails_closed_without_reading_target(self) -> None:
        from agentharness import pi_evidence_contract_v1 as contract

        with _copy_bus() as bus:
            victim = bus / "ledger.jsonl"
            outside = bus.parent / "outside-ledger.jsonl"
            outside.write_bytes(b"outside content must not be read")
            forbidden_identity = (outside.stat().st_dev, outside.stat().st_ino)
            original = contract._bounded_read
            original_fdopen = contract.os.fdopen
            swapped = False

            def swap(path: Path, limit: int, expected=None) -> bytes:
                nonlocal swapped
                if path == victim and not swapped:
                    victim.unlink()
                    victim.symlink_to(outside)
                    swapped = True
                return original(path, limit, expected)

            def reject_target_read(descriptor: int, *args, **kwargs):
                metadata = contract.os.fstat(descriptor)
                self.assertNotEqual(forbidden_identity, (metadata.st_dev, metadata.st_ino))
                return original_fdopen(descriptor, *args, **kwargs)

            with patch.object(contract, "_bounded_read", swap), patch.object(
                contract.os, "fdopen", reject_target_read
            ):
                with self.assertRaises(SnapshotValidationError) as raised:
                    build_evidence_snapshot_v1(bus)

        self.assertTrue(swapped)
        self.assertIn("snapshot.symlink_not_allowed", raised.exception.codes)

    def test_snapshot_swap_to_same_length_inode_fails_closed_without_reading_replacement(self) -> None:
        from agentharness import pi_evidence_contract_v1 as contract

        with _copy_bus() as bus:
            victim = bus / "ledger.jsonl"
            replacement = bus.parent / "replacement-ledger.jsonl"
            replacement.write_bytes(b"X" * victim.stat().st_size)
            forbidden_identity = (replacement.stat().st_dev, replacement.stat().st_ino)
            original = contract._bounded_read
            original_fdopen = contract.os.fdopen
            swapped = False

            def swap(path: Path, limit: int, expected=None) -> bytes:
                nonlocal swapped
                if path == victim and not swapped:
                    victim.unlink()
                    replacement.rename(victim)
                    swapped = True
                return original(path, limit, expected)

            def reject_replacement_read(descriptor: int, *args, **kwargs):
                metadata = contract.os.fstat(descriptor)
                self.assertNotEqual(forbidden_identity, (metadata.st_dev, metadata.st_ino))
                return original_fdopen(descriptor, *args, **kwargs)

            with patch.object(contract, "_bounded_read", swap), patch.object(
                contract.os, "fdopen", reject_replacement_read
            ):
                with self.assertRaises(SnapshotValidationError) as raised:
                    build_evidence_snapshot_v1(bus)

        self.assertTrue(swapped)
        self.assertIn("snapshot.file_changed", raised.exception.codes)

    def test_schema_ids_and_contract_constants_are_materialized(self) -> None:
        request_schema = json.loads((ROOT / "schemas/pi_tool_call_observation_batch.v1.schema.json").read_text())
        response_schema = json.loads((ROOT / "schemas/pi_tool_call_evidence_response_batch.v1.schema.json").read_text())
        self.assertEqual(REQUEST_SCHEMA_ID, request_schema["$id"])
        self.assertEqual("urn:agentharness:schema:pi-tool-call-evidence-response-batch:1", response_schema["$id"])
        self.assertEqual(SNAPSHOT_CONTRACT_ID, response_schema["$defs"]["snapshot"]["properties"]["snapshot_contract_id"]["const"])

        result_schema = response_schema["$defs"]["result"]
        reasons = {
            "ambiguous_evidence_match",
            "mapping_claim_not_independently_derivable",
        }
        self.assertTrue(reasons <= set(result_schema["properties"]["reason_code"]["enum"]))
        self.assertEqual(reasons, set(result_schema["properties"]["errors"]["items"]["enum"]))
        error_branches = result_schema["allOf"][3]["then"]["oneOf"]
        self.assertEqual(
            {(branch["properties"]["reason_code"]["const"], branch["properties"]["errors"]["items"]["const"]) for branch in error_branches},
            {(reason, reason) for reason in reasons},
        )
        for key in ("category_candidate", "intent_candidate", "target_scope_candidate"):
            self.assertEqual(
                request_schema["$defs"]["mapping_claim"]["properties"][key]["enum"],
                response_schema["$defs"]["mapping_echo"]["properties"][key]["enum"],
            )

    def test_external_dependency_symlinks_are_rejected_hermetically(self) -> None:
        with self.subTest("final file"), _copy_bus() as bus:
            external_root = bus.parent.parent
            policy = external_root / "examples/agent_policy.example.yaml"
            target = external_root / "real-policy.yaml"
            target.write_bytes(policy.read_bytes())
            policy.unlink()
            policy.symlink_to(target)
            with self.assertRaises(SnapshotValidationError) as raised:
                build_evidence_snapshot_v1(bus)
            self.assertIn("snapshot.symlink_not_allowed", raised.exception.codes)

        with self.subTest("parent directory"), _copy_bus() as bus:
            external_root = bus.parent.parent
            examples = external_root / "examples"
            real_examples = external_root / "real-examples"
            examples.rename(real_examples)
            examples.symlink_to(real_examples, target_is_directory=True)
            with self.assertRaises(SnapshotValidationError) as raised:
                build_evidence_snapshot_v1(bus)
            self.assertIn("snapshot.symlink_not_allowed", raised.exception.codes)

    def test_public_builder_verifier_and_evaluator_api(self) -> None:
        raw = {
            "tool_call_id": "call-public",
            "tool_name": "read_workspace",
            "arguments": {"path": "README.md"},
        }
        request = build_pi_observation_batch_v1([raw])
        self.assertNotIn("arguments", request["batch"]["observations"][0]["call_binding"])
        self.assertTrue(verify_pi_observation_batch_v1(request)["valid"])
        response = build_pi_evidence_response_v1(request, BUS_ROOT)
        self.assertEqual("complete", response["batch"]["evaluation_status"])
        self.assertEqual("error", response["batch"]["results"][0]["decision"])

    def test_builder_derives_mapping_and_preserves_only_raw_tool_name_digest_and_claim(self) -> None:
        request = build_pi_observation_batch_v1([
            {"tool_call_id": "lying-shell", "tool_name": "bash", "arguments": {"path": "README.md"}}
        ])
        observation = request["batch"]["observations"][0]
        self.assertEqual("bash", observation["call_binding"]["tool_name"])
        self.assertNotIn("arguments", observation["call_binding"])
        self.assertEqual("mystery_shell", observation["mapping_claim"]["tool_name_candidate"])

    def test_forged_shell_to_read_mapping_with_recomputed_ids_never_allows(self) -> None:
        request = build_pi_observation_batch_v1([
            {"tool_call_id": "forged-shell", "tool_name": "bash", "arguments": {"path": "README.md"}}
        ])
        claim = request["batch"]["observations"][0]["mapping_claim"]
        claim.update(
            tool_name_candidate="read_file",
            category_candidate="file_read",
            intent_candidate="inspect_workspace",
            target_scope_candidate="repository",
        )
        _recompute_request_ids(request)

        response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        result = response["batch"]["results"][0]
        self.assertEqual("error", result["decision"])
        self.assertEqual("mapping_claim_not_independently_derivable", result["reason_code"])
        self.assertIsNone(result["evidence_binding"])

        forged_response = copy.deepcopy(response)
        forged_result = forged_response["batch"]["results"][0]
        forged_result.update(
            decision="allow_candidate",
            reason_code="unique_ready_evidence_match",
            evidence_binding=_evidence_binding(),
            errors=[],
        )
        forged_response["summary"].update(allow_candidate=1, error=0)
        self.assertFalse(verify_pi_evidence_response_v1(forged_response, request)["valid"])

    def test_malformed_request_does_not_lookup_snapshot_or_echo_identity(self) -> None:
        request = _request([_read_observation("call-malformed")])
        request["batch"]["batch_id"] = "caller-controlled"
        with patch(
            "agentharness.pi_evidence_contract_v1.build_evidence_snapshot_v1",
            side_effect=AssertionError("snapshot lookup must not occur"),
        ):
            response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertIsNone(response["batch"]["batch_id"])
        self.assertIsNone(response["evidence_snapshot"])
        self.assertNotIn("caller-controlled", _canonical(response))

    def test_missing_evidence_digest_rejects_snapshot(self) -> None:
        with _copy_bus() as bus:
            report_path = bus / "handoffs" / "T008-handoff-report.yaml"
            report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
            report["handoffs"][0]["subject"].pop("preflight_digest")
            report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
            response = evaluate_pi_evidence_request_v1(_request([_read_observation("call")]), bus)
        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertEqual(["snapshot.evidence_chain_invalid"], response["errors"])

    def test_evaluator_never_executes_or_writes(self) -> None:
        request = _request([_read_observation("call-no-side-effects")])
        with patch("subprocess.run", side_effect=AssertionError("execution forbidden")), patch.object(
            Path, "write_text", side_effect=AssertionError("write forbidden")
        ), patch.object(Path, "write_bytes", side_effect=AssertionError("write forbidden")):
            response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        self.assertEqual("complete", response["batch"]["evaluation_status"])
        self.assertEqual([], _bad_status_paths(response))

    def test_duplicate_key_json_request_is_rejected(self) -> None:
        request = _request([_read_observation("duplicate-json")])
        source = _canonical(request).replace(
            '"schema_id":"urn:agentharness:schema:pi-tool-call-observation-batch:1"',
            '"schema_id":"urn:agentharness:schema:pi-tool-call-observation-batch:1","schema_id":"duplicate"',
            1,
        )
        with self.assertRaises(ContractValidationError) as raised:
            parse_pi_observation_batch_json_v1(source)
        self.assertIn("request.malformed_or_duplicate_json", raised.exception.codes)

    def test_response_verifier_accepts_current_response_and_rejected_shape(self) -> None:
        request = _request([_read_observation("verify-current")])
        complete = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        self.assertTrue(verify_pi_evidence_response_v1(complete, request)["valid"])
        rejected = evaluate_pi_evidence_request_v1({"malformed": True}, BUS_ROOT)
        self.assertIsNone(rejected["evidence_snapshot"])
        self.assertTrue(verify_pi_evidence_response_v1(rejected, request)["valid"])

    def test_response_verifier_rejects_shape_echo_binding_decision_and_status_tampering(self) -> None:
        request = _request([_read_observation("verify-tamper")])
        response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        mutations = [
            lambda p: p.__setitem__("extra", True),
            lambda p: p["batch"].__setitem__("batch_id", "pi-batch:" + "0" * 64),
            lambda p: p["batch"]["results"].append(copy.deepcopy(p["batch"]["results"][0])),
            lambda p: p["batch"]["results"][0].__setitem__("observation_id", "tampered"),
            lambda p: p["batch"]["results"][0]["binding_echo"].__setitem__("tool_call_id", "other"),
            lambda p: p["batch"]["results"][0]["mapping_claim_echo"].__setitem__("intent_candidate", "other"),
            lambda p: p["batch"]["results"][0].__setitem__("evidence_binding", {"result_status": NOT_EXECUTED}),
            lambda p: p["batch"]["results"][0].__setitem__("decision", "block"),
            lambda p: p["batch"]["results"][0].__setitem__("result_status", "executed"),
        ]
        for mutate in mutations:
            tampered = copy.deepcopy(response)
            mutate(tampered)
            with self.subTest(tampered=tampered):
                self.assertFalse(verify_pi_evidence_response_v1(tampered, request)["valid"])

    def test_path_classification_matches_t056_hardening_and_never_allows_unsafe_paths(self) -> None:
        unsafe = [
            "../secret", "%2e%2e%2fsecret", "%252e%252e%252fsecret", "/tmp/secret",
            "C:\\secret", "C:secret", "\\\\server\\share", "~/secret", "docs//secret",
            "docs/*.md", "docs/file;cat secret", "%43%3A%2E%2E%5Csecret", "%GG",
        ]
        for codepoint in [*range(0x20), 0x7F, ord("|"), ord("&")]:
            encoded = f"{codepoint:02X}"
            unsafe.extend([
                f"folder/file{chr(codepoint)}name.md",
                f"folder/file%{encoded}name.md",
                f"folder/file%25{encoded}name.md",
            ])
        for path in unsafe:
            with self.subTest(path=path):
                request = build_pi_observation_batch_v1([
                    {"tool_call_id": f"unsafe-{len(path)}", "tool_name": "read_workspace", "arguments": {"path": path}}
                ])
                claim = request["batch"]["observations"][0]["mapping_claim"]
                self.assertEqual("outside_repository", claim["target_scope_candidate"])
                response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
                self.assertNotEqual("allow_candidate", response["batch"]["results"][0]["decision"])
        for path in ("README.md", "docs/homebrew.md", "folder/file%20name.md"):
            with self.subTest(path=path):
                request = build_pi_observation_batch_v1([
                    {"tool_call_id": f"safe-{len(path)}", "tool_name": "read_workspace", "arguments": {"path": path}}
                ])
                self.assertEqual("repository", request["batch"]["observations"][0]["mapping_claim"]["target_scope_candidate"])

    def test_public_verifiers_are_total_and_emit_one_sanitized_code(self) -> None:
        cyclic = {"extra": None}
        cyclic["extra"] = cyclic
        request_report = verify_pi_observation_batch_v1(cyclic)
        self.assertEqual(["request.cycle_detected"], request_report["errors"])
        request = _request([_read_observation("total")])
        response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        response["extra"] = response
        response_report = verify_pi_evidence_response_v1(response, request)
        self.assertEqual(["response.invalid"], response_report["errors"])
        deep = current = {}
        for _ in range(70):
            current["extra"] = {}
            current = current["extra"]
        self.assertEqual(["request.depth_exceeded"], verify_pi_observation_batch_v1(deep)["errors"])

    def test_response_verifier_rejects_bool_counts_and_duplicate_rejected_codes(self) -> None:
        request = _request([_read_observation("strict")])
        response = evaluate_pi_evidence_request_v1(request, BUS_ROOT)
        response["summary"]["total"] = True
        self.assertEqual(["response.invalid"], verify_pi_evidence_response_v1(response, request)["errors"])
        rejected = evaluate_pi_evidence_request_v1({"bad": True}, BUS_ROOT)
        rejected["errors"] = ["request.invalid", "request.invalid"]
        self.assertEqual(["response.invalid"], verify_pi_evidence_response_v1(rejected, request)["errors"])

    def test_snapshot_metadata_limits_reject_before_any_file_read(self) -> None:
        cases = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(MAX_SNAPSHOT_FILES + 1):
                (root / f"file-{index:03d}.txt").touch()
            cases.append((root, "snapshot.resource_limit"))
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must reject before reads")):
                with self.assertRaises(SnapshotValidationError) as raised:
                    build_evidence_snapshot_v1(root)
            self.assertIn(cases[-1][1], raised.exception.codes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ledger.jsonl").touch()
            with (root / "large.bin").open("wb") as stream:
                stream.truncate(MAX_SNAPSHOT_FILE_BYTES + 1)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must reject before reads")):
                with self.assertRaises(SnapshotValidationError) as raised:
                    build_evidence_snapshot_v1(root)
            self.assertIn("snapshot.resource_limit", raised.exception.codes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ledger.jsonl").touch()
            size = MAX_SNAPSHOT_BYTES // 4 + 1
            for index in range(4):
                with (root / f"total-{index}.bin").open("wb") as stream:
                    stream.truncate(size)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must reject before reads")):
                with self.assertRaises(SnapshotValidationError) as raised:
                    build_evidence_snapshot_v1(root)
            self.assertIn("snapshot.resource_limit", raised.exception.codes)

    def test_snapshot_rejects_symlink_and_malformed_structured_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
            (root / "outside.txt").write_text("outside", encoding="utf-8")
            (root / "link.txt").symlink_to(root / "outside.txt")
            with self.assertRaises(SnapshotValidationError) as raised:
                build_evidence_snapshot_v1(root)
            self.assertIn("snapshot.symlink_not_allowed", raised.exception.codes)
        for name, content in (("bad.json", '{"a":1,"a":2}'), ("bad.yaml", "a: 1\na: 2\n")):
            with self.subTest(name=name), _copy_bus() as bus:
                (bus / name).write_text(content, encoding="utf-8")
                response = evaluate_pi_evidence_request_v1(_request([_read_observation("bad-structured")]), bus)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertIn("snapshot.structured_file_malformed", response["errors"])

    def test_snapshot_rejects_every_malformed_unselected_registry_entry(self) -> None:
        mutations = [
            lambda entry: entry.pop("adapter_kind"),
            lambda entry: entry.__setitem__("adapter_version", "1.x"),
            lambda entry: entry.__setitem__("status", "unknown"),
            lambda entry: entry.__setitem__("adapter_spec_digest", "sha256:not-a-digest"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate), _copy_bus() as bus:
                registry_path, registry, entry = _add_unselected_adapter(bus)
                mutate(entry)
                registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
                response = evaluate_pi_evidence_request_v1(_request([_read_observation("registry")]), bus)
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertEqual(["snapshot.evidence_chain_invalid"], response["errors"])

    def test_snapshot_rejects_malformed_unselected_pinned_spec_even_with_matching_digest(self) -> None:
        with _copy_bus() as bus:
            registry_path, registry, entry = _add_unselected_adapter(bus)
            spec_path = bus / entry["adapter_spec_path"]
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            spec["requirements"].pop("require_not_executed")
            spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
            entry["adapter_spec_digest"] = execution_handoff_digest(spec)
            registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
            response = evaluate_pi_evidence_request_v1(_request([_read_observation("spec")]), bus)
        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertEqual(["snapshot.evidence_chain_invalid"], response["errors"])


def _read_observation(call_id: str) -> dict:
    return _observation(call_id, "read_file", "file_read", "inspect_workspace", "repository", raw="read_workspace")


def _observation(call_id: str, tool: str, category: str, intent: str, scope: str, raw: str | None = None) -> dict:
    return {
        "observation_id": "pending",
        "order_index": 0,
        "result_status": NOT_EXECUTED,
        "call_binding": {
            "tool_call_id": call_id,
            "tool_name": raw or tool,
            "arguments_canonicalization_id": CANONICALIZATION_ID,
            "arguments_digest": arguments_digest_v1({"path": ".agent/config.yaml" if intent == "inspect_config" else "README.md", "call": call_id}),
            "result_status": NOT_EXECUTED,
        },
        "mapping_claim": {
            "tool_name_candidate": tool,
            "category_candidate": category,
            "intent_candidate": intent,
            "target_scope_candidate": scope,
            "result_status": NOT_EXECUTED,
        },
    }


def _request(observations: list[dict]) -> dict:
    for index, observation in enumerate(observations):
        observation["order_index"] = index
    request = {
        "schema_id": REQUEST_SCHEMA_ID,
        "contract_id": CONTRACT_ID,
        "kind": "pi_tool_call_observation_batch",
        "source": REQUEST_SOURCE,
        "result_status": NOT_EXECUTED,
        "adapter_contract": {
            "adapter_id": "pi-tool-call-v0",
            "adapter_version": "0.1.0",
            "result_status": NOT_EXECUTED,
        },
        "batch": {
            "batch_id": "pi-batch:" + "0" * 64,
            "batch_id_contract_id": BATCH_ID_CONTRACT_ID,
            "order_contract_id": ORDER_CONTRACT_ID,
            "result_status": NOT_EXECUTED,
            "observations": observations,
        },
    }
    batch_id = derive_batch_id_v1(request)
    request["batch"]["batch_id"] = batch_id
    batch_hex = batch_id.removeprefix("pi-batch:")
    for index, observation in enumerate(observations):
        observation["observation_id"] = f"pi-observation:{batch_hex}:{index:06d}"
    return request


def _recompute_request_ids(request: dict) -> None:
    batch_id = derive_batch_id_v1(request)
    request["batch"]["batch_id"] = batch_id
    batch_hex = batch_id.removeprefix("pi-batch:")
    for index, observation in enumerate(request["batch"]["observations"]):
        observation["observation_id"] = f"pi-observation:{batch_hex}:{index:06d}"


def _evidence_binding() -> dict:
    digest = "sha256:" + "1" * 64
    return {
        "request_id": "TR-read",
        "handoff_id": "handoff-read",
        "handoff_digest": digest,
        "export_item_digest": digest,
        "export_package_digest": digest,
        "adapter_spec_digest": digest,
        "result_status": NOT_EXECUTED,
    }


def _add_unselected_adapter(bus: Path) -> tuple[Path, dict, dict]:
    selected_spec = yaml.safe_load((bus / "adapters/pi-tool-call-v0.yaml").read_text(encoding="utf-8"))
    unselected_spec = copy.deepcopy(selected_spec)
    unselected_spec.update(adapter_id="other-adapter", adapter_version="1.2.3")
    spec_path = bus / "adapters/other-adapter.yaml"
    spec_path.write_text(yaml.safe_dump(unselected_spec, sort_keys=False), encoding="utf-8")
    entry = {
        "adapter_id": unselected_spec["adapter_id"],
        "adapter_kind": unselected_spec["adapter_kind"],
        "adapter_version": unselected_spec["adapter_version"],
        "execution_plane": unselected_spec["execution_plane"],
        "status": "disabled",
        "adapter_spec_path": "adapters/other-adapter.yaml",
        "adapter_spec_digest": execution_handoff_digest(unselected_spec),
    }
    registry_path = bus / "adapters/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["entries"].append(entry)
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    return registry_path, registry, entry


def _bad_status_paths(value, path="$") -> list[str]:
    bad = []
    if isinstance(value, dict):
        if value.get("result_status") != NOT_EXECUTED:
            bad.append(path)
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                bad.extend(_bad_status_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                bad.extend(_bad_status_paths(child, f"{path}[{index}]"))
    return bad


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _copy_bus():
    class CopyBus:
        def __enter__(self):
            self.temp = tempfile.TemporaryDirectory()
            self.path = Path(self.temp.name) / "workspace" / "bus"
            self.path.parent.mkdir()
            shutil.copytree(BUS_ROOT, self.path)
            external_root = self.path.parent.parent
            (external_root / "examples").mkdir(exist_ok=True)
            (external_root / "policies").mkdir(exist_ok=True)
            shutil.copy2(ROOT / "examples/agent_policy.example.yaml", external_root / "examples/agent_policy.example.yaml")
            shutil.copy2(ROOT / "policies/tool_governance.yaml", external_root / "policies/tool_governance.yaml")
            return self.path

        def __exit__(self, *args):
            self.temp.cleanup()

    return CopyBus()


if __name__ == "__main__":
    unittest.main()
