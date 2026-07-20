from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.adapter_registry import validate_adapter_registry_binding
from agentharness.audit_contract import NOT_EXECUTED
from agentharness.enterprise_audit_checklist import (
    build_enterprise_audit_checklist,
    validate_enterprise_audit_checklist_payload,
)
from agentharness.enterprise_audit_report import (
    build_enterprise_audit_report,
    validate_enterprise_audit_report_payload,
    verify_enterprise_audit_report,
)
from agentharness.handoff_exporter import build_handoff_export_package
from agentharness.handoff_inspector import inspect_handoff_bus
from agentharness.handoff_manifest import (
    build_handoff_export_manifest,
    verify_handoff_export_manifest,
)
from agentharness.loop_bus import validate_bus
from agentharness.validate import ValidationReport
from agentharness.yamlio import load_yaml


REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
DIRECT_HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
HANDOFF_REPORT_PATH = Path("handoffs") / "T008-handoff-report.yaml"
REGISTRY_PATH = Path("adapters") / "registry.yaml"
ZERO_DIGEST = "sha256:" + "0" * 64

EXPECTED_STAGE_ORDER = [
    "loop_bus_validation",
    "handoff_inspection",
    "adapter_registry_binding_validation",
    "handoff_export_package",
    "digest_manifest_build",
    "manifest_verification_readback",
    "enterprise_audit_report_build",
    "enterprise_audit_report_schema_validation",
    "enterprise_audit_report_readback_verification",
    "enterprise_audit_checklist_build",
    "enterprise_audit_checklist_schema_validation",
]
EXPECTED_EXPORTED_REQUEST_IDS = ["TR-read", "TR-approve-delete"]
EXPECTED_EXCLUDED_REQUEST_IDS = {
    "TR-read-unsupported-intent",
    "TR-missing-approval-delete",
    "TR-deny-unknown",
}


