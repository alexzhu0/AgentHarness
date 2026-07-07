from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.audit_contract import NOT_EXECUTED
from agentharness.pi_tool_call_mapping import (
    DECISION_VOCABULARY,
    build_pi_tool_call_mapping_report,
)


OBSERVATIONS_PATH = ROOT / "examples" / "pi_tool_call_mapping" / "pi_tool_call_observations.json"
EXPECTATIONS_PATH = ROOT / "examples" / "pi_tool_call_mapping" / "expected_mapping.json"
REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"


class PiToolCallMappingTests(unittest.TestCase):
    def test_t035_fixtures_validate_report_shape_counts_order_and_binding(self) -> None:
        report = _build_report()

        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual("0.1.0", report["version"])
        self.assertEqual("pi_tool_call_mapping_validation_report", report["kind"])
        self.assertEqual("build_pi_tool_call_mapping_report", report["source"])
        self.assertEqual(NOT_EXECUTED, report["result_status"])
        self.assertEqual([], report["errors"])
        self.assertEqual([], report["warnings"])

        summary = _expect_mapping(report["summary"])
        self.assertEqual(6, summary["observations"])
        self.assertEqual(6, summary["expectations"])
        self.assertEqual(6, summary["decisions"])
        self.assertEqual(1, summary["allow_candidate"])
        self.assertEqual(1, summary["block"])
        self.assertEqual(3, summary["unsupported"])
        self.assertEqual(1, summary["error"])
        self.assertEqual(list(DECISION_VOCABULARY), summary["decision_vocabulary"])
        self.assertEqual(NOT_EXECUTED, summary["result_status"])

        decisions = _expect_list(report["decisions"])
        self.assertEqual(
            [
                "pi-obs-001-read-workspace",
                "pi-obs-002-read-unsupported-intent",
                "pi-obs-003-edit-write-like",
                "pi-obs-004-bash-shell",
                "pi-obs-005-malformed-missing-tool",
                "pi-obs-006-read-outside-scope",
            ],
            [decision["observation_id"] for decision in decisions],
        )
        self.assertEqual(
            ["allow_candidate", "unsupported", "unsupported", "block", "error", "unsupported"],
            [decision["decision"] for decision in decisions],
        )
        self.assertTrue(all(decision["decision_matches_expectation"] for decision in decisions))

        first = _expect_mapping(decisions[0])
        binding = _expect_mapping(first["evidence_binding"])
        self.assertEqual("TR-read", binding["request_id"])
        self.assertEqual(
            {
                "tool_name": "read_file",
                "category": "file_read",
                "intent": "inspect_workspace",
                "target_scope": "repository",
            },
            binding["observation_request"],
        )
        self.assertEqual(
            {
                "tool_name": "read_file",
                "category": "file_read",
                "intent": "inspect_workspace",
                "target_scope": "repository",
            },
            binding["export_request"],
        )
        self.assertEqual("TR-read", _expect_mapping(binding["export"])["request_id"])
        self.assertEqual("TR-read", _expect_mapping(binding["manifest"])["request_id"])
        self.assertTrue(_expect_mapping(binding["gate"])["handoff_ready"])
        self.assertEqual(NOT_EXECUTED, _expect_mapping(binding["export"])["result_status"])
        self.assertEqual(NOT_EXECUTED, _expect_mapping(binding["manifest"])["result_status"])
        self.assertEqual(NOT_EXECUTED, _expect_mapping(binding["gate"])["result_status"])

        self.assertEqual([], _bad_result_status_paths(report))
        self.assertEqual([], _raw_host_path_matches(report))

    def test_report_is_deterministic(self) -> None:
        first = _canonical_json(_build_report())
        second = _canonical_json(_build_report())
        self.assertEqual(first, second)

    def test_missing_observations_file_fails_with_sanitized_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_pi_tool_call_mapping_report(
                Path(tmp) / "missing-observations.json",
                EXPECTATIONS_PATH,
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"], report)
        self.assertEqual([], _raw_host_path_matches(report))

    def test_missing_expectations_file_fails_with_sanitized_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_pi_tool_call_mapping_report(
                OBSERVATIONS_PATH,
                Path(tmp) / "missing-expectations.json",
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"], report)
        self.assertEqual([], _raw_host_path_matches(report))

    def test_wrong_kind_wrong_or_missing_result_status_fail(self) -> None:
        cases = [
            ("wrong_kind", "observations", lambda p: p.__setitem__("kind", "wrong")),
            (
                "wrong_schema_version",
                "observations",
                lambda p: p.__setitem__("schema_version", "9.9.9"),
            ),
            (
                "wrong_result_status",
                "observations",
                lambda p: p.__setitem__("result_status", "executed"),
            ),
            ("missing_result_status", "expectations", lambda p: p.pop("result_status")),
        ]
        for name, target, mutate in cases:
            with self.subTest(name=name), _temporary_payloads() as paths:
                payload = _load_json(paths[target])
                mutate(payload)
                _write_json(paths[target], payload)

                report = build_pi_tool_call_mapping_report(
                    paths["observations"],
                    paths["expectations"],
                    REGISTRY_BUS_ROOT,
                )

                self.assertFalse(report["ok"], name)
                self.assertTrue(report["errors"], report)

    def test_order_mismatch_and_duplicate_observation_ids_fail(self) -> None:
        with _temporary_payloads() as paths:
            expectations = _load_json(paths["expectations"])
            expectations["mapping_expectations"][0], expectations["mapping_expectations"][1] = (
                expectations["mapping_expectations"][1],
                expectations["mapping_expectations"][0],
            )
            _write_json(paths["expectations"], expectations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

            self.assertFalse(report["ok"])
            self.assertTrue(any("order" in error for error in report["errors"]), report["errors"])

        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][1]["observation_id"] = observations["observations"][0][
                "observation_id"
            ]
            _write_json(paths["observations"], observations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

            self.assertFalse(report["ok"])
            self.assertTrue(
                any("duplicate" in error for error in report["errors"]),
                report["errors"],
            )

    def test_invalid_decision_vocabulary_fails(self) -> None:
        with _temporary_payloads() as paths:
            expectations = _load_json(paths["expectations"])
            expectations["mapping_expectations"][0]["expected_decision"] = "allow"
            _write_json(paths["expectations"], expectations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        self.assertTrue(
            any("expected_decision" in error for error in report["errors"]),
            report["errors"],
        )

    def test_top_level_decision_vocabulary_must_match_exactly(self) -> None:
        with _temporary_payloads() as paths:
            expectations = _load_json(paths["expectations"])
            expectations["decision_vocabulary"] = [
                "allow_candidate",
                "allow",
                "block",
                "unsupported",
                "error",
            ]
            _write_json(paths["expectations"], expectations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        self.assertTrue(
            any("decision_vocabulary" in error for error in report["errors"]),
            report["errors"],
        )

    def test_allow_candidate_requires_semantic_request_match(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][0]["agentharness_refs_if_available"][
                "request_id_candidate"
            ] = "TR-approve-delete"
            _write_json(paths["observations"], observations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        first = _decision_by_id(report, "pi-obs-001-read-workspace")
        self.assertNotEqual("allow_candidate", first["decision"])
        self.assertEqual("error", first["decision"])
        self.assertTrue(
            any("request_semantic_mismatch" in error for error in first["errors"]),
            first["errors"],
        )
        self.assertTrue(
            any("request_semantic_mismatch" in error for error in report["errors"]),
            report["errors"],
        )

    def test_input_path_like_values_are_sanitized_from_report_payload(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][0]["tool_name"] = "/tmp/leaky_tool"
            _write_json(paths["observations"], observations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        serialized = _canonical_json(report)
        self.assertFalse(report["ok"])
        self.assertNotIn("/tmp/leaky_tool", serialized)
        self.assertEqual([], _raw_host_path_matches(report))
        first = _decision_by_id(report, "pi-obs-001-read-workspace")
        binding = _expect_mapping(first["evidence_binding"])
        self.assertEqual("<path>", _expect_mapping(binding["observation_request"])["tool_name"])

    def test_empty_valid_lists_fail_top_level_ok_when_checks_fail(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            expectations = _load_json(paths["expectations"])
            observations["observations"] = []
            expectations["mapping_expectations"] = []
            _write_json(paths["observations"], observations)
            _write_json(paths["expectations"], expectations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        failed_checks = [
            check["id"] for check in _expect_list(report["checks"]) if check["status"] == "fail"
        ]
        self.assertIn("decision_derivation", failed_checks)
        self.assertTrue(
            any("decision_derivation" in error for error in report["errors"]),
            report["errors"],
        )

    def test_unknown_tool_and_category_fail_closed_without_allow_candidate(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][0]["tool_name"] = "mystery_tool"
            observations["observations"][0]["category_candidate"] = "unknown_category"
            _write_json(paths["observations"], observations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        first = _decision_by_id(report, "pi-obs-001-read-workspace")
        self.assertIn(first["decision"], {"unsupported", "block"})
        self.assertNotEqual("allow_candidate", first["decision"])
        self.assertIn("unknown", first["reason"])

    def test_shell_malformed_and_unsupported_observations_cannot_be_allow_candidate(self) -> None:
        for observation_id in (
            "pi-obs-002-read-unsupported-intent",
            "pi-obs-003-edit-write-like",
            "pi-obs-004-bash-shell",
            "pi-obs-005-malformed-missing-tool",
            "pi-obs-006-read-outside-scope",
        ):
            with self.subTest(observation_id=observation_id), _temporary_payloads() as paths:
                expectations = _load_json(paths["expectations"])
                for item in expectations["mapping_expectations"]:
                    if item["observation_id"] == observation_id:
                        item["expected_decision"] = "allow_candidate"
                _write_json(paths["expectations"], expectations)

                report = build_pi_tool_call_mapping_report(
                    paths["observations"],
                    paths["expectations"],
                    REGISTRY_BUS_ROOT,
                )

                self.assertFalse(report["ok"])
                decision = _decision_by_id(report, observation_id)
                self.assertNotEqual("allow_candidate", decision["decision"])

    def test_allow_candidate_without_export_manifest_evidence_fails_closed(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][0]["agentharness_refs_if_available"][
                "request_id_candidate"
            ] = "TR-not-exported"
            _write_json(paths["observations"], observations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        first = _decision_by_id(report, "pi-obs-001-read-workspace")
        self.assertEqual("error", first["decision"])
        self.assertNotEqual("allow_candidate", first["decision"])
        self.assertTrue(
            any("missing request_id" in error for error in first["errors"]),
            first["errors"],
        )

    def test_tampered_expectation_decision_fails(self) -> None:
        with _temporary_payloads() as paths:
            expectations = _load_json(paths["expectations"])
            expectations["mapping_expectations"][0]["expected_decision"] = "block"
            _write_json(paths["expectations"], expectations)

            report = build_pi_tool_call_mapping_report(
                paths["observations"],
                paths["expectations"],
                REGISTRY_BUS_ROOT,
            )

        self.assertFalse(report["ok"])
        self.assertEqual(
            "allow_candidate",
            _decision_by_id(report, "pi-obs-001-read-workspace")["decision"],
        )
        self.assertTrue(
            any("expected 'block', got 'allow_candidate'" in error for error in report["errors"]),
            report["errors"],
        )


def _build_report() -> dict[str, Any]:
    return build_pi_tool_call_mapping_report(
        OBSERVATIONS_PATH,
        EXPECTATIONS_PATH,
        REGISTRY_BUS_ROOT,
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return copy.deepcopy(value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        encoding="utf-8",
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _decision_by_id(report: Mapping[str, Any], observation_id: str) -> Mapping[str, Any]:
    for decision in _expect_list(report["decisions"]):
        if decision.get("observation_id") == observation_id:
            return _expect_mapping(decision)
    raise AssertionError(f"missing decision {observation_id}")


def _expect_mapping(value: Any) -> Mapping[str, Any]:
    assert isinstance(value, Mapping), value
    return value


def _expect_list(value: Any) -> list[Any]:
    assert isinstance(value, list), value
    return value


def _bad_result_status_paths(value: Any, path: str = "$") -> list[str]:
    bad: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path != "$" else str(key)
            if key == "result_status" and item != NOT_EXECUTED:
                bad.append(child_path)
            bad.extend(_bad_result_status_paths(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            bad.extend(_bad_result_status_paths(item, f"{path}[{index}]"))
    return bad


def _raw_host_path_matches(value: Any) -> list[str]:
    payload = _canonical_json(value)
    needles = [
        str(ROOT),
        str(REGISTRY_BUS_ROOT),
        "/tmp/",
        "\\\\server",
        "C:\\\\Users",
    ]
    return [needle for needle in needles if needle in payload]


def _temporary_payloads():
    class _Payloads:
        def __enter__(self) -> dict[str, Path]:
            self._temp = tempfile.TemporaryDirectory()
            root = Path(self._temp.name)
            self.paths = {
                "observations": root / "pi_tool_call_observations.json",
                "expectations": root / "expected_mapping.json",
            }
            self.paths["observations"].write_text(
                OBSERVATIONS_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.paths["expectations"].write_text(
                EXPECTATIONS_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            return self.paths

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            self._temp.cleanup()

    return _Payloads()


if __name__ == "__main__":
    unittest.main()
