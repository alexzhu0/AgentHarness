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
from agentharness.handoff_manifest import (
    build_handoff_export_manifest,
    verify_handoff_export_manifest,
)
from agentharness.yamlio import load_yaml


REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
DIRECT_HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
HANDOFF_REPORT_PATH = Path("handoffs") / "T008-handoff-report.yaml"
REGISTRY_PATH = Path("adapters") / "registry.yaml"
ZERO_DIGEST = "sha256:" + "0" * 64


class HandoffManifestVerificationTests(unittest.TestCase):
    def test_current_manifest_verifies_successfully(self):
        report = _verify_manifest_value(_current_manifest())

        self.assertIs(True, report["ok"])
        self.assertEqual("handoff_manifest_verification_report", report["kind"])
        self.assertEqual("verify_handoff_export_manifest", report["source"])
        self.assertEqual("not_executed", report["result_status"])
        self.assertEqual("handoff_export_package", report["package_kind"])
        self.assertEqual("handoff_export_manifest", report["manifest_kind"])
        self.assertEqual(report["expected_package_digest"], report["manifest_package_digest"])
        self.assertEqual(
            {
                "items": 2,
                "matched": 2,
                "mismatched": 0,
                "missing": 0,
                "extra": 0,
                "result_status": "not_executed",
            },
            report["summary"],
        )
        self.assertEqual(
            ["TR-read", "TR-approve-delete"],
            [item["request_id"] for item in report["items"]],
        )
        self.assertTrue(all(item["result_status"] == "not_executed" for item in report["items"]))
        self.assertEqual([], report["errors"])

    def test_verification_cli_outputs_deterministic_json(self):
        manifest = _current_manifest()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            _write_json(manifest_path, manifest)
            first_code, first_output, _ = _run_cli(
                ["handoff", "verify-manifest", str(REGISTRY_BUS_ROOT), str(manifest_path)]
            )
            second_code, second_output, _ = _run_cli(
                ["handoff", "verify-manifest", str(REGISTRY_BUS_ROOT), str(manifest_path)]
            )

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual(first_output, second_output)
        payload = json.loads(first_output)
        self.assertIs(True, payload["ok"])

    def test_repeated_verification_data_is_deterministic(self):
        manifest = _current_manifest()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            _write_json(manifest_path, manifest)
            first = verify_handoff_export_manifest(REGISTRY_BUS_ROOT, manifest_path)
            second = verify_handoff_export_manifest(REGISTRY_BUS_ROOT, manifest_path)

        self.assertEqual(first, second)

    def test_verification_output_contains_no_absolute_host_paths(self):
        manifest = _current_manifest()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            _write_json(manifest_path, manifest)
            code, output, _ = _run_cli(
                ["handoff", "verify-manifest", str(REGISTRY_BUS_ROOT), str(manifest_path)]
            )

        self.assertEqual(0, code)
        self.assertNotIn("/home/", output)
        self.assertFalse(_contains_absolute_path(json.loads(output)))

    def test_structural_non_digest_edit_fails(self):
        manifest = _current_manifest()
        manifest["summary"]["blocked"] = 99

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertTrue(any("canonical object differs" in error for error in report["errors"]))

    def test_malformed_json_manifest_fails(self):
        report = _verify_raw_manifest("{bad")

        self.assertIs(False, report["ok"])
        self.assertTrue(any("malformed JSON" in error for error in report["errors"]))

    def test_invalid_utf8_manifest_cli_returns_json_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "bad-manifest.json"
            manifest_path.write_bytes(b"\xff")
            code, output, stderr = _run_cli(
                [
                    "handoff",
                    "verify-manifest",
                    str(REGISTRY_BUS_ROOT),
                    str(manifest_path),
                ]
            )

        self.assertEqual(1, code)
        payload = json.loads(output)
        self.assertEqual("", stderr)
        self.assertEqual("handoff_manifest_verification_report", payload["kind"])
        self.assertEqual("verify_handoff_export_manifest", payload["source"])
        self.assertEqual("not_executed", payload["result_status"])
        self.assertIs(False, payload["ok"])
        self.assertTrue(payload["errors"])
        self.assertTrue(any("malformed UTF-8" in error for error in payload["errors"]))

    def test_json_manifest_must_be_mapping(self):
        for value in ([], "manifest", None):
            with self.subTest(value=value):
                report = _verify_raw_manifest(json.dumps(value))

                self.assertIs(False, report["ok"])
                self.assertTrue(any("must be a JSON object" in error for error in report["errors"]))

    def test_wrong_top_level_fields_fail(self):
        cases = {
            "kind": "wrong_kind",
            "source": "wrong_source",
            "package_kind": "wrong_package",
            "result_status": "executed",
        }
        for field_name, bad_value in cases.items():
            with self.subTest(field_name=field_name):
                manifest = _current_manifest()
                manifest[field_name] = bad_value

                report = _verify_manifest_value(manifest)

                self.assertIs(False, report["ok"])
                self.assertTrue(any(field_name in error for error in report["errors"]))

    def test_forged_package_digest_fails(self):
        manifest = _current_manifest()
        manifest["package_digest"] = ZERO_DIGEST

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertTrue(any("package_digest" in error for error in report["errors"]))

    def test_forged_export_item_digest_fails(self):
        manifest = _current_manifest()
        manifest["items"][0]["export_item_digest"] = ZERO_DIGEST

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertTrue(any("export_item_digest" in error for error in report["errors"]))

    def test_forged_handoff_digest_fails(self):
        manifest = _current_manifest()
        manifest["items"][0]["handoff_digest"] = ZERO_DIGEST

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertTrue(any("handoff_digest" in error for error in report["errors"]))

    def test_missing_item_fails(self):
        manifest = _current_manifest()
        manifest["items"].pop()

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertEqual(1, report["summary"]["missing"])
        self.assertTrue(any("missing manifest item" in error for error in report["errors"]))

    def test_extra_item_fails(self):
        manifest = _current_manifest()
        extra = dict(manifest["items"][0])
        extra["request_id"] = "TR-extra"
        manifest["items"].append(extra)

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertEqual(1, report["summary"]["extra"])
        self.assertTrue(any("unexpected manifest item" in error for error in report["errors"]))

    def test_reordered_items_fail(self):
        manifest = _current_manifest()
        manifest["items"] = list(reversed(manifest["items"]))

        report = _verify_manifest_value(manifest)

        self.assertIs(False, report["ok"])
        self.assertEqual(2, report["summary"]["mismatched"])
        self.assertTrue(any("request_id" in error for error in report["errors"]))

    def test_stale_manifest_after_handoff_mutation_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
            shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
            manifest, manifest_report = build_handoff_export_manifest(bus_root)
            self.assertEqual([], manifest_report.errors)
            manifest_path = Path(tmpdir) / "manifest.json"
            _write_json(manifest_path, manifest)
            _mutate_handoff_report(
                bus_root,
                lambda handoff_report: handoff_report["handoffs"][0].__setitem__(
                    "handoff_id", "HOFF-TR-read-stale"
                ),
            )

            report = verify_handoff_export_manifest(bus_root, manifest_path)

        self.assertIs(False, report["ok"])
        self.assertTrue(report["errors"])

    def test_stale_manifest_after_registry_mutation_fails_through_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
            shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
            manifest_path = Path(tmpdir) / "manifest.json"
            _write_json(manifest_path, _current_manifest())
            _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )

            report = verify_handoff_export_manifest(bus_root, manifest_path)

        self.assertIs(False, report["ok"])
        self.assertTrue(any("expected_manifest" in error for error in report["errors"]))

    def test_direct_handoff_fixture_fails_through_export_validation(self):
        report = _verify_manifest_value(_current_manifest(), bus_root=DIRECT_HANDOFF_BUS_ROOT)

        self.assertIs(False, report["ok"])
        self.assertTrue(any("registry-backed" in error for error in report["errors"]))

    def test_verification_cli_failure_is_json(self):
        manifest = _current_manifest()
        manifest["package_digest"] = ZERO_DIGEST
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            _write_json(manifest_path, manifest)
            code, output, _ = _run_cli(
                ["handoff", "verify-manifest", str(REGISTRY_BUS_ROOT), str(manifest_path)]
            )

        self.assertEqual(1, code)
        payload = json.loads(output)
        self.assertIs(False, payload["ok"])

    def test_verify_manifest_cli_rejects_forbidden_flags(self):
        rejected_flags = [
            ["--out", "report.json"],
            ["--sign"],
            ["--timestamp"],
            ["--run"],
            ["--execute"],
            ["--dispatch"],
            ["--submit"],
            ["--mutation"],
            ["--mutate"],
            ["--verify"],
        ]

        for flag_args in rejected_flags:
            with self.subTest(flag_args=flag_args):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(
                            [
                                "handoff",
                                "verify-manifest",
                                str(REGISTRY_BUS_ROOT),
                                "manifest.json",
                                *flag_args,
                            ]
                        )
                self.assertEqual(2, raised.exception.code)
                self.assertIn("unrecognized arguments", stderr.getvalue())


def _current_manifest():
    manifest, report = build_handoff_export_manifest(REGISTRY_BUS_ROOT)
    if report.errors:
        raise AssertionError(report.errors)
    return json.loads(json.dumps(manifest))


def _verify_manifest_value(value, bus_root=REGISTRY_BUS_ROOT):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        _write_json(path, value)
        return verify_handoff_export_manifest(bus_root, path)


def _verify_raw_manifest(raw):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(raw, encoding="utf-8")
        return verify_handoff_export_manifest(REGISTRY_BUS_ROOT, path)


def _run_cli(argv):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


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


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


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