class EndToEndEvidenceChainTests(unittest.TestCase):
    def test_golden_chain_stage_order_counts_status_and_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = _build_chain(REGISTRY_BUS_ROOT, Path(first_tmp))
            second = _build_chain(REGISTRY_BUS_ROOT, Path(second_tmp))

        self.assertEqual(EXPECTED_STAGE_ORDER, first["stage_order"])
        self.assertEqual(EXPECTED_STAGE_ORDER, second["stage_order"])
        self.assertEqual(first["digests"], second["digests"])

        inspection = _expect_mapping(first["inspection"])
        package = _expect_mapping(first["package"])
        manifest = _expect_mapping(first["manifest"])
        manifest_readback = _expect_mapping(first["manifest_readback"])
        audit_report = _expect_mapping(first["audit_report"])
        audit_readback = _expect_mapping(first["audit_readback"])
        checklist = _expect_mapping(first["checklist"])

        _assert_handoff_summary_counts(self, _expect_mapping(inspection["summary"]))
        _assert_export_summary_counts(self, _expect_mapping(package["summary"]))
        _assert_export_summary_counts(self, _expect_mapping(manifest["summary"]))
        _assert_audit_summary_counts(self, _expect_mapping(audit_report["summary"]))
        _assert_checklist_summary_counts(self, _expect_mapping(checklist["summary"]))

        self.assertEqual(
            EXPECTED_EXPORTED_REQUEST_IDS,
            [item["request_id"] for item in _expect_list(package["exports"])],
        )
        self.assertEqual(
            EXPECTED_EXPORTED_REQUEST_IDS,
            [item["request_id"] for item in _expect_list(manifest["items"])],
        )
        handoff_rows = _expect_list(audit_report["handoffs"])
        self.assertEqual(
            EXPECTED_EXPORTED_REQUEST_IDS,
            [row["request_id"] for row in handoff_rows if row.get("exported") is True],
        )
        self.assertEqual(
            EXPECTED_EXCLUDED_REQUEST_IDS,
            {row["request_id"] for row in handoff_rows if row.get("exported") is False},
        )

        for payload in (
            inspection,
            package,
            manifest,
            manifest_readback,
            audit_report,
            audit_readback,
            checklist,
        ):
            self.assertEqual([], _bad_result_status_paths(payload))

    def test_legacy_direct_handoff_fixture_fails_readiness_export(self) -> None:
        inspection, inspection_report = inspect_handoff_bus(DIRECT_HANDOFF_BUS_ROOT)
        self.assertTrue(inspection_report.ok, inspection_report.errors)
        self.assertIsNotNone(inspection)

        package, report = build_handoff_export_package(DIRECT_HANDOFF_BUS_ROOT)

        self.assertIsNone(package)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("registry-backed handoff report is required" in error for error in report.errors),
            report.errors,
        )
        self.assert_no_raw_host_path(report)

    def test_forged_adapter_digest_fails_binding_and_export(self) -> None:
        with _temporary_fixture_copy(REGISTRY_BUS_ROOT) as bus_root:
            registry = _load_mapping(bus_root / REGISTRY_PATH)
            entries = _expect_list(registry["entries"])
            first_entry = _expect_dict(entries[0])
            first_entry["adapter_spec_digest"] = ZERO_DIGEST
            _write_yaml(bus_root / REGISTRY_PATH, registry)

            handoff_report = _load_mapping(bus_root / HANDOFF_REPORT_PATH)
            adapter_spec = _load_mapping(bus_root / _expect_str(handoff_report["adapter_spec_path"]))
            binding_report = validate_adapter_registry_binding(
                handoff_report,
                adapter_spec,
                bus_root,
            )
            package, export_report = build_handoff_export_package(bus_root)

        self.assertFalse(binding_report.ok)
        self.assertTrue(
            any("adapter_spec_digest" in error for error in binding_report.errors),
            binding_report.errors,
        )
        self.assertIsNone(package)
        self.assertFalse(export_report.ok)
        self.assert_no_raw_host_path(binding_report)
        self.assert_no_raw_host_path(export_report)

    def test_no_ready_handoffs_fails_safely(self) -> None:
        with _temporary_fixture_copy(REGISTRY_BUS_ROOT) as bus_root:
            handoff_report = _load_mapping(bus_root / HANDOFF_REPORT_PATH)
            remaining_handoffs = [
                item
                for item in _expect_list(handoff_report["handoffs"])
                if not _expect_mapping(item).get("gate", {}).get("handoff_ready")
            ]
            handoff_report["handoffs"] = remaining_handoffs
            summary = _expect_dict(handoff_report["summary"])
            summary["total"] = len(remaining_handoffs)
            summary["handoff_ready"] = 0
            summary["blocked"] = 2
            summary["unsupported"] = 1
            _write_yaml(bus_root / HANDOFF_REPORT_PATH, handoff_report)

            package, report = build_handoff_export_package(bus_root)
            checklist = build_enterprise_audit_checklist(bus_root)

        self.assertIsNone(package)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("no handoff_ready registry-backed handoffs to export" in error for error in report.errors),
            report.errors,
        )
        self.assertFalse(checklist["ok"])
        self.assertEqual(NOT_EXECUTED, checklist["result_status"])
        self.assertTrue(
            all(check["result_status"] == NOT_EXECUTED for check in checklist["checks"])
        )
        self.assert_no_raw_host_path(report)

    def test_audit_report_and_checklist_schema_drift_is_rejected(self) -> None:
        audit_report, audit_build_report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], audit_build_report.errors)
        assert audit_report is not None
        checklist = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)

        report_schema_drift = copy.deepcopy(audit_report)
        report_schema_drift["manifest_verification"]["evidence_envelope"] = {}
        checklist_schema_drift = copy.deepcopy(checklist)
        checklist_schema_drift["checks"][5].pop("command")

        self.assertFalse(
            validate_enterprise_audit_report_payload(report_schema_drift).ok
        )
        self.assertFalse(
            validate_enterprise_audit_checklist_payload(checklist_schema_drift).ok
        )

    def test_result_status_drift_is_rejected(self) -> None:
        audit_report, audit_build_report = build_enterprise_audit_report(REGISTRY_BUS_ROOT)
        self.assertEqual([], audit_build_report.errors)
        assert audit_report is not None
        checklist = build_enterprise_audit_checklist(REGISTRY_BUS_ROOT)

        top_level_report_drift = copy.deepcopy(audit_report)
        top_level_report_drift["result_status"] = "done"
        nested_report_drift = copy.deepcopy(audit_report)
        nested_report_drift["handoffs"][0]["result_status"] = "done"
        top_level_checklist_drift = copy.deepcopy(checklist)
        top_level_checklist_drift["result_status"] = "done"
        nested_checklist_drift = copy.deepcopy(checklist)
        nested_checklist_drift["checks"][0]["result_status"] = "done"

        self.assertFalse(validate_enterprise_audit_report_payload(top_level_report_drift).ok)
        self.assertFalse(validate_enterprise_audit_report_payload(nested_report_drift).ok)
        self.assertFalse(
            validate_enterprise_audit_checklist_payload(top_level_checklist_drift).ok
        )
        self.assertFalse(
            validate_enterprise_audit_checklist_payload(nested_checklist_drift).ok
        )

    def test_failure_messages_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_bus = Path(temp_dir) / "missing-bus"
            checklist = build_enterprise_audit_checklist(missing_bus)
            rendered = json.dumps(checklist, sort_keys=True)

        self.assertFalse(checklist["ok"])
        self.assertEqual(NOT_EXECUTED, checklist["result_status"])
        self.assertIn("<path>", rendered)
        self.assertNotIn(str(missing_bus), rendered)
        self.assertNotIn(temp_dir, rendered)
        self.assertNotIn("missing-bus", rendered)
        self.assertEqual([], _bad_result_status_paths(checklist))

    def assert_no_raw_host_path(self, report: ValidationReport) -> None:
        rendered = json.dumps(
            {"errors": report.errors, "warnings": report.warnings},
            sort_keys=True,
        )
        self.assertNotIn(str(ROOT), rendered)
        self.assertNotIn("/tmp/", rendered)
        self.assertNotIn("/home/", rendered)


