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
from agentharness.yamlio import load_yaml


REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
DIRECT_HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
HANDOFF_REPORT_PATH = Path("handoffs") / "T008-handoff-report.yaml"
REGISTRY_PATH = Path("adapters") / "registry.yaml"
ZERO_DIGEST = "sha256:" + "0" * 64


class HandoffExporterTests(unittest.TestCase):
    def test_registry_backed_fixture_exports_ready_items(self):
        package, report = build_handoff_export_package(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        self.assertIsNotNone(package)
        self.assertEqual("handoff_export_package", package["kind"])
        self.assertEqual("build_handoff_export_package", package["source"])
        self.assertEqual("not_executed", package["result_status"])
        self.assertEqual(
            {
                "reports": 1,
                "total_handoffs": 5,
                "exported": 2,
                "blocked": 2,
                "unsupported": 1,
                "result_status": "not_executed",
            },
            package["summary"],
        )
        self.assertEqual(
            ["TR-read", "TR-approve-delete"],
            [item["request_id"] for item in package["exports"]],
        )

    def test_export_excludes_blocked_and_unsupported_request_ids(self):
        package, report = build_handoff_export_package(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        exported = {item["request_id"] for item in package["exports"]}
        self.assertNotIn("TR-read-unsupported-intent", exported)
        self.assertNotIn("TR-missing-approval-delete", exported)
        self.assertNotIn("TR-deny-unknown", exported)

    def test_export_items_are_ready_registry_bound_and_not_executed(self):
        package, report = build_handoff_export_package(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)
        for item in package["exports"]:
            with self.subTest(request_id=item["request_id"]):
                self.assertEqual("handoff_export_item", item["kind"])
                self.assertEqual("not_executed", item["result_status"])
                self.assertEqual("not_executed", item["gate"]["result_status"])
                self.assertIs(True, item["gate"]["handoff_ready"])
                self.assertIs(True, item["gate"]["execution_allowed_by_preflight"])
                self.assertEqual("adapters/registry.yaml", item["adapter_registry_path"])
                self.assertEqual("adapters/pi-tool-call-v0.yaml", item["adapter_spec_path"])
                self.assertIn("adapter_spec_digest", item["adapter_ref"])
                self.assertEqual(
                    "sha256:ca33d2420c97e891b5d8a710334a8757c9f70413aa94d298d68aa913aabcc244",
                    item["adapter_ref"]["adapter_spec_digest"],
                )

    def test_optional_adapter_ref_digest_is_repopulated_from_registry_entry(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report["adapter_ref"].pop(
                    "adapter_spec_digest"
                ),
            )
        )

        self.assertEqual([], report.errors)
        self.assertEqual(2, len(package["exports"]))
        self.assertTrue(
            all("adapter_spec_digest" in item["adapter_ref"] for item in package["exports"])
        )

    def test_handoff_digest_matches_canonical_handoff_digest(self):
        package, report = build_handoff_export_package(REGISTRY_BUS_ROOT)
        handoff_report = load_yaml(REGISTRY_BUS_ROOT / HANDOFF_REPORT_PATH)
        handoffs = {handoff["request_id"]: handoff for handoff in handoff_report["handoffs"]}

        self.assertEqual([], report.errors)
        for item in package["exports"]:
            self.assertEqual(
                execution_handoff_digest(handoffs[item["request_id"]]),
                item["handoff_digest"],
            )

    def test_repeated_export_data_is_deterministic(self):
        first, first_report = build_handoff_export_package(REGISTRY_BUS_ROOT)
        second, second_report = build_handoff_export_package(REGISTRY_BUS_ROOT)

        self.assertEqual([], first_report.errors)
        self.assertEqual([], second_report.errors)
        self.assertEqual(first, second)

    def test_export_cli_outputs_deterministic_json(self):
        first_code, first_output = _run_cli(["handoff", "export", str(REGISTRY_BUS_ROOT)])
        second_code, second_output = _run_cli(["handoff", "export", str(REGISTRY_BUS_ROOT)])

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual(first_output, second_output)
        payload = json.loads(first_output)
        self.assertEqual("handoff_export_package", payload["kind"])
        self.assertEqual(2, len(payload["exports"]))

    def test_export_contains_no_absolute_host_paths(self):
        code, output = _run_cli(["handoff", "export", str(REGISTRY_BUS_ROOT)])

        self.assertEqual(0, code)
        payload = json.loads(output)
        self.assertNotIn("/home/", output)
        self.assertFalse(_contains_absolute_path(payload))

    def test_missing_bus_failure_contains_no_absolute_host_paths(self):
        host_paths = (
            "/home/reviewer/private/missing-bus",
            "/tmp/reviewer/private/missing-bus",
            "/Users/reviewer/private/missing-bus",
            r"C:\Users\reviewer\private\missing-bus",
            r"\\server\share\reviewer\missing-bus",
        )
        for missing_bus in host_paths:
            with self.subTest(missing_bus=missing_bus):
                code, output = _run_cli(["handoff", "export", missing_bus])

                self.assertEqual(1, code)
                self.assertIn("FAIL handoff export:", output)
                self.assertNotIn(missing_bus, output)
                for marker in ("/home/", "/tmp/", "/Users/", "C:\\", r"\\server"):
                    self.assertNotIn(marker, output)

        code, output = _run_cli(["handoff", "export", "fixtures/missing-bus"])

        self.assertEqual(1, code)
        self.assertIn("FAIL handoff export: fixtures/missing-bus", output)

    def test_direct_handoff_fixture_without_registry_binding_fails_export(self):
        package, report = build_handoff_export_package(DIRECT_HANDOFF_BUS_ROOT)

        self.assertIsNone(package)
        self.assertTrue(any("registry-backed" in error for error in report.errors))

    def test_export_cli_direct_handoff_fixture_fails_with_clear_error(self):
        code, output = _run_cli(["handoff", "export", str(DIRECT_HANDOFF_BUS_ROOT)])

        self.assertEqual(1, code)
        self.assertIn("FAIL handoff export:", output)
        self.assertIn("registry-backed handoff report is required", output)

    def test_missing_adapter_registry_path_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.pop("adapter_registry_path"),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("adapter_registry_path" in error for error in report.errors))

    def test_missing_adapter_ref_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.pop("adapter_ref"),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("adapter_ref" in error for error in report.errors))

    def test_registry_path_traversal_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.__setitem__(
                    "adapter_registry_path", "../registry.yaml"
                ),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("adapter_registry_path" in error for error in report.errors))

    def test_disabled_selected_adapter_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__("status", "disabled"),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("selected adapter must be active" in error for error in report.errors))

    def test_deprecated_selected_adapter_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__(
                    "status", "deprecated"
                ),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("selected adapter must be active" in error for error in report.errors))

    def test_forged_registry_digest_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("adapter_spec_digest" in error for error in report.errors))

    def test_adapter_ref_digest_mismatch_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report["adapter_ref"].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("adapter_ref.adapter_spec_digest" in error for error in report.errors))

    def test_handoff_adapter_spec_path_mismatch_fails_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report.__setitem__(
                    "adapter_spec_path", "adapters/other.yaml"
                ),
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("adapter_spec_path" in error for error in report.errors))

    def test_no_ready_handoffs_fails_export(self):
        package, report = _run_mutated_export(_remove_ready_handoffs)

        self.assertIsNone(package)
        self.assertIn("exports: no handoff_ready registry-backed handoffs to export", report.errors)

    def test_blocked_handoff_marked_ready_fails_before_export(self):
        package, report = _run_mutated_export(
            lambda bus_root: _mutate_handoff(
                bus_root,
                "TR-deny-unknown",
                _make_handoff_ready,
            )
        )

        self.assertIsNone(package)
        self.assertTrue(any("gate" in error for error in report.errors))

    def test_export_cli_has_no_out_flag(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["handoff", "export", str(REGISTRY_BUS_ROOT), "--out", "pkg.json"])

        self.assertEqual(2, raised.exception.code)
        self.assertIn("unrecognized arguments", stderr.getvalue())


def _run_mutated_export(mutate):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
        shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
        mutate(bus_root)
        return build_handoff_export_package(bus_root)


def _run_cli(argv):
    stream = StringIO()
    with redirect_stdout(stream):
        code = main(argv)
    return code, stream.getvalue()


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


def _contains_absolute_path(value):
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    if isinstance(value, str):
        return value.startswith("/")
    return False


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
