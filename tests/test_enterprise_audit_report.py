from contextlib import redirect_stderr, redirect_stdout
import copy
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import agentharness.cli as cli_module
from agentharness.audit_contract import sanitize_audit_message
import agentharness.enterprise_audit_checklist as checklist_module
from agentharness.enterprise_audit_checklist import (
    build_enterprise_audit_checklist,
    validate_enterprise_audit_checklist_payload,
)
import agentharness.enterprise_audit_report as audit_report_module
from agentharness.cli import main
from agentharness.enterprise_audit_report import (
    build_enterprise_audit_report,
    enterprise_audit_error_payload,
    validate_enterprise_audit_report_payload,
    verify_enterprise_audit_report,
)
from agentharness.validate import ValidationReport
from agentharness.yamlio import load_yaml


REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
DIRECT_HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
HANDOFF_REPORT_PATH = Path("handoffs") / "T008-handoff-report.yaml"
REGISTRY_PATH = Path("adapters") / "registry.yaml"
AUDIT_REPORT_SCHEMA = ROOT / "schemas" / "enterprise_audit_report.schema.yaml"
AUDIT_CHECKLIST_SCHEMA = ROOT / "schemas" / "enterprise_audit_checklist.schema.yaml"
ZERO_DIGEST = "sha256:" + "0" * 64
EXPECTED_EXPORTED = ["TR-read", "TR-approve-delete"]
EXPECTED_EXCLUDED = {
    "TR-read-unsupported-intent",
    "TR-missing-approval-delete",
    "TR-deny-unknown",
}