def _build_chain(bus_root: Path, temp_dir: Path) -> dict[str, Any]:
    stages: list[str] = []

    bus_report = validate_bus(bus_root)
    _require_ok(bus_report, "loop bus")
    stages.append("loop_bus_validation")

    inspection, inspection_report = inspect_handoff_bus(bus_root)
    _require_ok(inspection_report, "handoff inspection")
    assert inspection is not None
    stages.append("handoff_inspection")

    handoff_report = _load_mapping(bus_root / HANDOFF_REPORT_PATH)
    adapter_spec = _load_mapping(bus_root / _expect_str(handoff_report["adapter_spec_path"]))
    binding_report = validate_adapter_registry_binding(handoff_report, adapter_spec, bus_root)
    _require_ok(binding_report, "adapter registry binding")
    stages.append("adapter_registry_binding_validation")

    package, export_report = build_handoff_export_package(bus_root)
    _require_ok(export_report, "handoff export package")
    assert package is not None
    stages.append("handoff_export_package")

    manifest, manifest_report = build_handoff_export_manifest(bus_root)
    _require_ok(manifest_report, "digest manifest build")
    assert manifest is not None
    stages.append("digest_manifest_build")

    manifest_path = temp_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    manifest_readback = verify_handoff_export_manifest(bus_root, manifest_path)
    assert manifest_readback["ok"] is True, manifest_readback["errors"]
    stages.append("manifest_verification_readback")

    audit_report, audit_build_report = build_enterprise_audit_report(bus_root)
    _require_ok(audit_build_report, "enterprise audit report build")
    assert audit_report is not None
    stages.append("enterprise_audit_report_build")

    audit_schema_report = validate_enterprise_audit_report_payload(audit_report)
    _require_ok(audit_schema_report, "enterprise audit report schema validation")
    stages.append("enterprise_audit_report_schema_validation")

    audit_report_path = temp_dir / "audit-report.json"
    _write_json(audit_report_path, audit_report)
    audit_readback = verify_enterprise_audit_report(bus_root, audit_report_path)
    assert audit_readback["ok"] is True, audit_readback["errors"]
    stages.append("enterprise_audit_report_readback_verification")

    checklist = build_enterprise_audit_checklist(bus_root)
    assert checklist["ok"] is True, checklist["errors"]
    stages.append("enterprise_audit_checklist_build")

    checklist_schema_report = validate_enterprise_audit_checklist_payload(checklist)
    _require_ok(checklist_schema_report, "enterprise audit checklist schema validation")
    stages.append("enterprise_audit_checklist_schema_validation")

    payloads = {
        "inspection": inspection,
        "package": package,
        "manifest": manifest,
        "manifest_readback": manifest_readback,
        "audit_report": audit_report,
        "audit_readback": audit_readback,
        "checklist": checklist,
    }
    return {
        "stage_order": stages,
        **payloads,
        "digests": {
            name: _canonical_digest(payload) for name, payload in payloads.items()
        },
    }


