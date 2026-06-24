from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.cli import main
from agentharness.execution_handoff import execution_handoff_digest
from agentharness.handoff_exporter import build_handoff_export_package
from agentharness.handoff_manifest import build_handoff_export_manifest
from agentharness.yamlio import load_yaml


REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
DIRECT_HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
HANDOFF_REPORT_PATH = Path("handoffs") / "T008-handoff-report.yaml"
REGISTRY_PATH = Path("adapters") / "registry.yaml"
ZERO_DIGEST = "sha256:" + "0" * 64
EXCLUDED_REQUEST_IDS = {
    "TR-read-unsupported-intent",
    "TR-missing-approval-delete",
    "TR-deny-unknown",
}


class HandoffManifestTests(unittest.TestCase):
    def test_manifest_shape_and_ready_items(self):
        manifest, report = build_handoff_export_manifest(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        self.assertIsNotNone(manifest)
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual("handoff_export_manifest", manifest["kind"])
        self.assertEqual("build_handoff_export_manifest", manifest["source"])
        self.assertEqual("not_executed", manifest["result_status"])
        self.assertEqual("handoff_export_package", manifest["package_kind"])
        self.assertEqual(
            {
                "reports": 1,
                "total_handoffs": 5,
                "exported": 2,
                "blocked": 2,
                "unsupported": 1,
                "result_status": "not_executed",
            },
            manifest["summary"],
        )
        self.assertEqual(
            ["TR-read", "TR-approve-delete"],
            [item["request_id"] for item in manifest["items"]],
        )
        self.assertTrue(all(item["result_status"] == "not_executed" for item in manifest["items"]))

    def test_manifest_excludes_blocked_and_unsupported_request_ids(self):
        manifest, report = build_handoff_export_manifest(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        request_ids = {item["request_id"] for item in manifest["items"]}
        self.assertTrue(EXCLUDED_REQUEST_IDS.isdisjoint(request_ids))

    def test_manifest_preserves_export_order_and_digests(self):
        package, package_report = build_handoff_export_package(REGISTRY_BUS_ROOT)
        manifest, manifest_report = build_handoff_export_manifest(REGISTRY_BUS_ROOT)

        self.assertEqual([], package_report.errors)
        self.assertEqual([], manifest_report.errors)
        self.assertEqual(execution_handoff_digest(package), manifest["package_digest"])
        self.assertEqual(
            [item["request_id"] for item in package["exports"]],
            [item["request_id"] for item in manifest["items"]],
        )

        exports_by_request = {item["request_id"]: item for item in package["exports"]}
        for item in manifest["items"]:
            export_item = exports_by_request[item["request_id"]]
            with self.subTest(request_id=item["request_id"]):
                self.assertEqual(
                    execution_handoff_digest(export_item), item["export_item_digest"]
                )
                self.assertEqual(export_item["handoff_digest"], item["handoff_digest"])
                self.assertEqual(export_item["adapter_ref"], item["adapter_ref"])

    def test_manifest_cli_outputs_deterministic_json(self):
        first_code, first_output, _ = _run_cli(
            ["handoff", "manifest", str(REGISTRY_BUS_ROOT)]
        )
        second_code, second_output, _ = _run_cli(
            ["handoff", "manifest", str(REGISTRY_BUS_ROOT)]
        )

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual(first_output, second_output)
        payload = json.loads(first_output)
        self.assertEqual("handoff_export_manifest", payload["kind"])
        self.assertEqual(2, len(payload["items"]))

    def test_repeated_manifest_data_is_deterministic(self):
        first, first_report = build_handoff_export_manifest(REGISTRY_BUS_ROOT)
        second, second_report = build_handoff_export_manifest(REGISTRY_BUS_ROOT)

        self.assertEqual([], first_report.errors)
        self.assertEqual([], second_report.errors)
        self.assertEqual(first, second)

    def test_manifest_contains_no_absolute_host_paths(self):
        code, output, _ = _run_cli(["handoff", "manifest", str(REGISTRY_BUS_ROOT)])

        self.assertEqual(0, code)
        payload = json.loads(output)
        self.assertNotIn("/home/", output)
        self.assertFalse(_contains_absolute_path(payload))

    def test_direct_handoff_fixture_without_registry_binding_fails_manifest(self):
        manifest, report = build_handoff_export_manifest(DIRECT_HANDOFF_BUS_ROOT)

        self.assertIsNone(manifest)
        self.assertTrue(any("registry-backed" in error for error in report.errors))

    def test_manifest_cli_direct_handoff_fixture_fails_with_clear_error(self):
        code, output, _ = _run_cli(["handoff", "manifest", str(DIRECT_HANDOFF_BUS_ROOT)])

        self.assertEqual(1, code)
        self.assertIn("FAIL handoff manifest:", output)
        self.assertIn("registry-backed handoff report is required", output)

    def test_missing_registry_binding_fails_through_export_validation(self):
        manifest, report = _run_mutated_manifest(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.pop("adapter_registry_path"),
            )
        )

        self.assertIsNone(manifest)
        self.assertTrue(any("adapter_registry_path" in error for error in report.errors))

    def test_disabled_or_deprecated_selected_adapter_fails_manifest(self):
        for status in ("disabled", "deprecated"):
            with self.subTest(status=status):
                manifest, report = _run_mutated_manifest(
                    lambda bus_root: _mutate_registry(
                        bus_root,
                        lambda registry: registry["entries"][0].__setitem__("status", status),
                    )
                )

                self.assertIsNone(manifest)
                self.assertTrue(
                    any("selected adapter must be active" in error for error in report.errors)
                )

    def test_forged_registry_digest_fails_manifest(self):
        manifest, report = _run_mutated_manifest(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
        )

        self.assertIsNone(manifest)
        self.assertTrue(any("adapter_spec_digest" in error for error in report.errors))

    def test_handoff_adapter_spec_path_mismatch_fails_manifest(self):
        manifest, report = _run_mutated_manifest(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.__setitem__(
                    "adapter_spec_path", "adapters/other.yaml"
                ),
            )
        )

        self.assertIsNone(manifest)
        self.assertTrue(any("adapter_spec_path" in error for error in report.errors))

    def test_no_ready_handoffs_fails_manifest(self):
        manifest, report = _run_mutated_manifest(_remove_ready_handoffs)

        self.assertIsNone(manifest)
        self.assertIn("exports: no handoff_ready registry-backed handoffs to export", report.errors)

    def test_manifest_cli_has_no_file_trust_or_action_flags(self):
        rejected_flags = [
            ["--out", "manifest.json"],
            ["--sign"],
            ["--verify"],
            ["--timestamp"],
            ["--run"],
            ["--execute"],
            ["--dispatch"],
            ["--submit"],
            ["--mutation"],
            ["--mutate"],
        ]

        for flag_args in rejected_flags:
            with self.subTest(flag_args=flag_args):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(["handoff", "manifest", str(REGISTRY_BUS_ROOT), *flag_args])
                self.assertEqual(2, raised.exception.code)
                self.assertIn("unrecognized arguments", stderr.getvalue())


def _run_mutated_manifest(mutate):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
        shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
        mutate(bus_root)
        return build_handoff_export_manifest(bus_root)


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


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _run_cli(argv):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


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