class EnterpriseAuditReportTests(unittest.TestCase):
    def test_shared_sanitizer_hides_paths_and_preserves_urls(self):
        message = (
            r"see https://example.com/docs at /home/example-user/secret.yaml "
            r"and C:\\Users\\example-user\\secret.yaml and \\\\server\\share\\secret.yaml"
        )

        sanitized = sanitize_audit_message(message)

        self.assertIn("https://example.com/docs", sanitized)
        self.assertIn("<path>", sanitized)
        self.assertNotIn("/home/example-user", sanitized)
        self.assertNotIn("C:\\Users", sanitized)
        self.assertNotIn("server", sanitized)
        self.assertNotIn("share", sanitized)
        self.assertNotIn("secret.yaml", sanitized)

    def test_checklist_does_not_import_report_private_sanitizer(self):
        source = (ROOT / "src" / "agentharness" / "enterprise_audit_checklist.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("_sanitize_message", source)
        self.assertIn("sanitize_audit_message", source)

    def test_enterprise_audit_checklist_schema_artifact_loads(self):
        schema = yaml.safe_load(AUDIT_CHECKLIST_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual("0.1.0", schema["version"])
        self.assertEqual("enterprise_audit_checklist_schema", schema["name"])
        self.assertEqual("conceptual_schema", schema["kind"])
        schema_text = json.dumps(schema, sort_keys=True)
        self.assertIn("enterprise_audit_checklist_report", schema_text)
        self.assertIn("build_enterprise_audit_checklist", schema_text)
        self.assertIn("validate_enterprise_audit_checklist_payload", schema_text)
        self.assertIn("not_executed", schema_text)
        self.assertIn("runtime execution", schema_text)
        self.assertIn("adapter invocation", schema_text)
        self.assertIn("trust-root", schema_text)
        self.assertIn("file writing", schema_text)

    def test_checklist_payload_validator_accepts_positive_payload(self):
        payload = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)
        report = validate_enterprise_audit_checklist_payload(payload)

        self.assertEqual([], report.errors)
        self.assertTrue(report.ok)

    def test_checklist_payload_validator_rejects_contract_drift(self):
        payload = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)
        self.assertTrue(validate_enterprise_audit_checklist_payload(payload).ok)

        drift_cases = [
            ("non_mapping", lambda _payload: []),
            ("wrong_version", lambda value: _mutated(value, lambda item: item.__setitem__("version", "9.9.9"))),
            ("missing_version", lambda value: _mutated(value, lambda item: item.pop("version"))),
            ("wrong_kind", lambda value: _mutated(value, lambda item: item.__setitem__("kind", "wrong"))),
            ("missing_kind", lambda value: _mutated(value, lambda item: item.pop("kind"))),
            ("wrong_source", lambda value: _mutated(value, lambda item: item.__setitem__("source", "wrong"))),
            ("missing_source", lambda value: _mutated(value, lambda item: item.pop("source"))),
            ("wrong_result_status", lambda value: _mutated(value, lambda item: item.__setitem__("result_status", "executed"))),
            ("missing_result_status", lambda value: _mutated(value, lambda item: item.pop("result_status"))),
            ("unknown_top_level", lambda value: _mutated(value, lambda item: item.__setitem__("runtime_adapter", "external"))),
            (
                "nested_runtime_result_status",
                lambda value: _mutated(
                    value,
                    lambda item: item["checks"][0].__setitem__("result_status", "executed"),
                ),
            ),
            ("invalid_ok_type", lambda value: _mutated(value, lambda item: item.__setitem__("ok", "true"))),
            ("missing_goal", lambda value: _mutated(value, lambda item: item.pop("goal"))),
            (
                "invalid_goal_id",
                lambda value: _mutated(
                    value,
                    lambda item: item["goal"].__setitem__("id", "runtime_execution"),
                ),
            ),
            (
                "invalid_goal_status",
                lambda value: _mutated(
                    value,
                    lambda item: item["goal"].__setitem__("status", "manual"),
                ),
            ),
            (
                "invalid_summary_type",
                lambda value: _mutated(
                    value,
                    lambda item: item["summary"].__setitem__("checks", "7"),
                ),
            ),
            (
                "inconsistent_summary_count",
                lambda value: _mutated(
                    value,
                    lambda item: item["summary"].__setitem__("manual", 0),
                ),
            ),
            (
                "missing_check",
                lambda value: _mutated(value, lambda item: item["checks"].pop()),
            ),
            (
                "duplicate_check",
                lambda value: _mutated(
                    value,
                    lambda item: item["checks"].__setitem__(1, copy.deepcopy(item["checks"][0])),
                ),
            ),
            (
                "out_of_order_checks",
                lambda value: _mutated(value, lambda item: item["checks"].reverse()),
            ),
            (
                "invalid_check_status",
                lambda value: _mutated(
                    value,
                    lambda item: item["checks"][0].__setitem__("status", "unknown"),
                ),
            ),
            (
                "non_manual_missing_evidence",
                lambda value: _mutated(value, lambda item: item["checks"][0].pop("evidence")),
            ),
            (
                "manual_missing_command",
                lambda value: _mutated(value, lambda item: item["checks"][-1].pop("command")),
            ),
            (
                "manual_with_evidence",
                lambda value: _mutated(
                    value,
                    lambda item: item["checks"][-1].__setitem__("evidence", {}),
                ),
            ),
            (
                "non_string_top_error",
                lambda value: _mutated(value, lambda item: item["errors"].append({"bad": True})),
            ),
            (
                "non_string_check_warning",
                lambda value: _mutated(
                    value,
                    lambda item: item["checks"][0]["warnings"].append(123),
                ),
            ),
            (
                "raw_host_path_error",
                lambda value: _mutated(value, lambda item: item["errors"].append("leak /home/example-user/secret.yaml")),
            ),
            (
                "top_level_error_with_ok_true",
                lambda value: _mutated(value, lambda item: item["errors"].append("schema drift")),
            ),
            (
                "wrong_manual_command",
                lambda value: _mutated(
                    value,
                    lambda item: item["checks"][-1].__setitem__("command", "agentharness audit verify-report --run"),
                ),
            ),
        ]

        for name, mutate in drift_cases:
            with self.subTest(name=name):
                candidate = mutate(payload)
                report = validate_enterprise_audit_checklist_payload(candidate)
                self.assertFalse(report.ok, name)
                self.assertTrue(report.errors, name)

    def test_checklist_builder_self_check_failure_is_deterministic(self):
        failed = ValidationReport()
        failed.error("forced", "schema drift")

        with mock.patch.object(
            checklist_module,
            "validate_enterprise_audit_checklist_payload",
            return_value=failed,
        ):
            first = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)
            second = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)

        self.assertEqual(first, second)
        self.assertIs(first["ok"], False)
        self.assertEqual("fail", first["goal"]["status"])
        self.assertEqual("not_executed", first["result_status"])
        self.assertTrue(first["errors"])
        self.assertTrue(
            any("checklist_schema.self_check" in error for error in first["errors"])
        )
        self.assertNotIn("/home/", json.dumps(first, sort_keys=True))
        self.assertTrue(validate_enterprise_audit_checklist_payload(first).ok)

    def test_checklist_shape_and_fixture_summary(self):
        payload = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)

        self.assertEqual("0.1.0", payload["version"])
        self.assertEqual("enterprise_audit_checklist_report", payload["kind"])
        self.assertEqual("build_enterprise_audit_checklist", payload["source"])
        self.assertEqual("not_executed", payload["result_status"])
        self.assertIs(payload["ok"], True)
        self.assertEqual(
            {
                "id": "pre_execution_evidence_review",
                "status": "pass",
                "description": "deterministic pre-execution evidence is ready for reviewer inspection",
            },
            payload["goal"],
        )
        self.assertEqual(
            {
                "checks": 7,
                "passed": 5,
                "failed": 0,
                "blocked": 0,
                "manual": 2,
                "reports": 1,
                "total_handoffs": 5,
                "handoff_ready": 2,
                "exported": 2,
                "blocked_handoffs": 2,
                "unsupported": 1,
            },
            payload["summary"],
        )
        self.assertEqual([], payload["errors"])
        self.assertEqual([], payload["warnings"])
        self.assertEqual(
            [
                "file_bus_validation",
                "handoff_inspection",
                "registry_backed_export",
                "digest_manifest",
                "enterprise_audit_report",
                "saved_manifest_readback",
                "saved_audit_report_readback",
            ],
            [item["id"] for item in payload["checks"]],
        )
        self.assertEqual(
            ["pass", "pass", "pass", "pass", "pass", "manual", "manual"],
            [item["status"] for item in payload["checks"]],
        )
        for item in payload["checks"]:
            self.assertEqual("not_executed", item["result_status"])
            self.assertIn("errors", item)
            self.assertIn("warnings", item)
        self.assertEqual(
            ["TR-read", "TR-approve-delete"],
            _check_by_id(payload, "registry_backed_export")["evidence"]["exported_request_ids"],
        )
        self.assertEqual(
            ["TR-read", "TR-approve-delete"],
            _check_by_id(payload, "digest_manifest")["evidence"]["item_request_ids"],
        )
        self.assertEqual(
            "agentharness handoff verify-manifest <bus_root> <manifest_path>",
            _check_by_id(payload, "saved_manifest_readback")["command"],
        )
        self.assertEqual(
            "agentharness audit verify-report <bus_root> <audit_report_path>",
            _check_by_id(payload, "saved_audit_report_readback")["command"],
        )

    def test_checklist_repeated_builder_output_is_deterministic(self):
        first = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)
        second = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)

        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_checklist_cli_output_matches_builder_and_exits_zero(self):
        code, output, stderr = _run_cli(["audit", "checklist", str(REGISTRY_BUS_ROOT)])

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        payload = json.loads(output)
        self.assertEqual(build_enterprise_audit_checklist(REGISTRY_BUS_ROOT), payload)
        self.assertEqual("enterprise_audit_checklist_report", payload["kind"])
        self.assertIs(payload["ok"], True)

    def test_checklist_direct_legacy_fixture_does_not_pass_readiness(self):
        payload = build_enterprise_audit_checklist(DIRECT_HANDOFF_BUS_ROOT)

        self.assertIs(payload["ok"], False)
        self.assertEqual("fail", payload["goal"]["status"])
        self.assertEqual("pass", _check_by_id(payload, "file_bus_validation")["status"])
        self.assertEqual("pass", _check_by_id(payload, "handoff_inspection")["status"])
        self.assertEqual("fail", _check_by_id(payload, "registry_backed_export")["status"])
        self.assertEqual("blocked", _check_by_id(payload, "digest_manifest")["status"])
        self.assertEqual("blocked", _check_by_id(payload, "enterprise_audit_report")["status"])
        self.assertTrue(
            any("registry-backed handoff report is required" in error for error in payload["errors"])
        )
        self.assertFalse(_contains_absolute_path(payload))

    def test_checklist_registry_failures_and_forged_digest_fail_closed(self):
        cases = [
            (
                "missing_registry_path",
                lambda bus_root: _mutate_handoff_report(
                    bus_root, lambda handoff_report: handoff_report.pop("adapter_registry_path")
                ),
                "adapter_registry_path",
            ),
            (
                "missing_adapter_ref",
                lambda bus_root: _mutate_handoff_report(
                    bus_root, lambda handoff_report: handoff_report.pop("adapter_ref")
                ),
                "adapter_ref",
            ),
            (
                "forged_digest",
                lambda bus_root: _mutate_registry(
                    bus_root,
                    lambda registry: registry["entries"][0].__setitem__(
                        "adapter_spec_digest", ZERO_DIGEST
                    ),
                ),
                "adapter_spec_digest",
            ),
            (
                "missing_registry_file",
                lambda bus_root: (bus_root / REGISTRY_PATH).unlink(),
                "adapter_registry_path",
            ),
        ]

        for name, mutate, expected_error in cases:
            with self.subTest(name=name):
                payload = _run_mutated_checklist(mutate)

                self.assertIs(payload["ok"], False)
                self.assertIn(
                    _check_by_id(payload, "registry_backed_export")["status"],
                    {"fail", "blocked"},
                )
                self.assertEqual("blocked", _check_by_id(payload, "digest_manifest")["status"])
                self.assertEqual("blocked", _check_by_id(payload, "enterprise_audit_report")["status"])
                self.assertTrue(any(expected_error in error for error in payload["errors"]))
                self.assertFalse(_contains_absolute_path(payload))

    def test_checklist_no_ready_handoffs_remains_safe(self):
        payload = _run_mutated_checklist(_remove_ready_handoffs)

        self.assertIs(payload["ok"], False)
        self.assertEqual("pass", _check_by_id(payload, "file_bus_validation")["status"])
        self.assertEqual("pass", _check_by_id(payload, "handoff_inspection")["status"])
        self.assertEqual("fail", _check_by_id(payload, "registry_backed_export")["status"])
        self.assertEqual("blocked", _check_by_id(payload, "digest_manifest")["status"])
        self.assertEqual("blocked", _check_by_id(payload, "enterprise_audit_report")["status"])
        self.assertEqual("manual", _check_by_id(payload, "saved_manifest_readback")["status"])
        self.assertEqual("manual", _check_by_id(payload, "saved_audit_report_readback")["status"])
        self.assertTrue(any("no handoff_ready" in error for error in payload["errors"]))

    def test_checklist_missing_bus_errors_are_sanitized_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_bus = Path(tmpdir) / "missing-bus"
            code, output, stderr = _run_cli(["audit", "checklist", str(missing_bus)])

        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        payload = json.loads(output)
        self.assertEqual("enterprise_audit_checklist_report", payload["kind"])
        self.assertIs(payload["ok"], False)
        self.assertFalse(_contains_absolute_path(payload))
        self.assertNotIn(str(missing_bus), output)
        self.assertNotIn(tmpdir, output)
        self.assertNotIn("/tmp/", output)
        self.assertNotIn("/home/", output)

    def test_checklist_cli_rejects_file_output_and_action_flags(self):
        rejected_flags = [
            ["--out", "checklist.json"],
            ["--write"],
            ["--save"],
            ["--execute"],
            ["--dispatch"],
            ["--submit"],
            ["--run"],
            ["--mutate"],
            ["--sign"],
            ["--timestamp"],
        ]

        for flag_args in rejected_flags:
            with self.subTest(flag_args=flag_args):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(["audit", "checklist", str(REGISTRY_BUS_ROOT), *flag_args])
                self.assertEqual(2, raised.exception.code)
                self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_report_shape_and_fixture_summary(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual("0.1.0", payload["version"])
        self.assertEqual("enterprise_audit_report", payload["kind"])
        self.assertEqual("build_enterprise_audit_report", payload["source"])
        self.assertEqual("not_executed", payload["result_status"])
        self.assertEqual(
            {
                "execution_occurred": False,
                "runtime_adapter_invoked": False,
                "execution_owner": "external",
                "result_status": "not_executed",
            },
            payload["control_plane_boundary"],
        )
        self.assertEqual(
            {
                "reports": 1,
                "total_handoffs": 5,
                "handoff_ready": 2,
                "exported": 2,
                "blocked": 2,
                "unsupported": 1,
                "result_status": "not_executed",
            },
            payload["summary"],
        )
        self.assertEqual(
            [
                "file_bus",
                "tool_gate",
                "approval_record",
                "preflight",
                "handoff",
                "adapter_registry",
                "export_package",
                "digest_manifest",
                "manifest_verification",
            ],
            payload["evidence_chain"],
        )

    def test_enterprise_audit_report_schema_artifact_loads(self):
        schema = yaml.safe_load(AUDIT_REPORT_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual("0.1.0", schema["version"])
        self.assertEqual("enterprise_audit_report_schema", schema["name"])
        self.assertEqual("conceptual_schema", schema["kind"])
        schema_text = json.dumps(schema, sort_keys=True)
        self.assertIn("enterprise_audit_report", schema_text)
        self.assertIn("enterprise_audit_report_error", schema_text)
        self.assertIn("not_executed", schema_text)
        self.assertIn("runtime execution", schema_text)
        self.assertIn("adapter invocation", schema_text)
        self.assertIn("trust-root", schema_text)
        self.assertIn("file writing", schema_text)
        self.assertIn(
            "agentharness handoff verify-manifest <bus_root> <manifest_path>",
            schema_text,
        )

    def test_success_error_and_direct_failure_payloads_validate(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)
        self.assertTrue(validate_enterprise_audit_report_payload(payload).ok)

        error_report = ValidationReport()
        error_report.error("probe", "failure /home/example-user/secret.yaml")
        error_payload = enterprise_audit_error_payload(error_report)
        self.assertTrue(validate_enterprise_audit_report_payload(error_payload).ok)
        self.assertNotIn("/home/example-user/secret.yaml", json.dumps(error_payload))

        direct_payload, direct_report = build_enterprise_audit_report(DIRECT_HANDOFF_BUS_ROOT)
        self.assertIsNone(direct_payload)
        self.assertFalse(direct_report.ok)
        direct_error_payload = enterprise_audit_error_payload(direct_report)
        self.assertTrue(validate_enterprise_audit_report_payload(direct_error_payload).ok)

    def test_success_payload_validator_rejects_contract_drift(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)

        mutations = [
            (
                "wrong_kind",
                lambda value: value.__setitem__("kind", "wrong_kind"),
            ),
            (
                "wrong_source",
                lambda value: value.__setitem__("source", "other_source"),
            ),
            (
                "wrong_result_status",
                lambda value: value.__setitem__("result_status", "executed"),
            ),
            (
                "success_ok_field",
                lambda value: value.__setitem__("ok", True),
            ),
            (
                "empty_control_plane_boundary",
                lambda value: value.__setitem__("control_plane_boundary", {}),
            ),
            (
                "unknown_control_plane_boundary_field",
                lambda value: value["control_plane_boundary"].__setitem__(
                    "evidence_envelope", {}
                ),
            ),
            (
                "execution_occurred_true",
                lambda value: value["control_plane_boundary"].__setitem__(
                    "execution_occurred", True
                ),
            ),
            (
                "runtime_adapter_invoked_true",
                lambda value: value["control_plane_boundary"].__setitem__(
                    "runtime_adapter_invoked", True
                ),
            ),
            (
                "summary_missing_count",
                lambda value: value["summary"].pop("blocked"),
            ),
            (
                "empty_summary",
                lambda value: value.__setitem__("summary", {}),
            ),
            (
                "summary_unknown_field",
                lambda value: value["summary"].__setitem__("write_output", {}),
            ),
            (
                "summary_count_non_integer",
                lambda value: value["summary"].__setitem__("exported", "2"),
            ),
            (
                "top_level_evidence_envelope",
                lambda value: value.__setitem__("evidence_envelope", {}),
            ),
            (
                "top_level_write_output",
                lambda value: value.__setitem__("write_output", {"path": "/tmp/x"}),
            ),
            (
                "top_level_runtime_adapter",
                lambda value: value.__setitem__("runtime_adapter", "pi"),
            ),
            (
                "export_unknown_field",
                lambda value: value["export"].__setitem__("evidence_envelope", {}),
            ),
            (
                "exported_not_ready",
                lambda value: value["handoffs"][0].__setitem__("handoff_status", "blocked"),
            ),
            (
                "unsupported_exported",
                lambda value: value["handoffs"][2].__setitem__("exported", True),
            ),
            (
                "export_request_order_mismatch",
                lambda value: value["export"].__setitem__(
                    "exported_request_ids", ["TR-approve-delete", "TR-read"]
                ),
            ),
            (
                "manifest_request_mismatch",
                lambda value: value["manifest"].__setitem__("item_request_ids", ["TR-read"]),
            ),
            (
                "bad_digest",
                lambda value: value["manifest"].__setitem__(
                    "package_digest", "sha256:not-a-digest"
                ),
            ),
            (
                "manifest_unknown_field",
                lambda value: value["manifest"].__setitem__("runtime_adapter", "pi"),
            ),
            (
                "empty_manifest_verification",
                lambda value: value.__setitem__("manifest_verification", {}),
            ),
            (
                "missing_manifest_verification_command",
                lambda value: value["manifest_verification"].pop("command"),
            ),
            (
                "nested_manifest_verification_envelope",
                lambda value: value["manifest_verification"].__setitem__(
                    "evidence_envelope", {}
                ),
            ),
            (
                "manifest_verification_performed",
                lambda value: value["manifest_verification"].__setitem__("performed", True),
            ),
            (
                "nested_result_status_executed",
                lambda value: value["handoffs"][0].__setitem__(
                    "result_status", "executed"
                ),
            ),
        ]

        for name, mutate in mutations:
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                self.assertFalse(validate_enterprise_audit_report_payload(mutated).ok)

    def test_error_payload_validator_rejects_contract_drift(self):
        error_report = ValidationReport()
        error_report.error("probe", "failure")
        payload = enterprise_audit_error_payload(error_report)
        self.assertTrue(validate_enterprise_audit_report_payload(payload).ok)

        mutations = [
            ("wrong_kind", lambda value: value.__setitem__("kind", "wrong_kind")),
            ("wrong_source", lambda value: value.__setitem__("source", "other_source")),
            ("ok_true", lambda value: value.__setitem__("ok", True)),
            ("executed", lambda value: value.__setitem__("result_status", "executed")),
            ("empty_errors", lambda value: value.__setitem__("errors", [])),
            ("non_list_errors", lambda value: value.__setitem__("errors", "failure")),
            ("non_list_warnings", lambda value: value.__setitem__("warnings", "warning")),
            ("unknown_field", lambda value: value.__setitem__("evidence_envelope", {})),
            ("non_string_error", lambda value: value.__setitem__("errors", [123])),
            ("non_string_warning", lambda value: value.__setitem__("warnings", [123])),
            (
                "raw_posix_error_path",
                lambda value: value.__setitem__("errors", ["failure /home/example-user/secret.yaml"]),
            ),
            (
                "raw_windows_warning_path",
                lambda value: value.__setitem__(
                    "warnings", [r"warning C:\Users\example-user\secret.yaml"]
                ),
            ),
            (
                "raw_unc_error_path",
                lambda value: value.__setitem__(
                    "errors", [r"failure \\server\share\secret.yaml"]
                ),
            ),
            (
                "raw_escaped_unc_warning_path",
                lambda value: value.__setitem__(
                    "warnings", [r"warning \\\\server\\share\\secret.yaml"]
                ),
            ),
        ]

        for name, mutate in mutations:
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                self.assertFalse(validate_enterprise_audit_report_payload(mutated).ok)

    def test_error_payload_validator_preserves_urls(self):
        payload = {
            "version": "0.1.0",
            "kind": "enterprise_audit_report_error",
            "source": "build_enterprise_audit_report",
            "ok": False,
            "result_status": "not_executed",
            "errors": ["see https://example.com/docs"],
            "warnings": ["review https://example.com/docs"],
        }

        self.assertTrue(validate_enterprise_audit_report_payload(payload).ok)

    def test_builder_self_validation_failure_returns_report(self):
        def fail_validation(_payload):
            validation = ValidationReport()
            validation.error("self_check", "forced schema validation failure")
            return validation

        with mock.patch.object(
            audit_report_module,
            "validate_enterprise_audit_report_payload",
            fail_validation,
        ):
            payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)

        self.assertIsNone(payload)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("audit_report_schema.self_check" in error for error in report.errors)
        )

    def test_exported_and_excluded_request_ids(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        assert payload is not None
        self.assertEqual(EXPECTED_EXPORTED, payload["export"]["exported_request_ids"])
        self.assertEqual(EXPECTED_EXPORTED, payload["manifest"]["item_request_ids"])
        by_id = {item["request_id"]: item for item in payload["handoffs"]}
        self.assertIs(True, by_id["TR-read"]["exported"])
        self.assertIs(True, by_id["TR-approve-delete"]["exported"])
        for request_id in EXPECTED_EXCLUDED:
            self.assertIs(False, by_id[request_id]["exported"])
        self.assertEqual("unsupported", by_id["TR-read-unsupported-intent"]["handoff_status"])
        self.assertEqual("blocked", by_id["TR-missing-approval-delete"]["handoff_status"])
        self.assertEqual("blocked", by_id["TR-deny-unknown"]["handoff_status"])

    def test_manifest_verification_is_boundary_note_only(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        assert payload is not None
        self.assertEqual(
            {
                "performed": False,
                "reason": "requires_saved_manifest_path",
                "command": "agentharness handoff verify-manifest <bus_root> <manifest_path>",
                "result_status": "not_executed",
            },
            payload["manifest_verification"],
        )

    def test_report_contains_no_absolute_host_paths(self):
        code, output, _ = _run_cli(["audit", "report", str(REGISTRY_BUS_ROOT)])

        self.assertEqual(0, code)
        payload = json.loads(output)
        self.assertNotIn("/home/", output)
        self.assertFalse(_contains_absolute_path(payload))
        self.assertNotIn("bus_root", payload)

    def test_repeated_builder_output_is_deterministic(self):
        first, first_report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        second, second_report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)

        self.assertEqual([], first_report.errors)
        self.assertEqual([], second_report.errors)
        self.assertEqual(first, second)

    def test_repeated_cli_stdout_is_deterministic(self):
        first_code, first_output, _ = _run_cli(["audit", "report", str(REGISTRY_BUS_ROOT)])
        second_code, second_output, _ = _run_cli(["audit", "report", str(REGISTRY_BUS_ROOT)])

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual(first_output, second_output)
        self.assertEqual("enterprise_audit_report", json.loads(first_output)["kind"])

    def test_verify_report_positive_function_and_cli_contract(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_path = Path(tmpdir) / "audit-report.json"
            _write_json(saved_path, payload)

            verification = verify_enterprise_audit_report(REGISTRY_BUS_ROOT, saved_path)
            self.assertEqual("0.1.0", verification["version"])
            self.assertEqual("enterprise_audit_report_verification_report", verification["kind"])
            self.assertEqual("verify_enterprise_audit_report", verification["source"])
            self.assertEqual("enterprise_audit_report", verification["report_kind"])
            self.assertIs(True, verification["ok"])
            self.assertEqual("not_executed", verification["result_status"])
            self.assertEqual(
                verification["expected_report_digest"],
                verification["saved_report_digest"],
            )
            self.assertEqual([], verification["errors"])
            self.assertEqual([], verification["warnings"])
            self.assertEqual(
                {
                    "reports": 1,
                    "handoffs": 5,
                    "matched_handoffs": 5,
                    "mismatched_handoffs": 0,
                    "missing_handoffs": 0,
                    "extra_handoffs": 0,
                    "result_status": "not_executed",
                },
                verification["summary"],
            )
            self.assertTrue(verification["items"])
            self.assertEqual(
                {
                    "kind": "enterprise_audit_report_verification_item",
                    "request_id": "TR-read",
                    "ok": True,
                    "expected_handoff_status": "handoff_ready",
                    "saved_handoff_status": "handoff_ready",
                    "expected_exported": True,
                    "saved_exported": True,
                    "result_status": "not_executed",
                },
                verification["items"][0],
            )

            code, output, stderr = _run_cli(
                ["audit", "verify-report", str(REGISTRY_BUS_ROOT), str(saved_path)]
            )
            self.assertEqual(0, code)
            self.assertEqual("", stderr)
            self.assertEqual(verification, json.loads(output))
            self.assertNotIn("/home/", output)
            self.assertNotIn(str(saved_path), output)

    def test_verify_report_repeated_function_and_cli_output_is_deterministic(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_path = Path(tmpdir) / "audit-report.json"
            _write_json(saved_path, payload)

            first = verify_enterprise_audit_report(REGISTRY_BUS_ROOT, saved_path)
            second = verify_enterprise_audit_report(REGISTRY_BUS_ROOT, saved_path)
            self.assertEqual(first, second)

            first_code, first_output, first_stderr = _run_cli(
                ["audit", "verify-report", str(REGISTRY_BUS_ROOT), str(saved_path)]
            )
            second_code, second_output, second_stderr = _run_cli(
                ["audit", "verify-report", str(REGISTRY_BUS_ROOT), str(saved_path)]
            )
            self.assertEqual(0, first_code)
            self.assertEqual(0, second_code)
            self.assertEqual("", first_stderr)
            self.assertEqual("", second_stderr)
            self.assertEqual(first_output, second_output)

    def test_verify_report_malformed_inputs_fail_with_json(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            cases = []
            missing_path = tmp_root / "missing-report.json"
            cases.append(("unreadable", missing_path))
            invalid_utf8 = tmp_root / "invalid-utf8.json"
            invalid_utf8.write_bytes(b"\xff")
            cases.append(("invalid_utf8", invalid_utf8))
            malformed_json = tmp_root / "malformed.json"
            malformed_json.write_text("{not-json", encoding="utf-8")
            cases.append(("malformed_json", malformed_json))
            for index, value in enumerate(([payload], "text", None)):
                path = tmp_root / f"non-object-{index}.json"
                _write_json(path, value)
                cases.append((f"non_object_{index}", path))

            for name, path in cases:
                with self.subTest(name=name):
                    code, output, stderr = _run_cli(
                        ["audit", "verify-report", str(REGISTRY_BUS_ROOT), str(path)]
                    )
                    self.assertEqual(1, code)
                    self.assertEqual("", stderr)
                    verification = json.loads(output)
                    self.assertEqual(
                        "enterprise_audit_report_verification_report",
                        verification["kind"],
                    )
                    self.assertIs(False, verification["ok"])
                    self.assertEqual("not_executed", verification["result_status"])
                    self.assertTrue(verification["errors"])
                    self.assertNotIn("Traceback", output)
                    self.assertNotIn(tmpdir, output)
                    self.assertNotIn("/tmp/", output)
                    self.assertNotIn("/home/", output)

    def test_verify_report_schema_invalid_payloads_fail(self):
        error_report = ValidationReport()
        error_report.error("probe", "failure")
        error_payload = enterprise_audit_error_payload(error_report)
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)

        mutations = [
            ("error_payload", lambda _payload: error_payload),
            ("wrong_kind", lambda value: _mutated(value, lambda item: item.__setitem__("kind", "wrong"))),
            ("missing_kind", lambda value: _mutated(value, lambda item: item.pop("kind"))),
            ("wrong_source", lambda value: _mutated(value, lambda item: item.__setitem__("source", "wrong"))),
            ("wrong_version", lambda value: _mutated(value, lambda item: item.__setitem__("version", "9.9.9"))),
            ("wrong_result_status", lambda value: _mutated(value, lambda item: item.__setitem__("result_status", "executed"))),
            ("success_ok", lambda value: _mutated(value, lambda item: item.__setitem__("ok", True))),
            (
                "invalid_boundary",
                lambda value: _mutated(
                    value,
                    lambda item: item["control_plane_boundary"].__setitem__(
                        "execution_occurred", True
                    ),
                ),
            ),
            ("wrong_evidence_chain", lambda value: _mutated(value, lambda item: item["evidence_chain"].reverse())),
            ("summary_tamper", lambda value: _mutated(value, lambda item: item["summary"].__setitem__("handoff_ready", 99))),
            (
                "manifest_verification_command",
                lambda value: _mutated(
                    value,
                    lambda item: item["manifest_verification"].__setitem__(
                        "command", "agentharness handoff verify-manifest --out"
                    ),
                ),
            ),
            (
                "manifest_verification_performed",
                lambda value: _mutated(
                    value,
                    lambda item: item["manifest_verification"].__setitem__("performed", True),
                ),
            ),
            (
                "manifest_verification_reason",
                lambda value: _mutated(
                    value,
                    lambda item: item["manifest_verification"].__setitem__("reason", "already_verified"),
                ),
            ),
            (
                "manifest_verification_status",
                lambda value: _mutated(
                    value,
                    lambda item: item["manifest_verification"].__setitem__("result_status", "executed"),
                ),
            ),
        ]

        for name, make_payload in mutations:
            with self.subTest(name=name):
                verification = _verify_saved_payload(make_payload(payload))
                self.assertIs(False, verification["ok"])
                self.assertTrue(verification["errors"])

    def test_verify_report_valid_tampering_and_handoff_drift_fail(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)
        assert payload is not None

        extra = copy.deepcopy(payload["handoffs"][0])
        extra["request_id"] = "TR-extra"
        valid_tamper_cases = [
            (
                "export_request_order_mismatch",
                lambda value: value["export"].__setitem__(
                    "exported_request_ids", ["TR-approve-delete", "TR-read"]
                ),
            ),
            (
                "manifest_item_request_mismatch",
                lambda value: value["manifest"].__setitem__(
                    "item_request_ids", ["TR-approve-delete", "TR-read"]
                ),
            ),
            (
                "forged_manifest_digest",
                lambda value: value["manifest"].__setitem__("package_digest", ZERO_DIGEST),
            ),
            (
                "canonical_structural_edit",
                lambda value: value["handoffs"][0].__setitem__("tool_name", "read_file_changed"),
            ),
            (
                "missing_handoff",
                lambda value: value["handoffs"].pop(),
            ),
            (
                "extra_handoff",
                lambda value: value["handoffs"].append(copy.deepcopy(extra)),
            ),
            (
                "reordered_handoffs",
                lambda value: value["handoffs"].reverse(),
            ),
            (
                "changed_handoff_status",
                lambda value: value["handoffs"][0].__setitem__("handoff_status", "blocked"),
            ),
            (
                "changed_exported",
                lambda value: value["handoffs"][0].__setitem__("exported", False),
            ),
        ]

        for name, mutate in valid_tamper_cases:
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                verification = _verify_saved_payload(mutated)
                self.assertIs(False, verification["ok"])
                self.assertTrue(verification["errors"])

    def test_verify_report_stale_bus_and_direct_fixture_fail(self):
        payload, report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], report.errors)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            saved_path = tmp_root / "audit-report.json"
            _write_json(saved_path, payload)

            handoff_bus = tmp_root / "handoff-mutated"
            shutil.copytree(REGISTRY_BUS_ROOT, handoff_bus)
            _mutate_handoff(
                handoff_bus,
                "TR-read",
                lambda handoff: handoff["request"].__setitem__("tool_name", "read_file_v2"),
            )
            handoff_result = verify_enterprise_audit_report(handoff_bus, saved_path)
            self.assertIs(False, handoff_result["ok"])
            self.assertTrue(handoff_result["errors"])

            registry_bus = tmp_root / "registry-mutated"
            shutil.copytree(REGISTRY_BUS_ROOT, registry_bus)
            _mutate_registry(
                registry_bus,
                lambda registry: registry["entries"][0].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
            registry_result = verify_enterprise_audit_report(registry_bus, saved_path)
            self.assertIs(False, registry_result["ok"])
            self.assertTrue(registry_result["errors"])

            direct_result = verify_enterprise_audit_report(DIRECT_HANDOFF_BUS_ROOT, saved_path)
            self.assertIs(False, direct_result["ok"])
            self.assertTrue(direct_result["errors"])

    def test_audit_verify_report_cli_rejects_file_output_and_action_flags(self):
        rejected_flags = [
            ["--out", "audit.json"],
            ["--write"],
            ["--save"],
            ["--execute"],
            ["--dispatch"],
            ["--submit"],
            ["--run"],
            ["--mutation"],
            ["--mutate"],
            ["--sign"],
            ["--timestamp"],
        ]

        for flag_args in rejected_flags:
            with self.subTest(flag_args=flag_args):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(
                            [
                                "audit",
                                "verify-report",
                                str(REGISTRY_BUS_ROOT),
                                "/tmp/audit-report.json",
                                *flag_args,
                            ]
                        )
                self.assertEqual(2, raised.exception.code)
                self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_direct_legacy_handoff_fixture_fails_with_json_error(self):
        code, output, stderr = _run_cli(["audit", "report", str(DIRECT_HANDOFF_BUS_ROOT)])

        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        payload = json.loads(output)
        self.assertEqual("enterprise_audit_report_error", payload["kind"])
        self.assertEqual("build_enterprise_audit_report", payload["source"])
        self.assertIs(False, payload["ok"])
        self.assertEqual("not_executed", payload["result_status"])
        self.assertTrue(payload["errors"])
        self.assertIn("registry-backed handoff report is required", output)

    def test_error_payload_sanitizes_paths_but_preserves_urls(self):
        report = ValidationReport()
        raw_paths = [
            "/home/example-user/secret.yaml",
            "/tmp/agentharness-secret/report.yaml",
            r"C:\Users\example-user\secret.yaml",
            "D:/tmp/secret.yaml",
            r"\\server\share\secret.yaml",
        ]
        report.errors.extend(
            [
                f"error path {raw_paths[0]} and url https://example.com/docs",
                f"windows path {raw_paths[2]}",
                f"unc path {raw_paths[4]}",
            ]
        )
        report.warnings.extend(
            [
                f"tmp path {raw_paths[1]}",
                f"drive slash path {raw_paths[3]} and url https://example.com/docs",
            ]
        )

        payload = enterprise_audit_error_payload(report)

        text = "\n".join(payload["errors"] + payload["warnings"])
        for raw_path in raw_paths:
            self.assertNotIn(raw_path, text)
        self.assertIn("<path>", text)
        self.assertIn("https://example.com/docs", text)

    def test_unexpected_runtime_error_and_key_error_return_json_without_traceback(self):
        cases = [
            RuntimeError(
                r"boom /home/example-user/secret.yaml C:\Users\example-user\secret.yaml "
                r"\\server\share\secret.yaml https://example.com/docs"
            ),
            KeyError(r"missing D:/tmp/secret.yaml and /tmp/agentharness-secret/report.yaml"),
            KeyError(r"missing C:\\Users\\example-user\\secret.yaml and \\\\server\\share\\secret.yaml"),
        ]
        for exception in cases:
            with self.subTest(exception_type=type(exception).__name__):
                def raise_unexpected(_bus_root, exc=exception):
                    raise exc

                with mock.patch.object(
                    cli_module, "build_enterprise_audit_report", raise_unexpected
                ):
                    code, output, stderr = _run_cli(
                        ["audit", "report", str(REGISTRY_BUS_ROOT)]
                    )

                payload = json.loads(output)
                self.assertEqual(1, code)
                self.assertEqual("", stderr)
                self.assertEqual("enterprise_audit_report_error", payload["kind"])
                self.assertEqual("build_enterprise_audit_report", payload["source"])
                self.assertIs(False, payload["ok"])
                self.assertEqual("not_executed", payload["result_status"])
                self.assertTrue(payload["errors"])
                self.assertNotIn("Traceback", output)
                self.assertNotIn("/home/example-user/secret.yaml", output)
                self.assertNotIn("/tmp/agentharness-secret/report.yaml", output)
                self.assertNotIn(r"C:\Users\example-user\secret.yaml", output)
                self.assertNotIn(r"C:\\Users\\example-user\\secret.yaml", output)
                self.assertNotIn("C:<path>", output)
                self.assertNotIn("D:/tmp/secret.yaml", output)
                self.assertNotIn(r"\\server\share\secret.yaml", output)
                self.assertNotIn(r"\\\\server\\share\\secret.yaml", output)
                self.assertNotIn("server", output)
                self.assertNotIn("share", output)
                self.assertNotIn("secret.yaml", output)

    def test_unexpected_key_error_escaped_unc_path_is_fully_sanitized(self):
        def raise_key_error(_bus_root):
            raise KeyError(r"missing C:\\Users\\example-user\\secret.yaml and \\\\server\\share\\secret.yaml")

        with mock.patch.object(cli_module, "build_enterprise_audit_report", raise_key_error):
            code, output, stderr = _run_cli(["audit", "report", str(REGISTRY_BUS_ROOT)])

        payload = json.loads(output)
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertEqual("enterprise_audit_report_error", payload["kind"])
        self.assertEqual("build_enterprise_audit_report", payload["source"])
        self.assertIs(False, payload["ok"])
        self.assertEqual("not_executed", payload["result_status"])
        self.assertTrue(payload["errors"])
        self.assertNotIn("Traceback", output)
        self.assertNotIn(r"C:\Users\example-user\secret.yaml", output)
        self.assertNotIn(r"C:\\Users\\example-user\\secret.yaml", output)
        self.assertNotIn("C:<path>", output)
        self.assertNotIn(r"\\server\share\secret.yaml", output)
        self.assertNotIn(r"\\\\server\\share\\secret.yaml", output)
        self.assertNotIn("server", output)
        self.assertNotIn("share", output)
        self.assertNotIn("secret.yaml", output)

    def test_unexpected_error_recovery_falls_back_if_error_payload_fails(self):
        def raise_unexpected(_bus_root):
            raise RuntimeError("boom /home/example-user/secret.yaml")

        def raise_payload(_report):
            raise RuntimeError("payload failed /tmp/secret.yaml")

        with mock.patch.object(cli_module, "build_enterprise_audit_report", raise_unexpected):
            with mock.patch.object(cli_module, "enterprise_audit_error_payload", raise_payload):
                code, output, stderr = _run_cli(["audit", "report", str(REGISTRY_BUS_ROOT)])

        payload = json.loads(output)
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertEqual("enterprise_audit_report_error", payload["kind"])
        self.assertEqual("build_enterprise_audit_report", payload["source"])
        self.assertIs(False, payload["ok"])
        self.assertEqual("not_executed", payload["result_status"])
        self.assertTrue(payload["errors"])
        self.assertEqual([], payload["warnings"])
        self.assertNotIn("Traceback", output)
        self.assertNotIn("/home/", output)
        self.assertNotIn("/tmp/", output)

    def test_missing_bus_failure_json_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_bus = Path(tmpdir) / "missing-bus"
            code, output, stderr = _run_cli(["audit", "report", str(missing_bus)])

        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        payload = json.loads(output)
        self.assertEqual("enterprise_audit_report_error", payload["kind"])
        self.assertFalse(_contains_absolute_path(payload))
        self.assertNotIn(str(missing_bus), output)
        self.assertNotIn(tmpdir, output)
        self.assertNotIn("/tmp/", output)
        self.assertNotIn("/home/", output)

    def test_malformed_temp_fixture_failure_json_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
            shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
            (bus_root / HANDOFF_REPORT_PATH).write_text("not: [valid", encoding="utf-8")
            code, output, stderr = _run_cli(["audit", "report", str(bus_root)])

        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        payload = json.loads(output)
        self.assertEqual("enterprise_audit_report_error", payload["kind"])
        self.assertFalse(_contains_absolute_path(payload))
        self.assertNotIn(str(bus_root), output)
        self.assertNotIn(tmpdir, output)
        self.assertNotIn("/tmp/", output)
        self.assertNotIn("/home/", output)

    def test_registry_path_traversal_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.__setitem__(
                    "adapter_registry_path", "../registry.yaml"
                ),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("adapter_registry_path" in error for error in report.errors))

    def test_missing_adapter_registry_path_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.pop("adapter_registry_path"),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("adapter_registry_path" in error for error in report.errors))

    def test_missing_adapter_ref_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.pop("adapter_ref"),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("adapter_ref" in error for error in report.errors))

    def test_disabled_or_deprecated_selected_adapter_fails(self):
        for status in ("disabled", "deprecated"):
            with self.subTest(status=status):
                payload, report = _run_mutated_report(
                    lambda bus_root: _mutate_registry(
                        bus_root,
                        lambda registry: registry["entries"][0].__setitem__("status", status),
                    )
                )

                self.assertIsNone(payload)
                self.assertTrue(
                    any("selected adapter must be active" in error for error in report.errors)
                )

    def test_forged_registry_digest_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("adapter_spec_digest" in error for error in report.errors))

    def test_adapter_ref_digest_mismatch_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report["adapter_ref"].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("adapter_ref.adapter_spec_digest" in error for error in report.errors))

    def test_handoff_adapter_spec_path_mismatch_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.__setitem__(
                    "adapter_spec_path", "adapters/other.yaml"
                ),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("adapter_spec_path" in error for error in report.errors))

    def test_no_ready_handoffs_fails(self):
        payload, report = _run_mutated_report(_remove_ready_handoffs)

        self.assertIsNone(payload)
        self.assertTrue(any("no handoff_ready" in error for error in report.errors))

    def test_blocked_handoff_hand_authored_as_ready_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff(bus_root, "TR-deny-unknown", _make_handoff_ready)
        )

        self.assertIsNone(payload)
        self.assertTrue(any("gate" in error for error in report.errors))

    def test_report_level_result_status_tampering_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.__setitem__(
                    "result_status", "completed"
                ),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("result_status" in error for error in report.errors))

    def test_handoff_level_result_status_tampering_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: _mutate_handoff(
                bus_root,
                "TR-read",
                lambda handoff: handoff.__setitem__("result_status", "executed"),
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("result_status" in error for error in report.errors))

    def test_malformed_referenced_handoff_report_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: (bus_root / HANDOFF_REPORT_PATH).write_text(
                "not: [valid", encoding="utf-8"
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("handoff" in error.lower() for error in report.errors))

    def test_malformed_registry_file_fails(self):
        payload, report = _run_mutated_report(
            lambda bus_root: (bus_root / REGISTRY_PATH).write_text(
                "not: [valid", encoding="utf-8"
            )
        )

        self.assertIsNone(payload)
        self.assertTrue(any("registry" in error.lower() for error in report.errors))

    def test_audit_report_cli_rejects_file_output_and_action_flags(self):
        rejected_flags = [
            ["--out", "audit.json"],
            ["--write"],
            ["--save"],
            ["--execute"],
            ["--dispatch"],
            ["--submit"],
            ["--run"],
            ["--mutate"],
            ["--sign"],
            ["--timestamp"],
        ]

        for flag_args in rejected_flags:
            with self.subTest(flag_args=flag_args):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(["audit", "report", str(REGISTRY_BUS_ROOT), *flag_args])
                self.assertEqual(2, raised.exception.code)
                self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_builder_and_cli_do_not_write_to_bus_or_cwd(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            bus_root = tmp_root / "agent_bus_adapter_registry"
            cwd = tmp_root / "cwd"
            shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
            cwd.mkdir()
            before_bus = _file_snapshot(bus_root)
            before_cwd = _file_snapshot(cwd)

            payload, report = build_enterprise_audit_report(bus_root)
            self.assertEqual([], report.errors)
            self.assertIsNotNone(payload)
            assert payload is not None

            previous_cwd = Path.cwd()
            try:
                os.chdir(cwd)
                code, output, _ = _run_cli(["audit", "report", str(bus_root)])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(0, code)
            self.assertEqual("enterprise_audit_report", json.loads(output)["kind"])
            self.assertEqual(before_bus, _file_snapshot(bus_root))
            self.assertEqual(before_cwd, _file_snapshot(cwd))


def _run_mutated_checklist(mutate):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
        shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
        mutate(bus_root)
        return build_enterprise_audit_checklist(bus_root)


def _check_by_id(payload, check_id):
    for check in payload["checks"]:
        if check.get("id") == check_id:
            return check
    raise AssertionError(f"check not found: {check_id}")


def _run_mutated_report(mutate):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
        shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
        mutate(bus_root)
        return build_enterprise_audit_report(bus_root)


def _run_cli(argv):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _verify_saved_payload(payload):
    with tempfile.TemporaryDirectory() as tmpdir:
        saved_path = Path(tmpdir) / "audit-report.json"
        _write_json(saved_path, payload)
        return verify_enterprise_audit_report(REGISTRY_BUS_ROOT, saved_path)


def _mutated(payload, mutate):
    value = copy.deepcopy(payload)
    mutate(value)
    return value


def _mutate_registry(bus_root, mutate):
    path = bus_root / REGISTRY_PATH
    registry = load_yaml(path)
    mutate(registry)
    _write_yaml(path, registry)


def _mutate_handoff_report(bus_root, mutate):
    path = bus_root / HANDOFF_REPORT_PATH
    handoff_report = load_yaml(path)
    mutate(handoff_report)
    _write_yaml(path, handoff_report)


def _mutate_handoff(bus_root, request_id, mutate):
    def mutate_report(handoff_report):
        for handoff in handoff_report["handoffs"]:
            if handoff.get("request_id") == request_id:
                mutate(handoff)
                return
        raise AssertionError(f"request not found: {request_id}")

    _mutate_handoff_report(bus_root, mutate_report)


def _remove_ready_handoffs(bus_root):
    def mutate(handoff_report):
        handoff_report["handoffs"] = [
            handoff
            for handoff in handoff_report["handoffs"]
            if handoff.get("gate", {}).get("handoff_ready") is not True
        ]
        handoff_report["summary"] = {
            "total": 3,
            "handoff_ready": 0,
            "blocked": 2,
            "unsupported": 1,
            "result_status": "not_executed",
        }

    _mutate_handoff_report(bus_root, mutate)


def _make_handoff_ready(handoff):
    handoff["gate"]["handoff_ready"] = True
    handoff["gate"]["blocked_reason"] = None
    handoff["gate"]["unsupported_reason"] = None
    handoff["gate"]["execution_allowed_by_preflight"] = True


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _file_snapshot(root):
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


def _contains_absolute_path(value):
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    if isinstance(value, str):
        return value.startswith("/")
    return False


if __name__ == "__main__":
    unittest.main()