def _require_ok(report: ValidationReport, label: str) -> None:
    assert report.ok, f"{label}: errors={report.errors} warnings={report.warnings}"


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_mapping(path: Path) -> dict[str, Any]:
    value = load_yaml(path)
    assert isinstance(value, Mapping), path
    return dict(value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        encoding="utf-8",
    )


def _write_yaml(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _temporary_fixture_copy(source: Path):
    class _FixtureCopy:
        def __enter__(self) -> Path:
            self._temp = tempfile.TemporaryDirectory()
            self.root = Path(self._temp.name) / source.name
            shutil.copytree(source, self.root)
            return self.root

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            self._temp.cleanup()

    return _FixtureCopy()


def _bad_result_status_paths(value: Any, path: str = "$", has_root: bool = False) -> list[str]:
    bad: list[str] = []
    if isinstance(value, Mapping):
        next_has_root = has_root or "result_status" in value
        for key, item in value.items():
            child_path = f"{path}.{key}" if path != "$" else str(key)
            if key == "result_status" and item != NOT_EXECUTED:
                bad.append(child_path)
            bad.extend(_bad_result_status_paths(item, child_path, next_has_root))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            bad.extend(_bad_result_status_paths(item, f"{path}[{index}]", has_root))
    return bad


def _expect_mapping(value: Any) -> Mapping[str, Any]:
    assert isinstance(value, Mapping), value
    return value


def _expect_dict(value: Any) -> dict[str, Any]:
    assert isinstance(value, dict), value
    return value


def _expect_list(value: Any) -> list[Any]:
    assert isinstance(value, list), value
    return value


def _expect_str(value: Any) -> str:
    assert isinstance(value, str), value
    return value


def _assert_handoff_summary_counts(
    test: unittest.TestCase, summary: Mapping[str, Any]
) -> None:
    test.assertEqual(1, summary["reports"])
    test.assertEqual(5, summary["total"])
    test.assertEqual(2, summary["handoff_ready"])
    test.assertEqual(2, summary["blocked"])
    test.assertEqual(1, summary["unsupported"])
    test.assertEqual(NOT_EXECUTED, summary["result_status"])


def _assert_export_summary_counts(
    test: unittest.TestCase, summary: Mapping[str, Any]
) -> None:
    test.assertEqual(1, summary["reports"])
    test.assertEqual(5, summary["total_handoffs"])
    test.assertEqual(2, summary["exported"])
    test.assertEqual(2, summary["blocked"])
    test.assertEqual(1, summary["unsupported"])
    test.assertEqual(NOT_EXECUTED, summary["result_status"])


def _assert_audit_summary_counts(
    test: unittest.TestCase, summary: Mapping[str, Any]
) -> None:
    test.assertEqual(1, summary["reports"])
    test.assertEqual(5, summary["total_handoffs"])
    test.assertEqual(2, summary["handoff_ready"])
    test.assertEqual(2, summary["exported"])
    test.assertEqual(2, summary["blocked"])
    test.assertEqual(1, summary["unsupported"])
    test.assertEqual(NOT_EXECUTED, summary["result_status"])


def _assert_checklist_summary_counts(
    test: unittest.TestCase, summary: Mapping[str, Any]
) -> None:
    test.assertEqual(7, summary["checks"])
    test.assertEqual(5, summary["passed"])
    test.assertEqual(0, summary["failed"])
    test.assertEqual(0, summary["blocked"])
    test.assertEqual(2, summary["manual"])
    test.assertEqual(1, summary["reports"])
    test.assertEqual(5, summary["total_handoffs"])
    test.assertEqual(2, summary["handoff_ready"])
    test.assertEqual(2, summary["exported"])
    test.assertEqual(2, summary["blocked_handoffs"])
    test.assertEqual(1, summary["unsupported"])


if __name__ == "__main__":
    unittest.main()
